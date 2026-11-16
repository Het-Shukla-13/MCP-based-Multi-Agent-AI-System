from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, needs_rehash, verify_password
from app.crud.user import create_user
from app.db.database import get_db
from app.models import User
from app.schemas.user import LoginRequest, TokenResponse, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["Auth"])

# Same message for "no such email" and "wrong password": don't reveal which emails exist.
INVALID_LOGIN = "Incorrect email or password"
# Verifying against a dummy hash when the email is unknown keeps response time
# similar to a wrong password (timing would otherwise reveal registered emails).
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user.id), expires_in=settings.ACCESS_TOKEN_MINUTES * 60)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await create_user(db, payload)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email.lower()))).scalar_one_or_none()
    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN)
    if not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN)
    if needs_rehash(user.password_hash):  # upgrade old hashes transparently on login
        user.password_hash = hash_password(payload.password)
        db.add(user)
        await db.commit()
    return _token_response(user)


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)):
    return user
