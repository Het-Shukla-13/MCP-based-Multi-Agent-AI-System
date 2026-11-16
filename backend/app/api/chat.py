from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, owned_conversation
from app.db.database import get_db
from app.models import User
from app.services.message.message_service import send_message_from_payload

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatSendRequest(BaseModel):
    conversation_id: UUID
    content: str = Field(min_length=1, max_length=20_000)
    file_ids: list[UUID] = Field(default_factory=list)
    selected_agent: str | None = None
    format: str | None = None


@router.post("/send")
async def chat(payload: ChatSendRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Non-streaming alternative to the WebSocket (same pipeline)."""
    await owned_conversation(db, payload.conversation_id, user)
    return await send_message_from_payload(
        db, payload.conversation_id, payload.model_dump(mode="json"), user.id
    )
