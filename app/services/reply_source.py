from __future__ import annotations

import random
from typing import Optional

from app.models.enums import ReplyMode
from app.models.schemas import Lead

SIMULATED_REPLY_TEMPLATES = [
    "Thanks for reaching out, this looks interesting - can we set up a call next week?",
    "Not the right time for us, please remove me from your list.",
    "Can you send more details on pricing and integration?",
    "I'm out of the office until next month, will review then.",
    "Not interested, please don't contact again.",
]


def simulate_reply(lead: Lead) -> Optional[str]:
    """Demo/testing only: fabricates a plausible reply for ANY lead. Not a real
    reply -- never log or act on it as if a real person said it outside of demo runs."""
    if random.random() < 0.75:  # not every lead replies
        return random.choice(SIMULATED_REPLY_TEMPLATES)
    return None


def get_lead_reply(lead: Lead, reply_mode: ReplyMode) -> Optional[str]:
    """Single dispatch point mirroring `load_leads_raw()`'s pattern for data source."""
    if reply_mode == ReplyMode.SIMULATED:
        return simulate_reply(lead)
    elif reply_mode == ReplyMode.REAL_INBOX:
        return None  # real replies arrive later via the /reply endpoint, not inline
    raise ValueError(f"Unknown reply_mode: {reply_mode}")



"""
Reply source -- simulated (auto-generated during the run) or real (delivered
later via the webhook-style endpoint `POST /campaigns/{id}/leads/{lead_id}/reply`).

This is the API's take on the notebook's `ReplyMode` switch. In a notebook,
"real" replies meant polling an IMAP inbox synchronously inside the run loop --
that doesn't map well onto a stateless HTTP API, so REAL_INBOX mode here simply
means "don't fabricate a reply during the run; wait for one to be POSTed."
Wire an email provider's inbound-mail webhook (SendGrid Inbound Parse, Postmark,
Mailgun Routes, etc.) to call that endpoint and the rest of the pipeline
(classification, follow-up, lifecycle transitions) behaves identically either way.
"""