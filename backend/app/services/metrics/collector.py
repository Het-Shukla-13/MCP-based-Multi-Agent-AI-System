"""
Per-turn metrics collection.

The collector for the CURRENT turn lives in a ContextVar. Async tasks inherit the
context they were created in, so code deep inside the agent loop or the LLM service
can record into the right turn without passing a collector through every call.
(Thread pools are the exception: see llm_service.get_llm_response_async.)
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from app.services.metrics.redaction import redact_args
from app.services.metrics.writer import metrics_writer


@dataclass
class TurnCollector:
    user_id: UUID
    conversation_id: UUID
    turn_id: UUID = field(default_factory=uuid4)
    started: float = field(default_factory=perf_counter)
    mode: str = "routed"
    context_ms: int = 0
    agent_started: float | None = None
    agent_ms: int = 0
    first_token_at: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_used: bool = False
    # Time spent waiting for the user to approve a tool. Excluded from latency
    # numbers (they measure the system, not how fast the user clicks).
    confirm_ms: int = 0
    _confirm_ms_at_first_token: int = 0
    _tool_wait_ms: dict[str, int] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    _open_tools: dict[str, tuple[float, dict]] = field(default_factory=dict)

    # ---- marks ----
    def mark_first_token(self) -> None:
        if self.first_token_at is None:
            self.first_token_at = perf_counter()
            self._confirm_ms_at_first_token = self.confirm_ms

    def add_confirmation_wait(self, call_id: str, ms: int) -> None:
        self.confirm_ms += ms
        if call_id:
            self._tool_wait_ms[call_id] = self._tool_wait_ms.get(call_id, 0) + ms

    def tool_started(self, call_id: str, name: str, args: dict | None) -> None:
        self._open_tools[call_id] = (perf_counter(), {"tool": name, "args": redact_args(args or {})})

    def tool_finished(self, call_id: str, name: str, ok: bool) -> None:
        started, info = self._open_tools.pop(call_id, (None, {"tool": name, "args": {}}))
        ms = int((perf_counter() - started) * 1000) if started else None
        if ms is not None:
            ms = max(0, ms - self._tool_wait_ms.pop(call_id, 0))
        self.tools.append({**info, "ms": ms, "ok": ok})

    def record_llm(self, *, purpose: str, model: str, input_tokens: int, output_tokens: int,
                   duration_ms: int | None = None, ok: bool = True) -> None:
        """Count tokens toward this turn and queue a per-call row."""
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0
        record_llm_call(purpose=purpose, model=model, input_tokens=input_tokens, output_tokens=output_tokens,
                        duration_ms=duration_ms, ok=ok, turn_id=self.turn_id, user_id=self.user_id)

    # ---- finish ----
    def finish(self, *, message_id: UUID | None, agent_name: str | None, error: bool) -> None:
        now = perf_counter()
        tool_ms = sum(t["ms"] or 0 for t in self.tools)
        metrics_writer.put("turn", {
            "turn_id": self.turn_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "message_id": message_id,
            "agent_name": agent_name,
            "mode": self.mode,
            "total_ms": max(0, int((now - self.started) * 1000) - self.confirm_ms),
            "ttft_ms": (max(0, int((self.first_token_at - self.started) * 1000) - self._confirm_ms_at_first_token)
                        if self.first_token_at else None),
            "confirm_ms": self.confirm_ms,
            "context_ms": self.context_ms,
            "agent_ms": self.agent_ms,
            "tool_calls": len(self.tools),
            "tool_ms": tool_ms,
            "tools": self.tools,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "fallback_used": self.fallback_used,
            "error": error,
        })


current_turn: ContextVar[TurnCollector | None] = ContextVar("current_turn", default=None)


def record_llm_call(*, purpose: str, model: str, input_tokens: int | None, output_tokens: int | None,
                    duration_ms: int | None = None, ok: bool = True,
                    turn_id: UUID | None = None, user_id: UUID | None = None) -> None:
    metrics_writer.put("llm_call", {
        "turn_id": turn_id, "user_id": user_id, "purpose": purpose[:80], "model": model or "unknown",
        "input_tokens": input_tokens or 0, "output_tokens": output_tokens or 0,
        "duration_ms": duration_ms, "ok": ok,
    })


def _tool_succeeded(result: Any) -> bool:
    """
    MCP results carry an explicit boolean: {'content': [...], 'isError': False}.
    Use it. (Searching the text for "error" was wrong: every MCP result contains
    the key 'isError', even successful ones.)
    """
    if isinstance(result, dict):
        if "isError" in result:
            return not bool(result["isError"])
        if "error" in result:  # ADK reports tool exceptions as {"error": ...}
            return False
    return True


def observe_adk_event(event: Any, model: str | None = None) -> None:
    """
    Feed one ADK event into the current turn (no-op outside a turn).
    `model`: the model the caller configured; streamed events often omit model_version.
    """
    turn = current_turn.get()
    if turn is None:
        return
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    if getattr(event, "partial", False):
        if any(getattr(p, "text", None) for p in parts) and event.author != "root":
            turn.mark_first_token()
        return
    for part in parts:
        call = getattr(part, "function_call", None)
        if call is not None and call.name != "transfer_to_agent":
            turn.tool_started(call.id or call.name, call.name, dict(call.args or {}))
        response = getattr(part, "function_response", None)
        if response is not None and response.name != "transfer_to_agent":
            turn.tool_finished(response.id or response.name, response.name, _tool_succeeded(response.response))
    # Usage arrives on the final (non-partial) model event; counting partials would double it.
    usage = getattr(event, "usage_metadata", None)
    if usage is not None and (usage.prompt_token_count or usage.candidates_token_count):
        if any(getattr(p, "text", None) for p in parts) and event.author != "root":
            turn.mark_first_token()  # non-streaming mode: first text = whole answer
        turn.record_llm(
            purpose="router" if event.author == "root" else f"agent:{event.author}",
            model=getattr(event, "model_version", None) or model or "unknown",
            input_tokens=usage.prompt_token_count or 0,
            output_tokens=usage.candidates_token_count or 0,
        )
