from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, owned_conversation
from app.crud.conversation import create_conversation, delete_conversation, get_conversation, get_conversations
from app.db.database import get_db
from app.models import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationCreateRequest,
    ConversationRead,
    ConversationUpdateRequest,
)
from app.schemas.import_convo import ImportConversationRequest
from app.services.conversation.transfer_service import export_conversation, import_messages

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("/", response_model=ConversationRead, status_code=201)
async def create(payload: ConversationCreateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_conversation(db, ConversationCreate(title=payload.title, user_id=user.id))


@router.get("/", response_model=list[ConversationRead])
async def read_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await get_conversations(db, user.id)


@router.get("/{conversation_id}", response_model=ConversationRead)
async def read(conversation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_conversation(db, conversation_id, user)
    return await get_conversation(db, conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationRead)
async def rename(conversation_id: UUID, payload: ConversationUpdateRequest,
                 user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    conversation = await owned_conversation(db, conversation_id, user)
    conversation.title = payload.title  # metadata is internal state: not client-editable
    db.add(conversation)
    await db.commit()
    return await get_conversation(db, conversation_id)


@router.delete("/{conversation_id}", status_code=204)
async def delete(conversation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_conversation(db, conversation_id, user)
    await delete_conversation(db, conversation_id)
    return Response(status_code=204)


@router.get("/{conversation_id}/export")
async def export_conversation_api(conversation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_conversation(db, conversation_id, user)
    return await export_conversation(db, conversation_id)


@router.post("/{conversation_id}/import")
async def import_into_conversation_api(conversation_id: UUID, payload: ImportConversationRequest,
                                       user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Append imported messages to one of your conversations."""
    conversation = await owned_conversation(db, conversation_id, user)
    count = await import_messages(db, conversation=conversation, payload=payload)
    return {"status": "imported", "conversation_id": str(conversation.id), "message_count": count}


@router.post("/import", status_code=201)
async def import_as_new_conversation_api(payload: ImportConversationRequest,
                                         user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Create a new conversation from an exported file."""
    conversation = await create_conversation(
        db, ConversationCreate(title=payload.title or "Imported conversation", user_id=user.id)
    )
    conversation = await get_conversation(db, conversation.id)
    count = await import_messages(db, conversation=conversation, payload=payload)
    return {"status": "imported", "conversation_id": str(conversation.id), "message_count": count}
