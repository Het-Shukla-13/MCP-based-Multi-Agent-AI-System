# 15 · Templates, previews, XSS defences (`feature/file-generation-templates`)

## Template-based generation with context injection
`services/file_generation/templates.py` has 5 templates: report, meeting_notes, study_notes, comparison, email. Each is a Markdown skeleton with **required** and **optional** fields. Two new artifacts tools:
- `list_templates()`: names, descriptions, fields.
- `create_from_template(template, title, fields, file_format)`.

Division of work:
- The **agent** writes content fields from the conversation (discussion, action items, ...).
- The **server injects** what the model must not invent or format inconsistently: today's date and the title. Optional sections appear (with heading) only when provided.

**Errors are instructions.** Missing required fields return `Missing required field(s) for 'report': findings, recommendations`. In the live test the agent's first call was rejected, it read the message and retried correctly. Tool errors should tell the model exactly how to fix the call.

## Dead code removed
The old `ArtifactDocument` JSON-document pipeline (schemas, renderer functions, test) was only used by a test after the move to tools. The renderer now holds just: MIME types, `slugify`, `filename_timestamp`, `render_markdown_pdf`.

## Preview page security
The preview page renders **user/model-provided content in your browser**: a classic stored-XSS target.

1. **Escaping.** The uploaded **filename** was inserted into HTML raw. A file named `<img src=x onerror=alert(1)>.txt` would have run JavaScript. Now every string goes through `html.escape`.
2. **Content-Security-Policy with a nonce.** Rendered Markdown may legitimately contain HTML, and escaping it would break rendering. Instead, the response header says:
   ```
   default-src 'none'; script-src 'nonce-<random per request>'; style-src 'unsafe-inline';
   img-src 'self' data:; frame-src 'self'; base-uri 'none'; form-action 'none'
   ```
   Only *our* `<script nonce="...">` (the copy button) runs. Any `<script>` or `onerror=` in the content is blocked by the browser. The nonce is random per response, so injected content can't guess it.
   - `X-Content-Type-Options: nosniff` also stops browsers from guessing types.
   - The old inline `onclick=` handler was replaced by `addEventListener`, because inline handlers are blocked by such a CSP.
3. **Rendering by type:** Markdown rendered, images shown, PDFs embedded, CSV as a table, JSON pretty-printed.

## Verified live
- "Create meeting notes as a PDF…" → `list_templates → create_from_template` (rejected once, retried) → PDF with injected date, attendees, decisions, action items.
- Upload named `<img src=x onerror=alert(1)>.txt` → preview contains only the escaped form; CSP header present.

Tests: 29 passed (`tests/test_file_generation.py`: templates, missing fields, every template renders, PDF has no raw Markdown).
