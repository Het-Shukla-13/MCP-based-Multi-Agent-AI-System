"""
Artifacts MCP server: turn content the agent wrote into a downloadable file.

Replaces the old "pre-flight" file-generation path, which ran a keyword check and
often an extra LLM call on EVERY chat message and bypassed the agents entirely.
"""

import csv
import io
import json

from mcp.server.fastmcp import FastMCP

from app.mcp_servers.common import configure_server_logging, save_generated_file
from app.services.file_generation.file_renderer import filename_timestamp, render_markdown_pdf, slugify
from app.services.file_generation.templates import describe_templates, render_template

configure_server_logging("artifacts")
mcp = FastMCP("artifacts")

FORMATS = {
    "md": "text/markdown",
    "txt": "text/plain",
    "json": "application/json",
    "csv": "text/csv",
    "pdf": "application/pdf",
}



def file_stem(title: str) -> str:
    """Slug for the filename. Models often pass "notes.md" as the title; drop a known
    extension first so the file isn't named "notes-md.md"."""
    stem, dot, ext = title.strip().rpartition(".")
    if dot and stem and ext.lower() in FORMATS:
        title = stem
    return slugify(title)

@mcp.tool()
async def create_file(title: str, file_format: str, content: str, user_id: str = "", conversation_id: str = "") -> str:
    """Save content as a downloadable file. file_format: md, txt, json, csv or pdf.
    - md/txt/pdf: write the full document as Markdown (headings, lists, tables are rendered in PDF).
    - json: a valid JSON document.  - csv: comma-separated rows with a header line.
    Returns the download link to share with the user. user_id/conversation_id are filled in automatically."""
    fmt = file_format.lower().lstrip(".")
    if fmt not in FORMATS:
        return f"file_format must be one of {sorted(FORMATS)}"
    if not content.strip():
        return "content is empty."

    # Validate before saving so the user never downloads a broken file.
    if fmt == "json":
        try:
            content = json.dumps(json.loads(content), indent=2, ensure_ascii=False)
        except json.JSONDecodeError as exc:
            return f"Invalid JSON (line {exc.lineno}): {exc.msg}. Fix the content and call create_file again."
    if fmt == "csv":
        rows = list(csv.reader(io.StringIO(content.strip())))
        widths = {len(r) for r in rows if r}
        if len(rows) < 2 or len(widths) != 1:
            return "Invalid CSV: needs a header plus rows, all with the same number of columns."

    data = render_markdown_pdf(title, content) if fmt == "pdf" else content.encode("utf-8")
    saved = await save_generated_file(
        user_id, conversation_id, f"{filename_timestamp()}_{file_stem(title)}.{fmt}", data, FORMATS[fmt]
    )
    return f"File created: {saved['filename']}\n{saved}"


@mcp.tool()
async def list_templates() -> str:
    """List the document templates (report, meeting_notes, study_notes, comparison, email)
    with their required and optional fields. Call before create_from_template."""
    return describe_templates()


@mcp.tool()
async def create_from_template(template: str, title: str, fields: dict[str, str], file_format: str = "pdf",
                               user_id: str = "", conversation_id: str = "") -> str:
    """Create a consistently structured document from a template. `fields` maps field names to
    Markdown content written from the conversation (see list_templates). The date and title
    are added automatically. file_format: pdf, md or txt.
    user_id/conversation_id are filled in automatically."""
    fmt = file_format.lower().lstrip(".")
    if fmt not in {"pdf", "md", "txt"}:
        return "file_format must be pdf, md or txt for templates."
    try:
        markdown_text = render_template(template, title, fields)
    except ValueError as exc:
        return f"{exc}. Fix the fields and call create_from_template again."
    data = render_markdown_pdf("", markdown_text) if fmt == "pdf" else markdown_text.encode("utf-8")
    saved = await save_generated_file(
        user_id, conversation_id, f"{filename_timestamp()}_{file_stem(title)}.{fmt}", data, FORMATS[fmt]
    )
    return f"File created from template '{template}': {saved['filename']}\n{saved}"


if __name__ == "__main__":
    mcp.run()
