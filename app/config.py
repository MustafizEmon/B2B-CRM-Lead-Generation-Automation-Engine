from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.enums import DataSource, ReplyMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # App / server
    # ------------------------------------------------------------------ #
    app_name: str = "AI CRM Sales Automation API"
    app_env: str = Field(default="development")  # development | production
    api_v1_prefix: str = "/api/v1"
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])

    # ------------------------------------------------------------------ #
    # LLM (Groq)
    # ------------------------------------------------------------------ #
    groq_api_key: str = Field(default="", description="Required to actually run AI chains.")
    model_name: str = Field(default="openai/gpt-oss-120b")
    temperature: float = 0.4
    max_tokens: int = 2048

    # ------------------------------------------------------------------ #
    # Data source switch (⭐ SYNTHETIC vs CSV)
    # ------------------------------------------------------------------ #
    # In the API, the source is really determined by *which endpoint* the client
    # calls (POST /leads/upload vs POST /leads/synthetic) -- this default only
    # matters for background/CLI usage that doesn't specify one explicitly.
    default_data_source: DataSource = DataSource.CSV
    synthetic_lead_count_default: int = 10

    # ------------------------------------------------------------------ #
    # Send mode switch (⭐ dry-run vs live SMTP)
    # ------------------------------------------------------------------ #
    dry_run: bool = True

    # ------------------------------------------------------------------ #
    # Reply mode switch (⭐ simulated vs real/webhook-driven)
    # ------------------------------------------------------------------ #
    reply_mode: ReplyMode = ReplyMode.SIMULATED

    # ------------------------------------------------------------------ #
    # Resilience / rate limiting
    # ------------------------------------------------------------------ #
    retry_count: int = 5
    rate_limit_delay: float = 1.2
    backoff_base: float = 2.0
    tpm_limit: int = 8000
    tpm_safety_margin: float = 0.85
    cache_enabled: bool = True

    # ------------------------------------------------------------------ #
    # SMTP (used when dry_run=False)
    # ------------------------------------------------------------------ #
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = False
    smtp_sender_address: str = "sales-ai@yourcompany.com"

    # ------------------------------------------------------------------ #
    # Storage paths (mounted as a Docker volume in production)
    # ------------------------------------------------------------------ #
    storage_dir: str = "storage"
    uploads_dir: str = "storage/uploads"
    output_dir: str = "storage/outputs"
    report_dir: str = "storage/reports"
    log_dir: str = "storage/logs"

    log_level: str = "INFO"

    @field_validator(
        "uploads_dir", "output_dir", "report_dir", "log_dir", "storage_dir", mode="after"
    )
    @classmethod
    def _ensure_dir_exists(cls, v: str) -> str:
        Path(v).mkdir(parents=True, exist_ok=True)
        return v

    @property
    def is_llm_configured(self) -> bool:
        return bool(self.groq_api_key) and self.groq_api_key != "PASTE_YOUR_GROQ_API_KEY_HERE"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor -- import and call this, don't instantiate Settings()."""
    return Settings()


# Convenience module-level instance for code that isn't wired through FastAPI's
# dependency-injection (e.g. scripts, tests). Routes should still prefer the
# `Depends(get_settings)` pattern where possible for testability.
settings = get_settings()




"""Remark:
[Every runtime "switch" the (original research notebook) exposed as a notebook-level
CONFIG object is preserved here as an environment-variable-backed setting, using
pydantic-settings. This is the single source of truth the whole app reads from --
no module hardcodes a mode, a path, or a model name anywhere else.]

Two things are intentionally NOT baked in as static values because they are meant
to be changed at runtime (per campaign, or via the /api/v1/config endpoint):
  - dry_run / send_mode         (email actually sent vs. simulated)
  - reply_mode                  (simulated replies vs. real webhook-driven replies)

Both still have sane defaults here so the API is safe to call with zero
configuration beyond a Groq API key.
"""