"""
Request/response contracts for the HTTP API. Kept separate from `schemas.py`
(the internal/domain models) so that changing an internal pipeline shape never
silently breaks the public API contract, and vice versa.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import CampaignStatus, DataSource, ReplyMode
from app.models.schemas import CampaignStats, ProcessedLead


# --------------------------------------------------------------------------- #
# Leads
# --------------------------------------------------------------------------- #
class RejectedLeadRow(BaseModel):
    row: Dict[str, Any]
    rejection_reasons: str


class LeadBatchSummary(BaseModel):
    batch_id: str
    source: DataSource
    total_rows: int
    clean_count: int
    rejected_count: int
    sample_clean: List[Dict[str, Any]] = Field(default_factory=list)
    sample_rejected: List[RejectedLeadRow] = Field(default_factory=list)


class SyntheticLeadsRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=500)


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #
class CampaignCreateRequest(BaseModel):
    batch_id: str = Field(..., description="A batch_id returned by /leads/upload or /leads/synthetic")
    dry_run: Optional[bool] = Field(
        default=None, description="Override the server default send mode for this run only."
    )
    reply_mode: Optional[ReplyMode] = Field(
        default=None, description="Override the server default reply mode for this run only."
    )


class CampaignCreateResponse(BaseModel):
    campaign_id: str
    status: CampaignStatus
    batch_id: str
    dry_run: bool
    reply_mode: ReplyMode


class CampaignStatusResponse(BaseModel):
    campaign_id: str
    status: CampaignStatus
    batch_id: str
    dry_run: bool
    reply_mode: ReplyMode
    progress: Dict[str, int] = Field(
        default_factory=dict, description="e.g. {'processed': 3, 'total': 10}"
    )
    error: Optional[str] = None
    stats: Optional[CampaignStats] = None


class CampaignLeadsResponse(BaseModel):
    campaign_id: str
    count: int
    leads: List[ProcessedLead]


class LeadReplyRequest(BaseModel):
    reply_text: str = Field(..., min_length=1, description="The raw reply text from the lead.")


class LeadReplyResponse(BaseModel):
    lead_id: str
    classification: str
    lead_temperature: str
    follow_up_generated: bool
    lifecycle_stage: str


class ChartListResponse(BaseModel):
    campaign_id: str
    charts: List[str]


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class EffectiveConfigResponse(BaseModel):
    app_env: str
    model_name: str
    temperature: float
    max_tokens: int
    default_data_source: DataSource
    dry_run: bool
    reply_mode: ReplyMode
    retry_count: int
    rate_limit_delay: float
    backoff_base: float
    tpm_limit: int
    tpm_safety_margin: float
    cache_enabled: bool
    smtp_host: str
    smtp_port: int
    llm_configured: bool


class ConfigUpdateRequest(BaseModel):
    """Only the switches meant to be flipped at runtime are patchable here.
    Everything else (model name, TPM limits, SMTP host, ...) is infrastructure
    and belongs in environment variables / a redeploy, not a live PATCH."""
    dry_run: Optional[bool] = None
    reply_mode: Optional[ReplyMode] = None
    default_data_source: Optional[DataSource] = None
