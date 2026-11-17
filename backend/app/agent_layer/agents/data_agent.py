from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext
from app.prompts import load_prompt


class DataAgent(BaseAgent):

    name = "data"
    label = "Data Agent"
    description = (
        "Analysis of tabular data: CSV/Excel files, statistics, aggregations, trends, charts and pandas/SQL questions."
    )

    def _build_adk_agent(self) -> LlmAgent:
        return LlmAgent(
            name="data",
            model=settings.AGENT_MODEL,
            instruction=load_prompt("agents/data"),
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message
