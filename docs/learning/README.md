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

## Branching workflow
- `develop-be` is cut from `main`, with the latest feature branch merged in.
- Each fix or feature gets its own branch off `develop-be`, merged back with `--no-ff` and kept (never deleted).
- `develop-fe` follows the same pattern after the backend is complete.
