# tools/registry.py

from app.agent_layer.tools.base import BaseTool


class ToolRegistry:

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(
        self,
        tool: BaseTool,
    ):
        self._tools[tool.name] = tool

    def get(
        self,
        tool_name: str,
    ) -> BaseTool:

        tool = self._tools.get(tool_name)

        if not tool:
            raise ValueError(
                f"Tool '{tool_name}' not registered."
            )

        return tool

    def exists(
        self,
        tool_name: str,
    ) -> bool:
        return tool_name in self._tools

    def list_tools(
        self,
    ) -> list[str]:
        return list(self._tools.keys())


tool_registry = ToolRegistry()