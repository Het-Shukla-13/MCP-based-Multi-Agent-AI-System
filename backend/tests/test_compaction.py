"""Layered, view-only history compaction + background summary + atomic metadata patches."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.memory import memory_services
from app.services.memory.compaction import (
    KEEP_FULL_MESSAGES,
    NEWEST_MESSAGE_MAX_TOKENS,
    OLD_MESSAGE_MAX_TOKENS,
    collapse_code_blocks,
    compact_history,
    head_tail,
    unsummarized,
)
from app.services.tokenization.tokenizer import get_token_count

T0 = datetime(2026, 11, 1, 9, 0)


def msg(i, role, content):
    return SimpleNamespace(id=uuid4(), role=role, content=content, created_at=T0 + timedelta(minutes=i), token_count=None)


def chat(n, size=40):
    return [msg(i, "user" if i % 2 == 0 else "assistant", f"message {i} " + "word " * size) for i in range(n)]


def test_l0_small_history_is_untouched():
    result = compact_history(chat(6), budget=2600)
    assert result.layers == ["L0"] and not result.dropped
    assert len(result.messages) == 6 and not any(m.compacted for m in result.messages)


def test_l1_trims_old_big_messages_but_keeps_the_latest_exchange_verbatim():
    history = chat(6)
    history[1].content = "Here is the report:\n" + "detail " * 3000  # old huge paste
    history[-1].content = "latest answer " + "x " * 200
    result = compact_history(history, budget=2600)
    assert "L1" in result.layers and not result.dropped
    assert result.messages[1].compacted and result.messages[1].tokens <= OLD_MESSAGE_MAX_TOKENS
    assert "characters omitted" in result.messages[1].content
    assert result.messages[-1].content == history[-1].content  # newest kept as-is
    assert result.tokens_after <= 2600


def test_old_code_blocks_are_collapsed_before_anything_else():
    code = "```python\n" + "\n".join(f"line_{i} = {i}" for i in range(80)) + "\n```"
    collapsed = collapse_code_blocks(f"Fixed version:\n{code}\nDone.")
    assert "line_5 = 5" in collapsed and "line_40" not in collapsed
    assert "74 more lines omitted" in collapsed and collapsed.endswith("Done.")
    assert collapse_code_blocks("```\nshort\n```") == "```\nshort\n```"


def test_l2_drops_oldest_and_never_starts_with_an_orphan_assistant_reply():
    result = compact_history(chat(60, size=60), budget=1000)
    assert "L2" in result.layers and result.dropped
    assert result.tokens_after <= 1000
    assert result.messages[0].role == "user"
    assert len(result.messages) >= KEEP_FULL_MESSAGES


def test_order_and_identity_preserved_across_dropped_and_kept():
    history = chat(40, size=60)
    result = compact_history(history, budget=1200)
    assert [m.id for m in result.dropped + result.messages] == [m.id for m in history]


def test_l4_caps_even_the_newest_message():
    history = chat(2)
    history[-1].content = "pasted log:\n" + "ERROR something failed\n" * 4000
    result = compact_history(history, budget=2600)
    assert "L4" in result.layers
    assert result.messages[-1].tokens <= NEWEST_MESSAGE_MAX_TOKENS
    assert result.messages[-1].content.startswith("pasted log:")  # head kept
    assert result.messages[-1].content.rstrip().endswith("ERROR something failed")  # tail kept


def test_view_only_input_objects_are_never_modified():
    history = chat(30, size=200)
    before = [m.content for m in history]
    compact_history(history, budget=800)
    assert [m.content for m in history] == before


def test_head_tail_respects_the_token_cap():
    text = "start " + "filler " * 5000 + " end"
    out = head_tail(text, 300)
    assert get_token_count(out) <= 300 and out.startswith("start") and out.endswith("end")


def test_unsummarized_uses_the_marker():
    history = chat(10)
    marker = history[3].created_at.isoformat()
    assert [m.id for m in unsummarized(compact_history(history, 10).dropped, marker)] == \
        [m.id for m in compact_history(history, 10).dropped if m.created_at > history[3].created_at]
    assert len(unsummarized(compact_history(history, 10).dropped, None)) == len(compact_history(history, 10).dropped)


@pytest.mark.asyncio
async def test_hot_path_never_calls_the_llm(monkeypatch):
    async def boom(*_, **__):
        raise AssertionError("summary must not run on the hot path")

    monkeypatch.setattr(memory_services, "summarize_messages", boom)
    history, patch, result = await memory_services.build_smart_history(
        chat(60, size=80), {"stm": {"rolling_summary": "Earlier: user is planning a trip.", "summarized_until": None}})
    assert history[0].role == "system" and "planning a trip" in history[0].content
    assert patch["pending_summary"] is True and "L2" in patch["compaction_layers"]
    assert set(patch) == set(memory_services.TURN_KEYS)  # the turn never writes summary keys


@pytest.mark.asyncio
async def test_background_summary_folds_only_new_messages_once(monkeypatch):
    seen, patches = [], []

    async def fake_summarize(messages, existing_summary=""):
        seen.append([m.content.split()[1] for m in messages])
        return "Summary: " + " ".join(m.content.split()[1] for m in messages)

    async def fake_patch(db, conversation_id, patch, under=None):
        patches.append((under, patch))

    monkeypatch.setattr(memory_services, "summarize_messages", fake_summarize)
    monkeypatch.setattr(memory_services, "normalize_summary", lambda s: s)
    monkeypatch.setattr(memory_services, "is_valid_summary", lambda s: True)
    monkeypatch.setattr("app.crud.conversation.patch_conversation_metadata", fake_patch)

    history = chat(60, size=80)
    assert await memory_services.refresh_rolling_summary(None, "c", history, {}) is True
    under, patch = patches[-1]
    assert under == "stm" and set(patch) >= set(memory_services.SUMMARY_KEYS)
    # Run again with the stored marker: nothing new left the view -> no LLM call.
    calls = len(seen)
    assert await memory_services.refresh_rolling_summary(None, "c", history, {"stm": patch}) is False
    assert len(seen) == calls


# ---- atomic JSONB patch (real Postgres) -------------------------------------------

def _db_available() -> bool:
    try:
        from sqlalchemy import text

        from app.db.database import sync_session_scope
        with sync_session_scope() as db:
            db.execute(text("select 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _db_available(), reason="needs the Postgres container")
@pytest.mark.asyncio
async def test_patches_never_lose_a_concurrent_update():
    from sqlalchemy import delete, select, text

    from app.crud.conversation import patch_conversation_metadata
    from app.db.database import AsyncSessionLocal, engine
    from app.models import Conversation, User

    await engine.dispose()  # pytest-asyncio gives each test its own loop
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        conversation = Conversation(title="patch test", user_id=user.id, convo_metadata={"stm": {"rolling_summary": "old"}})
        db.add(conversation)
        await db.commit()
        cid = conversation.id
    try:
        # Three writers (turn STM keys, background summary, turn agent state), each
        # with its own session, all at once. Whole-dict writes would lose two of them.
        async with AsyncSessionLocal() as turn_db, AsyncSessionLocal() as bg_db, AsyncSessionLocal() as agent_db:
            await asyncio.gather(
                patch_conversation_metadata(turn_db, cid, {"last_token_usage": 900, "pending_summary": True}, under="stm"),
                patch_conversation_metadata(bg_db, cid, {"rolling_summary": "new summary"}, under="stm"),
                patch_conversation_metadata(agent_db, cid, {"agent_state": {"active_agent": "data"}}),
            )
        async with AsyncSessionLocal() as db:
            stored = (await db.execute(select(Conversation.convo_metadata).where(Conversation.id == cid))).scalar_one()
        assert stored["stm"]["rolling_summary"] == "new summary"
        assert stored["stm"]["last_token_usage"] == 900 and stored["stm"]["pending_summary"] is True
        assert stored["agent_state"] == {"active_agent": "data"}

        # New conversations hold JSON null (a jsonb scalar): patches must still work.
        async with AsyncSessionLocal() as db:
            await db.execute(text("UPDATE conversation SET convo_metadata = 'null'::jsonb WHERE id = :id"), {"id": cid})
            await db.commit()
            await patch_conversation_metadata(db, cid, {"pending_summary": True}, under="stm")
            await patch_conversation_metadata(db, cid, {"topics": ["x"]})
            stored = (await db.execute(select(Conversation.convo_metadata).where(Conversation.id == cid))).scalar_one()
        assert stored == {"stm": {"pending_summary": True}, "topics": ["x"]}
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Conversation).where(Conversation.id == cid))
            await db.commit()
        await engine.dispose()
