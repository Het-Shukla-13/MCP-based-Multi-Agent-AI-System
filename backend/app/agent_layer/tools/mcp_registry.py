"""
MCP client side: which MCP servers exist, and which agent may use which tools.

- One McpToolset (one child process + one MCP session) per server, created lazily
  and shared by all agents and requests. MCP's JSON-RPC request ids keep
  concurrent calls apart.
- Per-agent FilteredToolset (composition) = least privilege: an agent only sees
  the tools it needs, without starting another server process.
- Tool *selection* is done by the agent's model via function calling: ADK sends the
  tool schemas, the model decides which to call (and can chain several).
"""

import sys
from pathlib import Path

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from loguru import logger
from mcp import StdioServerParameters

BACKEND_ROOT = Path(__file__).resolve().parents[3]

# server name -> python module that runs it
MCP_SERVERS: dict[str, str] = {
    "files": "app.mcp_servers.files_server",
}

# agent name -> {server name: [allowed tool names]}
AGENT_TOOLS: dict[str, dict[str, list[str]]] = {
    "general": {"files": ["list_files", "search_files"]},
    "code": {"files": ["list_files", "search_files", "read_file"]},
    "data": {"files": ["list_files", "search_files", "read_file"]},
    "research": {"files": ["list_files", "search_files"]},
    "document": {"files": ["list_files", "search_files", "read_file"]},
    "image": {"files": ["list_files", "read_file"]},
}

# Arguments that identify WHOSE data a tool touches. Never trusted from the model.
IDENTITY_ARGS = ("user_id", "conversation_id")

_server_toolsets: dict[str, McpToolset] = {}


class FilteredToolset(BaseToolset):
    """A per-agent view of a shared server toolset, exposing only allowed tools."""

    def __init__(self, inner: McpToolset, allowed: list[str]):
        super().__init__()
        self._inner = inner
        self._allowed = set(allowed)

    async def get_tools(self, readonly_context: ReadonlyContext | None = None) -> list[BaseTool]:
        tools = await self._inner.get_tools(readonly_context)
        return [tool for tool in tools if tool.name in self._allowed]

    async def close(self) -> None:
        # The shared inner toolset is closed once, on app shutdown.
        return None


def _connection(module: str) -> StdioConnectionParams:
    return StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,           # same venv interpreter as the app
            args=["-m", module],
            cwd=str(BACKEND_ROOT),            # so `app.*` imports and .env resolve
        ),
        timeout=60,  # first call may load models (embeddings)
    )


def _server_toolset(server: str) -> McpToolset:
    if server not in _server_toolsets:
        _server_toolsets[server] = McpToolset(connection_params=_connection(MCP_SERVERS[server]))
    return _server_toolsets[server]


def get_toolsets_for_agent(agent_name: str) -> list[BaseToolset]:
    return [
        FilteredToolset(_server_toolset(server), allowed)
        for server, allowed in AGENT_TOOLS.get(agent_name, {}).items()
    ]


async def close_all_toolsets() -> None:
    """Stop MCP child processes on app shutdown."""
    for toolset in list(_server_toolsets.values()):
        try:
            await toolset.close()
        except Exception:
            logger.exception("Failed to close MCP toolset")
    _server_toolsets.clear()
