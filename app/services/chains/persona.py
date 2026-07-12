"""AI Chain 2 -- Buyer Persona Generation (LCEL)."""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence

from app.core.llm import invoke_with_resilience, llm
from app.models.schemas import BuyerPersona, Lead, LeadScore

persona_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an expert B2B buyer-persona strategist. Build a rich, realistic persona "
     "for the described lead."),
    ("human",
     "lead_id: {lead_id}\nname: {name}\nrole: {role}\ncompany: {company}\n"
     "industry: {industry}\ncompany_size: {company_size}\n"
     "lead_score: {score}\npriority: {priority}"),
])

persona_llm = llm.with_structured_output(BuyerPersona).bind(max_tokens=3072)
persona_chain: RunnableSequence = persona_prompt | persona_llm


def generate_persona(lead: Lead, score: LeadScore) -> BuyerPersona:
    payload = {**lead.model_dump(), "score": score.score, "priority": score.priority}
    return invoke_with_resilience("buyer_persona", persona_chain, payload, max_tokens_estimate=3072)
