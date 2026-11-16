from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from uuid import UUID

from app.schemas.conversation import ConversationCreate, ConversationRead
from app.crud.conversation import *
from app.db.database import get_db
from app.schemas.import_convo import ImportConversationRequest
from app.services.conversation.transfer_service import export_conversation, import_messages

router = APIRouter(prefix="/conversations", tags=["Conversations"])

@router.post("/", response_model=ConversationRead)
async def create(payload: ConversationCreate, db: AsyncSession = Depends(get_db)):
    try:
        conversation = await create_conversation(db, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return conversation

@router.get("/{conversation_id}", response_model=ConversationRead)
async def read(conversation_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        conversation = await get_conversation(db, conversation_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return conversation

@router.get("/", response_model=list[ConversationRead])
async def read_all(user_id:UUID, db: AsyncSession = Depends(get_db)):
    try:
        conversations = await get_conversations(db, user_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return conversations

@router.put("/{conversation_id}")
async def update(conversation_id: UUID, title: str, convo_metadata: dict, db: AsyncSession = Depends(get_db)):
    try:
        conversation = await get_conversation(db, conversation_id)
        updated_conversation = await update_conversation(db, conversation_id, title=title, convo_metadata=convo_metadata)
        return updated_conversation
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    
@router.delete("/{conversation_id}")
async def delete(conversation_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        await delete_conversation(db, conversation_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    
@router.get("/{conversation_id}/export")
async def export_conversation_api(conversation_id: UUID, db: AsyncSession = Depends(get_db)):
    return await export_conversation(db, conversation_id)


@router.post("/{conversation_id}/import")
async def import_into_conversation_api(
    conversation_id: UUID,
    payload: ImportConversationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Append imported messages to an existing conversation."""
    conversation = await get_conversation(db, conversation_id)  # 404 if missing
    count = await import_messages(db, conversation=conversation, payload=payload)
    return {"status": "imported", "conversation_id": str(conversation.id), "message_count": count}


@router.post("/import", status_code=201)
async def import_as_new_conversation_api(
    user_id: UUID,
    payload: ImportConversationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation from an exported file."""
    conversation = await create_conversation(
        db, ConversationCreate(title=payload.title or "Imported conversation", user_id=user_id)
    )
    conversation = await get_conversation(db, conversation.id)
    count = await import_messages(db, conversation=conversation, payload=payload)
    return {"status": "imported", "conversation_id": str(conversation.id), "message_count": count}
