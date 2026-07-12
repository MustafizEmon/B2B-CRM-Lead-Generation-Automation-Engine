"""Response classifier chain -- memory-aware (logs into the campaign's LeadMemoryStore)."""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence

from app.core.llm import invoke_with_resilience, llm
from app.core.memory import LeadMemoryStore
from app.models.schemas import EmailResponse

response_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a CRM response-classification engine. Classify the lead's reply into exactly "
     "one category from: interested, not_interested, meeting_requested, need_more_info, "
     "out_of_office, unsubscribe, spam, bounce, unknown. Also assess sentiment, urgency, "
     "lead temperature (cold/warm/hot), required action, and recommended next step."),
    ("human", "lead_id: {lead_id}\nreply_text: {reply_text}"),
])

response_llm = llm.with_structured_output(EmailResponse)
response_chain: RunnableSequence = response_prompt | response_llm


def classify_response(lead_id: str, reply_text: str, memory: LeadMemoryStore) -> EmailResponse:
    memory.log_human_event(lead_id, "REPLY", reply_text)
    result = invoke_with_resilience(
        "response_classifier", response_chain, {"lead_id": lead_id, "reply_text": reply_text}
    )
    memory.log_ai_event(
        lead_id, "CLASSIFICATION",
        f"{result.classification} | temperature={result.lead_temperature} | urgency={result.urgency}",
    )
    return result
