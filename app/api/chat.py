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

# Gợi ý bài tập/đề Itest (EPIC-10, US-23/US-24) kèm câu trả lời cho HỌC SINH:
# hỏi đáp / ôn tập / giải bài đều là lúc học sinh có thể muốn luyện thêm.
_ITEST_INTENTS = {"hoi_dap", "on_tap", "giai_bai"}


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
    # OFFERED = đủ điều kiện tạo video nhưng CHƯA sinh (chờ học sinh bấm "Tạo
    # video"); còn lại là vòng đời job sau khi bấm.
    status: str  # OFFERED | QUEUED | RENDERING | DONE | FAILED
    concept_key: str | None = None
    job_id: int | None = None
    video_url: str | None = None


class ItestOffer(BaseModel):
    # Đề nghị làm bài trắc nghiệm i-Test cho chủ đề học sinh vừa hỏi. Frontend
    # bấm nút -> gọi GET /itest/quiz?topic=... lấy đề THẬT (query i-Test trực
    # tiếp) rồi mở QuizModal tương tác. Chat KHÔNG query i-Test (giữ nhẹ/nhanh).
    topic: str


class Suggestion(BaseModel):
    # Chip gợi ý hành động dưới câu trả lời (bấm -> gửi `query` như tin nhắn mới).
    label: str
    query: str


class ChatResponse(BaseModel):
    reply: str
    intent: str | None
    citations: list[Citation]
    session_id: int
    video: VideoInfo | None = None  # None nếu câu này không thể đính video
    itest: ItestOffer | None = None  # đề nghị luyện tập i-Test (None nếu không phù hợp)
    suggestions: list[Suggestion] = []  # chip gợi ý bước tiếp theo


async def _maybe_video(
    session: AsyncSession, *, message: str, intent: str | None,
    answer: str, has_citations: bool,
) -> VideoInfo | None:
    """Quyết định câu này CÓ THỂ đính video không (gating). KHÔNG tự sinh: chỉ
    trả DONE nếu đã có sẵn (cache hit), hoặc OFFERED để UI hiện nút "Tạo video"
    (sinh on-demand khi học sinh bấm). Không raise: video là bổ sung, lỗi ở đây
    không được làm hỏng câu trả lời text (US-16 Scenario 1)."""
    if not settings.video_enabled or intent not in _VIDEO_INTENTS or not has_citations:
        return None
    if answer.startswith(KHONG_TIM_THAY):
        return None
    ck = concept_key(message, settings.sgk_version)
    if ck is None:
        return None
    try:
        done = await video_cache.get_done_video(session, ck, settings.sgk_version)
        if done is not None:  # đã có -> hiện player ngay, không cần bấm
            return VideoInfo(status="DONE", concept_key=ck, job_id=done.id, video_url=done.video_url)
        return VideoInfo(status="OFFERED", concept_key=ck)
    except Exception:  # noqa: BLE001
        return None


def _maybe_itest(*, message: str, intent: str | None, role: str, answer: str) -> ItestOffer | None:
    """Có nên mời HỌC SINH luyện tập bằng bài trắc nghiệm i-Test cho chủ đề này
    không (gating). Chỉ trả topic — KHÔNG query i-Test ở đây; frontend bấm nút
    mới gọi /itest/quiz (query trực tiếp) rồi mở QuizModal."""
    if role != "hoc_sinh" or intent not in _ITEST_INTENTS:
        return None
    if not answer or answer.startswith(KHONG_TIM_THAY):
        return None
    if not settings.itest_database_url:  # chưa cấu hình kho đề i-Test
        return None
    return ItestOffer(topic=message)


# Chỉ mời "tạo đề ngắn luyện tập" khi học khái niệm/ôn tập — KHÔNG mời khi đang
# giải một bài tập cụ thể (giai_bai): lúc đó gợi ý luyện thêm không hợp ngữ cảnh.
_SUGGEST_INTENTS = {"hoi_dap", "on_tap"}


def _suggestions(intent: str | None, topic: str) -> list[Suggestion]:
    """Chip 'tạo đề ngắn luyện tập' dưới câu trả lời. Query NHÚNG chủ đề vừa hỏi
    + từ khoá 'ôn tập' -> router vào nhánh on_tap và retrieve bám ĐÚNG nội dung
    vừa học (không sinh đề toàn ma trận, không lạc chủ đề). Câu giải bài tập
    (giai_bai) -> KHÔNG mời."""
    if intent not in _SUGGEST_INTENTS:
        return []
    topic = " ".join(topic.split())
    if "về:" in topic:  # bấm chip liên tiếp -> lấy đúng chủ đề, không lồng nhau
        topic = topic.split("về:")[-1].strip()
    topic = topic[:200].strip() or "phần vừa học"
    return [Suggestion(
        label="Tạo một đề ngắn luyện tập",
        query=f"Ôn tập nhanh và ra cho em vài bài tập ngắn để luyện về: {topic}",
    )]


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
    video = await _maybe_video(
        session, message=body.message, intent=intent, answer=answer,
        has_citations=bool(citations),
    )
    itest = _maybe_itest(
        message=body.message, intent=intent, role=user.role, answer=answer,
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

    return ChatResponse(
        reply=answer,
        intent=intent,
        citations=citations,
        session_id=session_pk,
        video=video,
        itest=itest,
        suggestions=_suggestions(intent, body.message),
    )
