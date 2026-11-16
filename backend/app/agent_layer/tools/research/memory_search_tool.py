from app.agent_layer.tools.base import BaseTool
from app.agent_layer.tools.schemas import ToolResult


class MemorySearchTool(BaseTool):

    name = "memory_search"

    description = (
        "Search memory system"
    )

    async def execute(
        self,
        **kwargs,
    ):

        return ToolResult(
            success=True,
            tool_name=self.name,
            data="",
        )