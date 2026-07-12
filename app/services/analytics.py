from __future__ import annotations

import logging
import os
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")  # headless rendering -- required in a server process
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from app.models.schemas import CampaignStats, ProcessedLead

logger = logging.getLogger("crm_ai.analytics")
sns.set_theme(style="whitegrid")

OUTCOME_ORDER = [
    "Converted (meeting booked)",
    "Replied - awaiting outcome",
    "Contacted - no reply yet",
    "Lost / not interested",
    "Send failed",
]

OUTCOME_COLORS = {
    "Converted (meeting booked)": "#55A868",
    "Replied - awaiting outcome": "#4C72B0",
    "Contacted - no reply yet": "#CCB974",
    "Lost / not interested": "#C44E52",
    "Send failed": "#7F7F7F",
}


def _derive_outcome(row: pd.Series) -> str:
    stage = row.get("lifecycle_stage")
    if stage == "CONVERTED":
        return "Converted (meeting booked)"
    if stage == "LOST":
        return "Lost / not interested"
    if row.get("send_status") == "failed":
        return "Send failed"
    if row.get("reply_received"):
        return "Replied - awaiting outcome"
    if row.get("send_status") in ("sent", "dry_run"):
        return "Contacted - no reply yet"
    return "Unknown"


def results_to_dataframe(results: List[ProcessedLead]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "lead_id": r.lead.lead_id, "name": r.lead.name, "email": r.lead.email,
            "company": r.lead.company, "industry": r.lead.industry, "role": r.lead.role,
            "company_size": r.lead.company_size,
            "score": int(r.score.score), "priority": r.score.priority,
            "conversion_probability": r.score.conversion_probability,
            "buying_intent_level": r.score.buying_intent_level,
            "persona_title": r.persona.persona_title,
            "positioning_strategy": r.strategy.positioning_strategy,
            "value_proposition": r.strategy.value_proposition,
            "urgency_hook": r.strategy.urgency_hook,
            "closing_strategy": r.strategy.closing_strategy,
            "email_subject": r.email_draft.subject, "email_body": r.email_draft.body,
            "email_cta": r.email_draft.cta,
            "send_status": r.send_result.status if r.send_result else "n/a",
            "send_attempts": r.send_result.attempts if r.send_result else None,
            "reply_received": r.reply_text is not None, "reply_text": r.reply_text,
            "response_classification": r.response.classification if r.response else None,
            "response_sentiment": r.response.sentiment if r.response else None,
            "response_urgency": r.response.urgency if r.response else None,
            "lead_temperature": r.response.lead_temperature if r.response else None,
            "recommended_next_step": r.response.recommended_next_step if r.response else None,
            "follow_up_sent": r.follow_up is not None,
            "follow_up_email": r.follow_up.follow_up_email if r.follow_up else None,
            "follow_up_urgency_score": int(r.follow_up.urgency_score) if r.follow_up else None,
            "follow_up_intent_analysis": r.follow_up.intent_analysis if r.follow_up else None,
            "lifecycle_stage": r.lifecycle_stage,
            "lifecycle_history": " -> ".join(r.lifecycle_history) if r.lifecycle_history else None,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["outcome"] = df.apply(_derive_outcome, axis=1)
    return df


def compute_campaign_stats(df: pd.DataFrame, rejected_count: int) -> CampaignStats:
    if df.empty:
        return CampaignStats(total_leads=rejected_count, rejected_leads=rejected_count)

    replies_received = int(df["reply_received"].sum())
    follow_ups_sent = int(df["follow_up_sent"].sum())
    converted = int((df["outcome"] == "Converted (meeting booked)").sum())
    lost = int((df["outcome"] == "Lost / not interested").sum())
    contacted_no_reply = int((df["outcome"] == "Contacted - no reply yet").sum())
    emails_sent = int(df["send_status"].isin(["sent", "dry_run"]).sum())

    return CampaignStats(
        total_leads=len(df) + rejected_count,
        valid_leads=len(df),
        rejected_leads=rejected_count,
        emails_sent=emails_sent,
        emails_failed=int((df["send_status"] == "failed").sum()),
        high_priority=int((df["priority"] == "High").sum()),
        medium_priority=int((df["priority"] == "Medium").sum()),
        low_priority=int((df["priority"] == "Low").sum()),
        avg_score=float(df["score"].mean()),
        avg_conversion_probability=float(df["conversion_probability"].mean()),
        replies_received=replies_received,
        follow_ups_sent=follow_ups_sent,
        converted=converted,
        lost=lost,
        contacted_no_reply=contacted_no_reply,
        reply_rate=float(replies_received / emails_sent) if emails_sent else 0.0,
        conversion_rate=float(converted / len(df)) if len(df) else 0.0,
        follow_up_rate=float(follow_ups_sent / replies_received) if replies_received else 0.0,
    )


def plot_analytics(df: pd.DataFrame, out_dir: str) -> Dict[str, str]:
    """Generates charts and returns {name: filepath}."""
    if df.empty:
        logger.info("No processed leads to plot yet.")
        return {}

    os.makedirs(out_dir, exist_ok=True)
    chart_paths: Dict[str, str] = {}

    def _save(fig, name):
        path = os.path.join(out_dir, name)
        fig.tight_layout()
        fig.savefig(path, dpi=130)
        plt.close(fig)
        chart_paths[name] = path

    fig, ax = plt.subplots(figsize=(6, 4))
    sns.histplot(df["score"], bins=10, kde=True, ax=ax, color="#4C72B0")
    ax.set_title("Lead Score Distribution"); ax.set_xlabel("Score (1-10)")
    _save(fig, "lead_score_distribution.png")

    fig, ax = plt.subplots(figsize=(5, 4))
    df["priority"].value_counts().reindex(["High", "Medium", "Low"]).plot(
        kind="bar", ax=ax, color=["#C44E52", "#DD8452", "#55A868"])
    ax.set_title("Priority Distribution"); ax.set_ylabel("Leads")
    _save(fig, "priority_distribution.png")

    fig, ax = plt.subplots(figsize=(7, 4))
    df["industry"].value_counts().plot(kind="barh", ax=ax, color="#55A868")
    ax.set_title("Industry Breakdown"); ax.invert_yaxis()
    _save(fig, "industry_breakdown.png")

    fig, ax = plt.subplots(figsize=(7, 4))
    df["persona_title"].value_counts().head(10).plot(kind="barh", ax=ax, color="#8172B2")
    ax.set_title("Persona Clustering (top titles)"); ax.invert_yaxis()
    _save(fig, "persona_clustering.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    sns.histplot(df["conversion_probability"], bins=10, kde=True, ax=ax, color="#937860")
    ax.set_title("Conversion Probability Histogram"); ax.set_xlabel("Predicted conversion probability")
    _save(fig, "conversion_probability.png")

    funnel_stages = ["VALIDATED", "SCORED", "ENRICHED", "CONTACTED", "REPLIED", "CONVERTED"]
    counts = [df["lifecycle_history"].fillna("").apply(lambda h, s=stage: s in h).sum()
              for stage in funnel_stages]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(funnel_stages, counts, color="#64B5CD")
    ax.set_title("Lead Funnel (leads reaching each stage)"); ax.invert_yaxis()
    for i, c in enumerate(counts):
        ax.text(c, i, f" {c}", va="center")
    _save(fig, "funnel.png")

    outcome_counts = df["outcome"].value_counts().reindex(
        [o for o in OUTCOME_ORDER if o in df["outcome"].unique()])
    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.pie(outcome_counts.values, labels=outcome_counts.index, autopct="%1.0f%%",
           colors=[OUTCOME_COLORS.get(o, "#999999") for o in outcome_counts.index],
           startangle=90, wedgeprops={"edgecolor": "white"})
    ax.set_title("Lead Outcome Breakdown\n(why leads converted, were lost, or are pending)")
    _save(fig, "outcome_breakdown.png")

    replied_df = df[df["reply_received"]]
    if not replied_df.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        replied_df["response_classification"].value_counts().plot(kind="barh", ax=ax, color="#4C72B0")
        ax.set_title("Reply Classification Breakdown\n(what leads said when they replied)")
        ax.set_xlabel("Replies"); ax.invert_yaxis()
        _save(fig, "reply_classification_breakdown.png")

    conv_by_priority = (
        df.assign(is_converted=df["outcome"] == "Converted (meeting booked)")
        .groupby("priority")["is_converted"].mean()
        .reindex(["High", "Medium", "Low"]).fillna(0) * 100
    )
    fig, ax = plt.subplots(figsize=(5.5, 4))
    conv_by_priority.plot(kind="bar", ax=ax, color=["#C44E52", "#DD8452", "#55A868"])
    ax.set_title("Conversion Rate by Priority Tier"); ax.set_ylabel("Conversion rate (%)"); ax.set_xlabel("")
    for i, v in enumerate(conv_by_priority.values):
        ax.text(i, v, f"{v:.0f}%", ha="center", va="bottom")
    _save(fig, "conversion_rate_by_priority.png")

    if not replied_df.empty and replied_df["lead_temperature"].notna().any():
        temp_outcome = pd.crosstab(replied_df["lead_temperature"], replied_df["outcome"])
        temp_outcome = temp_outcome.reindex(["cold", "warm", "hot"]).dropna(how="all")
        fig, ax = plt.subplots(figsize=(7, 4))
        temp_outcome.plot(kind="bar", stacked=True, ax=ax,
                           color=[OUTCOME_COLORS.get(c, "#999999") for c in temp_outcome.columns])
        ax.set_title("Outcome by Lead Temperature\n(among leads who replied)")
        ax.set_xlabel("Lead temperature"); ax.set_ylabel("Leads")
        ax.legend(fontsize=8, loc="upper right")
        plt.setp(ax.get_xticklabels(), rotation=0)
        _save(fig, "outcome_by_temperature.png")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    order = [o for o in OUTCOME_ORDER if o in df["outcome"].unique()]
    sns.boxplot(data=df, x="outcome", y="score", order=order, ax=ax, hue="outcome",
                palette={o: OUTCOME_COLORS.get(o, "#999999") for o in order}, legend=False)
    ax.set_title("Lead Score by Outcome\n(are higher-scored leads actually converting?)")
    ax.set_xlabel(""); ax.set_ylabel("Score (1-10)")
    plt.setp(ax.get_xticklabels(), rotation=15, ha="right")
    _save(fig, "score_by_outcome.png")

    if replied_df["follow_up_sent"].any() or (~replied_df["follow_up_sent"]).any():
        followup_conv = (
            replied_df.assign(is_converted=replied_df["outcome"] == "Converted (meeting booked)")
            .groupby("follow_up_sent")["is_converted"].mean() * 100
        )
        followup_conv.index = followup_conv.index.map({True: "Follow-up sent", False: "No follow-up sent"})
        fig, ax = plt.subplots(figsize=(5, 4))
        followup_conv.plot(kind="bar", ax=ax, color=["#7F7F7F", "#55A868"])
        ax.set_title("Conversion Rate: With vs. Without Follow-Up\n(among leads who replied)")
        ax.set_ylabel("Conversion rate (%)"); ax.set_xlabel("")
        plt.setp(ax.get_xticklabels(), rotation=0)
        for i, v in enumerate(followup_conv.values):
            ax.text(i, v, f"{v:.0f}%", ha="center", va="bottom")
        _save(fig, "followup_effectiveness.png")

    logger.info("Saved %d charts to '%s/'.", len(chart_paths), out_dir)
    return chart_paths



"""Note:
Campaign analytics -- turns a list of ProcessedLead into a flat DataFrame,
computes CampaignStats, and renders the chart set (saved as PNGs under the
campaign's output directory, served back via GET /campaigns/{id}/charts/{name}).

Ported 1:1 from the notebook's (for the initial research purpose) analytics cell, including the "outcome" derived
column and the 12-chart set (funnel, outcome breakdown, conversion-by-priority,
score-by-outcome, follow-up effectiveness, etc).
"""