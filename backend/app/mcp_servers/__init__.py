"""
MCP servers: tools exposed over the Model Context Protocol.

Each module is a standalone process (`python -m app.mcp_servers.<name>`) speaking
JSON-RPC over stdin/stdout. The agent layer connects to them with ADK's McpToolset.
IMPORTANT: never print() to stdout in these processes; stdout IS the protocol channel.
"""
