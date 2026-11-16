"""
Memory management API: list, search, create, edit, deactivate/delete long-term
memories, and view/rebuild the user profile derived from them.

The profile is NOT edited directly: it's computed from active memories
(preferences, facts, decisions, tasks) and cached in user_profile_snapshot.
Editing a memory then rebuilding the cache is the single, consistent way to
change what the assistant "knows" about a user.

All routes act on the authenticated user only (identity from the access token).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, owned_memory
from app.crud.memory import delete_memory, get_memories_by_user, touch_memory
from app.models import User
from app.crud.user_profile_snapshot import get_user_profile_snapshot
from app.db.database import get_db
from app.enums import MemoryType
from app.schemas.memory import MemoryCreateRequest, MemoryOut, MemoryPatchRequest
from app.services.embeddings.embedding_utils import embed_text_async
from app.services.memory.ltm_service import create_memory_with_embedding, search_memories_with_scores
from app.services.user_profile.user_profile_cache_service import (
    rebuild_user_profile_cache,
    remove_profile_items_by_value,
)

router = APIRouter(prefix="/memories", tags=["Memories"])


def _manual_memory_metadata(memory_type: MemoryType) -> dict:
    """
    A memory the user adds by hand is an explicit, concrete, first-person statement.
    The profile builder only includes memories carrying this metadata (the LLM
    extractor adds it automatically), so manual memories need it too.
    """
    return {
        "evidence": "explicit",
        "confidence_score": 1.0,
        "temporal_scope": "ongoing" if memory_type == MemoryType.task else "durable",
        "source_kind": "statement",
        "value_specificity": "concrete",
        "has_concrete_anchor": True,
        "specificity_score": 1.0,
        "profile_write_eligible": True,
        "profile_write_confidence": 1.0,
        "overwrite_risk": "none",
    }


@router.get("", response_model=list[MemoryOut])
async def list_memories(
    memory_type: MemoryType | None = None,
    include_inactive: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memories = await get_memories_by_user(
        db,
        user_id=user.id,
        memory_type=memory_type.value if memory_type else None,
        only_active=not include_inactive,
    )
    return memories


@router.get("/search", response_model=list[MemoryOut])
async def search_memories(
    query: str = Query(min_length=1),
    top_k: int = Query(default=5, ge=1, le=50),
    memory_type: MemoryType | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    results = await search_memories_with_scores(
        db,
        user_id=user.id,
        query_text=query,
        top_k=top_k,
        memory_type=memory_type.value if memory_type else None,
    )
    return [
        MemoryOut.model_validate(item["memory"]).model_copy(update={"distance": item["distance"]})
        for item in results
    ]


@router.post("", response_model=MemoryOut, status_code=201)
async def create_memory(payload: MemoryCreateRequest, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Manually teach the assistant something (source='user')."""
    memory = await create_memory_with_embedding(
        db,
        user_id=user.id,
        content=payload.content,
        memory_type=payload.memory_type.value,
        memory_metadata={**_manual_memory_metadata(payload.memory_type), **payload.memory_metadata},
        importance_score=payload.importance_score,
        source="user",
    )
    if memory is None:
        raise HTTPException(status_code=400, detail="Memory content is empty")
    await rebuild_user_profile_cache(db, user_id=user.id)
    return memory


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(memory_id: UUID, payload: MemoryPatchRequest, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    memory = await owned_memory(db, memory_id, user)
    updates = payload.model_dump(exclude_unset=True)

    # New text => new meaning => new embedding, otherwise search would still find
    # the memory by its OLD wording.
    embedding = None
    if "content" in updates and updates["content"] != memory.content:
        embedding = await embed_text_async(updates["content"])

    memory = await touch_memory(
        db,
        memory_id,
        content=updates.get("content"),
        importance_score=updates.get("importance_score"),
        embedding=embedding,
    )
    if "memory_type" in updates:
        memory.memory_type = updates["memory_type"].value
    if "is_active" in updates:
        memory.is_active = updates["is_active"]
    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    await rebuild_user_profile_cache(db, user_id=memory.user_id)
    return memory


@router.delete("/{memory_id}", status_code=204)
async def remove_memory(
    memory_id: UUID,
    hard: bool = Query(default=False, description="false = deactivate (reversible), true = delete permanently"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await owned_memory(db, memory_id, user)
    user_id = memory.user_id
    if hard:
        await delete_memory(db, memory_id)
    else:
        memory.is_active = False
        db.add(memory)
        await db.commit()
    await rebuild_user_profile_cache(db, user_id=user_id)
    return Response(status_code=204)


async def _profile_payload(db: AsyncSession, user_id: UUID) -> dict:
    snapshot = await get_user_profile_snapshot(db, user_id=user_id)
    if snapshot is None:
        snapshot = await rebuild_user_profile_cache(db, user_id=user_id)
    return {
        "preferences": snapshot.preferences,
        "facts": snapshot.facts,
        "active_goals": snapshot.active_goals,
        "decisions": snapshot.decisions,
        "profile_text": snapshot.profile_text,
        "source_memory_count": snapshot.source_memory_count,
    }


@router.get("/profile")
async def get_user_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _profile_payload(db, user.id)


@router.post("/profile/rebuild")
async def rebuild_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rebuild_user_profile_cache(db, user_id=user.id)
    return await _profile_payload(db, user.id)


@router.delete("/profile/items")
async def delete_profile_item(
    value: str = Query(min_length=1, description="Exact text of the profile item to remove"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    removed = await remove_profile_items_by_value(db, user_id=user.id, value=value)
    if not removed:
        raise HTTPException(status_code=404, detail="Profile item not found")
    return await _profile_payload(db, user.id)
