"""Note:
Lead ingestion endpoints.

    POST /api/v1/leads/upload      <- primary path: submit a real leads.csv
    POST /api/v1/leads/synthetic   <- generate Faker-based demo leads instead

Both run the same validation step and return a `batch_id` you then pass to
`POST /api/v1/campaigns` to actually run the AI pipeline over that batch.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.models.api_schemas import LeadBatchSummary, RejectedLeadRow
from app.models.enums import DataSource
from app.services.data_ingestion import generate_synthetic_leads, load_csv_leads_from_bytes
from app.services.validation import LeadValidator
from app.store.campaign_store import get_batch, save_batch

logger = logging.getLogger("crm_ai.api.leads")
router = APIRouter(prefix="/leads", tags=["Leads"])

validator = LeadValidator()


def _sanitize_records(df) -> list:
    """pandas NaN isn't valid JSON -- convert to None before serializing."""
    if df.empty:
        return []
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


def _summarize(batch, sample_size: int = 5) -> LeadBatchSummary:
    clean_sample = _sanitize_records(batch.clean_df.head(sample_size))
    rejected_sample = []
    if not batch.rejected_df.empty:
        for row in _sanitize_records(batch.rejected_df.head(sample_size)):
            reasons = row.pop("rejection_reasons", "") or ""
            rejected_sample.append(RejectedLeadRow(row=row, rejection_reasons=reasons))

    return LeadBatchSummary(
        batch_id=batch.batch_id,
        source=batch.source,
        total_rows=len(batch.raw_df),
        clean_count=len(batch.clean_df),
        rejected_count=len(batch.rejected_df),
        sample_clean=clean_sample,
        sample_rejected=rejected_sample,
    )


@router.post("/upload", response_model=LeadBatchSummary, status_code=status.HTTP_201_CREATED)
async def upload_leads_csv(file: UploadFile = File(..., description="CSV with columns: name, email, company, role, industry, company_size, website")):
    """Submit a real leads CSV. This is the primary way to feed leads into the
    system. The file is validated immediately (schema check, email format,
    duplicate removal, company-size normalization) -- clean rows become the
    batch used for campaigns; rejected rows are returned with reasons so you
    can fix and re-upload."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    raw_bytes = await file.read()
    try:
        raw_df = load_csv_leads_from_bytes(raw_bytes, file.filename)
        result = validator.validate(raw_df)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    batch = save_batch(DataSource.CSV, raw_df, result["clean"], result["rejected"])
    logger.info("Batch %s created from upload '%s': %d clean, %d rejected.",
                batch.batch_id, file.filename, len(batch.clean_df), len(batch.rejected_df))
    return _summarize(batch)


@router.post("/synthetic", response_model=LeadBatchSummary, status_code=status.HTTP_201_CREATED)
def generate_synthetic_batch(count: int = Query(default=10, ge=1, le=500)):
    """Generate `count` realistic synthetic leads (Faker) for demos and testing,
    without needing a real CSV. Goes through the same validation step as an
    upload, so the resulting batch_id behaves identically in /campaigns."""
    raw_df = generate_synthetic_leads(count)
    result = validator.validate(raw_df)
    batch = save_batch(DataSource.SYNTHETIC, raw_df, result["clean"], result["rejected"])
    logger.info("Synthetic batch %s created: %d clean, %d rejected.",
                batch.batch_id, len(batch.clean_df), len(batch.rejected_df))
    return _summarize(batch)


@router.get("/{batch_id}", response_model=LeadBatchSummary)
def get_lead_batch(batch_id: str):
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Lead batch '{batch_id}' not found.")
    return _summarize(batch, sample_size=25)
