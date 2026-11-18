"""Conversation search: FTS over the user's own messages + title matches (real Postgres)."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, text

from app.core.security import hash_password
from app.db.database import AsyncSessionLocal, engine
from app.models import Conversation, Message, User
from app.services.conversation.search_service import HL_END, HL_START, search_conversations
from tests.test_compaction import _db_available

pytestmark = [pytest.mark.skipif(not _db_available(), reason="needs the Postgres container"), pytest.mark.asyncio]


@pytest_asyncio.fixture
async def world():
    await engine.dispose()  # pytest-asyncio: fresh loop per test
    async with AsyncSessionLocal() as db:
        me = User(email=f"search-{uuid.uuid4().hex[:8]}@example.com", password_hash=hash_password("x"))
        other = User(email=f"search-{uuid.uuid4().hex[:8]}@example.com", password_hash=hash_password("x"))
        db.add_all([me, other])
        await db.flush()
        trip = Conversation(title="Lisbon trip plan", user_id=me.id)
        code = Conversation(title="Parser bug", user_id=me.id)
        theirs = Conversation(title="Their chat", user_id=other.id)
        pct = Conversation(title="Discount 100% off_sale", user_id=me.id)
        db.add_all([trip, code, theirs, pct])
        await db.flush()
        db.add_all([
            Message(conversation_id=trip.id, user_id=me.id, role="user", content="Where can I eat grilled sardines in Alfama?"),
            Message(conversation_id=trip.id, user_id=me.id, role="assistant", content="Try the small tascas near the cathedral for grilled sardines."),
            Message(conversation_id=code.id, user_id=me.id, role="user", content="The tokenizer crashes on unicode input"),
            Message(conversation_id=theirs.id, user_id=other.id, role="user", content="I also love grilled sardines"),
        ])
        await db.commit()
        ids = {"me": me.id, "other": other.id, "trip": trip.id, "code": code.id, "pct": pct.id, "theirs": theirs.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.user_id.in_([ids["me"], ids["other"]])))
        await db.execute(delete(Conversation).where(Conversation.user_id.in_([ids["me"], ids["other"]])))
        await db.execute(delete(User).where(User.id.in_([ids["me"], ids["other"]])))
        await db.commit()
    await engine.dispose()


async def test_finds_the_right_conversation_with_a_highlighted_snippet(world):
    async with AsyncSessionLocal() as db:
        results = await search_conversations(db, world["me"], "sardines")
    assert [r["conversation_id"] for r in results] == [str(world["trip"])]  # one hit per conversation
    assert results[0]["match"] == "message"
    assert f"{HL_START}sardines{HL_END}" in results[0]["snippet"]


async def test_never_returns_another_users_messages(world):
    async with AsyncSessionLocal() as db:
        mine = await search_conversations(db, world["me"], "grilled sardines")
        theirs = await search_conversations(db, world["other"], "grilled sardines")
    # The same words exist in both users' chats: each sees exactly their own.
    assert {r["conversation_id"] for r in mine} == {str(world["trip"])}
    assert {r["conversation_id"] for r in theirs} == {str(world["theirs"])}


async def test_stemming_title_substring_and_literal_wildcards(world):
    async with AsyncSessionLocal() as db:
        stem = await search_conversations(db, world["me"], "crashing tokenizer")  # crashes ~ crashing
        title = await search_conversations(db, world["me"], "parser")
        literal = await search_conversations(db, world["me"], "100% off_")
        wildcard = await search_conversations(db, world["me"], "%_")
    assert [r["conversation_id"] for r in stem] == [str(world["code"])]
    assert title[0]["conversation_id"] == str(world["code"]) and title[0]["match"] == "title"
    assert [r["conversation_id"] for r in literal] == [str(world["pct"])]
    assert wildcard == []  # % and _ are not wildcards here


async def test_short_or_odd_queries_are_safe(world):
    async with AsyncSessionLocal() as db:
        assert await search_conversations(db, world["me"], "s") == []
        assert await search_conversations(db, world["me"], "") == []
        assert await search_conversations(db, world["me"], '"unclosed -( & | ! :*') == []


async def test_the_query_can_use_the_gin_index(world):
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET LOCAL enable_seqscan = off"))  # tiny table: force the planner to show the index path
        plan = "\n".join(r[0] for r in (await db.execute(text(
            "EXPLAIN SELECT 1 FROM message WHERE to_tsvector('english', content) @@ websearch_to_tsquery('english', 'sardines')"
        ))).all())
    assert "message_content_fts_idx" in plan
