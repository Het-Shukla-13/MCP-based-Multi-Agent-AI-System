from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.agents.general_agent import GeneralAgent
from app.agent_layer.schemas import AgentContext, HistoryMessage


def _ctx(**kwargs) -> AgentContext:
    return AgentContext(user_id="u", conversation_id="c", user_message="next question", **kwargs)


def test_instruction_includes_db_history_in_order():
    agent = GeneralAgent()
    ctx = _ctx(history=[
        HistoryMessage(role="user", content="My project uses FastAPI."),
        HistoryMessage(role="assistant", content="Got it, FastAPI."),
    ])
    text = agent._compile_system_instruction("BASE", ctx)

    assert "RECENT CONVERSATION" in text
    assert text.index("USER: My project uses FastAPI.") < text.index("ASSISTANT: Got it, FastAPI.")


def test_instruction_includes_related_conversations_and_files():
    agent = GeneralAgent()
    text = agent._compile_system_instruction(
        "BASE",
        _ctx(related_conversations_context="Earlier chat about pgvector", rag_context="chunk text"),
    )
    assert "RELATED PAST CONVERSATIONS:\nEarlier chat about pgvector" in text
    assert "ATTACHED FILE CONTEXT:\nchunk text" in text


def test_empty_sections_are_omitted():
    agent = GeneralAgent()
    assert agent._compile_system_instruction("BASE", _ctx()) == "BASE"


def test_request_agent_is_fresh_and_does_not_touch_shared_state():
    agent = GeneralAgent()
    a = agent._build_request_agent(_ctx(profile_context="secret A"), "gemini-3.1-flash-lite")
    b = agent._build_request_agent(_ctx(profile_context="secret B"), "gemini-3.1-flash-lite")

    assert isinstance(a, LlmAgent) and a is not b
    assert "secret A" in a.instruction(None) and "secret B" in b.instruction(None)
