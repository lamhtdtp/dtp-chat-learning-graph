"""Dependencies dùng chung cho API: DB session + user hiện tại (từ Bearer JWT)."""

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.db.models import User
from app.db.session import get_session


async def get_current_user(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Thiếu Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_id = security.decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ hoặc hết hạn")

    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Người dùng không tồn tại")
    if not user.is_active:  # admin khoá -> chặn mọi endpoint
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tài khoản đã bị khoá.")
    return user
