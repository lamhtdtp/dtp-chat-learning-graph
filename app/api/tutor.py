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

from app.api import security
from app.api.deps import get_current_user
from app.config import settings
from app.db.models import CurriculumTopic, QuizAttempt, TopicContent, User
from app.db.session import get_session
from app.exam import diem_khop
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
_NEO_RE = re.compile(
    r"^(khoi_dong|hoat_dong|khai_niem|kien_thuc|minh_hoa|luyen_tap|bai_tap"
    r"|(vi_du|quiz):([1-9]\d?))$")
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


class AnhKem(BaseModel):
    """Hình minh hoạ đính theo câu trả lời."""

    url: str            # đã ký, xem được trong hạn
    caption: str
    tu: str             # nguồn trong bài: "Minh hoạ" | "Ví dụ 2"


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    khong_tim_thay: bool
    remaining: int | None = None  # số lượt còn lại hôm nay (None = không giới hạn)
    # Nhãn nguồn "nội bộ" để client hiển thị (vd "Ví dụ 2"). None = không dựa vào
    # nội dung bài, chỉ có SGK.
    nguon_bai: str | None = None
    # Hình của CHÍNH bài đang học, đính khi câu hỏi/câu trả lời nói tới hình vẽ.
    anh: list[AnhKem] = []


# Dấu hiệu câu hỏi/câu trả lời đang nói về HÌNH. Không có hàng rào này thì bài
# nào có ảnh là câu nào cũng đính ảnh, kể cả hỏi "luỹ thừa là gì" — nhiễu hơn là
# giúp. Cố ý không nhờ LLM quyết định: thêm một lượt gọi model cho việc mà vài từ
# khoá làm được là đắt vô ích.
_DAU_HINH = re.compile(
    r"hình|vẽ|sơ đồ|đồ thị|biểu đồ|quan sát|trục đối xứng|tâm đối xứng"
    r"|tam giác|tứ giác|hình vuông|chữ nhật|hình thoi|bình hành|thang cân"
    r"|đường thẳng|đoạn thẳng|tia |góc |điểm ", re.IGNORECASE)
# Tỉ lệ TỪ của caption xuất hiện trong câu hỏi + câu trả lời.
#
# CỐ Ý không dùng SequenceMatcher như chỗ khớp tên đơn vị: nó chia cho tổng độ
# dài hai chuỗi, nên caption 90 ký tự so với câu trả lời 1500 ký tự cho tỉ lệ
# ≤ 0.11 dù trùng từng chữ — đo thật thì tính năng không bao giờ chạy. Độ phủ từ
# không phụ thuộc độ dài.
_NGUONG_ANH = 0.25
_MAX_ANH = 2
# Từ quá ngắn/quá phổ thông thì không nói lên độ liên quan.
_BO_TU = {"là", "và", "của", "các", "một", "có", "cho", "trong", "với", "hình",
          "sau", "này", "đó", "thì", "hay", "nào", "về", "ở", "từ", "được"}


def _phu_tu(caption: str, van: str) -> float:
    """Bao nhiêu phần từ của caption xuất hiện trong văn bản câu hỏi + trả lời."""
    tu = {t for t in diem_khop.chuan(caption).split() if len(t) > 1 and t not in _BO_TU}
    if not tu:
        return 0.0
    co = set(diem_khop.chuan(van).split())
    return len(tu & co) / len(tu)


def _anh_cua_bai(c: TopicContent) -> list[tuple[str, str, str]]:
    """(url thô, caption, nhãn nguồn) của mọi hình trong bài — minh hoạ + hình ví dụ.

    Chỉ lấy ẢNH: video đã có thẻ phát riêng trong bài, đính lại vào câu trả lời
    chat thì học sinh phải xem hai lần cùng một thứ.
    """
    ra: list[tuple[str, str, str]] = []
    for m in _ds(c.minh_hoa_json):
        url = (m.get("url") or "").strip()
        if url and m.get("type") != "video":
            ra.append((url, (m.get("caption") or "Hình minh hoạ").strip(), "Minh hoạ"))
    for i, e in enumerate(_ds(c.vi_du_json), start=1):
        url = (e.get("anh") or "").strip()
        if url:
            # Caption của hình ví dụ = đề bài: đó là thứ tả đúng hình đang vẽ gì.
            ra.append((url, _bo_the(e.get("de", ""))[:120] or f"Hình ví dụ {i}", f"Ví dụ {i}"))
    return ra


