from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext


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
            instruction="""
You are a General Assistant.

You handle:
- conversations
- explanations
- general reasoning
- fallback queries

You MUST use provided context if present.

TOOLS:
- list_files / search_files: when the user refers to something they uploaded.
- When the user asks for a downloadable file (report, notes, CSV, JSON, PDF...), write the
  complete content yourself, call create_file, then share the returned download_url as a
  Markdown link [filename](download_url).
- For reports, meeting notes, study notes, comparisons or emails, prefer list_templates
  then create_from_template for a consistent structure.
""",
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message