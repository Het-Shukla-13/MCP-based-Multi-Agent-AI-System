from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.schemas.file import FileRead
    from app.schemas.message import MessageRead

class ConversationCreate(BaseModel):
    """Internal: user_id always comes from the authenticated user."""
    title: str
    user_id: UUID
    convo_metadata: Optional[dict] = None


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="New conversation", max_length=200)


class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

class ConversationRead(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    convo_metadata: Optional[dict] = None
    user_id: UUID
    messages: List["MessageRead"] = []
    files: List["FileRead"] = []

    model_config = ConfigDict(from_attributes=True)

class ConversationBasicRead(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    convo_metadata: Optional[dict] = None
    user_id: UUID

    model_config = ConfigDict(from_attributes=True)


class ConversationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    active_goals: list[str] = Field(default_factory=list)

    sentiment: Literal[
        "positive",
        "neutral",
        "negative",
        "mixed",
    ] = "neutral"

    summary_hint: str = ""

from app.schemas.file import FileRead
from app.schemas.message import MessageRead
ConversationRead.model_rebuild()
