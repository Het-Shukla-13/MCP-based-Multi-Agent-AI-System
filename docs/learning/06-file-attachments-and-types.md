# 06 · File uploads, types and processing (`fix/file-attachments-and-types`)

## 1. The AI reply stole the user's attachments
`build_ai_message_payload` copied the user's `file_ids` onto the assistant message. `_attach_files_to_message` then set `file.message_id = ai_message.id`, so the files *moved* to the AI reply. A file has exactly one `message_id`, so it can only belong to one message. Fix: the AI message gets `file_ids=[]`. Verified: the file stays on the `user` message.

## 2. Upload validation
**Size: stream, don't buffer.** `await file.read()` loaded the whole upload into RAM *before* checking 7 MB, so a 2 GB upload was read fully, then rejected. Now we read 1 MB at a time, write to disk, and stop as soon as the size passes 7 MB (HTTP **413 Payload Too Large**). A `try/except BaseException` deletes partial or rejected files, so nothing is left on disk.

**Type: check the content, not the name.** The filename and the browser's `Content-Type` are both chosen by the client, and the old code stored `file.content_type` as given. Now `file_validation.sniff_matches_extension` checks:
- **Magic bytes** (file signatures): PDF starts with `%PDF-`, PNG with `\x89PNG\r\n\x1a\n`, JPEG with `\xff\xd8\xff`.
- **DOCX/XLSX are ZIP files** (`PK\x03\x04`), and must contain `word/document.xml` or `xl/workbook.xml`.
- **Text formats** (txt, md, json, csv, code): must decode as UTF-8 and contain no NUL bytes.

The stored MIME type now comes from the verified extension. Verified: `fake.pdf` → 400, binary `.txt` → 400, 8 MB file → 413.

**One source of truth.** `ALLOWED_FILE_EXTENSIONS` was a separate hand-written list, so `.ts/.java/.c/.cpp/.go` had parsers but were rejected at upload. Now it's *derived* from the parser groups in `file_type_config.py`.

## 3. Dependencies
- **XLSX:** pandas needs `openpyxl` to read Excel files, and it wasn't installed, so every XLSX failed. Added.
- **Code parsing:** `tree-sitter-languages` is abandoned and incompatible with `tree-sitter` 0.25. It was replaced by its maintained successor, `tree-sitter-language-pack`, which has the same `get_parser()` API.
- **Byte offsets:** tree-sitter reports **byte** offsets, but the code sliced a Python `str` (character offsets). Any non-ASCII character, like `é` or an emoji, shifted every chunk. Now it slices the UTF-8 bytes.
- A parser failure now degrades to plain chunking, with a logged error, instead of failing the whole file.
- Removed about 15 debug `print()` calls, including one per syntax-tree node.

## 4. The hidden processing bug (found by testing, not by reading)
Multi-file uploads left every file except the first stuck at `uploaded`. We debugged it step by step:
1. Thread dump (`python -X faulthandler`, then `kill -ABRT`): both worker threads were **idle**. Not a deadlock.
2. Test client: all jobs **were** submitted.
3. Ran the jobs directly and called `future.exception()`: `'NoneType' object has no attribute 'push'`.

**Cause:** local mode called the **Celery task object** from pool threads. Celery's task wrapper uses per-thread state that only exists in the main thread, so every concurrent job after the first crashed instantly. **`ThreadPoolExecutor` stores exceptions inside the `Future`**, nobody looked, and the errors vanished.

**Fix:**
- `file_ingestion.ingest_file()`: plain function holding the real pipeline (parse → chunk → embed → store → status), with no Celery.
- `tasks/file_tasks.process_file`: a two-line Celery wrapper around it.
- Local mode submits `ingest_file` and adds `future.add_done_callback(...)` so every crash is logged.

## 5. Celery queue mismatch (also pre-existing)
Tasks were routed to queue `default`, but a worker started normally consumes queue `celery`, so tasks waited in Redis forever (we found 2 stuck). Fix: `task_default_queue = "default"`. Run the worker with:
```bash
cd backend && .venv/bin/celery -A app.core.celery_app.celery_app worker --pool=solo --loglevel=info
```

## Verified end to end (real server + Postgres)
All 11 types processed with chunks: PDF 10, DOCX 10, MD 1, JSON 1, JS 26, PY 1, TS 1, CSV 2, XLSX 1, JPEG (OCR) 3, TXT 1. Code chunks are AST-based (`function_definition` / `function_declaration`). File delete cascades to chunks. Celery mode: stuck tasks processed after the fix.
