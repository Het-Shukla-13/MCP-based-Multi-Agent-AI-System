"""
Files MCP server: lets agents list, search and read the user's uploaded files.

Run: python -m app.mcp_servers.files_server   (started automatically by the app)

user_id / conversation_id are injected by the agent layer (before_tool_callback)
and overwrite whatever the model passes, so a prompt cannot reach other users' files.
"""

import os

import pandas as pd
from app.services.file_processing.tabular import read_csv_robust
from mcp.server.fastmcp import FastMCP

from app.db.database import AsyncSessionLocal
from app.mcp_servers.common import (
    configure_server_logging,
    get_owned_files,
    match_file,
    parse_uuid,
    truncate,
)
from app.services.rag.retriever import retrieve_pipeline

configure_server_logging("files")
mcp = FastMCP("files")

def _extract_text(path: str, ext: str) -> str:
    if ext == ".pdf":
        import pymupdf4llm
        return pymupdf4llm.to_markdown(path)
    if ext == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(path).paragraphs)
    if ext == ".csv":
        return read_csv_robust(path).head(200).to_csv(index=False)
    if ext == ".xlsx":
        sheets = pd.read_excel(path, sheet_name=None)
        return "\n\n".join(f"## Sheet: {name}\n{df.head(200).to_csv(index=False)}" for name, df in sheets.items())
    if ext in {".jpg", ".jpeg", ".png"}:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(path).convert("RGB"))
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


@mcp.tool()
async def list_files(user_id: str = "", conversation_id: str = "") -> str:
    """List the files the user uploaded in this conversation (name, type, size, processing status).
    user_id and conversation_id are filled in automatically; pass empty strings."""
    async with AsyncSessionLocal() as db:
        files = await get_owned_files(db, parse_uuid(user_id, "user_id"), parse_uuid(conversation_id, "conversation_id"))
    if not files:
        return "No files have been uploaded in this conversation."
    lines = [f"- {f.filename} | {f.file_type} | {round(f.file_size / 1024, 1)} KB | {f.status}" for f in files]
    return "Uploaded files:\n" + "\n".join(lines)


@mcp.tool()
async def search_files(query: str, file_name: str = "", top_k: int = 6, user_id: str = "", conversation_id: str = "") -> str:
    """Semantic search over the user's uploaded files. Returns the most relevant passages.
    Use file_name to restrict the search to one file. user_id and conversation_id are filled in automatically."""
    uid, cid = parse_uuid(user_id, "user_id"), parse_uuid(conversation_id, "conversation_id")
    async with AsyncSessionLocal() as db:
        files = await get_owned_files(db, uid, cid)
        file_ids = []
        if file_name:
            target = match_file(files, file_name)
            if target is None:
                return f"No uploaded file matches '{file_name}'. Use list_files to see the available files."
            file_ids = [target.id]
        context = await retrieve_pipeline(query, file_ids, cid, uid, db)
    return truncate(context or "No relevant passages found in the uploaded files.")


@mcp.tool()
async def read_file(file_name: str, max_chars: int = 8000, user_id: str = "", conversation_id: str = "") -> str:
    """Read the text content of one uploaded file (PDF, DOCX, TXT, MD, code, CSV/XLSX preview, image OCR).
    Prefer search_files for large files. user_id and conversation_id are filled in automatically."""
    uid, cid = parse_uuid(user_id, "user_id"), parse_uuid(conversation_id, "conversation_id")
    async with AsyncSessionLocal() as db:
        files = await get_owned_files(db, uid, cid)
    target = match_file(files, file_name)
    if target is None:
        return f"No uploaded file matches '{file_name}'. Use list_files to see the available files."
    if not os.path.exists(target.storage_path):
        return f"The file '{target.filename}' is no longer available on the server."
    text = _extract_text(target.storage_path, os.path.splitext(target.filename)[1].lower())
    return f"# {target.filename}\n\n" + truncate(text, max(500, min(max_chars, 20_000)))


if __name__ == "__main__":
    mcp.run()  # stdio transport
