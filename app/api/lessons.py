"""API giáo trình có cấu trúc (mô hình mockup): mục lục Mạch→Đơn vị, nội dung
bài học 4 phần, tiến độ học sinh theo đơn vị kiến thức.

- GET  /curriculum            — mục lục + trạng thái tiến độ + cờ có nội dung
- GET  /lessons/{topic_id}    — nội dung 4 phần (khái niệm/minh họa/ví dụ/hướng dẫn dạy)
- GET  /progress/me           — tiến độ của HS hiện tại (gom theo mạch + % tổng)
- POST /progress              — cập nhật trạng thái 1 đơn vị (dat|dang|chua)

Phần "Kiểm tra nhanh" KHÔNG ở đây — sinh theo ma trận (P3, tái dùng app/exam).
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.api.deps import get_current_user
from app.db.models import (
    CurriculumTopic, Grade, QuizAttempt, StudentProgress, Subject, TopicContent, User,
)
from app.db.session import get_session
from app.lessons import media as media_svc
from app.lessons import nhac as nhac_svc
from app.lessons import quiz as quiz_svc
from app.lessons import stats as stats_svc
from app.llm.gateway import LLMUnavailable

# XP thưởng: mỗi câu đúng + thưởng khi đạt bài / khi tự đánh dấu hoàn thành.
_XP_PER_CORRECT = 5
_XP_QUIZ_PASS = 10
_XP_MARK_DONE = 15

router = APIRouter(tags=["lessons"])

# Ngưỡng ĐẠT bài kiểm tra nhanh -> đơn vị chuyển "dat" (đúng >= 70%).
_NGUONG_DAT = 0.7


def _is_author(user: User) -> bool:
    """Giáo viên/quản trị: xem được đáp án + nội dung chưa xuất bản (soạn/duyệt)."""
    return user.role in {"chuyen_gia", "giao_vien", "admin"}


def _sign_media(items: list[dict]) -> list[dict]:
    """Ký URL video nội bộ (/video/files/...) để HS phát được trong hạn; URL
    ngoài (http…) hoặc rỗng giữ nguyên."""
    out = []
    for m in items:
        url = m.get("url") or ""
        if url.startswith("/video/files/"):
            m = {**m, "url": security.sign_media(url)}
        out.append(m)
    return out

_MACH_EMOJI = {
    "số tự nhiên": "🔢", "số nguyên": "➖",
    "các hình phẳng trong thực tiễn": "🔺",
    "tính đối xứng của hình phẳng": "🔷",
    "phân số": "➗", "số thập phân": "💯",
    "các hình hình học cơ bản": "📐",
    "thu thập và tổ chức dữ liệu": "📊",
    "phân tích và xử lí dữ liệu": "📈",
    "một số yếu tố xác suất": "🎲",
}
_STATES = {"dat", "dang", "chua"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


async def _units(session: AsyncSession, mon: str, khoi: str) -> list[dict]:
    """Mục lục đã KHỬ TRÙNG: [{mach, em, dv:[{topic_id, ten}]}] theo order_index.
    Mỗi đơn vị (mach,dv) lấy topic_id ĐẠI DIỆN (bản gặp đầu)."""
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        return []
    rows = list(await session.scalars(
        select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
        .order_by(CurriculumTopic.order_index)
    ))
    groups: list[dict] = []
    gidx: dict[str, dict] = {}
    for t in rows:
        mach, dv = _norm(t.mach_noi_dung), _norm(t.don_vi_kien_thuc)
        if not dv:
            continue
        g = gidx.get(mach.lower())
        if g is None:
            g = {"mach": mach, "em": _MACH_EMOJI.get(mach.lower(), "📘"), "dv": [], "_seen": set()}
            gidx[mach.lower()] = g
            groups.append(g)
        if dv.lower() not in g["_seen"]:
            g["_seen"].add(dv.lower())
            g["dv"].append({"topic_id": t.id, "ten": dv})
    for g in groups:
        g.pop("_seen", None)
    return groups


async def _progress_map(session: AsyncSession, user_id: int) -> dict[int, str]:
    rows = await session.scalars(select(StudentProgress).filter_by(user_id=user_id))
    return {r.topic_id: r.trang_thai for r in rows}


@router.get("/curriculum")
async def get_curriculum(
    mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Mục lục Mạch→Đơn vị + trạng thái tiến độ của HS + cờ đã có nội dung."""
    groups = await _units(session, mon, khoi)
    prog = await _progress_map(session, user.id)
    # HS chỉ thấy đơn vị ĐÃ XUẤT BẢN; tác giả (GV/QT) thấy mọi bản có nội dung.
    q = select(TopicContent.topic_id)
    if not _is_author(user):
        q = q.filter(TopicContent.trang_thai == "published")
    have = set(await session.scalars(q))
    for g in groups:
        for d in g["dv"]:
            d["trang_thai"] = prog.get(d["topic_id"], "chua")
            d["co_noi_dung"] = d["topic_id"] in have
    return groups


