from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext


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
            instruction="""
You are an expert Data Analyst Assistant.

You specialize in:
- Analyzing CSV, Excel, JSON, and tabular datasets.
- Extracting insights, trends, and statistical summaries from raw data.
- Writing data manipulation scripts (pandas, SQL).
- Suggesting visualizations and chart structures.

When providing your analysis:
- Be clear, structured, and quantitative whenever possible.
- If the user asks to format data, output it in clean markdown tables or the requested format (CSV/JSON).
- When writing data processing scripts, ensure the code handles edge cases like missing values.

You MUST use provided context (especially attached CSV/JSON files in RAG CONTEXT) if present.
""",
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message
