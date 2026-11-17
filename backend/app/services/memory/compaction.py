"""
Layered compaction of the conversation history the agent sees (view-only).

Cheapest layer first; stop as soon as the history fits HISTORY_TOKEN_BUDGET:

  L0  fits already                       -> nothing to do
  L1  trim OLDER oversized messages       -> free: collapse long code blocks, then head+tail
  L2  drop the oldest messages            -> free: the rolling summary stands in for them
  L3  rolling summary of dropped messages -> one LLM call, AFTER the turn, in the background
  L4  hard-cap even the newest messages   -> last resort (e.g. a 50k-character paste)

View-only: the input messages are never modified. The functions build
ViewMessage copies. (Assigning message.content on a loaded ORM object would mark
it dirty and the next commit would silently rewrite the stored message.)

Before this, the history kept the last 10 messages whatever their size, and the
summary was generated synchronously on the hot path for ALL messages outside the
window on every turn (re-summarising the same messages again and again).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from app.services.tokenization.tokenizer import get_token_count

HISTORY_TOKEN_BUDGET = 2600
KEEP_FULL_MESSAGES = 2  # the latest exchange stays verbatim (up to the L4 cap)
OLD_MESSAGE_MAX_TOKENS = 350  # L1 cap for older messages
NEWEST_MESSAGE_MAX_TOKENS = 1200  # L4 cap for any message
CODE_BLOCK_KEEP_LINES = 6

_CODE_BLOCK = re.compile(r"```([^\n]*)\n(.*?)```", re.S)


@dataclass
class ViewMessage:
    id: Any
    role: str
    content: str
    created_at: datetime | None = None
    tokens: int = 0
    compacted: bool = False


@dataclass
class CompactionResult:
    messages: list[ViewMessage]
    dropped: list[ViewMessage] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    tokens_before: int = 0
    tokens_after: int = 0


def _tokens(message: ViewMessage) -> int:
    return get_token_count(message.content)


def to_view(messages: Iterable[Any]) -> list[ViewMessage]:
    view = []
    for m in messages:
        content = getattr(m, "content", "") or ""
        cached = getattr(m, "token_count", None)
        view.append(ViewMessage(id=getattr(m, "id", None), role=getattr(m, "role", ""), content=content,
                                created_at=getattr(m, "created_at", None),
                                tokens=cached if cached is not None else get_token_count(content)))
    return view


def collapse_code_blocks(text: str, keep_lines: int = CODE_BLOCK_KEEP_LINES) -> str:
    def shorten(match: re.Match) -> str:
        lang, body = match.group(1), match.group(2)
        lines = body.rstrip("\n").split("\n")
        if len(lines) <= keep_lines:
            return match.group(0)
        kept = "\n".join(lines[:keep_lines])
        return f"```{lang}\n{kept}\n# … {len(lines) - keep_lines} more lines omitted (earlier in this chat)\n```"
    return _CODE_BLOCK.sub(shorten, text)


def head_tail(text: str, max_tokens: int) -> str:
    """Keep the start and the end (where questions and conclusions usually are)."""
    if get_token_count(text) <= max_tokens:
        return text
    budget_chars = max(200, max_tokens * 4)  # ~4 chars/token, refined below
    head, tail = text[: budget_chars * 2 // 3], text[-budget_chars // 3:]
    omitted = len(text) - len(head) - len(tail)
    trimmed = f"{head.rstrip()}\n[… {omitted:,} characters omitted …]\n{tail.lstrip()}"
    while get_token_count(trimmed) > max_tokens and len(head) > 100:
        head, tail = head[: int(len(head) * 0.85)], tail[-int(len(tail) * 0.85):]
        omitted = len(text) - len(head) - len(tail)
        trimmed = f"{head.rstrip()}\n[… {omitted:,} characters omitted …]\n{tail.lstrip()}"
    return trimmed


def _shrink(message: ViewMessage, max_tokens: int) -> ViewMessage:
    content = collapse_code_blocks(message.content)
    if get_token_count(content) > max_tokens:
        content = head_tail(content, max_tokens)
    return ViewMessage(message.id, message.role, content, message.created_at, get_token_count(content), True)


def compact_history(messages: Iterable[Any], budget: int = HISTORY_TOKEN_BUDGET) -> CompactionResult:
    view = to_view(messages)
    before = sum(m.tokens for m in view)
    result = CompactionResult(messages=view, tokens_before=before, tokens_after=before)
    total = lambda: sum(m.tokens for m in result.messages)  # noqa: E731

    if before <= budget:
        result.layers.append("L0")
        return result

    # L1: older oversized messages -> collapsed code + head/tail
    older = len(result.messages) - KEEP_FULL_MESSAGES
    changed = False
    for i in range(max(0, older)):
        if result.messages[i].tokens > OLD_MESSAGE_MAX_TOKENS:
            result.messages[i] = _shrink(result.messages[i], OLD_MESSAGE_MAX_TOKENS)
            changed = True
    if changed:
        result.layers.append("L1")

    # L2: drop the oldest (the rolling summary covers them)
    while total() > budget and len(result.messages) > KEEP_FULL_MESSAGES:
        result.dropped.append(result.messages.pop(0))
    if result.dropped:
        result.layers.append("L2")
        # A history must not start with an orphaned assistant reply.
        while len(result.messages) > KEEP_FULL_MESSAGES and result.messages[0].role == "assistant":
            result.dropped.append(result.messages.pop(0))

    # L4: even the newest messages are too big
    if total() > budget:
        result.messages = [m if m.tokens <= NEWEST_MESSAGE_MAX_TOKENS else _shrink(m, NEWEST_MESSAGE_MAX_TOKENS)
                           for m in result.messages]
        result.layers.append("L4")

    result.tokens_after = total()
    return result


def unsummarized(dropped: list[ViewMessage], summarized_until: str | None) -> list[ViewMessage]:
    """Dropped messages the rolling summary doesn't cover yet (L3 work for the background)."""
    if not summarized_until:
        return list(dropped)
    cutoff = datetime.fromisoformat(summarized_until)
    return [m for m in dropped if m.created_at is None or m.created_at > cutoff]
