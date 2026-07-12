"""Shared enums used across the config, domain models, and services.

Kept in one module (rather than scattered per-file) so the two "mode switches"
requested by the project spec -- data source and reply source -- have a single,
obvious source of truth that both `app/config.py` and the API layer import from.
"""
from enum import Enum


class DataSource(str, Enum):
    """Where a lead batch's rows came from. Drives which ingestion path ran."""
    SYNTHETIC = "synthetic"   # Faker-generated demo leads (POST /leads/synthetic)
    CSV = "csv"               # real leads uploaded via POST /leads/upload


class ReplyMode(str, Enum):
    """How a lead's reply is obtained during/after a campaign run."""
    SIMULATED = "simulated"    # fabricate a plausible reply automatically (demo/testing)
    REAL_INBOX = "real_inbox"  # real replies arrive via POST .../leads/{lead_id}/reply
                                # (e.g. from an email-provider webhook or manual entry)


class SendMode(str, Enum):
    """Whether outbound email actually leaves the server."""
    DRY_RUN = "dry_run"   # simulate the send, log it, never open a socket
    LIVE = "live"         # connect to real SMTP (or MailHog) and send


class LifecycleStage(str, Enum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    SCORED = "SCORED"
    ENRICHED = "ENRICHED"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


class CampaignStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
