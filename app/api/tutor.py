"""Trợ lý hỏi–đáp bám SGK cho học sinh (panel chat bên phải, mô hình mockup).

STATELESS: KHÔNG khôi phục chat-graph/session/checkpointer đã bỏ ở P5 — chỉ tái
dùng khối RAG còn lại (retriever + qa_node + grounding) cho 1 lượt hỏi–đáp.
Trả lời CHỈ bám ngữ cảnh SGK (Qdrant); không tìm thấy thì báo, không bịa.

Giữ chốt chi phí LLM (bạn từng yêu cầu): giới hạn độ dài câu hỏi + số lượt/ngày
(dùng chung settings.chat_* + hạn mức riêng của user; admin miễn; fail-open nếu
Redis lỗi).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import User
from app.db.session import get_session
from app.graph.grounding import KHONG_TIM_THAY
from app.graph.nodes.qa import qa_node
from app.llm import cache as llm_cache
from app.llm.gateway import LLMUnavailable
from app.retrieval import retriever

router = APIRouter(prefix="/tutor", tags=["tutor"])

_MON_QDRANT = {"Toán": "toan", "Tiếng Anh": "tieng_anh"}


class Limits(BaseModel):
    max_chars: int


@router.get("/limits", response_model=Limits)
async def limits(user: User = Depends(get_current_user)) -> Limits:
    """Giới hạn ô nhập cho client biết TRƯỚC khi gửi.

    Có endpoint riêng vì `chat_max_chars` override được bằng env: frontend
    hardcode con số sẽ lệch âm thầm với backend, và HS chỉ biết mình viết quá dài
    sau khi đã mất một vòng request."""
    return Limits(max_chars=settings.chat_max_chars)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    mon: str = "Toán"
    context: str | None = None  # tên bài đang học — ghép vào truy vấn cho trúng hơn


class Citation(BaseModel):
    page_no: int
    nguon: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    khong_tim_thay: bool
    remaining: int | None = None  # số lượt còn lại hôm nay (None = không giới hạn)


async def _enforce_limit(user: User) -> int | None:
    limit = user.daily_limit_override if user.daily_limit_override is not None else settings.chat_daily_limit
    if user.role == "admin" or limit <= 0:
        return None
    key = f"chatquota:{user.id}:{datetime.now(timezone.utc):%Y%m%d}"
    try:
        used = await llm_cache.incr_quota(key, ttl=60 * 60 * 26)
    except Exception:  # noqa: BLE001 — Redis lỗi -> cho qua (fail-open)
        return None
    if used > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Bạn đã hỏi {limit} lượt hôm nay rồi, mai quay lại nhé!")
    return max(0, limit - used)


@router.post("/ask", response_model=AskResponse)
async def ask(
    body: AskRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AskResponse:
    q = body.question.strip()
    if not q:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Câu hỏi trống.")
    if len(q) > settings.chat_max_chars:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Câu hỏi quá dài (tối đa {settings.chat_max_chars} ký tự).")
    remaining = await _enforce_limit(user)

    mon_q = _MON_QDRANT.get(body.mon, "toan")
    query = f"{body.context}. {q}" if body.context else q
    role = user.role if user.role in ("hoc_sinh", "giao_vien") else "hoc_sinh"
    try:
        chunks = await retriever.retrieve(query, mon=mon_q, khoi="lop_6", top_k=5, score_threshold=0.4)
        out = await qa_node({
            "messages": [{"role": "user", "content": q}],
            "mon": mon_q, "role": role, "retrieved": chunks,
        })
    except LLMUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Trợ lý đang quá tải, thử lại sau ít phút nhé.")

    answer = out.get("answer", "")
    ktf = KHONG_TIM_THAY in answer
    cits: list[Citation] = []
    if not ktf:
        seen: set[int] = set()
        for c in chunks:
            if c.page_no not in seen:
                seen.add(c.page_no)
                cits.append(Citation(page_no=c.page_no, nguon=c.nguon))
    return AskResponse(answer=answer, citations=cits[:3], khong_tim_thay=ktf, remaining=remaining)