def _chon_anh(c: TopicContent | None, anchor: str | None, cau_hoi: str,
              tra_loi: str) -> list[AnhKem]:
    """Hình nên đính theo câu trả lời. Rỗng nếu bài không có hình hoặc không liên quan.

    Ba tầng, chặt trước lỏng sau:
      1. `anchor` — học sinh bấm "Hỏi" ngay ở Ví dụ 2 thì hình của Ví dụ 2 chắc
         chắn đúng, không cần đoán.
      2. Câu HỎI có nói về hình không (không xét câu trả lời — xem ghi chú dưới).
      3. Trong các hình của bài, chọn cái có caption phủ nhiều từ của câu
         hỏi + câu trả lời nhất.
    """
    if c is None:
        return []
    ds = _anh_cua_bai(c)
    if not ds:
        return []

    if anchor and anchor.startswith("vi_du:"):
        nhan = f"Ví dụ {anchor.split(':')[1]}"
        cua_vd = [x for x in ds if x[2] == nhan]
        if cua_vd:
            return [AnhKem(url=security.sign_media(u), caption=cap, tu=tu)
                    for u, cap, tu in cua_vd[:_MAX_ANH]]
    if anchor == "minh_hoa":
        mh = [x for x in ds if x[2] == "Minh hoạ"]
        if mh:
            return [AnhKem(url=security.sign_media(u), caption=cap, tu=tu)
                    for u, cap, tu in mh[:_MAX_ANH]]

    # Chỉ xét CÂU HỎI, không xét câu trả lời: bài hình học thì câu trả lời nào
    # cũng nhắc lại tên bài ("…về hình có trục đối xứng") nên lọc theo câu trả lời
    # là mở cửa cho mọi câu, kể cả "bài này có mấy phần?" (đã gặp thật). Ý muốn
    # của học sinh nằm ở câu hỏi.
    if not _DAU_HINH.search(cau_hoi):
        return []
    van = f"{cau_hoi} {tra_loi}"
    diem = sorted(((_phu_tu(cap, van), u, cap, tu) for u, cap, tu in ds), key=lambda x: -x[0])
    chon = [x[1:] for x in diem if x[0] >= _NGUONG_ANH][:_MAX_ANH]
    # Không caption nào khớp nhưng câu hỏi RÕ RÀNG về hình (đã qua `_DAU_HINH`) và
    # bài này có hình -> vẫn đưa hình đầu tiên. Caption kiểu "Hình minh hoạ" không
    # trùng chữ nào cả; im lặng ở đây nghĩa là tính năng gần như không bao giờ chạy.
    if not chon:
        chon = ds[:1]
    return [AnhKem(url=security.sign_media(u), caption=cap, tu=tu) for u, cap, tu in chon]


