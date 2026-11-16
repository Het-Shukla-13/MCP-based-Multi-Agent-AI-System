"""Read/delete your own messages. New messages go through /chat/send or the WebSocket,
so they always pass through the agents and the memory pipeline."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, owned_conversation, owned_message
from app.crud.message import delete_message, get_message, get_messages
from app.db.database import get_db
from app.models import User
from app.schemas.message import MessageRead

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.get("/", response_model=list[MessageRead])
async def read_all(conversation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_conversation(db, conversation_id, user)
    return await get_messages(db, conversation_id)


@router.get("/{message_id}", response_model=MessageRead)
async def read(message_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_message(db, message_id, user)
    return await get_message(db, message_id)


@router.delete("/{message_id}", status_code=204)
async def delete(message_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_message(db, message_id, user)
    await delete_message(db, message_id)
    return Response(status_code=204)
