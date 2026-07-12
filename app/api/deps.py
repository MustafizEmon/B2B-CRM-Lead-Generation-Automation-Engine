"""Shared FastAPI dependencies."""
from __future__ import annotations

from app.config import Settings, get_settings

# Re-exported so routes can do `Depends(get_settings)` from one place.
__all__ = ["get_settings", "Settings"]
