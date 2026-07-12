from __future__ import annotations

import logging
import random
from io import BytesIO
from typing import List

import pandas as pd
from faker import Faker

logger = logging.getLogger("crm_ai.ingestion")
fake = Faker()

REQUIRED_COLUMNS: List[str] = ["name", "email", "company", "role", "industry", "company_size", "website"]

INDUSTRIES = ["SaaS", "FinTech", "Healthcare", "E-commerce", "Manufacturing",
              "EdTech", "Logistics", "Cybersecurity", "Real Estate", "Retail"]
ROLES = ["CEO", "CTO", "VP Sales", "Head of Marketing", "Procurement Manager",
         "Operations Director", "IT Manager", "Founder"]
COMPANY_SIZES = ["1-50", "51-500", "501-5000", "5000+"]


def generate_synthetic_leads(n: int) -> pd.DataFrame:
    """Generate n diverse, realistic synthetic leads using Faker."""
    rows = []
    for _ in range(n):
        company = fake.company()
        rows.append({
            "name": fake.name(),
            "email": fake.company_email(),
            "company": company,
            "role": random.choice(ROLES),
            "industry": random.choice(INDUSTRIES),
            "company_size": random.choice(COMPANY_SIZES),
            "website": f"https://www.{company.lower().replace(',', '').replace(' ', '')[:20]}.com",
        })
    df = pd.DataFrame(rows)
    logger.info("Generated %d synthetic leads.", len(df))
    return df


def load_csv_leads_from_bytes(file_bytes: bytes, filename: str = "upload.csv") -> pd.DataFrame:
    """Parse an uploaded CSV file's raw bytes into a DataFrame.

    Raises ValueError with a client-friendly message on malformed CSV content,
    which the route layer turns into a 400 response.
    """
    try:
        df = pd.read_csv(BytesIO(file_bytes))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not parse '{filename}' as CSV: {exc}") from exc

    if df.empty:
        raise ValueError(f"'{filename}' contains no rows.")

    logger.info("Loaded %d leads from uploaded CSV '%s'.", len(df), filename)
    return df



"""
Lead ingestion -- synthetic (Faker) or real CSV, dispatched by data source.

In the notebook this was a single switch (`CONFIG.data_source`). In the API,
the "switch" is expressed as which endpoint the client calls:
  - POST /api/v1/leads/upload    -> load_csv_leads_from_upload()
  - POST /api/v1/leads/synthetic -> generate_synthetic_leads()

Both converge on the same `pd.DataFrame` shape (REQUIRED_COLUMNS) so every
downstream stage (validation, scoring, ...) is completely agnostic to which
path produced it.
"""