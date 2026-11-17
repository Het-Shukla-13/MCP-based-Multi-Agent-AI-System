# 34 · Agent evaluation suite (`feature/agent-evals`)

## Why
Unit and browser tests check that the *software* works. Evals check that the *agents behave well*: right agent, right tools, correct answers. Every later change (prompts, retrieval, compaction) is compared against the baseline recorded here.

## Run
```bash
cd backend
.venv/bin/python -m evals.run                   # all suites, compare with evals/baseline.json
.venv/bin/python -m evals.run --suite routing   # one suite
.venv/bin/python -m evals.run --update-baseline # accept current scores
```
Uses the real free-tier models, MCP tools and database (~5 min). Exits 1 if a suite drops more than `--tolerance` (0.05) below its baseline, so it can gate CI. Full results go to `evals/results/` (git-ignored); `baseline.json` is committed.

## Suites (`evals/datasets/*.jsonl`, one case per line)
| Suite | Question | Grading |
|---|---|---|
| routing (24) | Does the message reach an acceptable agent? Includes tricky cases (e-mail with `@`, greetings, explicit mentions, ambiguous topics with 2 acceptable agents) | `actual in expected` |
| tools (10) | Does the agent call the right tools and avoid forbidden ones? Includes "no tool needed" cases | any-of groups + forbidden list |
| answers (6) | Is the answer correct vs reference facts? | LLM judge, 1–5 for correctness / grounding / format; pass if correctness ≥ 4 |

Fixtures (`sales.csv`, `buggy.py`, `notes.md`) are uploaded and ingested for each run into a dedicated eval user's conversation.

## Concepts
- **Graders are pure functions** (`graders.py`), unit-tested without any LLM. Only the *system under test* is non-deterministic.
- **Judge ≠ answerer:** answers come from Gemini; the judge is gpt-oss (`EVAL_JUDGE_MODEL`). Models tend to rate their own outputs leniently (self-preference bias).
- **Structured judge output:** JSON scores with range validation, tolerant of code fences.
- **Reuse:** the tools suite observes calls with the turn-metrics collector from branch 33.
- **Acceptable sets:** "explain TCP vs UDP" can fairly go to general *or* research. Evals should encode what's *acceptable*, not one arbitrary answer.

## Reliability fix found by the first run
Routing 24 messages back to back hit the free tier's **requests-per-minute** limit (429) on **both** Gemini models within one minute, so the fallback failed too. A 429 tells you how long to wait (`retryDelay`). Now, when all models are rate-limited and the suggested wait is ≤ 20 s, the agent emits a `waiting` status, waits, and retries once instead of failing the turn (`quota_retry_delay`, `wait_for_quota`; unit-tested). The UI label for `waiting` is added in Phase J.

## Baseline
routing 1.0 · tools 1.0 · answers 1.0 (40/40). A perfect score **guards against regressions but can't show improvements** (no headroom), so harder cases (multi-turn follow-ups, long-document questions) get added in the retrieval/compaction branches.

*Side effect to know:* each run creates an eval conversation and uploads under `evals@example.com`.
