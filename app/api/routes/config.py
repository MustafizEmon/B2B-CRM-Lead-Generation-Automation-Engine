from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Settings, get_settings
from app.models.api_schemas import ConfigUpdateRequest, EffectiveConfigResponse

router = APIRouter(prefix="/config", tags=["Config"])


@router.get("", response_model=EffectiveConfigResponse)
def get_effective_config(settings: Settings = Depends(get_settings)):
    return EffectiveConfigResponse(
        app_env=settings.app_env,
        model_name=settings.model_name,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        default_data_source=settings.default_data_source,
        dry_run=settings.dry_run,
        reply_mode=settings.reply_mode,
        retry_count=settings.retry_count,
        rate_limit_delay=settings.rate_limit_delay,
        backoff_base=settings.backoff_base,
        tpm_limit=settings.tpm_limit,
        tpm_safety_margin=settings.tpm_safety_margin,
        cache_enabled=settings.cache_enabled,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        llm_configured=settings.is_llm_configured,
    )


@router.patch("", response_model=EffectiveConfigResponse)
def update_switches(payload: ConfigUpdateRequest, settings: Settings = Depends(get_settings)):
    """Flips the server-wide defaults for new campaigns. Campaigns already
    created keep whatever switch values they were created with -- this only
    affects future `POST /campaigns` calls that don't specify an override."""
    if payload.dry_run is not None:
        settings.dry_run = payload.dry_run
    if payload.reply_mode is not None:
        settings.reply_mode = payload.reply_mode
    if payload.default_data_source is not None:
        settings.default_data_source = payload.default_data_source
    return get_effective_config(settings)




"""Note:
Runtime configuration endpoints -- view the server's effective switches, and
flip the two "mode" switches (dry_run, reply_mode) without a redeploy.

Everything else (model name, TPM limits, SMTP host, storage paths) is
infrastructure-level and intentionally NOT patchable here -- change it via
environment variables and restart the container instead. See README >
Configuration for the full rationale.
"""