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
from app.config import settings
from app.db.models import ChatSession, Message, User
from app.db.session import get_session
from app.graph.grounding import KHONG_TIM_THAY
from app.llm.gateway import LLMUnavailable
from app.video import cache as video_cache
from app.video.concept import concept_key

router = APIRouter(tags=["chat"])

# Chỉ đính video cho câu hỏi khái niệm/ôn tập CÓ grounding — không sinh cho câu
# giải bài hay câu không bám SGK (US-19 gating: kiểm soát chi phí).
_VIDEO_INTENTS = {"hoi_dap", "on_tap"}


class ChatRequest(BaseModel):
    message: str
    session_id: int | None = None  # None = phiên mới


class Citation(BaseModel):
    nguon: str
    page_no: int
    chuong_so: int | None
    bai_so: int | None
    tap: int | None = None  # để mở ảnh trang gốc


class VideoInfo(BaseModel):
    job_id: int
    status: str  # QUEUED | RENDERING | DONE | FAILED
    video_url: str | None = None


class ChatResponse(BaseModel):
    reply: str
    intent: str | None
    citations: list[Citation]
    session_id: int
    video: VideoInfo | None = None  # None nếu câu này không đính video


async def _maybe_video(
    session: AsyncSession, *, message: str, intent: str | None,
    answer: str, has_citations: bool,
) -> tuple[VideoInfo | None, int | None]:
    """Quyết định có đính video không (gating), trả (VideoInfo, job_id_cần_enqueue).
    job_id_cần_enqueue chỉ khác None khi vừa tạo job mới -> caller enqueue Celery
    SAU commit. Không bao giờ raise ra ngoài: video là bổ sung, lỗi ở đây không
    được làm hỏng câu trả lời text (US-16 Scenario 1)."""
    if not settings.video_enabled or intent not in _VIDEO_INTENTS or not has_citations:
        return None, None
    if answer.startswith(KHONG_TIM_THAY):
        return None, None
    ck = concept_key(message, settings.sgk_version)
    if ck is None:
        return None, None
    try:
        done = await video_cache.get_done_video(session, ck, settings.sgk_version)
        if done is not None:  # cache hit -> dùng lại, không tạo job mới
            return VideoInfo(job_id=done.id, status="DONE", video_url=done.video_url), None
        job, created = await video_cache.get_or_create_job(session, ck, settings.sgk_version)
        return VideoInfo(job_id=job.id, status=job.status, video_url=job.video_url), (
            job.id if created else None
        )
    except Exception:  # noqa: BLE001
        return None, None


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

    intent = result.get("intent")
    video, enqueue_job_id = await _maybe_video(
        session, message=body.message, intent=intent, answer=answer,
        has_citations=bool(citations),
    )

    session.add(Message(session_id=session_pk, role="user", content=body.message))
    session.add(Message(
        session_id=session_pk, role="assistant", content=answer,
        citations_json=json.dumps([c.model_dump() for c in citations], ensure_ascii=False),
    ))
    await session.execute(
        update(ChatSession).where(ChatSession.id == session_pk).values(last_active=func.now())
    )
    await session.commit()

    # Enqueue SAU commit: job row đã tồn tại khi worker đọc. Lỗi enqueue (broker
    # down) không làm hỏng câu trả lời — chỉ là video không tới.
    if enqueue_job_id is not None:
        try:
            from app.ingestion.celery_app import render_video_task

            render_video_task.delay(job_id=enqueue_job_id)
        except Exception:  # noqa: BLE001
            pass

    return ChatResponse(
        reply=answer,
        intent=intent,
        citations=citations,
        session_id=session_pk,
        video=video,
    )
