# 12 · Agent tools: five MCP servers (`feature/agent-tools`)

## Servers and who uses them
| Server | Tools | Agents | Free? |
|---|---|---|---|
| files | list_files, search_files, read_file | all | local |
| data | table_info, aggregate, filter_rows, top_n, value_counts, correlation | data | local pandas |
| web | web_search, fetch_page | research | ddgs metasearch + Wikipedia API, no key |
| code | analyze_code | code | local tree-sitter/ast |
| image | describe_image, generate_image | image | Gemini vision (free) / Pollinations.ai (free) |
| artifacts | create_file (md, txt, json, csv, pdf) | all except image | local |

Each agent's instructions now say *when* to use which tool and how to format output. The tool **docstrings** say *how* to call them.

## Free-service verification (live, not from docs)
- **Gemini image generation:** free-tier quota is `limit: 0`, so it's paid only and not used. Gemini **vision** is free and used.
- **Pollinations.ai:** free, keyless. Adds a small watermark; prompts go to a third-party service.
- **ddgs** scrapes public search engines, which **rate-limit**. During testing every engine blocked us at once. So `web_search` tries 6 engines in turn, then falls back to **Wikipedia's official REST API** (free, keyless, built for programs) and labels the source.

## Security
- **No code execution.** The data tools are fixed, validated operations, never "run this pandas code" (that would be remote code execution). `analyze_code` only parses.
- **SSRF protection** in `fetch_page`. The host is resolved, and private, loopback, link-local and reserved IPs are refused (e.g. `localhost:8010` = our own API, `169.254.169.254` = cloud metadata). Redirects are re-checked on every hop. *Known limitation:* DNS rebinding between the check and the connection. Fully closing it needs IP pinning.
- **Identity injection** (from branch 11) applies to every new tool.
- Tests probe the guards directly, because the model refused the live SSRF prompt itself and so never exercised the guard.

## File generation became a tool
**Before:** every message ran a keyword check, often an *extra LLM call* to classify "file request?", and file requests bypassed the agents entirely.
**Now:** the agent writes the content and calls `create_file`. That's one fewer LLM call per message, and the agent's context and tools are used (e.g. data → aggregate → create_file).

Generated files: the tool result contains `generated_file_id`. `collect_generated_files` reads it from ADK function-response events, and the file is attached to the assistant message. Deleted: `intent_router.py`, `file_generation_service.py` and two prompts.

**PDF rendering:** Markdown → HTML (`markdown` with tables) → PyMuPDF `Story`, giving real headings, lists and tables. The old renderer printed `#` and `|` literally, in a Latin-only font.

## Reliability fixes found by live testing
| Symptom | Cause | Fix |
|---|---|---|
| Image agent error after the tool succeeded | Gemini `503 high demand`; fallback only triggered on 429 | `is_retryable_provider_error` (429/5xx/overloaded) for agents and router |
| Image generation failed | Pollinations 503 for `model=flux` (overload) | Retries with backoff, then the default model |
| No memories saved for a turn | One extracted item had an invalid enum, so the *whole batch* was rejected | Validate memories one by one (`memory_extractor`) |
| "Web search unavailable" | Engines rate-limited this IP | Engine chain + Wikipedia fallback |

## Verified live
| Request | Tools called | Result |
|---|---|---|
| Revenue per region (sales.csv) | table_info → aggregate | North 5,550 ✅ (checked by hand) |
| Check buggy.py | analyze_code → read_file | Missing `)` found ✅ |
| Latest PostgreSQL? | web_search ×2 | 18 (18.7) with sources ✅ |
| What's in the image? | describe_image | Accurate description ✅ |
| Draw a robot | generate_image | Image attached ✅ |
| PDF report per region | table_info → aggregate ×2 → create_file | PDF attached ✅ |

Tests: 25 passed (new `tests/test_mcp_tools.py`).
