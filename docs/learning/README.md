# Learning Notes

One note per branch, in the order the work was done. Each note covers: the concept, where the code lives, what was wrong, what changed, why it's better, and how to test it.

| # | Branch | Topic |
|---|---|---|
| 01 | `fix/llm-model-config` | Model lifecycle, provider routing, reasoning models, fallbacks, tokenizers |
| 02 | `chore/python-312` | Python 3.12 venv, removed unused faiss-cpu (summary only: no separate note) |
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
| 20 | `feature/fe-markdown` | Safe Markdown rendering, no raw HTML, tokenised file URLs, memo |
| 21 | `fix/adk-context-leak` | Inspecting model input, ADK before_model_callback |
| 22 | `feature/fe-composer` | Mention parsing, per-conversation state, drag-and-drop, client vs server validation |
| 23 | `fix/profile-stale-items` | Rebuild caches from the source of truth |
| 24 | `feature/fe-memory-and-conversations` | Blob downloads, file import, memory UI, accessible drawer |
| 25 | `feature/refresh-tokens` | Access vs refresh tokens, hashing secrets, rotation, reuse detection |
| 26 | `feature/fe-session-refresh` | 401 retry interceptor, single-flight refresh, pre-connect refresh |
| 27 | `feature/fe-ws-reconnect` | Exponential backoff, jitter, resync after reconnect |
| 28 | `feature/fe-responsive` | Off-canvas drawer, dvh, hover media query, CSS cascade order |
| 29 | `fix/fe-stale-responses` | Out-of-order responses, latest-request guard |
| 30 | `feature/fe-e2e-tests` | Playwright test runner, isolation, web-first assertions, flaky vs real bugs |
| 31 | `docs/fe-readme` | Documentation for users and future developers |
| 32 | `chore/single-env` | One config file, URL-encoding credentials, env_file trade-off |
| 33 | `feature/turn-metrics` | Per-turn latency/tokens/tools via a ContextVar collector, batched writer, p50/p95, PII redaction |
| 34 | `feature/agent-evals` | JSONL eval suites, pure graders, LLM judge on a different model, baseline + regression exit code |
| 35 | `feature/prompts-as-files` | Prompts in Markdown with includes/placeholders; byte-identical refactor proof; `.gitignore` trap |
| 36 | `feature/turn-runner` | Server-owned turns: per-conversation lanes, Stop keeps the draft, queue, heartbeat + sweeper, replay |
| 37 | `feature/tool-confirmation` | Approve/reject/revise side-effect tools by awaiting in the tool callback; opt-in capability |
| 38 | `feature/parallel-tools` | Blocking calls in async MCP tools, readers-writer tool scheduler, interval-union tool time |
| 39 | `feature/hybrid-retrieval` | Retrieval eval with a context budget, parent/child chunks, weighted RRF hybrid search, HTTP timeouts |
| 40 | `feature/layered-compaction` | View-only L0-L4 history compaction, background summary, atomic JSONB patches, graceful degradation |
| 41 | `feature/fe-design-tokens` | Design tokens, warm light/dark without flash, computed WCAG contrast, migration by property role, visual tests |
| 42 | `feature/fe-restyle` | Panel scrolling, reading column, lucide icons with aria-labels, toasts, one focus ring, reduced motion |
| 43 | `feature/fe-streaming-polish` | Frame-batched deltas, live step checklist (pure reducer), turn_state replay, draft-wiping race |
| 44 | `feature/fe-composer-turns` | Stop, queue chips, offline notice, follow-the-bottom scroll; reading values out of setState updaters (bug) |
| 45 | `fix/ws-error-attribution` + `feature/fe-confirmations` | Errors echo their command; approval cards; fake WebSocket server tests |
| 46 | `fix/quota-503` + `feature/conversation-search` + `feature/fe-states-and-search` | 503 + Retry-After, Postgres FTS search, ⌘K palette, skeletons, drafts, copy fallback |
| 47 | `fix/db-pool-starvation` + `fix/pipeline-connection-release` | Flaky tests were a pool outage: global cap, explicit pool, release connections during AI calls (120 s → 0.1 s) |
| 48 | `feature/metrics-daily` + `feature/fe-usage-view` | Usage view: form first, validated chart colour, focusable chart with table view |
| 49 | `fix/eval-judge-rate-limit` + `feature/background-jobs-switch` | Inconclusive vs failed evals, fallback judge, a blocked test hides regressions, test runs vs daily quotas |

## Branching workflow
- `develop-be` is cut from `main`, with the latest feature branch merged in.
- Each fix or feature gets its own branch off `develop-be`, merged back with `--no-ff` and kept (never deleted).
- `develop-fe` follows the same pattern after the backend is complete.
