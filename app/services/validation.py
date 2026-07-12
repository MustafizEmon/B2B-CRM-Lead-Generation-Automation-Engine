from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

import pandas as pd

from app.services.data_ingestion import REQUIRED_COLUMNS

logger = logging.getLogger("crm_ai.validation")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LeadValidator:
    """Schema validation, cleaning, dedup, and normalization for raw lead DataFrames."""

    def __init__(self, required_columns: List[str] = None) -> None:
        self.required_columns = required_columns or REQUIRED_COLUMNS

    def _check_schema(self, df: pd.DataFrame) -> List[str]:
        return [c for c in self.required_columns if c not in df.columns]

    def _normalize_company_size(self, value: Any) -> str:
        if pd.isna(value):
            return "unknown"
        v = str(value).strip().lower()
        mapping = {
            "small": "1-50", "1-50": "1-50",
            "medium": "51-500", "51-500": "51-500",
            "large": "501-5000", "501-5000": "501-5000",
            "enterprise": "5000+", "5000+": "5000+",
        }
        return mapping.get(v, v)

    def validate(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        missing_cols = self._check_schema(df)
        if missing_cols:
            raise ValueError(f"Input data missing required columns: {missing_cols}")

        df = df.copy()
        df["lead_id"] = [f"L{idx:04d}" for idx in range(len(df))]

        clean_rows, rejected_rows = [], []

        for _, row in df.iterrows():
            reasons = []

            for col in self.required_columns:
                val = row.get(col)
                if pd.isna(val) or str(val).strip() == "":
                    if col != "website":  # website is optional
                        reasons.append(f"missing_{col}")

            email_val = str(row.get("email", ""))
            if not EMAIL_RE.match(email_val):
                reasons.append("invalid_email_format")

            row_dict = row.to_dict()
            row_dict["company_size"] = self._normalize_company_size(row_dict.get("company_size"))

            if reasons:
                row_dict["rejection_reasons"] = "; ".join(reasons)
                rejected_rows.append(row_dict)
            else:
                clean_rows.append(row_dict)

        clean_df = pd.DataFrame(clean_rows)
        rejected_df = pd.DataFrame(rejected_rows)

        if not clean_df.empty:
            before = len(clean_df)
            clean_df = clean_df.drop_duplicates(subset=["email"], keep="first")
            deduped = before - len(clean_df)
            if deduped:
                logger.info("Removed %d duplicate lead(s) by email.", deduped)

        logger.info("Validation complete: %d clean, %d rejected.", len(clean_df), len(rejected_df))
        return {"clean": clean_df.reset_index(drop=True), "rejected": rejected_df.reset_index(drop=True)}



"""
Data validation & cleaning -- schema check, missing-value detection, email
format validation, duplicate removal, and company-size normalization.

Direct port of the notebook's `LeadValidator`. Returns both the clean
DataFrame (fed into the pipeline) and the rejected DataFrame (with reasons,
surfaced back to the API caller so they know exactly which rows were dropped
and why).
"""