def _ds(raw: str | None) -> list[dict]:
    """Cột JSON -> list các dict. Rác/kiểu lạ -> [] chứ KHÔNG nổ.

    `json.loads` trên cột bị sửa tay có thể ra dict, số, hoặc JSONDecodeError; khi
    đó vòng `for m in ...` lặp qua KHOÁ (chuỗi) rồi `m.get(...)` nổ AttributeError
    -> 500 cho cả câu hỏi. Nội dung do AI sinh + chuyên gia sửa tay trong CMS nên
    đây là đầu vào không tin được, phải chặn ở một chỗ.
    """
    try:
        d = json.loads(raw or "[]")
    except (TypeError, ValueError):
        log.warning("Cột JSON của nội dung bài không đọc được, bỏ qua")
        return []
    if not isinstance(d, list):
        return []
    return [x for x in d if isinstance(x, dict)]


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
    vd = _ds(c.vi_du_json)

    # `kien_thuc` là TÊN MỚI của phần khái niệm (§1.1); `khai_niem` giữ lại cho
    # client cũ. Hai neo cùng trỏ một chỗ.
    if anchor in ("khai_niem", "kien_thuc"):
        return f"KIẾN THỨC TRỌNG TÂM:\n{kn}", "Kiến thức trọng tâm"

    # 4 phần mới: nội dung nằm ở cột riêng, KÈM kiến thức trọng tâm làm nền —
    # hỏi về một bài luyện tập mà không có lý thuyết thì trả lời được rất ít.
    if anchor in ("khoi_dong", "hoat_dong", "luyen_tap", "bai_tap"):
        from app.lessons import bo_cuc as _bc

        ten = next(x["ten"] for x in _bc.PHAN if x["id"] == anchor)
        noi = _bo_the(_bc.noi_dung(c, anchor))
        if not noi:
            # Phần chưa soạn -> rơi về cả bài thay vì đưa mô hình một đoạn rỗng
            # rồi nhận về câu trả lời bịa.
            anchor = None
        else:
            return f"KIẾN THỨC TRỌNG TÂM:\n{kn}\n\n{ten.upper()}:\n{noi}", ten

    if anchor == "minh_hoa":
        mh = _ds(c.minh_hoa_json)
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
        quiz = _ds(c.quiz_json)
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
    bai_hoc, nguon_bai, ten_dv, noi_dung = "", None, body.context, None
    if body.topic_id is not None:
        bai_hoc, nguon_bai, ten_dv, noi_dung = await _ngu_canh_bai(
            session, user, body.topic_id, anchor, ten_dv)

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
    # Không đính hình khi trợ lý đã nói "không có trong sách": kèm một cái hình
    # vào câu từ chối thì đọc thành trả lời nửa vời.
    # Đính hình là việc PHỤ. Nó chạy SAU khi đã gọi LLM, tức là đã tiêu một lượt
    # hỏi của học sinh và đã tốn tiền — để nó ném lên thành 500 là mất luôn câu
    # trả lời đã trả tiền. Lỗi ở đây chỉ được ghi log rồi trả lời không kèm hình.
    anh: list[AnhKem] = []
    if not ktf:
        try:
            anh = _chon_anh(noi_dung, anchor, q, answer)
        except Exception:  # noqa: BLE001 — không được làm vỡ câu trả lời
            log.exception("Chọn hình minh hoạ lỗi (topic=%s, anchor=%s)",
                          body.topic_id, anchor)
    return AskResponse(answer=answer, citations=cits[:3], khong_tim_thay=ktf,
                       remaining=remaining, nguon_bai=None if ktf else nguon_bai,
                       anh=anh)


async def _ngu_canh_bai(
    session: AsyncSession, user: User, topic_id: int, anchor: str | None, ten_cu: str | None,
) -> tuple[str, str | None, str | None, TopicContent | None]:
    """Đọc nội dung đơn vị đang mở -> (ngữ cảnh, nhãn nguồn, tên đơn vị, bản nội dung).

    Trả luôn bản nội dung để chỗ gọi lấy hình mà không phải truy vấn lần hai —
    và để hình đi theo ĐÚNG luật quyền ở dưới (chưa xuất bản thì không có gì).

    Topic/nội dung không có thì trả rỗng chứ KHÔNG 404: câu hỏi vẫn trả lời được
    bằng SGK như trước, chặn ở đây chỉ tổ làm hỏng trải nghiệm vì một cái id cũ."""
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        return "", None, ten_cu, None
    ten_dv = re.sub(r"\s+", " ", (topic.don_vi_kien_thuc or "").strip()) or ten_cu

    c = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    # Học sinh chỉ được ngữ cảnh từ bản ĐÃ XUẤT BẢN — cùng luật với GET /lessons.
    if c is None or (user.role not in _TAC_GIA and c.trang_thai != "published"):
        return "", None, ten_dv, None

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
    return doan[:_MAX_BAI], nhan, ten_dv, c
