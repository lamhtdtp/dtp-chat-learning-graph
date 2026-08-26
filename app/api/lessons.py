"""API giáo trình có cấu trúc (mô hình mockup): mục lục Mạch→Đơn vị, nội dung
bài học 4 phần, tiến độ học sinh theo đơn vị kiến thức.

- GET  /curriculum            — mục lục + trạng thái tiến độ + cờ có nội dung
- GET  /lessons/{topic_id}    — nội dung 4 phần (khái niệm/minh họa/ví dụ/hướng dẫn dạy)
- GET  /progress/me           — tiến độ của HS hiện tại (gom theo mạch + % tổng)
- POST /progress              — cập nhật trạng thái 1 đơn vị (dat|dang|chua)

Phần "Kiểm tra nhanh" KHÔNG ở đây — sinh theo ma trận (P3, tái dùng app/exam).
"""
import json
from datetime import timedelta
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.api.deps import get_current_user
from app.db.models import (
    BlueprintCell, CurriculumTopic, Grade, QuizAttempt, StudentProgress, StudySession,
    Subject, TopicContent, User,
)
from app.db.session import get_session
from app.lessons import bo_cuc as bo_cuc_svc
from app.lessons import media as media_svc
from app.lessons import phien as phien_svc
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

def _sign_vi_du(items: list[dict]) -> list[dict]:
    """Ký hình của ví dụ; `anh_prompt` là ghi chú nội bộ cho người soạn, HS không cần."""
    out = []
    for e in items:
        anh = e.get("anh") or ""
        e = {k: v for k, v in e.items() if k != "anh_prompt"}
        out.append({**e, "anh": security.sign_media(anh)}
                   if anh.startswith("/video/files/") else e)
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
        "vi_du": _sign_vi_du(json.loads(c.vi_du_json or "[]")),
        # 4 phần nội dung mới (§1.1). Ba phần cũ vẫn trả ở khoá cũ để client chưa
        # cập nhật không vỡ.
        "khoi_dong": c.khoi_dong or "",
        "hoat_dong": c.hoat_dong or "",
        "luyen_tap": c.luyen_tap or "",
        "bai_tap": c.bai_tap or "",
        # Thứ tự + số thứ tự các phần ĐANG HIỆN. Client CHỈ render theo mảng này —
        # tự suy thứ tự ở FE là chỗ để số lệch với bản chuyên gia đang soạn.
        "bo_cuc": bo_cuc_svc.hien_thuc_te(c, c.bo_cuc_json),
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
    # Mạch "hiện tại" = mạch chưa hoàn thành đầu tiên. Chỉ là MẶC ĐỊNH khi chưa
    # mở bài nào; client tự chọn mạch của bài đang mở từ danh sách `mach` dưới đây
    # (trước chỉ trả mỗi `current_mach` nên vòng tiến độ đứng ở mạch cũ suốt).
    current = next((m for m in mach_out if m["phan_tram"] < 100), mach_out[-1] if mach_out else None)

    # % theo YÊU CẦU CẦN ĐẠT: mỗi ô ma trận là một yêu cầu, tính đạt khi đơn vị
    # chứa nó đã đạt (cùng quy ước với GET /me/ycd).
    ids = [d["topic_id"] for g in groups for d in g["dv"]]
    cell_rows = (await session.execute(
        select(BlueprintCell.topic_id, func.count())
        .where(BlueprintCell.topic_id.in_(ids or [0]))
        .group_by(BlueprintCell.topic_id))).all()
    ycd_tong = sum(n for _, n in cell_rows)
    ycd_dat = sum(n for tid, n in cell_rows if prog.get(tid) == "dat")

    st = await stats_svc.get_or_create(session, user.id)
    xp_week, streak, xp_total = st.week_points, st.streak_days, st.xp_total
    await session.commit()  # get_or_create có thể vừa tạo dòng mới
    return {
        "overall": overall, "dat": done, "tong": total,
        "current_mach": current, "mach": mach_out, "streak": streak,
        "ycd_dat": ycd_dat, "ycd_tong": ycd_tong,
        "ycd_phan_tram": round(100 * ycd_dat / ycd_tong) if ycd_tong else 0,
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
        # `phan` + `ycd` để client chỉ HS về đúng đoạn cần đọc lại (§3.4). Câu cũ
        # (sinh trước khi có 2 khoá này) -> mặc định kien_thuc, phần luôn có mặt.
        ket_qua.append({"dung": dung, "chon": chon, "dap_an": q["a"], "giai": q.get("giai", ""),
                        "phan": q.get("phan") or "kien_thuc", "ycd": q.get("ycd", "")})

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


class PhienBody(BaseModel):
    topic_id: int
    giay: int = 30   # client ping mỗi ~30s khi tab đang hiện; server chặn trần
    # Các phần HS đã cuộn qua. Server HỢP NHẤT, không ghi đè (xem phien.ping).
    phan_doc: list[str] = []


@router.post("/me/phien")
async def ping_phien(
    body: PhienBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Ghi thời gian học (REQ §8). Client gửi "vừa học thêm k giây", KHÔNG gửi tổng.

    Nhận tổng từ client thì mở devtools là tự khai 10 tiếng học; server cộng dồn và
    chặn trần theo khoảng ping."""
    if await session.get(CurriculumTopic, body.topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    ph = await phien_svc.ping(session, user.id, body.topic_id, body.giay, body.phan_doc)
    so_giay = ph.so_giay
    await session.commit()
    return {"topic_id": body.topic_id, "so_giay_phien": so_giay}


@router.get("/me/thoi-gian")
async def me_thoi_gian(
    ngay: int = 14,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """4 ô thời gian + biểu đồ ngày + lịch sử phiên (REQ §3.6 khối 1–3)."""
    d = await phien_svc.thoi_gian(session, user.id, max(1, min(ngay, 90)))
    rows = (await session.execute(
        select(StudySession, CurriculumTopic.don_vi_kien_thuc)
        .join(CurriculumTopic, CurriculumTopic.id == StudySession.topic_id)
        .where(StudySession.user_id == user.id)
        .order_by(StudySession.mo_luc.desc()).limit(20))).all()
    # Kết quả kiểm tra + tổng số phần của từng bài, gom một lượt (tránh N+1).
    tids = {p.topic_id for p, _ in rows}
    contents = {c.topic_id: c for c in await session.scalars(
        select(TopicContent).where(TopicContent.topic_id.in_(tids or {0})))}
    # Lần nộp quiz thuộc CHÍNH phiên đó. Lấy "lần gần nhất theo bài" thì kết quả
    # hôm nay gán cả vào phiên tuần trước — nhãn nói sai về phiên đang xem.
    qa_rows = (await session.execute(
        select(QuizAttempt).where(QuizAttempt.user_id == user.id,
                                  QuizAttempt.topic_id.in_(tids or {0}))
        .order_by(QuizAttempt.created_at.desc(), QuizAttempt.id.desc()))).scalars().all()

    def _quiz_cua_phien(ph) -> QuizAttempt | None:
        """Lần nộp nằm trong khoảng phiên. Nới 5 phút sau `dong_luc`: HS nộp bài
        rồi mới rời trang, ping cuối có thể đã dừng trước đó."""
        tre = ph.dong_luc + timedelta(minutes=5)
        for a in qa_rows:
            if a.topic_id == ph.topic_id and ph.mo_luc <= a.created_at <= tre:
                return a          # qa_rows sắp mới -> cũ, cái đầu là mới nhất
        return None

    lich_su = []
    for p, ten in rows:
        c = contents.get(p.topic_id)
        # Mẫu số = số phần ĐANG HIỆN của bài đó, tính lại mỗi lần đọc: chuyên gia
        # ẩn/thêm phần thì "x/y" phải đổi theo, không dùng số cứng 7.
        hien = bo_cuc_svc.hien_thuc_te(c, c.bo_cuc_json) if c else []
        tong_phan = len(hien)
        # Lọc theo phần ĐANG HIỆN, không theo toàn bộ IDS: học sinh đọc 4 phần rồi
        # chuyên gia ẩn bớt một phần thì hồ sơ hiện "Đọc 4/3 phần" — tử lớn hơn
        # mẫu, đọc vào không hiểu gì.
        # Bài chưa có nội dung thì không có tập "đang hiện" để đối chiếu — lọc
        # theo IDS như cũ (mẫu số bằng 0 nên giao diện tự ẩn dòng này).
        id_hien = {x["id"] for x in hien} if hien else bo_cuc_svc.IDS
        da_doc = [x for x in phien_svc.doc_phan(p) if x in id_hien]
        a = _quiz_cua_phien(p)
        lich_su.append({
            "topic_id": p.topic_id, "ten": (ten or "").strip(),
            "luc": p.mo_luc.isoformat(), "phut": round((p.so_giay or 0) / 60),
            "so_hoi": p.so_hoi or 0,
            "doc_x": len(da_doc), "doc_y": tong_phan,
            "quiz": {"diem": a.diem, "tong": a.tong, "dat": a.dat} if a else None,
            "dang_hoc": phien_svc.dang_hoc(p),
        })
    d["lich_su"] = lich_su
    return d


@router.get("/me/ycd")
async def me_ycd(
    mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Đạt tới đâu theo yêu cầu cần đạt (REQ §3.6 khối 4).

    Giữ ĐÚNG thứ tự trong ma trận, không sắp lại theo số lần sai — chuyên gia đọc
    theo mạch, đảo thứ tự là mất mạch.
    """
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        return {"mach": []}
    topics = list(await session.scalars(
        select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
        .order_by(CurriculumTopic.order_index)))
    ids = [t.id for t in topics]
    ten_topic = {t.id: t for t in topics}
    prog = await _progress_map(session, user.id)

    cells = list(await session.scalars(
        select(BlueprintCell).where(BlueprintCell.topic_id.in_(ids or [0]))
        .order_by(BlueprintCell.id)))
    # Số lần làm sai theo ĐƠN VỊ (không theo chỉ số câu — đề sinh lại thì chỉ số
    # trỏ sai đề, xem ghi chú ở QuizAttempt).
    sai_rows = (await session.execute(
        select(QuizAttempt.topic_id, func.count())
        .where(QuizAttempt.user_id == user.id, ~QuizAttempt.dat)
        .group_by(QuizAttempt.topic_id))).all()
    sai = {tid: n for tid, n in sai_rows}

    mach: dict[str, list] = {}
    for c in cells:
        t = ten_topic.get(c.topic_id)
        if t is None:
            continue
        tt = prog.get(c.topic_id, "chua")
        mach.setdefault((t.mach_noi_dung or "").strip(), []).append({
            "ycd": c.yeu_cau_can_dat, "muc_do": c.muc_do,
            "topic_id": c.topic_id, "don_vi": (t.don_vi_kien_thuc or "").strip(),
            "trang_thai": tt, "sai": sai.get(c.topic_id, 0),
        })
    return {"mach": [{"mach": k, "ycd": v} for k, v in mach.items()]}


# Số câu đề ôn tập. Ôn chương gọn, cuối kỳ dài hơn vì gộp cả học kỳ (REQ §3.5).
_SO_CAU_ON = {"mach": 12, "hoc_ky": 30}


@router.get("/on-tap")
async def on_tap(
    pham_vi: str, gia_tri: str, mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Trang Ôn tập chương / cuối học kỳ (REQ §3.5).

    `pham_vi`: "mach" (gia_tri = tên mạch) | "hoc_ky" (gia_tri = "hk1"|"hk2").

    KHÔNG phải `CurriculumTopic` mới — đây là *view* gộp các đơn vị trong phạm vi.
    Không có 7 phần, không bài mới: chỉ gom lại + đề lấy từ blueprint_cells của
    toàn bộ đơn vị trong phạm vi.
    """
    if pham_vi not in _SO_CAU_ON:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'pham_vi phải là "mach" hoặc "hoc_ky"')
    # `gia_tri` rỗng từng đi tới đây rồi rơi vào 404 "phạm vi không có đơn vị nào"
    # — đọc vào tưởng dữ liệu thiếu, trong khi lỗi là client gửi tham số rỗng.
    if not (gia_tri or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Thiếu `gia_tri` (tên mạch hoặc hk1/hk2)")
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy môn/khối")

    q = select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
    if pham_vi == "mach":
        q = q.filter(CurriculumTopic.mach_noi_dung == gia_tri)
    else:
        q = q.filter(CurriculumTopic.hoc_ky == gia_tri)
    topics = list(await session.scalars(q.order_by(CurriculumTopic.order_index)))
    if not topics:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Phạm vi ôn tập không có đơn vị nào")

    ids = [t.id for t in topics]
    prog = await _progress_map(session, user.id)
    contents = {c.topic_id: c for c in await session.scalars(
        select(TopicContent).where(TopicContent.topic_id.in_(ids)))}

    # Khử trùng theo TÊN đơn vị: mục lục khử trùng nên một đơn vị có thể ứng nhiều
    # topic_id; không khử thì danh sách ôn tập hiện lặp cùng một bài.
    bai, da_co = [], set()
    for t in topics:
        ten = (t.don_vi_kien_thuc or "").strip()
        if not ten or ten.lower() in da_co:
            continue
        da_co.add(ten.lower())
        c = contents.get(t.id)
        bai.append({
            "topic_id": t.id, "ten": ten, "mach": (t.mach_noi_dung or "").strip(),
            "trang_thai": prog.get(t.id, "chua"),
            "co_noi_dung": bool(c and (c.khai_niem or "").strip()),
        })
    chua_xong = sum(1 for b in bai if b["trang_thai"] != "dat")

    # "Cần nhớ" gom từ blockquote trong Kiến thức trọng tâm của các bài — chỗ chuyên
    # gia đã đánh dấu là phần phải nhớ, không cần AI sinh lại.
    can_nho = []
    for b in bai:
        c = contents.get(b["topic_id"])
        for m in re.findall(r"(?is)<blockquote[^>]*>(.*?)</blockquote>", (c.khai_niem if c else "") or ""):
            txt = re.sub(r"<[^>]+>", "", m).strip()
            if txt:
                can_nho.append({"topic_id": b["topic_id"], "ten": b["ten"], "y": txt})
    ycd = await session.scalar(select(func.count()).select_from(BlueprintCell)
                               .where(BlueprintCell.topic_id.in_(ids))) or 0

    # Số câu THẬT gom được, không phải chỉ tiêu: bài chưa có đề kiểm tra nhanh thì
    # không góp câu nào. Hứa 12 câu rồi đưa ra 8 là nói sai với học sinh.
    #
    # Đếm theo đề ĐÃ PARSE, không theo `if c.quiz_json`: chuỗi "[]" cũng khác
    # rỗng nên bài có cột quiz_json = "[]" từng bị tính là "có đề" trong khi
    # không góp câu nào.
    so_cau_bai = [len(json.loads(c.quiz_json or "[]")) for c in contents.values()]
    co = sum(so_cau_bai)
    return {
        "pham_vi": pham_vi, "gia_tri": gia_tri,
        "so_bai": len(bai), "chua_xong": chua_xong,
        "bai": bai, "can_nho": can_nho[:8], "ycd": ycd,
        "so_cau_de": min(_SO_CAU_ON[pham_vi], co),
        "so_cau_toi_da": _SO_CAU_ON[pham_vi],
        "so_bai_co_de": sum(1 for n in so_cau_bai if n > 0),
    }


# ─────────────── Đề ôn tập chương / cuối kỳ (REQ §3.5) ───────────────
# Đề ôn tập KHÔNG sinh mới bằng AI: gom lại chính các câu đã sinh theo ma trận
# cho từng đơn vị trong phạm vi. Sinh mới sẽ lệch khỏi ma trận đặc tả và tốn AI
# cho thứ đã có sẵn.

async def _topics_pham_vi(session: AsyncSession, pham_vi: str, gia_tri: str,
                          mon: str, khoi: str) -> list[CurriculumTopic]:
    if pham_vi not in _SO_CAU_ON:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'pham_vi phải là "mach" hoặc "hoc_ky"')
    # `gia_tri` rỗng từng đi tới đây rồi rơi vào 404 "phạm vi không có đơn vị nào"
    # — đọc vào tưởng dữ liệu thiếu, trong khi lỗi là client gửi tham số rỗng.
    if not (gia_tri or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Thiếu `gia_tri` (tên mạch hoặc hk1/hk2)")
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy môn/khối")
    q = select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
    q = (q.filter(CurriculumTopic.mach_noi_dung == gia_tri) if pham_vi == "mach"
         else q.filter(CurriculumTopic.hoc_ky == gia_tri))
    return list(await session.scalars(q.order_by(CurriculumTopic.order_index)))


async def _de_on_tap(session: AsyncSession, topics: list[CurriculumTopic],
                     so_cau: int) -> list[tuple[int, int, dict]]:
    """(topic_id, chỉ số câu trong quiz của bài, câu) — RẢI ĐỀU qua các bài.

    Lấy tuần tự từng bài sẽ ra đề toàn câu của 2 bài đầu rồi hết chỗ; rải theo
    vòng thì mỗi bài góp một câu trước khi bài nào góp câu thứ hai.
    """
    contents = {c.topic_id: c for c in await session.scalars(
        select(TopicContent).where(TopicContent.topic_id.in_([t.id for t in topics] or [0])))}
    theo_bai: list[list[tuple[int, int, dict]]] = []
    for t in topics:
        c = contents.get(t.id)
        quiz = json.loads(c.quiz_json) if c and c.quiz_json else []
        if quiz:
            theo_bai.append([(t.id, i, q) for i, q in enumerate(quiz)])

    ra: list[tuple[int, int, dict]] = []
    vong = 0
    while len(ra) < so_cau and any(len(b) > vong for b in theo_bai):
        for b in theo_bai:
            if vong < len(b) and len(ra) < so_cau:
                ra.append(b[vong])
        vong += 1
    return ra


@router.get("/on-tap/de")
async def de_on_tap(
    pham_vi: str, gia_tri: str, mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Đề ôn tập của một mạch / học kỳ. KHÔNG kèm đáp án (chấm ở server).

    Mỗi câu mang `topic_id` + `idx` để lúc nộp server tra lại đáp án đúng — client
    không giữ đáp án, giống hệt luồng kiểm tra nhanh của từng bài.
    """
    topics = await _topics_pham_vi(session, pham_vi, gia_tri, mon, khoi)
    if not topics:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Phạm vi ôn tập không có đơn vị nào")
    cap = await _de_on_tap(session, topics, _SO_CAU_ON[pham_vi])
    if not cap:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Các bài trong phạm vi này chưa có bài kiểm tra nhanh nên chưa gom được đề ôn tập.")
    ten = {t.id: (t.don_vi_kien_thuc or "").strip() for t in topics}
    return {
        "pham_vi": pham_vi, "gia_tri": gia_tri, "so_cau": len(cap),
        "cau": [{"topic_id": tid, "idx": i, "bai": ten.get(tid, ""),
                 "q": q["q"], "o": q["o"], "lv": q.get("lv", "de")}
                for tid, i, q in cap],
    }


class OnTapSubmit(BaseModel):
    pham_vi: str
    gia_tri: str
    mon: str = "Toán"
    khoi: str = "Lớp 6"
    # Đáp án theo THỨ TỰ câu của đề vừa nhận; -1 = bỏ trống.
    answers: list[int]


@router.post("/on-tap/submit")
async def submit_on_tap(
    body: OnTapSubmit,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Chấm đề ôn tập ở server.

    CỐ Ý không đổi trạng thái đạt/chưa đạt của từng đơn vị: ôn tập là xem lại cả
    mạch, một câu sai ở đây không có nghĩa là bài đó tụt lại. Vẫn cộng XP và ghi
    `QuizAttempt` cho từng bài có câu trong đề để hồ sơ học tập thấy được.
    """
    topics = await _topics_pham_vi(session, body.pham_vi, body.gia_tri, body.mon, body.khoi)
    cap = await _de_on_tap(session, topics, _SO_CAU_ON[body.pham_vi])
    if not cap:
        raise HTTPException(status.HTTP_409_CONFLICT, "Phạm vi này chưa gom được đề ôn tập")

    ten = {t.id: (t.don_vi_kien_thuc or "").strip() for t in topics}
    ket_qua, diem = [], 0
    theo_bai: dict[int, list[bool]] = {}
    for i, (tid, _idx, q) in enumerate(cap):
        chon = body.answers[i] if i < len(body.answers) else -1
        dung = chon == q["a"]
        diem += 1 if dung else 0
        theo_bai.setdefault(tid, []).append(dung)
        ket_qua.append({"dung": dung, "chon": chon, "dap_an": q["a"],
                        "giai": q.get("giai", ""), "phan": q.get("phan") or "kien_thuc",
                        "ycd": q.get("ycd", ""), "topic_id": tid, "bai": ten.get(tid, "")})

    tong = len(cap)
    dat = diem / tong >= _NGUONG_DAT
    for tid, ds in theo_bai.items():
        session.add(QuizAttempt(user_id=user.id, topic_id=tid,
                                diem=sum(ds), tong=len(ds), nguon="on_tap",
                                dat=sum(ds) / len(ds) >= _NGUONG_DAT))
    xp = diem * _XP_PER_CORRECT + (_XP_QUIZ_PASS if dat else 0)
    st = await stats_svc.award(session, user.id, xp)
    out = {"diem": diem, "tong": tong, "dat_yeu_cau": dat,
           "trang_thai": "dat" if dat else "dang", "ket_qua": ket_qua,
           "xp": xp, "xp_week": st.week_points, "streak": st.streak_days}
    await session.commit()
    return out
