# 39 — Retrieval: measure first, then parent/child chunks + weighted hybrid search

Branch: `feature/hybrid-retrieval` (Phase H)

## 1. Measure first: a retrieval-only eval

`evals/datasets/retrieval.jsonl` has 32 cases. Each case passes only if **every expected snippet is in the context the agent would receive** and that context fits a **6,000-character budget**. No LLM is involved, so it is deterministic and cheap. It runs in its own conversation, with fixtures in `evals/fixtures/retrieval/`:

- `ops-manual.md`: 12 sites with an identical section template (confusable), codes (`KS-4471-B`, `E-7731`) and paraphrase targets;
- `incident-log.txt`: no headings;
- `parts-catalogue.md`: one 320-row table with near-duplicate codes (`HX-3127-B` vs `HX-3127-C`);
- `security-policy.md`: long sections with a fact buried in the middle.

Groups: exact · confusable · paraphrase · context · table · long. The A/B script also reports **hit@1** (the first passage holds the answer) and **MRR** (mean reciprocal rank), because pass/fail stops discriminating once both variants pass.

**Why the budget matters.** Without it, a variant that dumps a whole 19 KB file into the prompt "passes". Recall alone rewards the most expensive behaviour.

## 2. What the measurements found (in order)

| Step | Score | p95 context | Finding |
|---|---|---|---|
| baseline (vector + "section scoping" + MMR) | 0.750 | 19,127 | wrong chunks dropped; the whole catalogue injected |
| − section scoping | 0.781 | 20,045 | the heuristic was harmful |
| + parent/child chunking (vector) | **1.000** | 5,931 | the biggest win |
| + hybrid, equal weights | 1.000 | 5,931 | hit@1 0.875 → 0.906; one paraphrase case got worse |
| + hybrid, query-weighted | **1.000** | 5,931 | **hit@1 0.938, MRR 0.969**, no group worse |

**Finding A: a heuristic was deleting right answers.**

- "Section scoping" kept only the best-scoring section and added a bonus for query/title word overlap.
- "evacuation meeting place for **Leipzig**" overlaps 1 of 2 words with "Shifts (**Leipzig**)" (+0.12) but only 1 of 3 with "Emergency procedures (**Leipzig**)" (no bonus).
- So the correct chunk, ranked **#1** by vector search, was replaced by the shifts section.
- It also explained an average context of 379 characters: 20 candidates were collapsed to about one chunk.

**Finding B: unbounded chunks.**

- The Markdown chunker split only on headings, so a 320-row table became **one 18,837-character chunk**.
- That chunk was far past the embedding model's input window (`gemini-embedding-001` reads about the first 2,048 tokens), and the entire table landed in the prompt on every match.

**Finding C: embeddings handle codes better than folklore says.** "Exact" questions scored 8/8 with vectors alone. Keyword search earned its place only on **near-duplicate** codes, B vs C, where vectors ranked the wrong row first.

## 3. Parent/child chunks (`app/services/file_processing/hierarchy.py`)

- Each logical unit (a section; a whole TXT file; a PDF section) becomes **parents** of at most 1,500 characters, split on paragraph or table-row boundaries.
- Each parent becomes **children** of about 400 characters (80 overlap).
- Children are **searched**; parents are **read** by the agent.
- Tables are split by rows, and every parent and child repeats the header row, so a row still says which column is the price.
- Prose and tables never share a parent.
- **Contextual header:** a child is embedded as `section title + child` (the stored text stays plain), so an orphaned piece of a section still "knows" what it is about.

Applies to PDF, DOCX, Markdown and TXT. Code, CSV and XLSX keep their own chunkers (no parent).

## 4. Hybrid search (`app/services/rag/retriever.py`)

- **Keyword half:**
  - `chunk.search_vector` is `GENERATED ALWAYS AS (to_tsvector('english', content)) STORED`, with a GIN index. Postgres keeps it in sync, including for rows that existed before the migration.
  - The query is an **OR** of `plainto_tsquery` per term. `websearch_to_tsquery` ANDs every word, which natural questions rarely satisfy. `plainto_tsquery('HX-3127-C')` keeps the code as a phrase.
  - Ranking uses `ts_rank_cd`.
