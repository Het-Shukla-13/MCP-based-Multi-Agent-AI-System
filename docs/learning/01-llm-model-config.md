# 01 · LLM model configuration (`fix/llm-model-config`)

## The problem
Every non-agent LLM call (context routing, summarization, memory extraction, metadata, intent detection, file generation) used `groq/llama-3.1-8b-instant`. Groq **retired** that model on 2026-08-16, so all of those calls returned `404 model does not exist`. The agent fallback `groq/llama-3.3-70b-versatile` was retired too. It also could never have worked, because ADK needs the `litellm` package for non-Gemini models, and that package isn't installed.

## Concept 1: models have a lifecycle
Hosted models go through preview → stable → deprecated → shut down. Lessons:
- **Never hard-code model names in many places.** The six agents each had `model="gemini-3.1-flash-lite"`. Now there is one setting (`AGENT_MODEL`) in `app/core/config.py`.
- **Verify with a real call, not docs or blogs.** `gemini-2.5-flash-lite` still appears in the model list, but a real request returns *"no longer available to new users"*.
- Check what your key can see:
  ```bash
  curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
  curl -s "https://generativelanguage.googleapis.com/v1beta/models" -H "x-goog-api-key: $GEMINI_API_KEY"
  ```

## Concept 2: provider routing through one interface
Both Groq and Gemini support the **OpenAI-compatible Chat Completions API**, so the same `client.chat.completions.create(...)` works for both. Only the client changes:
- a name starting with `gemini` → `OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/")`
- anything else → `Groq(...)`

This lives in `_call_model()` in `app/services/llm/llm_service.py`. Callers never care which provider answered.

## Concept 3: reasoning models
`openai/gpt-oss-20b` (open-weight, free on Groq) *thinks* before answering. With a small `max_tokens`, it can spend the whole budget on hidden reasoning and return **empty content**, which we saw in testing. Two parameters fix this:
- `reasoning_effort: "low"` keeps the thinking short. Our tasks (classify, summarize, extract JSON) don't need deep reasoning. It is configurable with `LLM_REASONING_EFFORT`.
- `include_reasoning: false` drops the reasoning text from the response, which saves bandwidth and log noise.

These are Groq-specific fields, so they're sent with `extra_body`. That is the OpenAI SDK's escape hatch for provider-specific parameters.

## Concept 4: fallbacks
`get_llm_response()` now catches failures. If the error is *retryable by switching model* (429 rate limit, quota, 404 retired model, 5xx outage), it retries once on `LLM_FALLBACK_MODEL` (`gemini-3.5-flash-lite`, on a different provider). The design choices:
- It uses a **different provider**, so one provider's outage or quota doesn't take the app down.
- It falls back **only on retryable errors**. A bug in our own request, such as a bad JSON schema, should fail loudly, not be hidden.
- It logs a warning with both model names, so you can see when the fallback was used.

## Concept 5: tokenizers are not models
Token counting (for the short-term memory window) used the `NousResearch/Llama-2-7b-hf` tokenizer with `local_files_only=True`. It was never downloaded, so every count **silently** fell back to `len(text)/4`. It's also the wrong tokenizer for our models.

Now we use `tiktoken` with the `o200k_base` encoding, which is gpt-oss's tokenizer family. `tiktoken` is a small library with nothing to run locally. It fetches one encoding file once and caches it. Gemini tokenizes slightly differently, but for budgeting a close, consistent estimate is enough.

## What changed
| File | Change |
|---|---|
| `app/core/config.py` | New defaults: `MODEL=openai/gpt-oss-20b`, `LLM_FALLBACK_MODEL`, `LLM_REASONING_EFFORT`, `AGENT_FALLBACK_MODEL=gemini-3.5-flash-lite` |
| `app/services/llm/llm_service.py` | `_call_model()` (provider routing + reasoning params), fallback in `get_llm_response()`, removed the commented-out prompt and the dead `qwen` branch |
| `app/agent_layer/agents/*.py` | `model=settings.AGENT_MODEL` instead of a hard-coded string |
| `app/agent_layer/core/base.py` | Removed the model override in `__init__`, since agents now read the setting directly |
| `app/services/tokenization/tokenizer.py` | `tiktoken` `o200k_base` instead of the Llama-2 tokenizer |
| `backend/.env.example` | **New.** Documents every setting, without secrets |

## Environment note
The old `.venv` pointed to a Python 3.10 install that no longer exists. Moving the project folder also breaks venvs, because they store absolute paths. It was rebuilt with:
```bash
cd backend
uv venv --python 3.12 .venv      # see .python-version; system Python is untouched
uv pip install --python .venv/bin/python -r requirements.txt
```
Later moved to **3.12** (`chore/python-312`): the only blocker, `faiss-cpu==1.7.4`, was unused and was removed.

## How to test
```bash
cd backend && .venv/bin/python -c "
import asyncio; from app.services.llm import llm
print(asyncio.run(llm.chat([{'role':'user','content':'Reply with exactly: pong'}])))"
```
Verified live: chat ✅, JSON/structured ✅, fallback from a retired model ✅, token count ✅, ADK agent on the primary and fallback models ✅.

## Not fixed yet (and where it will be)
- Agents change `self.adk_agent.model` on a **shared** instance during fallback, which is a race between users. → `fix/agent-isolation-and-async`
- `runner.run()` blocks the event loop. → same branch
