"""
CRM lifecycle state machine -- tracks each lead's progress through:

    NEW -> VALIDATED -> SCORED -> ENRICHED -> CONTACTED -> REPLIED -> CONVERTED \-> LOST
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd

from app.models.enums import LifecycleStage
from app.models.schemas import LeadLifecycleState

logger = logging.getLogger("crm_ai.state_machine")

VALID_TRANSITIONS: Dict[LifecycleStage, List[LifecycleStage]] = {
    LifecycleStage.NEW: [LifecycleStage.VALIDATED, LifecycleStage.LOST],
    LifecycleStage.VALIDATED: [LifecycleStage.SCORED, LifecycleStage.LOST],
    LifecycleStage.SCORED: [LifecycleStage.ENRICHED, LifecycleStage.LOST],
    LifecycleStage.ENRICHED: [LifecycleStage.CONTACTED, LifecycleStage.LOST],
    LifecycleStage.CONTACTED: [LifecycleStage.REPLIED, LifecycleStage.LOST],
    LifecycleStage.REPLIED: [LifecycleStage.CONVERTED, LifecycleStage.LOST],
    LifecycleStage.CONVERTED: [],
    LifecycleStage.LOST: [],
}


class CRMStateMachine:
    """Tracks lifecycle state for every lead in a single campaign (in-memory only)."""

    def __init__(self) -> None:
        self._states: Dict[str, LeadLifecycleState] = {}

    def register(self, lead_id: str) -> LeadLifecycleState:
        state = LeadLifecycleState(lead_id=lead_id)
        self._states[lead_id] = state
        return state

    def transition(self, lead_id: str, target: LifecycleStage) -> LeadLifecycleState:
        state = self._states.setdefault(lead_id, LeadLifecycleState(lead_id=lead_id))
        allowed = VALID_TRANSITIONS.get(state.stage, [])
        if target not in allowed and target != state.stage:
            logger.warning("Illegal transition for %s: %s -> %s (forcing anyway, flagging)",
                            lead_id, state.stage, target)
        state.advance(target)
        return state

    def get(self, lead_id: str) -> Optional[LeadLifecycleState]:
        return self._states.get(lead_id)

    def as_dataframe(self) -> pd.DataFrame:
        rows = [{"lead_id": s.lead_id, "stage": s.stage.value, "history": " -> ".join(s.history)}
                for s in self._states.values()]
        return pd.DataFrame(rows)
