"""
Human-in-the-loop confirmation for tools with side effects.

Policy lives here (which tools, what the model is told); transport lives in the
TurnRunner (it asks the connected client and waits). They meet through a
ContextVar: the runner publishes a ``Confirmer`` for the turn it is running, and
the agent's async before_tool_callback awaits it.

No confirmer in the context (evals, the HTTP endpoint, tests) = no human to ask:
the call proceeds, exactly as before this feature.

Why not ADK's built-in ``require_confirmation``? It ends the run and expects the
client to resume the SAME ADK session with a FunctionResponse. Our ADK sessions
are throwaway per request (our DB is the history) and a turn may be retried on a
fallback model, so keeping sessions alive across socket messages would be
awkward. It also only knows approve/reject. Awaiting inside the callback keeps
the turn one continuous run and supports "revise with feedback".
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Awaitable, Callable, Collection

# Tools that create something the user will see/download. Read-only tools never ask.
CONFIRMATION_REQUIRED = frozenset({"create_file", "create_from_template", "generate_image"})

ACTIONS = frozenset({"approve", "approve_all", "reject", "revise"})
PREVIEW_CHARS = 1500
MAX_FEEDBACK_CHARS = 1000


@dataclass(frozen=True)
class Decision:
    action: str  # approve | approve_all | reject | revise | expired
    feedback: str = ""


# (agent, tool, args, call_id) -> Decision
Confirmer = Callable[[str, str, dict, str], Awaitable[Decision]]

current_confirmer: ContextVar[Confirmer | None] = ContextVar("current_confirmer", default=None)


def needs_confirmation(tool_name: str) -> bool:
    return tool_name in CONFIRMATION_REQUIRED


def preview_args(args: dict, hidden: Collection[str] = ()) -> dict:
    """What the user is shown: no identity args, long text truncated."""
    preview = {}
    for key, value in args.items():
        if key in hidden:
            continue
        if isinstance(value, str) and len(value) > PREVIEW_CHARS:
            value = value[:PREVIEW_CHARS] + f"… ({len(value) - PREVIEW_CHARS} more characters)"
        preview[key] = value
    return preview


def tool_response_for(tool_name: str, decision: Decision) -> dict | None:
    """
    None -> run the tool. A dict -> ADK skips the tool and hands this dict to the
    model AS the tool's result, so the model reads the user's decision and adapts.
    """
    if decision.action in ("approve", "approve_all"):
        return None
    if decision.action == "revise":
        return {
            "status": "revision_requested",
            "user_feedback": decision.feedback,
            "instruction": (
                f"The user reviewed this {tool_name} call and asked for changes: "
                f"\"{decision.feedback}\". Apply the feedback to the arguments and call "
                f"{tool_name} again (the user will review it again)."
            ),
        }
    reason = "did not respond in time" if decision.action == "expired" else "declined"
    return {
        "status": "rejected",
        "instruction": (
            f"The user {reason} this {tool_name} call, so nothing was created. Do not call "
            f"{tool_name} again in this turn. Answer in the chat instead and mention briefly "
            "that no file/image was created."
        ),
    }
