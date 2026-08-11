"""Trợ lý hỏi–đáp bám SGK cho học sinh (panel chat bên phải, mô hình mockup).

STATELESS: KHÔNG khôi phục chat-graph/session/checkpointer đã bỏ ở P5 — chỉ tái
dùng khối RAG còn lại (retriever + qa_node + grounding) cho 1 lượt hỏi–đáp.

HAI NGUỒN, CÓ THỨ TỰ: nội dung ĐƠN VỊ ĐANG HỌC (topic_content, do chuyên gia
soạn) đứng trước, SGK (Qdrant) để đối chiếu. Trước đây chỉ có SGK nên trợ lý trả
lời bằng chữ khác, ví dụ khác với bài học sinh đang mở — thậm chí báo "không có
trong SGK" cho đúng đoạn đang hiện trên màn hình. `anchor` cắt xuống còn đúng
đoạn đang hỏi (khái niệm / minh hoạ / ví dụ N / câu kiểm tra N).

Giữ chốt chi phí LLM (bạn từng yêu cầu): giới hạn độ dài câu hỏi + số lượt/ngày
(dùng chung settings.chat_* + hạn mức riêng của user; admin miễn; fail-open nếu
Redis lỗi).
"""
import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import CurriculumTopic, QuizAttempt, TopicContent, User
from app.db.session import get_session
from app.graph.grounding import KHONG_TIM_THAY
from app.graph.nodes.qa import qa_node
from app.llm import cache as llm_cache
from app.llm.gateway import LLMUnavailable
from app.retrieval import retriever

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor", tags=["tutor"])

_MON_QDRANT = {"Toán": "toan", "Tiếng Anh": "tieng_anh"}
_TAC_GIA = {"chuyen_gia", "giao_vien", "admin"}

# Neo = đoạn học sinh đang hỏi. Khớp CHẶT để `anchor` không thành đường tuồn chuỗi
# tuỳ ý vào prompt. None = hỏi chung cả bài.
_NEO_RE = re.compile(r"^(khai_niem|minh_hoa|(vi_du|quiz):([1-9]\d?))$")
# Trần ngữ cảnh bài học trong prompt. Bài dài (nhiều ví dụ) mà nhét hết thì mỗi
# lượt hỏi đội token vô ích, trong khi phần trả lời chỉ cần đúng đoạn đang đọc.
_MAX_BAI = 6000


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
    # Đơn vị kiến thức đang mở. Có nó thì trợ lý đọc được ĐÚNG nội dung chuyên gia
    # soạn, không chỉ SGK.
    topic_id: int | None = None
    # Đoạn đang hỏi: khai_niem | minh_hoa | vi_du:N | quiz:N (N đếm từ 1).
    anchor: str | None = None
    # (Cũ) tên bài dạng chuỗi — giữ cho client chưa cập nhật; `topic_id` ưu tiên hơn.
    context: str | None = None


class Citation(BaseModel):
    page_no: int
    nguon: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    khong_tim_thay: bool
    remaining: int | None = None  # số lượt còn lại hôm nay (None = không giới hạn)
    # Nhãn nguồn "nội bộ" để client hiển thị (vd "Ví dụ 2"). None = không dựa vào
    # nội dung bài, chỉ có SGK.
    nguon_bai: str | None = None


