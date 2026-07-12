"""AI Chain 3 -- Sales Strategy Generator (LCEL)."""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence

from app.core.llm import invoke_with_resilience, llm
from app.models.schemas import BuyerPersona, Lead, SalesStrategy

strategy_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a B2B sales strategy consultant. Given a lead and their buyer persona, "
     "craft a concrete sales strategy."),
    ("human",
     "lead_id: {lead_id}\ncompany: {company}\nindustry: {industry}\nrole: {role}\n"
     "persona_title: {persona_title}\npain_points: {pain_points}\nobjections: {objections}"),
])

strategy_llm = llm.with_structured_output(SalesStrategy).bind(max_tokens=3072)
strategy_chain: RunnableSequence = strategy_prompt | strategy_llm


def generate_strategy(lead: Lead, persona: BuyerPersona) -> SalesStrategy:
    payload = {
        "lead_id": lead.lead_id, "company": lead.company, "industry": lead.industry,
        "role": lead.role, "persona_title": persona.persona_title,
        "pain_points": persona.pain_points, "objections": persona.objections,
    }
    return invoke_with_resilience("sales_strategy", strategy_chain, payload, max_tokens_estimate=3072)
