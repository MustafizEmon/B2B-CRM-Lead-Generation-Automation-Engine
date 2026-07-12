from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from app.config import Settings
from app.core.memory import LeadMemoryStore
from app.core.state_machine import CRMStateMachine
from app.models.enums import CampaignStatus, DataSource, ReplyMode
from app.models.schemas import ProcessedLead
from app.services.email_sender import EmailSender

_LOCK = threading.Lock()


@dataclass
class LeadBatch:
    batch_id: str
    source: DataSource
    raw_df: pd.DataFrame
    clean_df: pd.DataFrame
    rejected_df: pd.DataFrame


@dataclass
class Campaign:
    campaign_id: str
    batch_id: str
    dry_run: bool
    reply_mode: ReplyMode
    status: CampaignStatus = CampaignStatus.QUEUED
    error: Optional[str] = None
    progress: Dict[str, int] = field(default_factory=lambda: {"processed": 0, "total": 0})
    results: List[ProcessedLead] = field(default_factory=list)
    state: CRMStateMachine = field(default_factory=CRMStateMachine)
    memory: LeadMemoryStore = field(default_factory=LeadMemoryStore)
    email_sender: Optional[EmailSender] = None
    chart_paths: Dict[str, str] = field(default_factory=dict)
    report_paths: Dict[str, str] = field(default_factory=dict)  # {"csv": ..., "markdown": ..., "excel": ...}
    stats: Optional[dict] = None  # populated with CampaignStats.model_dump() once complete


_BATCHES: Dict[str, LeadBatch] = {}
_CAMPAIGNS: Dict[str, Campaign] = {}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def save_batch(source: DataSource, raw_df: pd.DataFrame, clean_df: pd.DataFrame,
               rejected_df: pd.DataFrame) -> LeadBatch:
    batch = LeadBatch(
        batch_id=new_id("batch"), source=source, raw_df=raw_df, clean_df=clean_df, rejected_df=rejected_df
    )
    with _LOCK:
        _BATCHES[batch.batch_id] = batch
    return batch


def get_batch(batch_id: str) -> Optional[LeadBatch]:
    return _BATCHES.get(batch_id)


def create_campaign(batch_id: str, settings: Settings, dry_run: Optional[bool],
                     reply_mode: Optional[ReplyMode]) -> Campaign:
    effective_dry_run = settings.dry_run if dry_run is None else dry_run
    effective_reply_mode = settings.reply_mode if reply_mode is None else reply_mode

    campaign = Campaign(
        campaign_id=new_id("campaign"),
        batch_id=batch_id,
        dry_run=effective_dry_run,
        reply_mode=effective_reply_mode,
    )
    campaign.email_sender = EmailSender(settings, dry_run=effective_dry_run)
    with _LOCK:
        _CAMPAIGNS[campaign.campaign_id] = campaign
    return campaign


def get_campaign(campaign_id: str) -> Optional[Campaign]:
    return _CAMPAIGNS.get(campaign_id)




"""Note:
In-process stores for lead batches and campaigns.

Deliberately simple (plain dicts guarded by a lock) rather than a database:
this mirrors the notebook's "no permanent memory" design goal for anything
conversation/LLM-related, while still letting completed campaign *reports*
persist to disk (storage/reports, storage/outputs) so downloads work.

IMPORTANT for production: this in-memory store only works with a single
Uvicorn/Gunicorn worker process. If you scale to multiple workers or multiple
replicas behind a load balancer, replace `_BATCHES` / `_CAMPAIGNS` with Redis
(or Postgres) so every worker sees the same state. See README > "Future
Improvements" for the suggested approach.
"""