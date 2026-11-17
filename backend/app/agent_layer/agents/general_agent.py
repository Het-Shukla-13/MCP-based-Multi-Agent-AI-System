from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext
from app.prompts import load_prompt


class GeneralAgent(BaseAgent):

    name = "general"
    label = "General Assistant"
    description = (
        "Default conversational agent: greetings, small talk, general questions, explanations and anything that does not clearly fit another agent."
    )

    def _build_adk_agent(self) -> LlmAgent:
        return LlmAgent(
            name="general",
            model=settings.AGENT_MODEL,
            instruction=load_prompt("agents/general"),
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message