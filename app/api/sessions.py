"""Lịch sử hội thoại: liệt kê phiên, xem tin nhắn 1 phiên, xoá phiên. Tất cả
scope theo user hiện tại (Bearer JWT). Việc lưu tin nhắn khi chat nằm ở
app/api/chat.py."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import ChatSession, Message, User
from app.db.session import get_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionRow(BaseModel):
    id: int
    title: str
    last_active: str


class MessageRow(BaseModel):
    role: str
    content: str
    citations: list | None = None


@router.get("", response_model=list[SessionRow])
async def list_sessions(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[SessionRow]:
    rows = await session.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.last_active.desc())
    )
    return [SessionRow(id=r.id, title=r.title, last_active=r.last_active.isoformat()) for r in rows]


async def _owned_session(session: AsyncSession, user: User, session_id: int) -> ChatSession:
    s = await session.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id)
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên chat")
    return s


@router.get("/{session_id}", response_model=list[MessageRow])
async def get_session_messages(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MessageRow]:
    await _owned_session(session, user, session_id)
    rows = await session.scalars(
        select(Message).where(Message.session_id == session_id).order_by(Message.id)
    )
    return [
        MessageRow(
            role=m.role,
            content=m.content,
            citations=json.loads(m.citations_json) if m.citations_json else None,
        )
        for m in rows
    ]


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _owned_session(session, user, session_id)
    await session.execute(delete(Message).where(Message.session_id == session_id))
    await session.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await session.commit()
