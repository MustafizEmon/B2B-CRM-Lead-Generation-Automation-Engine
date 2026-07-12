from __future__ import annotations

import logging
import smtplib
import time
from email.mime.text import MIMEText
from typing import Optional

from app.config import Settings
from app.models.schemas import EmailDraft, Lead, SendResult

logger = logging.getLogger("crm_ai.email")


class EmailSender:
    def __init__(self, settings: Settings, dry_run: Optional[bool] = None) -> None:
        self.settings = settings
        self.dry_run = settings.dry_run if dry_run is None else dry_run

    def _send_via_smtp(self, to_addr: str, subject: str, body: str) -> None:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.settings.smtp_sender_address
        msg["To"] = to_addr

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as server:
            if self.settings.smtp_use_tls:
                server.starttls()
            if self.settings.smtp_username:
                server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.sendmail(self.settings.smtp_sender_address, [to_addr], msg.as_string())

    def send(self, lead: Lead, draft: EmailDraft) -> SendResult:
        start = time.time()

        if self.dry_run:
            logger.info("[DRY RUN] Would send to %s | subject='%s'", lead.email, draft.subject)
            return SendResult(lead_id=lead.lead_id, status="dry_run", attempts=1,
                               latency_seconds=time.time() - start)

        last_exc = None
        for attempt in range(1, self.settings.retry_count + 1):
            try:
                self._send_via_smtp(lead.email, draft.subject, draft.body)
                return SendResult(lead_id=lead.lead_id, status="sent", attempts=attempt,
                                   latency_seconds=time.time() - start)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = self.settings.backoff_base ** attempt
                logger.warning("SMTP send to %s failed (attempt %d): %s. Retrying in %.1fs.",
                               lead.email, attempt, exc, wait)
                time.sleep(wait)

        return SendResult(lead_id=lead.lead_id, status="failed", attempts=self.settings.retry_count,
                           latency_seconds=time.time() - start, error=str(last_exc))



"""Remark:
Email delivery -- dry-run (default) or real SMTP, with retry + exponential backoff.

The `dry_run` switch is passed in per-call (from the campaign's effective
config) rather than read as a hardcoded global, so a single running server can
have one campaign in dry-run and another sending for real at the same time.
"""