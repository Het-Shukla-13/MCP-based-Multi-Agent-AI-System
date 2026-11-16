from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentContext(BaseModel):
    user_id: str
    conversation_id: str
    user_message: str

    # MEMORY LAYER (your system)
    # Recent turns from OUR database (token-limited window, oldest first), excluding
    # the current user message. This, not ADK's session store, is the agent's history.
    history: list[HistoryMessage] = Field(default_factory=list)
    stm_context: str = ""
    ltm_context: str = ""
    profile_context: str = ""

    related_conversations_context: str = ""

    # RAG / FILE CONTEXT
    rag_context: str = ""

    # METADATA
    conversation_metadata: Dict = {}

    # Agent that answered the previous turn. Passed explicitly (not read from
    # conversation_metadata, which the memory router may leave empty) so the
    # LLM router can keep the conversation "sticky" to the current agent.
    previous_agent: str = "general"

    # The agent to route to. If set by the frontend (@mention), it bypasses LLM routing.
    # If None, the LLM selector picks the best agent.
    selected_agent: Optional[str] = Field(
        default=None,
        description="Explicitly selected agent from the frontend @mention. Overrides LLM routing when set."
    )


class AgentResponse(BaseModel):
    selected_agent: Optional[str] = None   # Echo back the agent chosen for this turn
    agent_name: str
    content: Optional[str] = None  # LLM output content
    # Files created by tools during this turn (attached to the assistant message).
    generated_file_ids: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    active_agent: str = "general"
    last_agent: str | None = None