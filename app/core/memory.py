from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.chat_history import InMemoryChatMessageHistory


class LeadMemoryStore:
    """Per-lead conversational memory, scoped to a single campaign run."""

    def __init__(self) -> None:
        self._histories: Dict[str, InMemoryChatMessageHistory] = {}

    def _history(self, lead_id: str) -> InMemoryChatMessageHistory:
        return self._histories.setdefault(lead_id, InMemoryChatMessageHistory())

    def log_ai_event(self, lead_id: str, label: str, content: str) -> None:
        """Record an AI-generated pipeline artifact (score, persona, email, ...)."""
        self._history(lead_id).add_ai_message(f"[{label}] {content}")

    def log_human_event(self, lead_id: str, label: str, content: str) -> None:
        """Record a lead-originated event (their reply, an inbound message, ...)."""
        self._history(lead_id).add_user_message(f"[{label}] {content}")

    def get_messages(self, lead_id: str) -> List[Any]:
        return self._history(lead_id).messages

    def get_transcript(self, lead_id: str) -> str:
        """Flat text transcript, handy for injecting into a prompt as context."""
        return "\n".join(f"{m.type}: {m.content}" for m in self.get_messages(lead_id))

    def clear(self, lead_id: Optional[str] = None) -> None:
        if lead_id:
            self._histories.pop(lead_id, None)
        else:
            self._histories.clear()





"""
Per-lead conversational memory.

Uses `InMemoryChatMessageHistory` (the modern, maintained replacement for the
deprecated `ConversationBufferMemory`). Each lead gets its own lightweight,
in-RAM message history scoped to a single campaign. Nothing is persisted to
disk and everything is discarded when the campaign's memory store is garbage
collected -- matching the project's "no permanent memory" design goal.

In the API, one `LeadMemoryStore` instance is created per campaign (see
`app/store/campaign_store.py`), not a single global one, so concurrent
campaigns never leak context into each other.
"""