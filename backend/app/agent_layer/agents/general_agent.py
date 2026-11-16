from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext


class GeneralAgent(BaseAgent):

    name = "general"

    def _build_adk_agent(self) -> LlmAgent:
        return LlmAgent(
            name="general",
            model=settings.AGENT_MODEL,
            instruction="""
You are a General Assistant.

You handle:
- conversations
- explanations
- general reasoning
- fallback queries

You MUST use provided context if present.
""",
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message