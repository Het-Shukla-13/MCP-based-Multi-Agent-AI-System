# Learning Notes

One note per branch, in the order the work was done. Each note covers: the concept, where the code lives, what was wrong, what changed, why it's better, and how to test it.

| # | Branch | Topic |
|---|---|---|
| 01 | `fix/llm-model-config` | Model lifecycle, provider routing, reasoning models, fallbacks, tokenizers |
| 02 | `chore/python-312` | Python 3.12 venv, removed unused faiss-cpu |

## Branching workflow
- `develop-be` is cut from `main`, with the latest feature branch merged in.
- Each fix or feature gets its own branch off `develop-be`, merged back with `--no-ff` and kept (never deleted).
- `develop-fe` follows the same pattern after the backend is complete.
