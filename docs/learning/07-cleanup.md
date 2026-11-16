# 07 · Cleanup (`chore/cleanup`)

## Dependencies: direct deps only
The old `requirements.txt` was a raw `pip freeze` with 185 pins, mixing what the app **uses** with everything those packages pulled in, plus leftovers from experiments (`chromadb`, `langchain-openai`/`-groq`/`-community`/`-classic`, `scikit-learn`, `fastapi-pagination`, `PyPDF2`...). Problems:
- You can't tell what the app actually needs.
- Upgrading one package means fighting 185 pins.
- Unused packages still cost install time and add security exposure.

Now `requirements.txt` lists **~40 direct dependencies**, grouped and commented, and the installer resolves the rest (148 packages installed). Test-only tools live in `requirements-dev.txt` (`-r requirements.txt` + pytest/httpx).

**How we found them:** grep every `import` in the code, then add runtime-only packages that are never imported (uvicorn, drivers, python-multipart, email-validator, openpyxl, redis).

**The trap we hit, and why we test:** SQLAlchemy's async engine needs `greenlet` at runtime, but the code never imports it, so the grep missed it. The live server failed with `the greenlet library is required`. The correct declaration is the **extra** `sqlalchemy[asyncio]`, which brings greenlet with it. The same idea applies to `uvicorn[standard]` (websockets + fast loop) and `celery[redis]`.

## Real bug found by an "old" test: headings dropped from DOCX/MD
`MarkdownHeaderTextSplitter` defaults to `strip_headers=True`: it moves `# Heading` lines into `doc.metadata` and removes them from the text. Our code kept only `page_content`, so **every heading in every DOCX/MD file was lost** and couldn't be searched. Fix: `strip_headers=False`, plus `section_title`/`section_id` metadata for the retriever's section grouping. Result: the sample DOCX produces 12 chunks that start with their headings.

**Lesson:** when an old test fails, first ask whether the **test** is wrong or the **code** is wrong. Here 3 failures were outdated tests (features deliberately removed or fields added), and 1 was a real bug.

## Tests updated
- Removed tests for helpers that were deliberately deleted (`_contains_identity_signal`, `_is_identity_fact_text`).
- `ContextPolicy` now requires all fields, so the test builds a real policy and overrides it with `model_copy(update=...)`.
- Test doubles (`DummyCreatedMemory`) got the fields the promoter now reads (`importance_score`, `source`, `is_active`).
- Result: `7 passed`.

## Smaller items
| Item | Change |
|---|---|
| 18 scratch scripts in `agent_layer/tests/` | Deleted. They had no asserts, ran on import, and some called live APIs |
| `echo=True` on both DB engines | Now `DB_ECHO` setting (default off). Every SQL statement had been printed to the log |
| CORS hard-coded to `localhost:5173` | `CORS_ORIGINS` setting (JSON list in `.env`) |
| `ws_router` imported twice in `main.py` | Removed duplicate |
| Pydantic `class Config` (deprecated) | `model_config = SettingsConfigDict(...)` |
| Unused `import PyPDF2` | Removed |
