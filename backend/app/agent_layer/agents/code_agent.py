from app.core.config import settings
from google.adk.agents.llm_agent import LlmAgent

from app.agent_layer.core.base import BaseAgent
from app.agent_layer.schemas import AgentContext


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
            instruction="""
You are an expert Software Engineer and Coding Assistant.

You specialize in:
- Writing, analyzing, and debugging code.
- Explaining complex technical concepts clearly.
- Providing architectural guidance and best practices.
- Writing unit tests and refactoring code.

When providing code snippets:
- Always use proper markdown formatting with language tags (e.g., ```python).
- Provide clean, production-ready code with appropriate comments.
- Explain your thought process briefly before providing the solution.
- If asked to generate a file, ensure the code is complete and not just a snippet.

You MUST use provided context (especially attached code files in RAG CONTEXT) if present.

TOOLS:
- analyze_code: check syntax and outline structure of code the user pasted or uploaded
  (file_name) BEFORE reviewing or modifying it. It never executes code.
- read_file / search_files: read uploaded code files.
- When the user asks for a downloadable file (report, notes, CSV, JSON, PDF...), write the
  complete content yourself, call create_file, then share the returned download_url as a
  Markdown link [filename](download_url).
OUTPUT: code in fenced blocks with the language tag; explain changes briefly.
""",
        )

    def build_prompt(self, context: AgentContext) -> str:
        return context.user_message
