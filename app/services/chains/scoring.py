"""AI Chain 1 -- Lead Scoring (LCEL)."""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence

from app.core.llm import invoke_with_resilience, llm
from app.models.schemas import Lead, LeadScore

lead_scoring_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a senior B2B sales qualification analyst. You evaluate leads on decision "
     "authority, budget power, industry fit, company size, urgency signals, and role relevance."),
    ("human",
     "Evaluate this lead:\n"
     "lead_id: {lead_id}\nname: {name}\nrole: {role}\ncompany: {company}\n"
     "industry: {industry}\ncompany_size: {company_size}\nwebsite: {website}"),
])

# with_structured_output() forces the response into the LeadScore schema via the
# provider's native tool-calling / JSON-schema mode, instead of hoping the model
# follows a text instruction -- eliminates "missing required field" parse failures.
lead_scoring_llm = llm.with_structured_output(LeadScore)
lead_scoring_chain: RunnableSequence = lead_scoring_prompt | lead_scoring_llm


def score_lead(lead: Lead) -> LeadScore:
    payload = lead.model_dump()
    return invoke_with_resilience("lead_scoring", lead_scoring_chain, payload)
