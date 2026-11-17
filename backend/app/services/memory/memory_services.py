"""
Short-term memory (STM): the recent-history view of a conversation + a rolling summary.

Hot path (every turn): compact_history() builds the view with NO LLM call
(layers L0-L2, L4 in compaction.py) and uses the rolling summary as it is.

Background (after the turn): refresh_rolling_summary() folds the messages that
left the view and aren't summarised yet into the summary (layer L3), and moves
the `summarized_until` marker so each message is summarised once.

STM state lives in conversation.convo_metadata["stm"]. The turn and the
background job write DIFFERENT keys through atomic JSONB patches, so neither can
overwrite the other's update.
"""
from datetime import datetime

from loguru import logger

from app.services.memory.compaction import (
    HISTORY_TOKEN_BUDGET,
    CompactionResult,
    ViewMessage,
    compact_history,
    unsummarized,
)
from app.services.summarization.summarization_service import (
    is_valid_summary,
    normalize_summary,
    summarize_messages,
)
from app.services.time.timing import log_async_timing

SUMMARY_PREFIX = "Compressed memory from earlier conversation."
# Keys each writer owns inside convo_metadata["stm"].
TURN_KEYS = ("last_token_usage", "last_dropped_count", "recent_message_count", "pending_summary", "compaction_layers")
SUMMARY_KEYS = ("rolling_summary", "summarized_until", "summary_update_count")


def get_stm_state(convo_metadata: dict | None) -> dict:
    if not convo_metadata:
        return {}
    stm_state = convo_metadata.get("stm")
    return stm_state if isinstance(stm_state, dict) else {}


def build_summary_message(rolling_summary: str) -> ViewMessage | None:
    if not rolling_summary:
        return None
    return ViewMessage(
        id=None,
        role="system",
        content=(
            f"{SUMMARY_PREFIX}\n"
            "Use it only as background context. Prefer the newer raw messages when they conflict.\n"
            "Do not switch into meta commentary just because this summary exists.\n\n"
            f"{rolling_summary}"
        ),
    )


@log_async_timing("build_smart_history")
async def build_smart_history(messages, convo_metadata: dict | None = None, max_tokens: int = HISTORY_TOKEN_BUDGET):
    """
    -> (history view incl. summary pseudo-message, turn-owned STM patch, CompactionResult).
    No LLM call: if messages left the view unsummarised, `pending_summary` asks the
    background job to summarise them after this turn.
    """
    stm_state = get_stm_state(convo_metadata)
    result: CompactionResult = compact_history(messages, budget=max_tokens)
    pending = unsummarized(result.dropped, stm_state.get("summarized_until"))

    stm_patch = {
        "last_token_usage": result.tokens_after,
        "last_dropped_count": len(result.dropped),
        "recent_message_count": len(result.messages),
        "pending_summary": bool(pending),
        "compaction_layers": result.layers,
    }
    if result.layers != ["L0"]:
        logger.info("STM compaction | layers={} | tokens {} -> {} | dropped={} | unsummarized={}",
                    result.layers, result.tokens_before, result.tokens_after, len(result.dropped), len(pending))

    history = list(result.messages)
    summary_message = build_summary_message(stm_state.get("rolling_summary", ""))
    if summary_message:
        history = [summary_message] + history
    return history, stm_patch, result


async def refresh_rolling_summary(db, conversation_id, messages, convo_metadata: dict | None) -> bool:
    """
    L3, run in the background after a turn: summarise only the dropped messages
    newer than `summarized_until`, then patch the summary keys atomically.
    Returns True when the summary changed.
    """
    from app.crud.conversation import patch_conversation_metadata

    stm_state = get_stm_state(convo_metadata)
    result = compact_history(messages)
    todo = unsummarized(result.dropped, stm_state.get("summarized_until"))
    if not todo:
        return False
    existing = stm_state.get("rolling_summary", "")
    candidate = normalize_summary(await summarize_messages(todo, existing_summary=existing))
    if not is_valid_summary(candidate):
        logger.warning("STM summary rejected | messages={} | preview={}", len(todo), candidate[:200])
        return False
    newest = max((m.created_at for m in todo if m.created_at), default=None)
    await patch_conversation_metadata(db, conversation_id, {
        "rolling_summary": candidate,
        "summarized_until": (newest or datetime.utcnow()).isoformat(),
        "summary_update_count": int(stm_state.get("summary_update_count", 0)) + 1,
        "pending_summary": False,
    }, under="stm")
    logger.info("STM summary refreshed | conversation={} | folded_messages={} | chars={}",
                conversation_id, len(todo), len(candidate))
    return True