def _bo_the(s: str) -> str:
    """HTML chuyên gia soạn -> văn bản thuần cho prompt. Thẻ không mang thông tin
    gì cho mô hình mà vẫn tính tiền token."""
    s = re.sub(r"(?i)<br\s*/?>", "\n", s or "")
    s = re.sub(r"(?i)</(p|div|li|h[1-6]|blockquote)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _doan_bai(c: TopicContent, anchor: str | None) -> tuple[str, str | None]:
    """Cắt phần bài học ứng với neo -> (ngữ cảnh cho prompt, nhãn nguồn).

    Neo không hợp lệ / trỏ ra ngoài mảng -> rơi về cả bài, KHÔNG lỗi: học sinh
    đang giữa chừng bài học, một cái neo lệch không đáng để chặn câu hỏi."""
    kn = _bo_the(c.khai_niem)
    vd = json.loads(c.vi_du_json or "[]")

    if anchor == "khai_niem":
        return f"KHÁI NIỆM:\n{kn}", "Khái niệm"

    if anchor == "minh_hoa":
        mh = json.loads(c.minh_hoa_json or "[]")
        caps = "\n".join(f"- {m.get('caption') or m.get('type') or ''}" for m in mh)
        # Minh hoạ là ảnh/video: trợ lý chỉ có chú thích trong tay, nên kèm khái
        # niệm để còn nói được điều gì có ích thay vì tả một cái poster.
        return f"KHÁI NIỆM:\n{kn}\n\nMINH HOẠ (chú thích):\n{caps}", "Minh hoạ"

    if anchor and anchor.startswith("vi_du:"):
        i = int(anchor.split(":")[1]) - 1
        if 0 <= i < len(vd):
            e = vd[i]
            return (f"KHÁI NIỆM:\n{kn}\n\nVÍ DỤ {i + 1}:\nĐề: {_bo_the(e.get('de', ''))}\n"
                    f"Lời giải: {_bo_the(e.get('giai', ''))}"), f"Ví dụ {i + 1}"

    if anchor and anchor.startswith("quiz:"):
        i = int(anchor.split(":")[1]) - 1
        quiz = json.loads(c.quiz_json or "[]")
        if 0 <= i < len(quiz):
            q = quiz[i]
            pa = "\n".join(f"{chr(65 + j)}. {_bo_the(str(o))}" for j, o in enumerate(q.get("o", [])))
            dung = chr(65 + q["a"]) if isinstance(q.get("a"), int) else "?"
            return (f"KHÁI NIỆM:\n{kn}\n\nCÂU {i + 1} TRONG BÀI KIỂM TRA NHANH:\n"
                    f"{_bo_the(q.get('q', ''))}\n{pa}\nĐáp án đúng: {dung}\n"
                    f"Lời giải: {_bo_the(q.get('giai', ''))}"), f"Bài kiểm tra · Câu {i + 1}"

    # Cả bài: khái niệm + ví dụ. CỐ Ý KHÔNG kèm quiz — hỏi trợ lý một câu bâng quơ
    # mà nhận về nguyên đề + đáp án thì bài kiểm tra thành vô nghĩa.
    vds = "\n\n".join(
        f"VÍ DỤ {i + 1}:\nĐề: {_bo_the(e.get('de', ''))}\nLời giải: {_bo_the(e.get('giai', ''))}"
        for i, e in enumerate(vd))
    return f"KHÁI NIỆM:\n{kn}" + (f"\n\n{vds}" if vds else ""), "Toàn bài"


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
    anchor = body.anchor if (body.anchor and _NEO_RE.match(body.anchor)) else None
    bai_hoc, nguon_bai, ten_dv = "", None, body.context
    if body.topic_id is not None:
        bai_hoc, nguon_bai, ten_dv = await _ngu_canh_bai(session, user, body.topic_id, anchor, ten_dv)

    remaining = await _enforce_limit(user)

    mon_q = _MON_QDRANT.get(body.mon, "toan")
    query = f"{ten_dv}. {q}" if ten_dv else q
    role = user.role if user.role in ("hoc_sinh", "giao_vien") else "hoc_sinh"
    # Qdrant/embedding hỏng KHÔNG còn được phép giết câu trả lời: nếu học sinh
    # đang hỏi về một bài đã biên soạn thì nội dung bài đủ để trả lời tử tế.
    # (Trước lát 1 thì chỉ có SGK nên lỗi ở đây là hết đường -> 500.)
    try:
        chunks = await retriever.retrieve(query, mon=mon_q, khoi="lop_6", top_k=5, score_threshold=0.4)
    except Exception as exc:  # noqa: BLE001 — client Qdrant ném nhiều loại lỗi mạng
        if not bai_hoc:
            log.warning("Truy hồi SGK lỗi và không có nội dung bài để thay: %s", exc)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "Trợ lý đang quá tải, thử lại sau ít phút nhé.")
        log.warning("Truy hồi SGK lỗi, trả lời bằng nội dung bài đang học: %s", exc)
        chunks = []

    try:
        out = await qa_node({
            "messages": [{"role": "user", "content": q}],
            "mon": mon_q, "role": role, "retrieved": chunks,
            "bai_hoc": bai_hoc, "topic_id": body.topic_id, "anchor": anchor,
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
    return AskResponse(answer=answer, citations=cits[:3], khong_tim_thay=ktf,
                       remaining=remaining, nguon_bai=None if ktf else nguon_bai)


async def _ngu_canh_bai(
    session: AsyncSession, user: User, topic_id: int, anchor: str | None, ten_cu: str | None,
) -> tuple[str, str | None, str | None]:
    """Đọc nội dung đơn vị đang mở -> (ngữ cảnh, nhãn nguồn, tên đơn vị).

    Topic/nội dung không có thì trả rỗng chứ KHÔNG 404: câu hỏi vẫn trả lời được
    bằng SGK như trước, chặn ở đây chỉ tổ làm hỏng trải nghiệm vì một cái id cũ."""
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        return "", None, ten_cu
    ten_dv = re.sub(r"\s+", " ", (topic.don_vi_kien_thuc or "").strip()) or ten_cu

    c = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    # Học sinh chỉ được ngữ cảnh từ bản ĐÃ XUẤT BẢN — cùng luật với GET /lessons.
    if c is None or (user.role not in _TAC_GIA and c.trang_thai != "published"):
        return "", None, ten_dv

    if anchor and anchor.startswith("quiz:") and user.role not in _TAC_GIA:
        # Chưa nộp bài mà hỏi "câu 3 đáp án gì" thì trợ lý sẽ trả lời thật — hỏi
        # đủ 8 lượt là có trọn bộ đáp án. Chỉ mở sau khi đã có lần nộp.
        da_lam = await session.scalar(
            select(QuizAttempt.id).filter_by(user_id=user.id, topic_id=topic_id).limit(1))
        if da_lam is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Bạn làm bài kiểm tra nhanh xong rồi hỏi mình về câu này nhé!")

    doan, nhan = _doan_bai(c, anchor)
    return doan[:_MAX_BAI], nhan, ten_dv
