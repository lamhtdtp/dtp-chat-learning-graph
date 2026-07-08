"""Đăng ký / đăng nhập email + mật khẩu -> JWT. Phase này chỉ register + login
thô (quên/đổi mật khẩu để sau — xem full-system-spec mục 2)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.db.models import User
from app.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Literal["hoc_sinh", "giao_vien"] = "hoc_sinh"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    exists = await session.scalar(select(User).where(User.email == body.email))
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được đăng ký")

    user = User(
        email=body.email,
        password_hash=security.hash_password(body.password),
        name=body.name,
        role=body.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return TokenResponse(token=security.create_token(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")
    return TokenResponse(token=security.create_token(user.id))
