from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import campaigns, config as config_routes, health, leads
from app.config import settings


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f"{settings.log_dir}/pipeline.log"),
        ],
    )


_configure_logging()
logger = logging.getLogger("crm_ai.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Runs once when the application starts and once when it shuts down.
    """

    # Startup
    logger.info(
        "%s starting. env=%s llm_configured=%s dry_run=%s reply_mode=%s model=%s",
        settings.app_name,
        settings.app_env,
        settings.is_llm_configured,
        settings.dry_run,
        settings.reply_mode.value,
        settings.model_name,
    )

    yield

    # Shutdown
    logger.info("%s shutting down.", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description=(
        "AI-powered B2B CRM sales automation API -- LangChain (LCEL) + Groq. "
        "Submit leads via CSV upload, run an AI campaign (scoring, persona, "
        "strategy, personalized email, response handling), and pull back "
        "analytics, charts, and reports."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,  # Modern replacement for @app.on_event
)

# ---------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------

app.include_router(health.router)
app.include_router(leads.router, prefix=settings.api_v1_prefix)
app.include_router(campaigns.router, prefix=settings.api_v1_prefix)
app.include_router(config_routes.router, prefix=settings.api_v1_prefix)

# ---------------------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------------------


@app.get("/", tags=["Health"])
async def root():
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "api_prefix": settings.api_v1_prefix,
    }