"""
Context policy: which memory sources are attached to a turn.

Previously an LLM call ("context router") decided per message whether to include
long-term memory, profile, files, etc. That cost one extra model call per message,
often returned "no" (silently dropping attached-file context), and contradicted the
spec ("always include recent STM + top-k relevant LTM").

Now every source is always retrieved and *relevance* is decided by similarity
scores (see unified_memory_service), which is cheaper, deterministic and testable.
"""

from pydantic import BaseModel, ConfigDict, Field


class ContextPolicy(BaseModel):
    needs_recent_history: bool
    needs_stm_summary: bool
    needs_file_context: bool
    needs_user_profile: bool
    needs_long_term_memory: bool
    needs_related_conversations: bool
    needs_conversation_metadata: bool

    is_self_contained: bool
    is_topic_shift: bool
    allow_temporary_modes: bool

    confidence: float = Field(ge=0.0, le=1.0)
    reason: str

    model_config = ConfigDict(extra="forbid")


def build_context_policy(*, has_rag_context: bool) -> ContextPolicy:
    """Always-on policy; relevance filtering happens on similarity scores."""
    return ContextPolicy(
        needs_recent_history=True,
        needs_stm_summary=True,
        needs_file_context=has_rag_context,
        needs_user_profile=True,
        needs_long_term_memory=True,
        needs_related_conversations=True,
        needs_conversation_metadata=True,
        is_self_contained=False,
        is_topic_shift=False,
        allow_temporary_modes=False,
        confidence=1.0,
        reason="Always retrieve; filter by similarity threshold.",
    )
