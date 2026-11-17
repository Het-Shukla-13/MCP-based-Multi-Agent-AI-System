from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext
from app.prompts import load_prompt


class CodeAgent(BaseAgent):

    name = "code"
    label = "Code Agent"
    description = (
        "Writing, explaining, reviewing and debugging source code; programming questions; uploaded code files (.py, .js, .ts, ...)."
    )

    def _build_adk_agent(self) -> LlmAgent:
        return LlmAgent(
            name="code",
            model=settings.AGENT_MODEL,
            instruction=load_prompt("agents/code"),
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message
