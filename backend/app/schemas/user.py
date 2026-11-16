from __future__ import annotations
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import List
from uuid import UUID
from datetime import datetime

from app.schemas.conversation import ConversationBasicRead

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserUpdate(BaseModel):
    current_password: str  # re-authenticate before changing credentials
    email: EmailStr | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)

class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
