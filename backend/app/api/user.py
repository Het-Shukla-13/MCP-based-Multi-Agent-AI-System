"""Account management for the signed-in user only (no listing or editing other users)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_current_user
from app.core.security import hash_password, verify_password
from app.db.database import get_db
from app.models import User
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead)
async def read_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserRead)
async def update_me(payload: UserUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Re-authenticate: a stolen token alone must not be enough to take over the account.
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.email and payload.email.lower() != user.email:
        taken = (await db.execute(select(User).where(User.email == payload.email.lower()))).scalar_one_or_none()
        if taken:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = payload.email.lower()
    if payload.new_password:
        user.password_hash = hash_password(payload.new_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/me", status_code=204)
async def delete_me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.delete(user)
    await db.commit()
    return Response(status_code=204)
