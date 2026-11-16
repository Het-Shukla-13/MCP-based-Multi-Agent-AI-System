from __future__ import annotations

import csv
import html
import json
import secrets

import markdown
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.file_generation.file_renderer import format_from_path, get_mime_type
from app.crud.file import get_file

router = APIRouter(prefix="/files", tags=["File Generation"])


@router.get("/generated/{file_id}/download")
async def download_generated_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    file_record = await get_file(db, file_id)
    path = Path(file_record.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated file is missing from storage.")

    mime_type = file_record.file_type or get_mime_type(format_from_path(path))
    return FileResponse(
        path,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_record.filename}"',
        },
    )


@router.get("/generated/{file_id}/raw")
async def raw_generated_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    file_record = await get_file(db, file_id)
    path = Path(file_record.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated file is missing from storage.")

    mime_type = file_record.file_type or get_mime_type(format_from_path(path))
    headers = {}
    if mime_type == "application/pdf":
        headers["Content-Disposition"] = f'inline; filename="{file_record.filename}"'

    return FileResponse(
        path,
        media_type=mime_type,
        headers=headers or None,
    )


PREVIEW_CSS = """
body { font-family: system-ui, sans-serif; margin: 0; background: #f6f7f9; color: #1d2433; }
.bar { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;
       padding: 0.9rem 1.25rem; background: #fff; border-bottom: 1px solid #e3e6eb; }
.title { font-weight: 600; } .type { color: #667085; font-size: 0.85rem; }
.actions { display: flex; gap: 0.75rem; } .actions a, .actions button { font-size: 0.9rem; }
.content { max-width: 960px; margin: 1.25rem auto; background: #fff; border: 1px solid #e3e6eb;
           border-radius: 8px; padding: 1.5rem; overflow-x: auto; }
pre { white-space: pre-wrap; word-break: break-word; }
table { border-collapse: collapse; } th, td { border: 1px solid #d0d5dd; padding: 4px 8px; }
th { background: #f2f4f7; } img { max-width: 100%; } iframe { width: 100%; height: 80vh; border: 0; }
"""


def _preview_body(file_id: UUID, mime_type: str, raw: str | None) -> str:
    raw_url = f"/files/generated/{file_id}/raw"
    if mime_type == "application/pdf":
        return f'<iframe src="{raw_url}" title="PDF preview"></iframe>'
    if mime_type.startswith("image/"):
        return f'<img src="{raw_url}" alt="Generated image">'
    if mime_type == "text/csv" and raw is not None:
        rows = list(csv.reader(raw.splitlines()))[:500]
        if rows:
            head = "".join(f"<th>{html.escape(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    if mime_type == "application/json" and raw is not None:
        try:
            raw = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    if mime_type == "text/markdown" and raw is not None:
        # Model-written Markdown may contain raw HTML; the CSP below stops any script.
        return markdown.markdown(raw, extensions=["tables", "fenced_code", "sane_lists"])
    return f'<pre id="preview-text">{html.escape(raw or "")}</pre>'


@router.get("/generated/{file_id}/preview", response_class=HTMLResponse)
async def preview_generated_file(file_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Browser preview of a generated file.

    Security: the page renders user/model-provided content, so
    - every string is HTML-escaped (filenames included: uploads choose their own names), and
    - a Content-Security-Policy allows ONLY our own copy-button script (per-request nonce);
      a <script> or onerror= inside rendered Markdown is blocked by the browser (stored XSS).
    """
    file_record = await get_file(db, file_id)
    path = Path(file_record.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated file is missing from storage.")

    mime_type = (file_record.file_type or "").split(";")[0].strip().lower()
    raw = path.read_text(encoding="utf-8", errors="replace") if mime_type.startswith(("text/", "application/json")) else None
    nonce = secrets.token_urlsafe(16)
    name = html.escape(file_record.filename)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preview: {name}</title><style>{PREVIEW_CSS}</style></head>
<body>
  <div class="bar">
    <div><div class="title">{name}</div><div class="type">{html.escape(mime_type)}</div></div>
    <div class="actions">
      <a href="/files/generated/{file_id}/download">Download</a>
      <a href="/files/generated/{file_id}/raw" target="_blank" rel="noreferrer">Open raw</a>
      <button type="button" id="copy-btn">Copy text</button>
    </div>
  </div>
  <div class="content" id="preview-root">{_preview_body(file_id, mime_type, raw)}</div>
  <script nonce="{nonce}">
    document.getElementById('copy-btn').addEventListener('click', function () {{
      navigator.clipboard.writeText(document.getElementById('preview-root').innerText);
    }});
  </script>
</body></html>"""
    csp = (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}'; "
        "style-src 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; base-uri 'none'; form-action 'none'"
    )
    return HTMLResponse(content=page, headers={"Content-Security-Policy": csp, "X-Content-Type-Options": "nosniff"})
