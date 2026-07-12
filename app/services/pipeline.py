from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from langchain_core.runnables import RunnableLambda, RunnableSequence

from app.models.enums import LifecycleStage
from app.models.schemas import Lead, ProcessedLead
from app.services.chains.email_gen import generate_email
from app.services.chains.followup import generate_followup
from app.services.chains.persona import generate_persona
from app.services.chains.response_classifier import classify_response
from app.services.chains.scoring import score_lead
from app.services.chains.strategy import generate_strategy
from app.services.reply_source import get_lead_reply

logger = logging.getLogger("crm_ai.pipeline")


def _mk_lead(row: pd.Series) -> Lead:
    return Lead(
        lead_id=row["lead_id"], name=row["name"], email=row["email"], company=row["company"],
        role=row["role"], industry=row["industry"], company_size=row["company_size"],
        website=row.get("website"),
    )


def _build_lead_pipeline(campaign) -> RunnableSequence:
    """Builds the LCEL sequence bound to this campaign's memory store, so every
    stage's logging lands in the right per-campaign LeadMemoryStore."""
    memory = campaign.memory

    def _score_and_log(lead: Lead):
        score = score_lead(lead)
        memory.log_ai_event(
            lead.lead_id, "SCORE",
            f"score={int(score.score)}/10 priority={score.priority} intent={score.buying_intent_level} "
            f"reasoning={score.reasoning}",
        )
        return lead, score

    def _persona_and_log(pair):
        lead, score = pair
        persona = generate_persona(lead, score)
        memory.log_ai_event(
            lead.lead_id, "PERSONA",
            f"{persona.persona_title} | pain_points={persona.pain_points} | goals={persona.goals}",
        )
        return lead, score, persona

    def _strategy_and_log(triple):
        lead, score, persona = triple
        strategy = generate_strategy(lead, persona)
        memory.log_ai_event(
            lead.lead_id, "STRATEGY",
            f"positioning={strategy.positioning_strategy} | value_prop={strategy.value_proposition}",
        )
        return lead, score, persona, strategy

    def _email_and_log(quad):
        lead, score, persona, strategy = quad
        draft = generate_email(lead, persona, strategy)
        memory.log_ai_event(lead.lead_id, "EMAIL_SENT", f"subject={draft.subject!r} body={draft.body}")
        return lead, score, persona, strategy, draft

    return (
        RunnableLambda(_score_and_log)
        | RunnableLambda(_persona_and_log)
        | RunnableLambda(_strategy_and_log)
        | RunnableLambda(_email_and_log)
    )


def process_lead(campaign, row: pd.Series) -> Optional[ProcessedLead]:
    """Runs one lead through the full pipeline: score -> persona -> strategy ->
    email -> send -> (reply -> classify -> follow-up). Any stage exception marks
    the lead LOST and returns None rather than aborting the whole campaign."""
    lead = _mk_lead(row)
    campaign.state.register(lead.lead_id)
    campaign.state.transition(lead.lead_id, LifecycleStage.VALIDATED)

    lead_pipeline = _build_lead_pipeline(campaign)

    try:
        lead_out, score, persona, strategy, draft = lead_pipeline.invoke(lead)
    except Exception as exc:  # noqa: BLE001
        logger.error("Pipeline failed for lead %s: %s", lead.lead_id, exc)
        campaign.state.transition(lead.lead_id, LifecycleStage.LOST)
        return None

    campaign.state.transition(lead.lead_id, LifecycleStage.SCORED)
    campaign.state.transition(lead.lead_id, LifecycleStage.ENRICHED)

    processed = ProcessedLead(lead=lead_out, score=score, persona=persona,
                               strategy=strategy, email_draft=draft)

    send_result = campaign.email_sender.send(lead_out, draft)
    processed.send_result = send_result
    if send_result.status in ("sent", "dry_run"):
        campaign.state.transition(lead.lead_id, LifecycleStage.CONTACTED)

    reply_text = get_lead_reply(lead_out, campaign.reply_mode)
    if reply_text:
        apply_reply(campaign, processed, reply_text)

    state = campaign.state.get(lead.lead_id)
    if state:
        processed.lifecycle_stage = state.stage.value
        processed.lifecycle_history = list(state.history)
    return processed


def apply_reply(campaign, processed: ProcessedLead, reply_text: str) -> None:
    """Shared by both the inline (simulated) reply path and the
    `/leads/{lead_id}/reply` webhook endpoint (real-inbox path)."""
    lead_id = processed.lead.lead_id
    processed.reply_text = reply_text
    try:
        response = classify_response(lead_id, reply_text, campaign.memory)
        processed.response = response
        campaign.state.transition(lead_id, LifecycleStage.REPLIED)

        if response.classification in ("interested", "meeting_requested", "need_more_info"):
            followup = generate_followup(lead_id, processed.email_draft.body, reply_text, campaign.memory)
            processed.follow_up = followup

        if response.classification == "meeting_requested":
            campaign.state.transition(lead_id, LifecycleStage.CONVERTED)
        elif response.classification in ("not_interested", "unsubscribe", "spam", "bounce"):
            campaign.state.transition(lead_id, LifecycleStage.LOST)
    except Exception as exc:  # noqa: BLE001
        logger.error("Response classification failed for %s: %s", lead_id, exc)

    state = campaign.state.get(lead_id)
    if state:
        processed.lifecycle_stage = state.stage.value
        processed.lifecycle_history = list(state.history)


def run_campaign(campaign, df: pd.DataFrame) -> None:
    """Synchronous batch runner -- called from a FastAPI BackgroundTask.
    Appends results directly onto `campaign.results` and updates
    `campaign.progress` as it goes, so GET /campaigns/{id} can report progress
    for a still-running campaign."""
    campaign.progress["total"] = len(df)
    campaign.progress["processed"] = 0

    for _, row in df.iterrows():
        result = process_lead(campaign, row)
        if result:
            campaign.results.append(result)
        campaign.progress["processed"] += 1

    logger.info("Campaign %s complete. %d/%d leads processed successfully.",
                campaign.campaign_id, len(campaign.results), len(df))




"""
Full pipeline orchestration -- LCEL Sequence composition per lead, driven by a
`Campaign` object (see `app/store/campaign_store.py`) that owns everything
scoped to a single run: its CRM state machine, its per-lead memory store, its
effective dry_run / reply_mode, and its accumulating results list.

This mirrors the notebook's (initial research/observation) `process_lead()` / `run_campaign()` almost line
for line; the only structural change is that state that used to live in
notebook globals (`crm_state`, `lead_memory`, `email_sender`) now lives on the
`Campaign` instance so multiple campaigns can run concurrently without
clobbering each other.
"""