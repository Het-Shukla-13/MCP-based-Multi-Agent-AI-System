from abc import ABC, abstractmethod
import logging
from time import perf_counter

from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from app.agent_layer.schemas import AgentContext, AgentResponse
from app.agent_layer.tools.registry import tool_registry
from app.core.config import settings

logger = logging.getLogger(__name__)

APP_NAME = "agent_system"


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

    The only shared object is ``session_service``. It stores ADK chat history
    keyed by (user_id, conversation_id), so different conversations never mix.
    """

    name: str
    description: str = ""
    tools: list[str] = []

    def __init__(self):
        # ADK session store (history per user+conversation).
        # Will be replaced by our DB-backed history in feature/agent-context-wiring.
        self.session_service = InMemorySessionService()

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
        return f"""
{base_instruction}

--- BACKGROUND CONTEXT (Do not explicitly mention this context unless relevant) ---

MEMORY (STM):
{context.stm_context}

LONG TERM MEMORY (LTM):
{context.ltm_context}

USER PROFILE:
{context.profile_context}

RAG CONTEXT:
{context.rag_context}

CONVERSATION METADATA:
{context.conversation_metadata}
"""

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        """True for 429 / RESOURCE_EXHAUSTED / quota errors."""
        exc_str = str(exc).lower()
        return "429" in exc_str or "resource_exhausted" in exc_str or "quota" in exc_str

    def _build_request_agent(self, context: AgentContext, model: str) -> LlmAgent:
        """Fresh LlmAgent for one request: base agent + compiled instruction + model."""
        adk_agent = self._build_adk_agent()
        compiled_instruction = self._compile_system_instruction(adk_agent.instruction, context)
        # An instruction *provider* (callable) stops ADK from treating {...} in our
        # context text as session-state placeholders.
        adk_agent.instruction = lambda _ctx, text=compiled_instruction: text
        adk_agent.model = model
        return adk_agent

    async def _ensure_session(self, context: AgentContext) -> None:
        session = await self.session_service.get_session(
            app_name=APP_NAME,
            user_id=context.user_id,
            session_id=context.conversation_id,
        )
        if session is None:
            await self.session_service.create_session(
                app_name=APP_NAME,
                user_id=context.user_id,
                session_id=context.conversation_id,
            )

    async def _run_with_model(self, context: AgentContext, prompt: str, model: str) -> str:
        """Run one ADK turn on `model` without blocking the event loop."""
        started_at = perf_counter()
        logger.info(
            "Agent run START | agent=%s | model=%s | user_id=%s | conversation_id=%s | prompt_chars=%d",
            self.name, model, context.user_id, context.conversation_id, len(prompt),
        )

        await self._ensure_session(context)
        runner = Runner(
            agent=self._build_request_agent(context, model),
            session_service=self.session_service,
            app_name=APP_NAME,
        )

        final_text = ""
        # run_async yields events while awaiting the model, so other requests keep
        # being served. (The old sync runner.run() froze the whole server.)
        async for event in runner.run_async(
            user_id=context.user_id,
            session_id=context.conversation_id,
            new_message=Content(role="user", parts=[Part.from_text(text=prompt)]),
        ):
            # Read text Parts directly; str(event.content) would leak the object repr.
            content = getattr(event, "content", None)
            for part in getattr(content, "parts", None) or []:
                text = getattr(part, "text", None)
                if text:
                    final_text += text

        logger.info(
            "Agent run END | agent=%s | model=%s | duration_s=%s | response_chars=%d",
            self.name, model, round(perf_counter() - started_at, 3), len(final_text),
        )
        return final_text

    async def run(self, context: AgentContext) -> AgentResponse:
        context = await self.prepare_context(context)
        prompt = self.build_prompt(context)
        primary_model = settings.AGENT_MODEL

        logger.info(
            "Agent dispatch | agent=%s | model=%s | selected_agent=%s",
            self.name, primary_model, context.selected_agent,
        )

        try:
            final_text = await self._run_with_model(context, prompt, primary_model)
        except Exception as primary_exc:
            fallback_model = settings.AGENT_FALLBACK_MODEL
            if not (self._is_quota_error(primary_exc) and fallback_model):
                raise
            logger.warning(
                "Agent '%s' hit quota on '%s'. Falling back to '%s'. error=%s",
                self.name, primary_model, fallback_model, primary_exc,
            )
            # Fallback uses its own fresh agent object; nothing shared is mutated.
            final_text = await self._run_with_model(context, prompt, fallback_model)

        return AgentResponse(
            content=final_text.strip(),
            agent_name=self.name,
            selected_agent=context.selected_agent,
        )

    async def execute_tool(self, tool_name: str, **kwargs):
        tool = tool_registry.get(tool_name)
        return await tool.execute(**kwargs)

    async def prepare_context(self, context: AgentContext) -> AgentContext:
        return context
