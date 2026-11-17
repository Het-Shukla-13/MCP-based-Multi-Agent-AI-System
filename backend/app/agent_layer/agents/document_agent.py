from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext
from app.prompts import load_prompt


class DocumentAgent(BaseAgent):

    name = "document"
    label = "Document Agent"
    description = (
        "Reading, summarizing and answering questions about documents such as PDF and DOCX files, reports and long text."
    )

    def _build_adk_agent(self) -> LlmAgent:
        return LlmAgent(
            name="document",
            model=settings.AGENT_MODEL,
            instruction=load_prompt("agents/document"),
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message
