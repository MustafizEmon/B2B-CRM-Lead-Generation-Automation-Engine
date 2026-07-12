"""Liveness/readiness endpoints -- Plan-> (used by Docker HEALTHCHECK and load balancers)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Settings, get_settings

router = APIRouter(tags=["Health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "llm_configured": settings.is_llm_configured,
    }
