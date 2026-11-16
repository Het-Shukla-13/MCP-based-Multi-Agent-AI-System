# 11 · MCP client + first MCP server (`feature/mcp-client`)

## What MCP is
The **Model Context Protocol** is a standard way for an AI app to use tools that live in a **separate program**, an *MCP server*:
- The server announces its tools: name, description, JSON input schema.
- A client connects, lists them and calls them.
- Messages are JSON-RPC over **stdio** (child process stdin/stdout) or HTTP.

Write a tool once as an MCP server and any MCP host (our agents, Claude Desktop, IDEs) can use it.

## Architecture
```
FastAPI app                                  MCP server processes
 agent ─ FilteredToolset ─┐
 agent ─ FilteredToolset ─┼─ McpToolset ──stdio JSON-RPC──▶ files server
 agent ─ FilteredToolset ─┘   (one per server, shared)       list_files / search_files / read_file
```
- `app/mcp_servers/files_server.py`: built with **FastMCP**. A decorated function's signature becomes the input schema and its **docstring becomes the description the model reads**.
- `app/agent_layer/tools/mcp_registry.py`:
  - `MCP_SERVERS`: server → module.
  - `AGENT_TOOLS`: agent → allowed tools (least privilege).
  - **One `McpToolset` per server**: one child process, shared by all agents and requests. JSON-RPC request ids keep concurrent calls apart.
  - **`FilteredToolset`**: a per-agent *view* built by composition. It asks the shared toolset for its tools and keeps only the allowed ones. Using `tool_filter` on separate toolsets would have started one heavy process per filter.
- Tool **selection** = model function calling. ADK sends the tool schemas, the model decides which to call and can **chain** several (verified: `list_files → read_file → read_file` in one turn).
- MCP child processes are closed on app shutdown (`close_all_toolsets`).

## Security: never trust identifiers from the model
Tools take `user_id` and `conversation_id`. A prompt-injected document could ask the model to pass another user's ids. `BaseAgent._identity_injector` is a `before_tool_callback` that **overwrites** those args with the real request identity before every call. The server also only queries files owned by that user *and* conversation.

**Lesson:** test a security control deterministically. Our live injection attempt was refused by the model, so it never reached the callback and proved nothing. `test_tool_identity_args_are_overwritten_with_request_identity` calls the callback directly with forged ids.

## Gotchas hit (and why)
| Problem | Cause | Fix |
|---|---|---|
| `McpToolset` import failed | Latest `mcp` 2.x installed; ADK needs `mcp<2` | Use ADK's extra `google-adk[mcp]` |
| Server died at handshake | Loguru parsed `<files>` as a colour tag | `[mcp:files]` prefix |
| Tool had no description | An **f-string** docstring is not a docstring (`__doc__` is None) | Plain string |
| (rule) | stdout **is** the protocol channel in stdio servers | Log to stderr, never `print()` |

## Data bug found by a tool test
`basic-data.csv` starts with a `# comment` line. `pd.read_csv` took it as the header, so all real columns were lost, in **ingestion (RAG chunks) too**. The new `tabular.read_csv_robust` skips leading `#` lines. It doesn't use `comment="#"`, which would also cut values containing `#`. Tested.

## Status events
`emit_tool_events` reports `{"status":"tool","agent":"data","tool":"read_file"}` for every MCP call. The UI can show "Data agent → reading file…".

## Removed
The old `agent_layer/tools/` scaffolding: a custom registry, a `ToolSelector` that was never called, and a `MemorySearchTool` stub that returned empty data. ADK's native tool handling replaces all of it.

## Verified live
| Question | Agent → tools |
|---|---|
| What files did I upload? | general → list_files |
| Section headings of the report? | document → read_file |
| CSV columns/rows + report's future section | data → list_files → read_file → read_file |

Tests: 21 passed.
