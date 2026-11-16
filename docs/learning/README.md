# Learning Notes

One note per branch, in the order the work was done. Each note covers: the concept, where the code lives, what was wrong, what changed, why it's better, and how to test it.

| # | Branch | Topic |
|---|---|---|
| 01 | `fix/llm-model-config` | Model lifecycle, provider routing, reasoning models, fallbacks, tokenizers |
| 02 | `chore/python-312` | Python 3.12 venv, removed unused faiss-cpu |
| 03 | `fix/agent-isolation-and-async` | Shared mutable state, event loop blocking, sticky routing |
| 04 | `fix/memory-pipeline-crashes` | Model-vs-dict contracts, return-type honesty, silent failures |
| 05 | `fix/migrations-and-vector-index` | Alembic chains, squashing, pgvector operators and HNSW, FK cascade |
| 06 | `fix/file-attachments-and-types` | Streaming uploads, magic bytes, dependencies, Future exceptions, Celery queues |
| 07 | `chore/cleanup` | Direct vs transitive deps, extras, strip_headers bug, stale tests |
| 08 | `feature/agent-context-wiring` | DB as single source of history, rules vs LLM decisions, relevance thresholds |
| 09 | `feature/memory-management-api` | Derived data, re-embedding, StrEnum (3.11 change), export formats |
| 10 | `feature/adk-root-agent` | ADK sub_agents + transfer_to_agent, descriptions as routing, status events, regex lookbehind |
| 11 | `feature/mcp-client` | MCP protocol, McpToolset, composition for least privilege, identity injection, stdio rules |
| 12 | `feature/agent-tools` | Five MCP servers, SSRF, no-RCE design, free-service verification, retryable errors |
| 13 | `feature/gemini-embeddings` | Vector spaces, re-embedding, rate limits, threshold calibration, vision OCR |
| 14 | `feature/streaming-responses` | SSE partial events, delta protocol, measuring latency, background work |
| 15 | `feature/file-generation-templates` | Templates + context injection, tool errors as instructions, XSS, CSP nonces |
| 16 | `feature/auth` | Argon2id, JWT pitfalls, ownership checks, 404 vs 403, tokens in URLs |
| 17 | `docs/architecture` | Diagrams as code (Mermaid), design decisions, requirements mapping |
| 18 | `feature/fe-auth` | Interceptors, tokens in URLs, case-sensitive imports, CORS-masked 500s |
| 19 | `feature/fe-streaming` | WebSocket event handling, draft vs saved messages, derived state |

## Branching workflow
- `develop-be` is cut from `main`, with the latest feature branch merged in.
- Each fix or feature gets its own branch off `develop-be`, merged back with `--no-ff` and kept (never deleted).
- `develop-fe` follows the same pattern after the backend is complete.
