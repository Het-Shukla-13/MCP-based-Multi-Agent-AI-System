"""
Request authentication and ownership checks shared by all routes.

Identity comes ONLY from the token. user_id values sent by the client are never
trusted. Missing and not-owned resources both return 404, so callers cannot
probe which ids exist (a 403 would confirm existence).
"""

from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models import Conversation, File, Memory, Message, User

_bearer = HTTPBearer(auto_error=False)

NOT_FOUND = "Not found"


async def _user_from_token(token: str | None, db: AsyncSession) -> User:
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await _user_from_token(credentials.credentials if credentials else None, db)


async def get_current_user_header_or_query(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(default=None, description="Access token, for links opened directly by the browser"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    For URLs the browser opens itself (file download/preview, <img src>), which can't
    carry an Authorization header. Tokens in URLs can end up in logs/history, so this
    is used only on those read-only file routes, and tokens are short-lived.
    """
    return await _user_from_token(credentials.credentials if credentials else token, db)


async def owned_conversation(db: AsyncSession, conversation_id: UUID, user: User) -> Conversation:
    conversation = (
        await db.execute(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return conversation


async def owned_file(db: AsyncSession, file_id: UUID, user: User) -> File:
    file = (await db.execute(select(File).where(File.id == file_id, File.user_id == user.id))).scalar_one_or_none()
    if file is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return file


async def owned_message(db: AsyncSession, message_id: UUID, user: User) -> Message:
    message = (
        await db.execute(select(Message).where(Message.id == message_id, Message.user_id == user.id))
    ).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return message


async def owned_memory(db: AsyncSession, memory_id: UUID, user: User) -> Memory:
    memory = (
        await db.execute(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    ).scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return memory
