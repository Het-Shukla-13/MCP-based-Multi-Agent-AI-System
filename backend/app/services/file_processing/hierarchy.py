"""
Parent/child chunking for documents (PDF, DOCX, Markdown, TXT).

Small chunks match precisely; big chunks give the model enough context to
answer. Parent/child gets both:

- a logical unit (a section, or a whole TXT file) is split into PARENTS of at
  most PARENT_MAX_CHARS on paragraph / table-row boundaries;
- each parent is split into CHILDREN of about CHILD_MAX_CHARS;
- children are embedded and keyword-indexed (what we SEARCH);
- the matched child's parent is what the agent READS.

Tables: a Markdown table is split by rows and every parent/child repeats the
header row, so "| HX-3127-C | Seal kit | 156.70 EUR | R15-06 |" still says
which column is the price. Before this, a whole 300-row table was ONE chunk:
far past the embedding model's input limit, and the entire table was injected
into the prompt whenever it matched.
"""
from __future__ import annotations

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

PARENT_MAX_CHARS = 1500
CHILD_MAX_CHARS = 400
CHILD_OVERLAP = 80

_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")
_child_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHILD_MAX_CHARS, chunk_overlap=CHILD_OVERLAP, separators=["\n\n", "\n", ". ", " ", ""]
)
_long_paragraph_splitter = RecursiveCharacterTextSplitter(
    chunk_size=PARENT_MAX_CHARS, chunk_overlap=0, separators=["\n", ". ", " ", ""]
)


def _segments(text: str) -> list[tuple[str, str | None]]:
    """(segment, table_header) pairs: paragraphs, or single table rows with their header."""
    segments: list[tuple[str, str | None]] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        lines = paragraph.split("\n")
        table_at = next((i for i in range(len(lines) - 1)
                         if lines[i].lstrip().startswith("|") and _TABLE_SEPARATOR.match(lines[i + 1])), None)
        if table_at is not None:
            if table_at:  # text right above the table (no blank line in between)
                segments.extend(_plain("\n".join(lines[:table_at])))
            header = "\n".join(lines[table_at:table_at + 2])
            segments.extend((row, header) for row in lines[table_at + 2:] if row.strip())
        else:
            segments.extend(_plain(paragraph))
    return segments


def _plain(paragraph: str) -> list[tuple[str, None]]:
    if len(paragraph) <= PARENT_MAX_CHARS:
        return [(paragraph, None)]
    return [(piece, None) for piece in _long_paragraph_splitter.split_text(paragraph)]


def split_parents(text: str, max_chars: int = PARENT_MAX_CHARS) -> list[str]:
    """Greedy packing of segments; a table and prose never share a parent."""
    parents: list[str] = []
    current: list[str] = []
    current_header: str | None = None
    size = 0

    def flush():
        nonlocal current, size
        if current:
            body = "\n".join(current) if current_header else "\n\n".join(current)
            parents.append(f"{current_header}\n{body}" if current_header else body)
        current, size = [], 0

    for segment, header in _segments(text):
        budget = max_chars - (len(header) + 1 if header else 0)
        if current and (header != current_header or size + len(segment) + 2 > budget):
            flush()
        current_header = header
        current.append(segment)
        size += len(segment) + 2
    flush()
    return parents


def split_children(parent: str) -> list[str]:
    lines = parent.split("\n")
    if len(lines) > 2 and lines[0].lstrip().startswith("|") and _TABLE_SEPARATOR.match(lines[1]):
        header, rows = "\n".join(lines[:2]), lines[2:]
        children, current = [], []
        for row in rows:
            if current and len(header) + sum(len(r) + 1 for r in current) + len(row) > CHILD_MAX_CHARS:
                children.append(header + "\n" + "\n".join(current))
                current = []
            current.append(row)
        if current:
            children.append(header + "\n" + "\n".join(current))
        return children
    if len(parent) <= CHILD_MAX_CHARS:
        return [parent]
    return _child_splitter.split_text(parent)


def build_hierarchy(units: list[dict]) -> list[dict]:
    """
    units: [{"content": section text, "metadata": {...}}] (one per logical section)
    returns child chunks: {"content", "metadata" (+ parent_key, child_index), "parent_content"}
    """
    chunks: list[dict] = []
    for unit_index, unit in enumerate(units):
        content = (unit.get("content") or "").strip()
        if not content:
            continue
        for parent_index, parent in enumerate(split_parents(content)):
            parent_key = f"{unit_index}:{parent_index}"
            for child_index, child in enumerate(split_children(parent)):
                if child.strip():
                    chunks.append({
                        "content": child.strip(),
                        "metadata": {**(unit.get("metadata") or {}), "parent_key": parent_key, "child_index": child_index},
                        "parent_content": parent,
                    })
    return chunks
