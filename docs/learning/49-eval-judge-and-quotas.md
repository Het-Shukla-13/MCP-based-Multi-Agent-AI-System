# 49 — When the evaluator itself fails: inconclusive, fallback judge, quota budgets

Branch: `fix/eval-judge-rate-limit` (+ the memory e2e locator fix).

## What happened

- After the embedding quota reset, the full eval run reported **answers 0.667, REGRESSION**.
- Both "failures" were `429` from Groq on `openai/gpt-oss-20b`, which is the **judge** and not the product.
- The full error said **tokens per day: Limit 200,000, Used 199,661**.

## Two design flaws exposed

1. **Infrastructure failures counted as product failures.**
   - A rate-limited judge made a correct answer look wrong.
   - An eval gate that cries wolf trains people to ignore it.
2. **The "non-LLM" e2e suite isn't LLM-free.**
   - The tests don't call models, but the backend they drive does: every imported conversation schedules background memory maintenance (extraction, metadata), which runs on the same Groq model.
   - Many full e2e runs today, chasing the pool bug from note 47, used up the shared daily budget.

## The fix (harness only; the product is unchanged)

- **Short limits** (per minute) are waited out, using the provider-suggested delay, capped at 60 s.
  - `retry_after_seconds()` parses Groq's "try again in 1m2.5s" and Gemini's `retryDelay`.
  - It returns `None` for errors that aren't rate limits.
- **Long limits** (per day) switch to `EVAL_JUDGE_FALLBACK_MODEL = openai/gpt-oss-120b`.
  - It was chosen from the models this key can actually use (listed via the API; all `active=True`).
  - Groq budgets are per model, so it has its own allowance.
  - It is **not** a Gemini model: the answers come from Gemini agents, and a same-family judge tends to prefer its own style (self-preference bias).
  - Each result records **which judge** scored it.
- **No judge available** marks the case **inconclusive**: excluded from the score and reported. If more than ⅓ of a suite is inconclusive, the run exits **2**, so an outage can neither fail nor pass the gate.
- **Product failures** (the agent itself erroring) still count as failures.

Verified live: on the first rerun the primary judge was out of quota, **all 6 were marked inconclusive, and the run exited 2** instead of reporting a regression. With the fallback judge, answers scored **6/6** and the run exited 0.

**Final eval state:** routing 1.000, tools 1.000, answers 1.000, retrieval 1.000 (32/32 through the real runner, confirming the baseline set from the A/B runs).

## A regression that hid behind a blocked test

- The memory e2e test had been blocked by the embedding quota for two days.
- Meanwhile, the new "Search chats" sidebar button made its `getByRole("button", {name: "Search"})` ambiguous.
- Once unblocked, it failed in 1.9 s. Scoping the locator to the Memory dialog fixed it.
- **The lesson:** a blocked test is a blind spot, and regressions pile up behind it. Unblock tests fast, or make them independent of the external dependency.

## Final e2e state

- 47 fast tests, plus memory, plus 2 real-LLM tests (streaming reply, agent labels, safe tables): **all pass**.

## Recommendation (not done yet)

Run the backend for e2e with background memory maintenance **disabled** (a setting), so test runs stop spending the daily LLM budget that real users and evals need. The memory e2e test uses the explicit memory API, so it's unaffected.
