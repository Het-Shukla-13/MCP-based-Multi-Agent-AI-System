from loguru import logger
from pydantic import BaseModel, Field

from app.services.llm import llm

from app.agent_layer.tools.schemas import (
    ToolSelection,
)


class ToolSelector:

    @staticmethod
    async def select_tool(
        query: str,
        available_tools: list[str],
    ) -> str:

        tools_text = "\n".join(
            f"- {tool}"
            for tool in available_tools
        )

        prompt = f"""
You are a tool router.

User Query:
{query}

Available Tools:
{tools_text}

Choose the SINGLE best tool.

Return JSON:

{{
    "selected_tool": "<tool_name>",
    "reason": "<why>"
}}
"""

        try:
            decision = await llm.structured(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                purpose="tool_selection",
                response_model=ToolSelection,
            )

            logger.info(
                "Tool selected | tool={} | reason={}",
                decision.selected_tool,
                decision.reason,
            )

            return decision.selected_tool

        except Exception:
            logger.exception(
                "Tool selection failed"
            )

            return available_tools[0]