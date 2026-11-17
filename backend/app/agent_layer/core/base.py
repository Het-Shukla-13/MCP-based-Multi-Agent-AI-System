from abc import ABC, abstractmethod
import asyncio
import logging
import re
from time import perf_counter

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from collections.abc import Awaitable, Callable
from typing import Any

from app.agent_layer.core.confirmation import (
    current_confirmer,
    needs_confirmation,
    preview_args,
    tool_response_for,
)
from app.agent_layer.schemas import AgentContext, AgentResponse
from app.agent_layer.tools.mcp_registry import IDENTITY_ARGS, get_toolsets_for_agent
from app.core.config import settings
from app.services.metrics.collector import current_turn, observe_adk_event

logger = logging.getLogger(__name__)

APP_NAME = "agent_system"

StatusCallback = Callable[[dict], Awaitable[None]]

_RETRYABLE_MARKERS = ("429", "resource_exhausted", "quota", "500", "503", "unavailable",
                      "overloaded", "high demand", "internal error", "deadline")


MAX_QUOTA_WAIT_SECONDS = 20.0


def quota_retry_delay(exc: Exception) -> float | None:
    """
    For a rate-limit (429 / RESOURCE_EXHAUSTED) error, the delay the provider asks for,
    e.g. "'retryDelay': '12s'" or "retry in 12.3s". None if not a rate limit.
    Free tiers limit requests PER MINUTE, so a short wait usually succeeds.
    """
    text = str(exc)
    if "429" not in text and "resource_exhausted" not in text.lower():
        return None
    match = re.search(r"retryDelay'?\"?:\s*'?\"?(\d+(?:\.\d+)?)s", text) or re.search(r"retry in (\d+(?:\.\d+)?)\s*s", text, re.I)
    return float(match.group(1)) + 0.5 if match else 10.0


async def wait_for_quota(exc: Exception, on_status: "StatusCallback | None", agent: str) -> bool:
    """Wait out a short rate-limit window (telling the UI). False if not worth waiting."""
    delay = quota_retry_delay(exc)
    if delay is None or delay > MAX_QUOTA_WAIT_SECONDS:
        return False
    logger.warning("All models rate-limited; waiting %.1fs before one retry", delay)
    await emit_status(on_status, {"status": "waiting", "agent": agent, "seconds": round(delay)})
    await asyncio.sleep(delay)
    return True


def is_retryable_provider_error(exc: Exception) -> bool:
    """Rate limits AND temporary provider outages (e.g. Gemini 503 'high demand')
    deserve a retry on the fallback model; bugs in our own request do not."""
    text = str(exc).lower()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


async def emit_status(on_status: StatusCallback | None, event: dict) -> None:
    if on_status is None:
        return
    try:
        await on_status(event)
    except Exception:  # a closed socket must never break the turn
        logger.warning("Status callback failed", exc_info=True)


_GENERATED_ID = re.compile(r"generated_file_id['\"]?\s*[:=]\s*['\"]?([0-9a-f-]{36})")


def collect_generated_files(event: Any, found: list[str]) -> None:
    """Tool results that created files carry 'generated_file_id: <uuid>'; remember them."""
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        response = getattr(part, "function_response", None)
        if response is not None:
            for file_id in _GENERATED_ID.findall(str(response.response)):
                if file_id not in found:
                    found.append(file_id)


def run_config() -> RunConfig:
    """SSE streaming: ADK yields partial text events, then one final complete event."""
    mode = StreamingMode.SSE if settings.STREAMING_ENABLED else StreamingMode.NONE
    return RunConfig(streaming_mode=mode)


def event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    return "".join(getattr(p, "text", None) or "" for p in (getattr(content, "parts", None) or []))


async def emit_text_delta(on_status: StatusCallback | None, event: Any) -> None:
    """Forward a streamed text piece. Partial events carry NEW text only."""
    if getattr(event, "partial", False):
        text = event_text(event)
        if text:
            await emit_status(on_status, {"status": "delta", "agent": event.author, "text": text})


def _is_routing_bookkeeping(content: Any) -> bool:
    """ADK's 'For context: [root] ... transfer_to_agent ...' turns (see strip_routing_context)."""
    texts = [getattr(p, "text", None) or "" for p in (getattr(content, "parts", None) or [])]
    return bool(texts) and texts[0].strip() == "For context:" and any("transfer_to_agent" in t for t in texts)


