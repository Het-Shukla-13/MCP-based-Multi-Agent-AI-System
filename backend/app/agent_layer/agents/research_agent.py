from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext
from app.prompts import load_prompt


class ResearchAgent(BaseAgent):

    name = "research"
    label = "Research Agent"
    description = (
        "Research and synthesis: looking up facts, current events, comparisons and structured reports on a topic."
    )
    def _build_adk_agent(self) -> LlmAgent:
        return LlmAgent(
            name="research",
            model=settings.AGENT_MODEL,
            instruction=load_prompt("agents/research"),
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message
