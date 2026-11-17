import asyncio
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


def test_tool_identity_args_are_overwritten_with_request_identity():
    # Security: whatever ids the model passes, tools get the real request identity.
    agent = GeneralAgent()
    request_agent = agent._build_request_agent(
        AgentContext(user_id="real-user", conversation_id="real-conv", user_message="x"),
        "gemini-3.1-flash-lite",
    )
    forged = {"user_id": "attacker", "conversation_id": "other-conv", "query": "secrets"}
    tool = type("T", (), {"name": "search_files"})()

    result = asyncio.run(request_agent.before_tool_callback(tool, forged, None))

    assert result is None  # proceed with the call
    assert forged == {"user_id": "real-user", "conversation_id": "real-conv", "query": "secrets"}


def test_agents_get_least_privilege_tool_views():
    from app.agent_layer.tools.mcp_registry import AGENT_TOOLS

    assert "read_file" not in AGENT_TOOLS["general"]["files"]
    assert "read_file" in AGENT_TOOLS["document"]["files"]


def test_routing_bookkeeping_turns_are_removed_from_sub_agent_input():
    from types import SimpleNamespace as NS
    from app.agent_layer.core.base import strip_routing_context

    def turn(*texts):
        return NS(role="user", parts=[NS(text=t) for t in texts])

    request = NS(contents=[
        turn("Say hi"),
        turn("For context:", "[root] called tool `transfer_to_agent` with parameters: {'agent_name': 'general'}"),
        turn("For context:", "[root] `transfer_to_agent` tool returned result: {'result': None}"),
        turn("For context:", "[code] said something unrelated"),  # not routing: kept
    ])
    strip_routing_context(None, request)
    assert [[p.text for p in c.parts][0] for c in request.contents] == ["Say hi", "For context:"]
    assert "transfer_to_agent" not in str([p.text for c in request.contents for p in c.parts])


def test_quota_retry_delay_parses_provider_hint():
    from app.agent_layer.core.base import quota_retry_delay

    assert quota_retry_delay(Exception("429 RESOURCE_EXHAUSTED {'retryDelay': '12s'}")) == 12.5
    assert quota_retry_delay(Exception("Rate limited, please retry in 3.2 s")) is None  # no 429 marker
    assert quota_retry_delay(Exception("429 Too Many Requests, retry in 3.2s")) == 3.7
    assert quota_retry_delay(Exception("429 RESOURCE_EXHAUSTED")) == 10.0  # no hint: default
    assert quota_retry_delay(Exception("503 UNAVAILABLE")) is None
