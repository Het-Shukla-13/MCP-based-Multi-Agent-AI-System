from app.agent_layer.tools.registry import (
    tool_registry,
)

from app.agent_layer.tools.research.memory_search_tool import (
    MemorySearchTool,
)

tool_registry.register(
    MemorySearchTool()
)