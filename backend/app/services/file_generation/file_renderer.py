"""Rendering helpers for generated files (artifacts MCP server + generated-file endpoints)."""

import io
import re
from datetime import datetime
from pathlib import Path

import fitz

MIME_TYPES: dict[str, str] = {
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "png": "image/png",
}


def get_mime_type(output_format: str) -> str:
    return MIME_TYPES.get(output_format, "application/octet-stream")


def format_from_path(path: Path) -> str:
    return path.suffix.lower().lstrip(".").replace("jpeg", "jpg")


def filename_timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def slugify(text: str, fallback: str = "generated-file") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return cleaned[:80].strip("-") or fallback


PDF_CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.45; color: #222; }
h1 { font-size: 20pt; margin: 0 0 8pt 0; }
h2 { font-size: 15pt; margin: 14pt 0 6pt 0; }
h3 { font-size: 12.5pt; margin: 10pt 0 4pt 0; }
p, li { margin: 0 0 5pt 0; }
table { border-collapse: collapse; margin: 6pt 0; }
th, td { border: 1px solid #999; padding: 3pt 6pt; font-size: 10pt; }
th { background-color: #eee; }
code, pre { font-family: monospace; font-size: 9.5pt; }
pre { background-color: #f4f4f4; padding: 6pt; }
"""


def render_markdown_pdf(title: str, markdown_text: str) -> bytes:
    """
    Markdown -> HTML -> PDF with PyMuPDF's Story layout engine: real headings, lists,
    tables and code blocks (the old renderer printed '#' and '|' literally).
    """
    import markdown as md

    body = md.markdown(markdown_text, extensions=["tables", "fenced_code", "sane_lists"])
    if title and not markdown_text.lstrip().startswith("# "):
        body = f"<h1>{title}</h1>\n{body}"
    story = fitz.Story(html=body, user_css=PDF_CSS)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    page_rect = fitz.paper_rect("a4")
    content_rect = page_rect + (48, 48, -48, -48)  # margins
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
    writer.close()
    data = buffer.getvalue()
    if not data or fitz.open("pdf", data).page_count == 0:
        raise ValueError("PDF rendering failed.")
    return data
