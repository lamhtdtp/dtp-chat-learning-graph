"""POST /chat — chạy graph hội thoại, bắt buộc Bearer JWT.

thread_id checkpointer = "{user_id}:{session_id}" để mỗi phiên chat của mỗi user
tách biệt; state graph sống trong Redis (stateless app). Ngoài ra tin nhắn được
lưu vào Postgres (chat_sessions/messages) để dựng sidebar lịch sử (xem
app/api/sessions.py). session_id là ID phiên trong DB; bỏ trống -> tạo phiên mới.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.api.deps import get_current_user
from app.db.models import ChatSession, Message, User
from app.db.session import get_session
from app.llm.gateway import LLMUnavailable

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: int | None = None  # None = phiên mới


class Citation(BaseModel):
    nguon: str
    page_no: int
    chuong_so: int | None
    bai_so: int | None
    tap: int | None = None  # để mở ảnh trang gốc


class ChatResponse(BaseModel):
    reply: str
    intent: str | None
    citations: list[Citation]
    session_id: int


def _title_from(text: str) -> str:
    t = text.strip().replace("\n", " ")
    return t[:60] + ("…" if len(t) > 60 else "")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    # Lấy/ tạo phiên (kiểm quyền sở hữu nếu client gửi session_id).
    if body.session_id is None:
        chat_session = ChatSession(user_id=user.id, title=_title_from(body.message))
        session.add(chat_session)
        await session.flush()
    else:
        chat_session = await session.scalar(
            select(ChatSession).where(
                ChatSession.id == body.session_id, ChatSession.user_id == user.id
            )
        )
        if chat_session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên chat")

    # Lấy id vào biến TRƯỚC khi commit — sau commit ORM object có thể bị expire,
    # truy cập .id sẽ cần lazy-load async trong ngữ cảnh sai -> MissingGreenlet.
    session_pk = chat_session.id

    graph = request.app.state.graph
    thread_id = f"{user.id}:{session_pk}"
    try:
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": body.message}], "role": user.role},
            config={"configurable": {"thread_id": thread_id}},
        )
    except LLMUnavailable:
        # Provider hết quota (429)/mất kết nối -> 503 + thông báo thân thiện.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Hệ thống đang bận (quá giới hạn gọi AI), bạn thử lại sau ít phút nhé.",
        )

    retrieved = result.get("retrieved") or []
    citations = [
        Citation(nguon=r.nguon, page_no=r.page_no, chuong_so=r.chuong_so, bai_so=r.bai_so, tap=r.tap)
        for r in retrieved
    ]
    answer = result.get("answer") or ""

    session.add(Message(session_id=session_pk, role="user", content=body.message))
    session.add(Message(
        session_id=session_pk, role="assistant", content=answer,
        citations_json=json.dumps([c.model_dump() for c in citations], ensure_ascii=False),
    ))
    await session.execute(
        update(ChatSession).where(ChatSession.id == session_pk).values(last_active=func.now())
    )
    await session.commit()

    return ChatResponse(
        reply=answer,
        intent=result.get("intent"),
        citations=citations,
        session_id=session_pk,
    )