@router.get("/lessons/{topic_id}")
async def get_lesson(
    topic_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Nội dung bài học 4 phần cho 1 đơn vị. Chưa biên soạn -> trả khung rỗng."""
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    c = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    base = {"topic_id": topic_id, "mach": _norm(topic.mach_noi_dung), "dv": _norm(topic.don_vi_kien_thuc)}
    author = _is_author(user)
    # HS chỉ đọc bản đã xuất bản; bản nháp/chờ duyệt coi như "chưa biên soạn".
    if c is None or (not author and c.trang_thai != "published"):
        return {**base, "khai_niem": "", "minh_hoa": [], "vi_du": [], "quiz": [],
                "co_quiz": False, "nhac": [], "day": None, "nguon": None,
                "trang_thai": "chua_bien_soan"}
    quiz = json.loads(c.quiz_json or "[]")
    return {
        **base,
        "khai_niem": c.khai_niem,
        # fill_video_urls TRƯỚC khi ký: video AI đặt hàng lúc biên soạn có url=None
        # tới khi job render xong, không có bước này thì HS mãi thấy poster rỗng.
        "minh_hoa": _sign_media(
            await media_svc.fill_video_urls(session, json.loads(c.minh_hoa_json or "[]"))
        ),
        "vi_du": json.loads(c.vi_du_json or "[]"),
        # HS KHÔNG nhận đáp án/lời giải (chấm ở server) — chỉ đề + phương án.
        "quiz": quiz if author else [{"q": x["q"], "o": x["o"], "lv": x.get("lv", "de")} for x in quiz],
        "co_quiz": len(quiz) > 0,
        # Lời nhắc chủ động của trợ lý ở các mốc trong bài (đã sinh sẵn lúc biên
        # soạn — xem app/lessons/nhac). `giai` đi kèm để client hiện phản hồi
        # ngay khi HS bấm chọn, KHÔNG phải gọi LLM và không tốn lượt hỏi.
        "nhac": nhac_svc.doc_nhac(c),
        "day": json.loads(c.day_json) if c.day_json else None,
        # `nguon` là tư liệu THÔ chuyên gia dán vào cho AI, không phải nội dung
        # bài học — không giao diện HS nào hiển thị nó. Chỉ trả cho tác giả.
        "nguon": c.nguon if author else None,
        "trang_thai": c.trang_thai,
    }


@router.get("/progress/me")
async def my_progress(
    mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Tiến độ HS theo đơn vị, gom theo mạch + % hoàn thành tổng."""
    groups = await _units(session, mon, khoi)
    prog = await _progress_map(session, user.id)
    total = done = doing = 0
    out = []
    for g in groups:
        items, gdone = [], 0
        for d in g["dv"]:
            st = prog.get(d["topic_id"], "chua")
            items.append({"topic_id": d["topic_id"], "ten": d["ten"], "trang_thai": st})
            total += 1
            if st == "dat":
                done += 1; gdone += 1
            elif st == "dang":
                doing += 1
        pct = round(100 * gdone / len(items)) if items else 0
        out.append({"mach": g["mach"], "em": g["em"], "phan_tram": pct, "dv": items})
    overall = round(100 * done / total) if total else 0
    return {"overall": overall, "dat": done, "dang": doing, "tong": total, "mach": out}


@router.get("/me/stats")
async def my_stats(
    mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Dữ liệu hero gamification: % tổng, đơn vị đạt/tổng, mạch hiện tại, streak,
    điểm XP tuần này."""
    groups = await _units(session, mon, khoi)
    prog = await _progress_map(session, user.id)
    total = done = 0
    mach_out = []
    for g in groups:
        n = len(g["dv"])
        gdone = sum(1 for d in g["dv"] if prog.get(d["topic_id"], "chua") == "dat")
        total += n
        done += gdone
        mach_out.append({"mach": g["mach"], "em": g["em"],
                         "phan_tram": round(100 * gdone / n) if n else 0})
    overall = round(100 * done / total) if total else 0
    # Mạch "hiện tại" = mạch chưa hoàn thành đầu tiên (để hiển thị trên vòng tiến độ).
    current = next((m for m in mach_out if m["phan_tram"] < 100), mach_out[-1] if mach_out else None)

    st = await stats_svc.get_or_create(session, user.id)
    xp_week, streak, xp_total = st.week_points, st.streak_days, st.xp_total
    await session.commit()  # get_or_create có thể vừa tạo dòng mới
    return {
        "overall": overall, "dat": done, "tong": total,
        "current_mach": current, "streak": streak,
        "xp_week": xp_week, "xp_total": xp_total,
    }


class ProgressUpdate(BaseModel):
    topic_id: int
    trang_thai: str


@router.post("/progress")
async def set_progress(
    body: ProgressUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Cập nhật trạng thái 1 đơn vị cho HS hiện tại (upsert)."""
    if body.trang_thai not in _STATES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trạng thái không hợp lệ")
    if await session.get(CurriculumTopic, body.topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    row = await session.scalar(
        select(StudentProgress).filter_by(user_id=user.id, topic_id=body.topic_id)
    )
    da_dat_truoc = row is not None and row.trang_thai == "dat"
    if row is None:
        session.add(StudentProgress(user_id=user.id, topic_id=body.topic_id, trang_thai=body.trang_thai))
    else:
        row.trang_thai = body.trang_thai
    # Thưởng XP khi CHUYỂN sang "dat" (không cộng lại nếu đã đạt từ trước).
    if body.trang_thai == "dat" and not da_dat_truoc:
        await stats_svc.award(session, user.id, _XP_MARK_DONE)
    out = {"topic_id": body.topic_id, "trang_thai": body.trang_thai}
    await session.commit()
    return out


async def _upsert_progress(session: AsyncSession, user_id: int, topic_id: int, trang_thai: str) -> None:
    row = await session.scalar(
        select(StudentProgress).filter_by(user_id=user_id, topic_id=topic_id)
    )
    if row is None:
        session.add(StudentProgress(user_id=user_id, topic_id=topic_id, trang_thai=trang_thai))
    else:
        # Không hạ cấp: đã "dat" thì làm lại chưa đạt không kéo về "dang".
        if not (row.trang_thai == "dat" and trang_thai == "dang"):
            row.trang_thai = trang_thai


@router.post("/lessons/{topic_id}/quiz/generate")
async def generate_quiz(
    topic_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Sinh (lại) bài kiểm tra nhanh theo ma trận rồi cache vào nội dung đơn vị.
    CHỈ tác giả (GV/QT). Tạo bản nội dung rỗng nếu chưa có."""
    if not _is_author(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ giáo viên/quản trị được sinh đề kiểm tra")
    if await session.get(CurriculumTopic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    try:
        quiz = await quiz_svc.generate_quiz(session, topic_id)
    except LLMUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Hệ thống AI đang quá tải, thử lại sau ít phút nhé.")
    if not quiz:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI chưa soạn được câu hỏi hợp lệ, thử lại nhé.")
    c = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    if c is None:
        c = TopicContent(topic_id=topic_id)
        session.add(c)
    c.quiz_json = json.dumps(quiz, ensure_ascii=False)
    await session.commit()
    return {"topic_id": topic_id, "quiz": quiz, "so_cau": len(quiz)}


class QuizSubmit(BaseModel):
    topic_id: int
    # đáp án HS chọn theo THỨ TỰ câu (index phương án); -1 = bỏ trống.
    answers: list[int]


@router.post("/quiz/submit")
async def submit_quiz(
    body: QuizSubmit,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """HS nộp bài kiểm tra nhanh -> chấm ở SERVER (đáp án không gửi ra client),
    cập nhật tiến độ đơn vị: đúng ≥70% -> 'dat', ngược lại 'dang'."""
    topic = await session.get(CurriculumTopic, body.topic_id)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    c = await session.scalar(select(TopicContent).filter_by(topic_id=body.topic_id))
    quiz = json.loads(c.quiz_json) if c and c.quiz_json else []
    if not quiz:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Đơn vị này chưa có bài kiểm tra nhanh")

    ket_qua = []
    diem = 0
    for i, q in enumerate(quiz):
        chon = body.answers[i] if i < len(body.answers) else -1
        dung = chon == q["a"]
        if dung:
            diem += 1
        ket_qua.append({"dung": dung, "chon": chon, "dap_an": q["a"], "giai": q.get("giai", "")})

    tong = len(quiz)
    dat = diem / tong >= _NGUONG_DAT
    trang_thai = "dat" if dat else "dang"
    await _upsert_progress(session, user.id, body.topic_id, trang_thai)
    # Ghi lại TỪNG lần nộp (không khử trùng) — student_progress chỉ giữ trạng thái
    # cuối nên không có nó thì mất sạch quá trình học.
    session.add(QuizAttempt(user_id=user.id, topic_id=body.topic_id,
                            diem=diem, tong=tong, dat=dat))
    # XP: mỗi câu đúng + thưởng nếu đạt. Cập nhật streak/điểm tuần.
    xp = diem * _XP_PER_CORRECT + (_XP_QUIZ_PASS if dat else 0)
    st = await stats_svc.award(session, user.id, xp)
    xp_week, streak = st.week_points, st.streak_days  # đọc TRƯỚC commit
    # Đọc lại trạng thái CUỐI (có thể vẫn "dat" nhờ không hạ cấp) trước commit.
    row = await session.scalar(
        select(StudentProgress).filter_by(user_id=user.id, topic_id=body.topic_id)
    )
    trang_thai_cuoi = row.trang_thai if row else trang_thai
    out = {
        "diem": diem, "tong": tong, "dat_yeu_cau": dat,
        "trang_thai": trang_thai_cuoi, "ket_qua": ket_qua,
        "xp": xp, "xp_week": xp_week, "streak": streak,
    }
    await session.commit()
    return out