def strip_routing_context(callback_context: Any, llm_request: Any) -> None:
    """
    before_model_callback for sub-agents.

    After the root delegates, ADK appends the root's transfer_to_agent call and result
    to the sub-agent's input as extra USER turns ("For context: [root] called tool
    transfer_to_agent ..."). The model sees them as things the user said and sometimes
    repeats them in the reply. They carry no information for the answer, so drop them.
    Returning None lets the (edited) request proceed.
    """
    llm_request.contents = [c for c in llm_request.contents if not _is_routing_bookkeeping(c)]
    return None


async def emit_tool_events(on_status: StatusCallback | None, event: Any) -> None:
    """Report MCP tool calls (not ADK's internal transfer_to_agent) as status events."""
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        call = getattr(part, "function_call", None)
        if call is not None and call.name != "transfer_to_agent":
            await emit_status(on_status, {"status": "tool", "agent": event.author, "tool": call.name})


class BaseAgent(ABC):
    """
    ADK-backed base agent.

    Concurrency model
    -----------------
    One instance of each agent class is shared by every user, so the instance
    must hold NO per-request state. For every request we build a fresh ADK
    ``LlmAgent`` (instruction + model for *this* request) and a fresh ``Runner``.
    Both are cheap Python objects; nothing shared is mutated, so concurrent
    users can never see each other's memory/RAG/profile context.

    History comes from OUR database (``context.history``), not from ADK's session
    store: each request gets a throwaway in-memory session. So history survives
    restarts, is shared by all agents (switching agents keeps context) and is
    token-bounded by the STM window.
    """

    name: str
    label: str = ""
    # Shown to the root agent's model by ADK: this text IS the routing criterion.
    description: str = ""

    @abstractmethod
    def _build_adk_agent(self) -> LlmAgent:
        """
        Return a NEW LlmAgent with this agent's name, model and base instruction.
        Called once per request, so it must not return a cached instance.
        """

    @abstractmethod
    def build_prompt(self, context: AgentContext) -> str:
        """Convert the agent context into the user-turn prompt string."""

    def _compile_system_instruction(self, base_instruction: str, context: AgentContext) -> str:
        """
        Inject per-request context into the system instruction (not the chat
        history), so ADK doesn't duplicate it into every stored turn.
        """
        sections = [
            ("SUMMARY OF EARLIER CONVERSATION", context.stm_context),
            ("RECENT CONVERSATION (oldest first)", self._render_history(context)),
            ("RELEVANT LONG-TERM MEMORY", context.ltm_context),
            ("USER PROFILE", context.profile_context),
            ("RELATED PAST CONVERSATIONS", context.related_conversations_context),
            ("ATTACHED FILE CONTEXT", context.rag_context),
            ("CONVERSATION METADATA", str(context.conversation_metadata or "")),
        ]
        body = "\n\n".join(
            f"{title}:\n{text.strip()}" for title, text in sections if text and text.strip()
        )
        if not body:
            return base_instruction
        return (
            f"{base_instruction}\n\n"
            "--- BACKGROUND CONTEXT (use when relevant; do not mention it explicitly) ---\n\n"
            f"{body}"
        )

    @staticmethod
    def _render_history(context: AgentContext) -> str:
        return "\n".join(f"{m.role.upper()}: {m.content}" for m in context.history)

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        return is_retryable_provider_error(exc)

    def _build_request_agent(self, context: AgentContext, model: str) -> LlmAgent:
        """Fresh LlmAgent for one request: base agent + compiled instruction + model."""
        adk_agent = self._build_adk_agent()
        compiled_instruction = self._compile_system_instruction(adk_agent.instruction, context)
        # An instruction *provider* (callable) stops ADK from treating {...} in our
        # context text as session-state placeholders.
        adk_agent.instruction = lambda _ctx, text=compiled_instruction: text
        adk_agent.model = model
        adk_agent.description = self.description
        # When used as a sub-agent of the root: answer, don't bounce the request
        # back to the root or sideways to another agent.
        adk_agent.disallow_transfer_to_parent = True
        adk_agent.disallow_transfer_to_peers = True

        # MCP tools for this agent (least-privilege view of shared servers).
        adk_agent.tools = list(get_toolsets_for_agent(self.name))
        adk_agent.before_tool_callback = self._identity_injector(context)
        adk_agent.before_model_callback = strip_routing_context
        return adk_agent

    def _identity_injector(self, context: AgentContext):
        """
        Never trust identifiers chosen by the model: a prompt-injected document could
        ask a tool to read another user's files. Overwrite them with the real request
        identity before EVERY tool call.
        """
        identity = {"user_id": context.user_id, "conversation_id": context.conversation_id}

        async def before_tool(tool, args: dict, tool_context):
            for key in IDENTITY_ARGS:
                if key in args or key in identity:
                    args[key] = identity[key]
            logger.info("Tool call | agent=%s | tool=%s | args=%s", self.name, tool.name,
                        {k: v for k, v in args.items() if k not in IDENTITY_ARGS})
            # Side-effect tools wait for the user (approve / reject / revise) when a
            # human is connected; the returned dict, if any, replaces the tool result.
            confirmer = current_confirmer.get()
            if confirmer is not None and needs_confirmation(tool.name):
                call_id = getattr(tool_context, "function_call_id", None) or ""
                decision = await confirmer(self.name, tool.name, preview_args(args, IDENTITY_ARGS), call_id)
                logger.info("Tool confirmation | agent=%s | tool=%s | decision=%s",
                            self.name, tool.name, decision.action)
                return tool_response_for(tool.name, decision)
            return None  # None = proceed with the (patched) call

        return before_tool


    async def _run_with_model(
        self,
        context: AgentContext,
        prompt: str,
        model: str,
        on_status: StatusCallback | None = None,
        generated_files: list[str] | None = None,
    ) -> str:
        """Run one ADK turn on `model` without blocking the event loop."""
        started_at = perf_counter()
        logger.info(
            "Agent run START | agent=%s | model=%s | user_id=%s | conversation_id=%s | prompt_chars=%d",
            self.name, model, context.user_id, context.conversation_id, len(prompt),
        )

        # Throwaway session: ADK needs one to run, but our DB is the history.
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name=APP_NAME, user_id=context.user_id)
        runner = Runner(
            agent=self._build_request_agent(context, model),
            session_service=session_service,
            app_name=APP_NAME,
        )

        final_text = ""
        # run_async yields events while awaiting the model, so other requests keep
        # being served. (The old sync runner.run() froze the whole server.)
        async for event in runner.run_async(
            user_id=context.user_id,
            session_id=session.id,
            new_message=Content(role="user", parts=[Part.from_text(text=prompt)]),
            run_config=run_config(),
        ):
            observe_adk_event(event, model)  # metrics: tokens, tool timings, first token
            await emit_tool_events(on_status, event)
            await emit_text_delta(on_status, event)
            if generated_files is not None:
                collect_generated_files(event, generated_files)
            # Final text from NON-partial events only: in streaming mode the last
            # event repeats the whole text, so adding partials too would double it.
            if not getattr(event, "partial", False):
                final_text += event_text(event)

        logger.info(
            "Agent run END | agent=%s | model=%s | duration_s=%s | response_chars=%d",
            self.name, model, round(perf_counter() - started_at, 3), len(final_text),
        )
        return final_text

    async def run(self, context: AgentContext, on_status: StatusCallback | None = None) -> AgentResponse:
        context = await self.prepare_context(context)
        prompt = self.build_prompt(context)
        primary_model = settings.AGENT_MODEL

        logger.info(
            "Agent dispatch | agent=%s | model=%s | selected_agent=%s",
            self.name, primary_model, context.selected_agent,
        )

        try:
            generated: list[str] = []
            final_text = await self._run_with_model(context, prompt, primary_model, on_status, generated)
        except Exception as primary_exc:
            fallback_model = settings.AGENT_FALLBACK_MODEL
            if not (is_retryable_provider_error(primary_exc) and fallback_model):
                raise
            logger.warning(
                "Agent '%s' failed on '%s' (retryable). Falling back to '%s'. error=%s",
                self.name, primary_model, fallback_model, primary_exc,
            )
            turn = current_turn.get()
            if turn is not None:
                turn.fallback_used = True
            # Fallback uses its own fresh agent object; nothing shared is mutated.
            generated = []
            try:
                final_text = await self._run_with_model(context, prompt, fallback_model, on_status, generated)
            except Exception as fallback_exc:
                # Both models rate-limited in the same minute: wait the provider's
                # suggested delay (if short) and retry the fallback once.
                if not await wait_for_quota(fallback_exc, on_status, self.name):
                    raise
                generated = []
                final_text = await self._run_with_model(context, prompt, fallback_model, on_status, generated)

        return AgentResponse(
            content=final_text.strip(),
            agent_name=self.name,
            selected_agent=context.selected_agent,
            generated_file_ids=generated,
        )

    async def prepare_context(self, context: AgentContext) -> AgentContext:
        return context