- **Fusion: Reciprocal Rank Fusion** — `score = Σ weight / (60 + rank)`. It works on *ranks*, so a cosine of 0.71 and a ts_rank of 0.05 never need a common scale. Items that both lists like rise to the top.
- **Query-dependent weight:**
  - The keyword list counts fully when the query has an identifier-like term (it contains a digit: `HX-3127-C`, `E-7731`, `DC-09`).
  - Otherwise it counts at 0.3, because common words such as a city name match many sections equally.
  - Caveat: one parameter tuned on 32 cases risks overfitting. It has an independent rationale, but more cases would firm it up.
- **Passages:** children are mapped to their parents, de-duplicated, and returned up to 4 passages within the 6,000-character budget, each with `Source: file > section` so the agent can cite it.
- **pgvector filtered search:** HNSW plus `WHERE file_id IN …` used to fetch about `ef_search` nearest rows of *all users* and filter afterwards, which could leave too few rows. With pgvector 0.8, `SET LOCAL hnsw.iterative_scan = relaxed_order` keeps scanning until the LIMIT is met.
- `RETRIEVAL_MODE=hybrid|vector` in settings acts as both a kill switch and an A/B switch.

## 5. Migration and existing data

- Migration `bb99311688d9` adds:
  - the `chunk_parent` table;
  - `chunk.parent_id`, an FK named explicitly because autogenerate left it `None`, which would break the downgrade;
  - `search_vector` and its GIN index.
- Up, down and up again were tested.
- Old chunks keep working, because a chunk without a parent is returned as itself. To upgrade them, run `python -m scripts.rechunk` (`--dry-run` first). It writes the new chunks **before** deleting the old ones.

## 6. Bug found while running the evals: no HTTP timeout

The first full eval run sat for about an hour with almost no CPU use. The database was idle, and the process held a **closed** connection to Google.

**Cause:** `genai.Client(api_key=...)` has **no timeout by default**, so a dropped connection blocks forever. The same code embeds user uploads, which means an upload could stay "processing" forever.

**Fix:**

- All three Gemini clients get `http_options=HttpOptions(timeout=GEMINI_HTTP_TIMEOUT_MS)` (60 s).
- Embedding retries now also cover `httpx.TimeoutException` and `NetworkError`.
- A guard test (`tests/test_timeouts.py`) fails on any `genai.Client(...)` call without `http_options`.

**How it was diagnosed:**

1. Check the CPU time of the process. It wasn't moving, so the process was waiting, not working.
2. Check `pg_stat_activity`. Nothing was waiting on locks.
3. Run `lsof -p <pid> -i`. It showed a CLOSED socket to Google, so the process was blocked on network I/O.

**The second hang had a different cause: an unbounded retry delay.** The next eval run stopped again with CPU flat, but this time the log said `Embedding rate-limited; retrying in 78760.0s`.

- The free tier's **daily** embedding quota was used up (by the A/B runs). Google answered with `retryDelay ≈ 22 h`, and our retry loop obeyed it.
- **Fix:** waits above `MAX_RETRY_WAIT_SECONDS = 60` now raise `EmbeddingQuotaExhausted` straight away with a clear message. The agent side already capped its wait at 20 s.
- **Test:** a fake 22-hour 429 must raise without sleeping.

**Status of the evals for this branch:**

- routing 24/24, tools 10/10.
- answers 5/6: the failure was a Gemini **503 "high demand"**, a provider outage, not a regression.
- The retrieval suite could not be re-run in `evals.run` after the quota ran out. Its baseline of 1.0 comes from the A/B script, which uses the same `retrieve_pipeline`, the same grader and the same budget.
- Re-run `python -m evals.run --suite retrieval` after the daily quota resets.

**Lesson:** every outbound call needs a timeout. "The library probably has a sane default" is how you get hangs that last for hours.

## Lessons

- Make the eval hard enough to fail, and include the **cost** (the context budget), not only recall.
- The biggest win was **chunk shape**, not the search algorithm. The fanciest piece (hybrid) gave the smallest gain, and only once weighted.
- Delete heuristics that the data says are harmful, even clever-looking ones.
- When pass/fail saturates, switch to a finer metric (hit@1, MRR) instead of declaring a tie.
