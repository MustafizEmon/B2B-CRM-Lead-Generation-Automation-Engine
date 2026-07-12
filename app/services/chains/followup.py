"""Follow-up generator chain -- uses the full per-lead conversation transcript for context."""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence

from app.core.llm import invoke_with_resilience, llm
from app.core.memory import LeadMemoryStore
from app.models.schemas import FollowUp

followup_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a sales follow-up specialist. Given the full conversation history with this "
     "lead (original outreach, their reply, and any prior stage notes), write a natural "
     "follow-up email, analyze intent, and score urgency 1-10. Use conversation_history for "
     "context and continuity, but write only the new follow-up message itself."),
    ("human",
     "lead_id: {lead_id}\nconversation_history:\n{conversation_history}\n\n"
     "original_email: {original_email}\nreply_text: {reply_text}"),
])

followup_llm = llm.with_structured_output(FollowUp).bind(max_tokens=2048)
followup_chain: RunnableSequence = followup_prompt | followup_llm


def generate_followup(lead_id: str, original_email: str, reply_text: str, memory: LeadMemoryStore) -> FollowUp:
    payload = {
        "lead_id": lead_id,
        "conversation_history": memory.get_transcript(lead_id),
        "original_email": original_email,
        "reply_text": reply_text,
    }
    result = invoke_with_resilience("follow_up", followup_chain, payload, max_tokens_estimate=2048)
    memory.log_ai_event(lead_id, "FOLLOW_UP", result.follow_up_email)
    return result
