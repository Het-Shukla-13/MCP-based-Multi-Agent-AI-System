from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

EXPORT_FORMAT = "mcp-agent-conversation"
EXPORT_VERSION = 1


class ImportMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)
    created_at: Optional[datetime] = None


class ImportConversationRequest(BaseModel):
    format: Optional[str] = None
    version: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=200)
    convo_metadata: Optional[dict] = None
    messages: list[ImportMessage] = Field(min_length=1, max_length=2000)
