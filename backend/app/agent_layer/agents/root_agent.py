"""
Root agent: real ADK multi-agent delegation.

Each request builds a fresh tree:

    root (ROUTER_MODEL, no answering, only routing)
     ├── general   ┐
     ├── code      │  per-request LlmAgents with this user's context
     ├── data      │  (BaseAgent._build_request_agent)
     ├── research  │
     ├── document  │
     └── image     ┘

ADK gives the root a built-in `transfer_to_agent(agent_name)` tool and lists each
sub-agent's `description` in its prompt. The root's model picks one, ADK hands the
turn over, and the sub-agent answers. Every ADK event has an `author`, which tells
us which agent produced the reply.

An explicit @mention skips the root entirely (one model call instead of two).
"""

import logging
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from app.agent_layer.agents.code_agent import CodeAgent
from app.agent_layer.agents.data_agent import DataAgent
from app.agent_layer.agents.document_agent import DocumentAgent
from app.agent_layer.agents.general_agent import GeneralAgent
from app.agent_layer.agents.image_agent import ImageAgent
from app.agent_layer.agents.research_agent import ResearchAgent
from app.agent_layer.core import agent_registry
from app.agent_layer.core.base import (
    APP_NAME,
    BaseAgent,
    StatusCallback,
    collect_generated_files,
    emit_status,
    emit_text_delta,
    run_config,
    emit_tool_events,
    is_retryable_provider_error,
)
from app.agent_layer.schemas import AgentContext, AgentResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

ROOT_NAME = "root"
DEFAULT_AGENT = "general"
ROUTER_HISTORY_MESSAGES = 4


for _agent_cls in (GeneralAgent, CodeAgent, DataAgent, ResearchAgent, DocumentAgent, ImageAgent):
    if not agent_registry.exists(_agent_cls.name):
        agent_registry.register(_agent_cls())


class AgentExecutionError(Exception):
    """All models failed for this turn; carries the agent that was handling it."""

    def __init__(self, agent_name: str, cause: Exception):
        super().__init__(f"{agent_name} agent failed: {cause}")
        self.agent_name = agent_name
        self.cause = cause


def _router_instruction(context: AgentContext, agents: list[BaseAgent]) -> str:
    recent = "\n".join(
        f"{m.role.upper()}: {m.content[:300]}" for m in context.history[-ROUTER_HISTORY_MESSAGES:]
    )
    names = ", ".join(a.name for a in agents)
    return f"""You are the ROUTER of a multi-agent assistant. You never answer the user yourself.
For every message, call transfer_to_agent with exactly one of: {names}.

Rules:
- Pick the agent whose description best matches what the user is asking for NOW.
- Follow-ups ("and?", "make it shorter", "add type hints") belong to the agent that
  handled the previous turn: {context.previous_agent}.
- Greetings, small talk and anything unclear go to {DEFAULT_AGENT}.
- Attached files: code files -> code, CSV/XLSX -> data, PDF/DOCX -> document, images -> image.

Recent conversation (for follow-up detection only):
{recent or "(none)"}
"""


class RootAgent:

    @property
    def valid_agents(self) -> set[str]:
        return set(agent_registry.list_agents())

    async def run(
        self,
        context: AgentContext,
        on_status: StatusCallback | None = None,
    ) -> AgentResponse:
        async def emit(event: dict) -> None:
            await emit_status(on_status, event)

        # 1) Explicit selection (@mention or UI pick): run that agent directly.
        if context.selected_agent and context.selected_agent in self.valid_agents:
            agent = agent_registry.get(context.selected_agent)
            logger.info("Agent selection | mode=explicit | agent=%s", agent.name)
            await emit({"status": "working", "agent": agent.name, "mode": "explicit"})
            try:
                return await agent.run(context, on_status=on_status)
            except Exception as exc:
                raise AgentExecutionError(agent.name, exc) from exc

        # 2) ADK delegation through the root agent (primary models, then fallbacks).
        await emit({"status": "routing", "agent": ROOT_NAME})
        attempts = [(settings.ROUTER_MODEL, settings.AGENT_MODEL)]
        if settings.ROUTER_FALLBACK_MODEL or settings.AGENT_FALLBACK_MODEL:
            attempts.append(
                (settings.ROUTER_FALLBACK_MODEL or settings.ROUTER_MODEL,
                 settings.AGENT_FALLBACK_MODEL or settings.AGENT_MODEL)
            )

        last_exc: Exception | None = None
        for router_model, agent_model in attempts:
            try:
                return await self._delegate(context, router_model, agent_model, emit, on_status)
            except Exception as exc:
                last_exc = exc
                if not is_retryable_provider_error(exc):
                    break
                logger.warning("Delegation failed on %s/%s (retryable); trying fallbacks", router_model, agent_model)
        raise AgentExecutionError(ROOT_NAME, last_exc)

    async def _delegate(self, context, router_model, agent_model, emit, on_status) -> AgentResponse:
        agents = [agent_registry.get(name) for name in agent_registry.list_agents()]
        root = LlmAgent(
            name=ROOT_NAME,
            model=router_model,
            description="Routes each user message to the best specialised agent.",
            instruction=lambda _ctx, text=_router_instruction(context, agents): text,
            sub_agents=[a._build_request_agent(context, agent_model) for a in agents],
        )

        session_service = InMemorySessionService()  # throwaway; our DB is the history
        session = await session_service.create_session(app_name=APP_NAME, user_id=context.user_id)
        runner = Runner(agent=root, session_service=session_service, app_name=APP_NAME)

        answered_by: str | None = None
        transferred_to: str | None = None
        texts: dict[str, str] = {}
        generated: list[str] = []

        async for event in runner.run_async(
            user_id=context.user_id,
            session_id=session.id,
            new_message=Content(role="user", parts=[Part.from_text(text=context.user_message)]),
            run_config=run_config(),
        ):
            await emit_tool_events(on_status, event)
            if event.author != ROOT_NAME:  # never stream the router's own text
                await emit_text_delta(on_status, event)
            collect_generated_files(event, generated)
            if getattr(event, "partial", False):
                continue  # final text comes from the complete (non-partial) events
            parts = (event.content.parts if event.content and event.content.parts else [])
            for part in parts:
                call = getattr(part, "function_call", None)
                if call is not None and call.name == "transfer_to_agent":
                    transferred_to = (call.args or {}).get("agent_name")
                    await emit({"status": "working", "agent": transferred_to, "mode": "routed"})
                text = getattr(part, "text", None)
                if text:
                    texts[event.author] = texts.get(event.author, "") + text
                    if event.author != ROOT_NAME:
                        answered_by = event.author

        if answered_by is None:
            # The router answered itself or transferred nowhere: let General answer.
            logger.warning("Root did not delegate (transfer=%s); falling back to %s", transferred_to, DEFAULT_AGENT)
            await emit({"status": "working", "agent": DEFAULT_AGENT, "mode": "fallback"})
            context.selected_agent = DEFAULT_AGENT
            return await agent_registry.get(DEFAULT_AGENT).run(context, on_status=on_status)

        logger.info("Agent selection | mode=adk_delegation | router=%s | agent=%s", router_model, answered_by)
        return AgentResponse(
            content=texts[answered_by].strip(),
            agent_name=answered_by,
            selected_agent=answered_by,
            generated_file_ids=generated,
        )
