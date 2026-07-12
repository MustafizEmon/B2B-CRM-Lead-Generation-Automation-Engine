"""AI Chain 4 -- Personalized Email Generation (LCEL)."""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence

from app.core.llm import invoke_with_resilience, llm
from app.models.schemas import BuyerPersona, EmailDraft, Lead, SalesStrategy

email_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an elite B2B sales copywriter. Write natural, human, non-hype, non-spammy "
     "outreach emails under 150 words, role-specific and industry-specific, with a soft "
     "CTA. Always include a subject, body, a clear cta, personalization_notes explaining "
     "what you personalized and why, an emotional_tone label, and 2-3 subject_variants."),
    ("human",
     "lead_id: {lead_id}\nname: {name}\nrole: {role}\ncompany: {company}\nindustry: {industry}\n"
     "persona_title: {persona_title}\nrecommended_messaging: {recommended_messaging}\n"
     "value_proposition: {value_proposition}\nurgency_hook: {urgency_hook}"),
])

email_llm = llm.with_structured_output(EmailDraft).bind(max_tokens=2048)
email_chain: RunnableSequence = email_prompt | email_llm


def generate_email(lead: Lead, persona: BuyerPersona, strategy: SalesStrategy) -> EmailDraft:
    payload = {
        "lead_id": lead.lead_id, "name": lead.name, "role": lead.role, "company": lead.company,
        "industry": lead.industry, "persona_title": persona.persona_title,
        "recommended_messaging": persona.recommended_messaging,
        "value_proposition": strategy.value_proposition, "urgency_hook": strategy.urgency_hook,
    }
    return invoke_with_resilience("email_generation", email_chain, payload, max_tokens_estimate=2048)
