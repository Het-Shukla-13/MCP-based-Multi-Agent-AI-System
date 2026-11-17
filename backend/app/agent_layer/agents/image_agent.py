from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext
from app.prompts import load_prompt


class ImageAgent(BaseAgent):

    name = "image"
    label = "Image Agent"
    description = (
        "Understanding uploaded images (describe, read text, analyse) and creating images or image prompts."
    )

    def _build_adk_agent(self) -> LlmAgent:
        return LlmAgent(
            name="image",
            model=settings.AGENT_MODEL,
            instruction=load_prompt("agents/image"),
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message
