"""
Domain models -- a direct, 1:1 port of the Pydantic models. These are used both as LLM structured-output schemas 
(via `llm.with_structured_output(Model)`) and as the internal data contracts
passed between pipeline stages, so keep them here rather than duplicating
shapes in the API layer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import LifecycleStage


class Lead(BaseModel):
    lead_id: str
    name: str
    email: EmailStr
    company: str
    role: str
    industry: str
    company_size: str
    website: Optional[str] = None

    @field_validator("company_size")
    @classmethod
    def normalize_size(cls, v: str) -> str:
        v = v.strip().lower()
        mapping = {"small": "1-50", "medium": "51-500", "large": "501-5000", "enterprise": "5000+"}
        return mapping.get(v, v)


class LeadValidationResult(BaseModel):
    lead_id: str
    is_valid: bool
    reasons: List[str] = Field(default_factory=list)


class LeadScore(BaseModel):
    lead_id: str
    # Declared as float, not int: Groq's structured-output mode validates the model's
    # tool-call arguments against the JSON schema *before* Pydantic ever sees them --
    # if the schema says "integer" and the model reasons its way to a half-point score
    # (e.g. 6.5), the API call itself fails with a 400 error. Accepting float and
    # rounding after the fact avoids that failure mode while still giving a clean
    # whole-number score downstream.
    score: float = Field(ge=1, le=10, description="Whole-number lead score from 1-10.")
    priority: Literal["High", "Medium", "Low"]
    reasoning: str
    conversion_probability: float = Field(ge=0.0, le=1.0)
    buying_intent_level: Literal["Low", "Medium", "High", "Very High"]

    @field_validator("score", mode="after")
    @classmethod
    def round_score(cls, v: float) -> float:
        return float(round(v))


class BuyerPersona(BaseModel):
    lead_id: str
    persona_title: str
    pain_points: List[str]
    goals: List[str]
    motivations: List[str]
    objections: List[str]
    decision_style: str
    communication_style: str
    triggers: List[str]
    risk_factors: List[str]
    recommended_messaging: str
    sales_strategy: str


class SalesStrategy(BaseModel):
    lead_id: str
    positioning_strategy: str
    value_proposition: str
    competitor_angle: str
    urgency_hook: str
    objection_handling: str
    closing_strategy: str


class EmailDraft(BaseModel):
    lead_id: str
    subject: str
    body: str
    cta: str
    personalization_notes: str
    emotional_tone: str
    subject_variants: List[str] = Field(default_factory=list)


class EmailResponse(BaseModel):
    lead_id: str
    classification: Literal[
        "interested", "not_interested", "meeting_requested", "need_more_info",
        "out_of_office", "unsubscribe", "spam", "bounce", "unknown",
    ]
    sentiment: str
    urgency: Literal["low", "medium", "high"]
    lead_temperature: Literal["cold", "warm", "hot"]
    action_required: str
    recommended_next_step: str


class FollowUp(BaseModel):
    lead_id: str
    follow_up_email: str
    intent_analysis: str
    urgency_score: float = Field(ge=1, le=10, description="Whole-number urgency score from 1-10.")

    @field_validator("urgency_score", mode="after")
    @classmethod
    def round_urgency(cls, v: float) -> float:
        return float(round(v))


class LeadEnrichment(BaseModel):
    lead_id: str
    persona: Optional[BuyerPersona] = None
    strategy: Optional[SalesStrategy] = None


class LeadLifecycleState(BaseModel):
    lead_id: str
    stage: LifecycleStage = LifecycleStage.NEW
    history: List[str] = Field(default_factory=lambda: [LifecycleStage.NEW.value])
    timestamps: Dict[str, str] = Field(default_factory=dict)

    def advance(self, stage: LifecycleStage) -> None:
        self.stage = stage
        self.history.append(stage.value)
        self.timestamps[stage.value] = datetime.now(timezone.utc).isoformat()


class SendResult(BaseModel):
    lead_id: str
    status: Literal["sent", "failed", "dry_run"]
    attempts: int
    latency_seconds: float
    error: Optional[str] = None


class ProcessedLead(BaseModel):
    """Everything the pipeline produced for a single lead. This is the shape
    returned by GET /campaigns/{id}/leads/{lead_id} and embedded in the
    campaign-wide leads list."""
    lead: Lead
    score: LeadScore
    persona: BuyerPersona
    strategy: SalesStrategy
    email_draft: EmailDraft
    send_result: Optional[SendResult] = None
    reply_text: Optional[str] = None
    response: Optional[EmailResponse] = None
    follow_up: Optional[FollowUp] = None
    lifecycle_stage: Optional[str] = None
    lifecycle_history: List[str] = Field(default_factory=list)


class CampaignStats(BaseModel):
    total_leads: int = 0
    valid_leads: int = 0
    rejected_leads: int = 0
    emails_sent: int = 0
    emails_failed: int = 0
    high_priority: int = 0
    medium_priority: int = 0
    low_priority: int = 0
    avg_score: float = 0.0
    avg_conversion_probability: float = 0.0
    # --- Outcome / funnel tracking ---
    replies_received: int = 0
    follow_ups_sent: int = 0
    converted: int = 0
    lost: int = 0
    contacted_no_reply: int = 0
    reply_rate: float = 0.0
    conversion_rate: float = 0.0
    follow_up_rate: float = 0.0


class CampaignReport(BaseModel):
    generated_at: str
    stats: CampaignStats
    insights: List[str]
    recommendations: List[str]
