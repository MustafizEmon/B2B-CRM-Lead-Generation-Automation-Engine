from __future__ import annotations

import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import Settings, get_settings
from app.models.api_schemas import (
    CampaignCreateRequest,
    CampaignCreateResponse,
    CampaignLeadsResponse,
    CampaignStatusResponse,
    ChartListResponse,
    LeadReplyRequest,
    LeadReplyResponse,
)
from app.models.enums import CampaignStatus
from app.models.schemas import CampaignStats
from app.services.analytics import compute_campaign_stats, plot_analytics, results_to_dataframe
from app.services.pipeline import apply_reply, run_campaign
from app.services.reporting import (
    export_csv,
    export_excel_report,
    export_markdown_report,
    generate_insights_and_recommendations,
)
from app.store.campaign_store import create_campaign, get_batch, get_campaign

logger = logging.getLogger("crm_ai.api.campaigns")
router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


def _execute_campaign(campaign_id: str, settings: Settings) -> None:
    """Runs in a background thread. Any exception is caught and stored on the
    campaign so GET /campaigns/{id} can surface it instead of the request
    just silently never completing."""
    campaign = get_campaign(campaign_id)
    batch = get_batch(campaign.batch_id) if campaign else None
    if not campaign or not batch:
        return

    campaign.status = CampaignStatus.RUNNING
    try:
        run_campaign(campaign, batch.clean_df)

        results_df = results_to_dataframe(campaign.results)
        stats = compute_campaign_stats(results_df, len(batch.rejected_df))

        chart_dir = os.path.join(settings.output_dir, campaign_id)
        report_dir = os.path.join(settings.report_dir, campaign_id)
        os.makedirs(chart_dir, exist_ok=True)
        os.makedirs(report_dir, exist_ok=True)

        chart_paths = plot_analytics(results_df, chart_dir)
        insights_data = generate_insights_and_recommendations(stats, results_df)

        csv_path = os.path.join(chart_dir, "leads_processed.csv")
        md_path = os.path.join(report_dir, "campaign_report.md")
        xlsx_path = os.path.join(report_dir, "campaign_report.xlsx")

        export_csv(results_df, csv_path)
        export_markdown_report(stats, insights_data["insights"], insights_data["recommendations"],
                                chart_paths, report_dir, md_path)
        export_excel_report(results_df, batch.rejected_df, stats, xlsx_path)

        campaign.chart_paths = chart_paths
        campaign.report_paths = {"csv": csv_path, "markdown": md_path, "excel": xlsx_path}
        campaign.stats = stats.model_dump()
        campaign.status = CampaignStatus.COMPLETED
        logger.info("Campaign %s completed successfully.", campaign_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Campaign %s failed.", campaign_id)
        campaign.status = CampaignStatus.FAILED
        campaign.error = str(exc)


@router.post("", response_model=CampaignCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_and_run_campaign(
    payload: CampaignCreateRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
):
    """Kicks off a campaign over a previously-uploaded/generated lead batch.

    `dry_run` and `reply_mode` are optional per-request overrides of the
    server's default switches (see GET /api/v1/config) -- omit them to use
    the current server defaults.
    """
    if not settings.is_llm_configured:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured on the server. Set it in the environment and restart.",
        )

    batch = get_batch(payload.batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Lead batch '{payload.batch_id}' not found.")
    if batch.clean_df.empty:
        raise HTTPException(status_code=422, detail="This batch has no valid leads to process.")

    campaign = create_campaign(payload.batch_id, settings, payload.dry_run, payload.reply_mode)
    background_tasks.add_task(_execute_campaign, campaign.campaign_id, settings)

    return CampaignCreateResponse(
        campaign_id=campaign.campaign_id, status=campaign.status, batch_id=campaign.batch_id,
        dry_run=campaign.dry_run, reply_mode=campaign.reply_mode,
    )


def _get_campaign_or_404(campaign_id: str):
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found.")
    return campaign


@router.get("/{campaign_id}", response_model=CampaignStatusResponse)
def get_campaign_status(campaign_id: str):
    campaign = _get_campaign_or_404(campaign_id)
    stats = CampaignStats(**campaign.stats) if campaign.stats else None
    return CampaignStatusResponse(
        campaign_id=campaign.campaign_id, status=campaign.status, batch_id=campaign.batch_id,
        dry_run=campaign.dry_run, reply_mode=campaign.reply_mode, progress=campaign.progress,
        error=campaign.error, stats=stats,
    )


@router.get("/{campaign_id}/leads", response_model=CampaignLeadsResponse)
def list_campaign_leads(campaign_id: str):
    campaign = _get_campaign_or_404(campaign_id)
    return CampaignLeadsResponse(campaign_id=campaign_id, count=len(campaign.results), leads=campaign.results)


@router.get("/{campaign_id}/leads/{lead_id}")
def get_campaign_lead(campaign_id: str, lead_id: str):
    campaign = _get_campaign_or_404(campaign_id)
    for processed in campaign.results:
        if processed.lead.lead_id == lead_id:
            return processed
    raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found in campaign '{campaign_id}'.")


@router.post("/{campaign_id}/leads/{lead_id}/reply", response_model=LeadReplyResponse)
def submit_lead_reply(campaign_id: str, lead_id: str, payload: LeadReplyRequest):
    """Real-inbox reply path: call this from an email-provider inbound webhook
    (or manually) to deliver an actual reply for a contacted lead. Triggers
    classification, an optional follow-up email, and the matching lifecycle
    transition -- identical downstream behavior to a simulated reply."""
    campaign = _get_campaign_or_404(campaign_id)

    processed = next((p for p in campaign.results if p.lead.lead_id == lead_id), None)
    if not processed:
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found in campaign '{campaign_id}'.")
    if processed.send_result is None or processed.send_result.status not in ("sent", "dry_run"):
        raise HTTPException(status_code=409, detail="This lead has not been contacted yet.")

    apply_reply(campaign, processed, payload.reply_text)

    return LeadReplyResponse(
        lead_id=lead_id,
        classification=processed.response.classification if processed.response else "unknown",
        lead_temperature=processed.response.lead_temperature if processed.response else "cold",
        follow_up_generated=processed.follow_up is not None,
        lifecycle_stage=processed.lifecycle_stage or "UNKNOWN",
    )


@router.get("/{campaign_id}/report/csv")
def download_csv_report(campaign_id: str):
    campaign = _get_campaign_or_404(campaign_id)
    _require_completed(campaign)
    return FileResponse(campaign.report_paths["csv"], filename="leads_processed.csv", media_type="text/csv")


@router.get("/{campaign_id}/report/markdown")
def download_markdown_report(campaign_id: str):
    campaign = _get_campaign_or_404(campaign_id)
    _require_completed(campaign)
    return FileResponse(campaign.report_paths["markdown"], filename="campaign_report.md", media_type="text/markdown")


@router.get("/{campaign_id}/report/excel")
def download_excel_report(campaign_id: str):
    campaign = _get_campaign_or_404(campaign_id)
    _require_completed(campaign)
    return FileResponse(
        campaign.report_paths["excel"], filename="campaign_report.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/{campaign_id}/charts", response_model=ChartListResponse)
def list_charts(campaign_id: str):
    campaign = _get_campaign_or_404(campaign_id)
    _require_completed(campaign)
    return ChartListResponse(campaign_id=campaign_id, charts=sorted(campaign.chart_paths.keys()))


@router.get("/{campaign_id}/charts/{chart_name}")
def get_chart(campaign_id: str, chart_name: str):
    campaign = _get_campaign_or_404(campaign_id)
    _require_completed(campaign)
    path = campaign.chart_paths.get(chart_name)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Chart '{chart_name}' not found.")
    return FileResponse(path, media_type="image/png")


def _require_completed(campaign) -> None:
    if campaign.status != CampaignStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Campaign is '{campaign.status.value}', not completed yet. Poll GET /campaigns/{{id}}.",
        )



"""Note:
Campaign endpoints -- create/run a campaign over a lead batch, poll status,
fetch processed leads, submit real replies, and download reports/charts.

A campaign runs as a FastAPI BackgroundTask: POST /campaigns returns
immediately with status=queued, and the AI pipeline (scoring -> persona ->
strategy -> email -> send -> reply handling) executes asynchronously. Poll
GET /campaigns/{id} until status is "completed" (or "failed").
"""