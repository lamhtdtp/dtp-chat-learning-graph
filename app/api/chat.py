"""POST /chat — chạy graph hội thoại, bắt buộc Bearer JWT.

thread_id checkpointer = "{user_id}:{session_id}" để mỗi phiên chat của mỗi user
tách biệt; state graph sống trong Redis (stateless app). Ngoài ra tin nhắn được
lưu vào Postgres (chat_sessions/messages) để dựng sidebar lịch sử (xem
app/api/sessions.py). session_id là ID phiên trong DB; bỏ trống -> tạo phiên mới.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import ChatSession, Message, User
from app.db.session import get_session
from app.api import security
from app.graph.grounding import KHONG_TIM_THAY
from app.llm import cache as llm_cache
from app.llm.gateway import LLMUnavailable
from app.video import cache as video_cache
from app.video.concept import (
    concept_key, free_concept_key, is_video_request, topic_from_request,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# Chỉ đính video cho câu hỏi khái niệm/ôn tập CÓ grounding — không sinh cho câu
# giải bài hay câu không bám SGK (US-19 gating: kiểm soát chi phí).
_VIDEO_INTENTS = {"hoi_dap", "on_tap"}

# Gợi ý bài tập/đề Itest (EPIC-10, US-23/US-24) kèm câu trả lời cho HỌC SINH:
# hỏi đáp / ôn tập / giải bài đều là lúc học sinh có thể muốn luyện thêm.
_ITEST_INTENTS = {"hoi_dap", "on_tap", "giai_bai"}


# Ánh xạ KEY môn ở frontend (subjects.ts) -> giá trị `mon` trong payload Qdrant.
# Frontend dùng "anh" cho gọn; dữ liệu OCR/ingest gắn mon="tieng_anh". Không map
# thì retrieve lọc sai -> hỏi Tiếng Anh lại ra chunk Toán (hoặc rỗng).
_SUBJECT_TO_MON = {"toan": "toan", "anh": "tieng_anh"}


class ChatRequest(BaseModel):
    message: str
    session_id: int | None = None  # None = phiên mới
    subject: str = "toan"          # môn học -> gắn vào phiên để lọc lịch sử theo môn


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
    # Chip gợi ý dưới câu trả lời. action="ask" -> gửi `query` như tin nhắn mới;
    # action="practice_exam" -> mở đề ngắn sinh theo ma trận (như giáo viên).
    label: str
    query: str = ""
    action: str = "ask"


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
    answer: str, has_citations: bool, mon: str = "toan",
) -> VideoInfo | None:
    """Quyết định câu này CÓ THỂ đính video không (gating). KHÔNG tự sinh: chỉ
    trả DONE nếu đã có sẵn (cache hit), hoặc OFFERED để UI hiện nút "Tạo video"
    (sinh on-demand khi học sinh bấm). Không raise: video là bổ sung, lỗi ở đây
    không được làm hỏng câu trả lời text (US-16 Scenario 1)."""
    if not settings.video_enabled or intent not in _VIDEO_INTENTS or not has_citations:
        return None
    if answer.startswith(KHONG_TIM_THAY):
        return None
    # Khái niệm cố định -> auto-offer (dùng lại video chung). Nếu không khớp mà học
    # sinh CHỦ ĐỘNG xin video, chủ đề đã grounded (has_citations) -> free-key theo
    # đúng câu hỏi + môn, vẫn sinh được video (US-16: video theo yêu cầu).
    ck = concept_key(message, settings.sgk_version, mon)
    if ck is None:
        if not is_video_request(message):
            return None
        ck = free_concept_key(topic_from_request(message), mon, settings.sgk_version)
    try:
        done = await video_cache.get_done_video(session, ck, settings.sgk_version)
        if done is not None:  # đã có -> hiện player ngay, không cần bấm
            return VideoInfo(status="DONE", concept_key=ck, job_id=done.id,
                             video_url=security.sign_media(done.video_url) if done.video_url else None)
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


def _suggestions(intent: str | None) -> list[Suggestion]:
    """Chip 'Tạo một đề ngắn luyện tập' dưới câu trả lời — bấm sẽ sinh đề NGẮN
    bám ĐÚNG ma trận đặc tả (như luồng giáo viên), không phải gửi prompt chat.
    Câu giải bài tập (giai_bai) -> KHÔNG mời."""
    if intent not in _SUGGEST_INTENTS:
        return []
    return [Suggestion(label="Tạo một đề ngắn luyện tập", action="practice_exam")]


def _title_from(text: str) -> str:
    t = text.strip().replace("\n", " ")
    return t[:60] + ("…" if len(t) > 60 else "")


_BURST_MAX = 8       # tối đa 8 lượt chat trong _BURST_WINDOW giây (chống gọi dồn/DoS)
_BURST_WINDOW = 10


async def _enforce_limits(user: User) -> None:
    """Chặn lạm dụng LLM (đếm bằng Redis, atomic INCR + TTL; fail-open nếu Redis
    lỗi): (1) chống gọi dồn/DoS trong cửa sổ ngắn — mọi vai trò; (2) hạn mức
    lượt/ngày — admin miễn, dùng `daily_limit_override` của user nếu có."""
    # (1) Burst guard — chống gửi dồn dập (script/DoS)
    try:
        b = await llm_cache.incr_quota(f"burst:{user.id}", ttl=_BURST_WINDOW)
    except Exception:  # noqa: BLE001
        b = 0
    if b > _BURST_MAX:
        logger.warning("Nghi DoS: user %s gửi %s lượt trong %ss", user.id, b, _BURST_WINDOW)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Bạn thao tác quá nhanh. Chờ vài giây rồi thử lại nhé.",
        )

    # (2) Hạn mức theo ngày
    limit = user.daily_limit_override if user.daily_limit_override is not None else settings.chat_daily_limit
    if limit <= 0 or user.role == "admin":
        return
    key = f"chatquota:{user.id}:{datetime.now(timezone.utc):%Y%m%d}"
    try:
        n = await llm_cache.incr_quota(key, ttl=2 * 24 * 3600)
    except Exception:  # noqa: BLE001 - best-effort: Redis lỗi -> cho qua
        logger.warning("chat quota: Redis lỗi, bỏ qua giới hạn cho user %s", user.id)
        return
    if n > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Bạn đã dùng hết {limit} lượt hỏi trong hôm nay. Hẹn gặp lại vào ngày mai nhé!",
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    # Chặn input rác/quá dài (tránh treo + tốn token) và giới hạn lượt/ngày.
    msg = body.message.strip()
    if not msg:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Câu hỏi trống.")
    if len(msg) > settings.chat_max_chars:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Câu hỏi quá dài (tối đa {settings.chat_max_chars} ký tự). Bạn rút gọn lại nhé!",
        )
    await _enforce_limits(user)

    # Lấy/ tạo phiên (kiểm quyền sở hữu nếu client gửi session_id).
    if body.session_id is None:
        chat_session = ChatSession(user_id=user.id, subject=body.subject, title=_title_from(body.message))
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
            # Truyền `mon` của phiên -> retrieve_node lọc Qdrant theo môn (đa môn).
            {"messages": [{"role": "user", "content": body.message}], "role": user.role,
             "mon": _SUBJECT_TO_MON.get(body.subject, body.subject)},
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
    # Video minh hoạ: đa môn — gate theo khái niệm CÓ trong môn (concept_key trả
    # None nếu môn chưa khai báo khái niệm nào). i-Test & chip "đề ngắn" vẫn CHỈ
    # có dữ liệu Toán nên giữ gate is_toan.
    mon = _SUBJECT_TO_MON.get(body.subject, body.subject)
    is_toan = body.subject == "toan"
    video = await _maybe_video(
        session, message=body.message, intent=intent, answer=answer,
        has_citations=bool(citations), mon=mon,
    )
    itest = _maybe_itest(
        message=body.message, intent=intent, role=user.role, answer=answer,
    ) if is_toan else None

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
        suggestions=_suggestions(intent) if is_toan else [],
    )
