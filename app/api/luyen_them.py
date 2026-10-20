"""Luyện thêm từ kho đề (US-25) — tối đa 4 câu của DTP Testbank, đúng YCCĐ của bài
đang học, đặt ngay dưới Bài kiểm tra nhanh.

- POST /lessons/{topic_id}/luyen-them  — rút câu (testbank `/pool` + `questions:resolve`),
  chọn theo YCCĐ của bài (`app.lessons.luyen_them.chon_cau`), sinh SẴN lý do từng
  phương án, lưu lượt phía máy chủ. Trả đề, KHÔNG kèm đáp án / lời giải / lý do.
- POST /lessons/luyen-them/submit      — chấm ở máy chủ trên bản đã lưu; không gọi
  testbank, không gọi LLM. Đủ 3 câu chấm được thì xét đạt bài (ngưỡng 70%, không hạ cấp).

Ghép hai thứ có sẵn: nguồn câu + cách chấm + lý do của đề cuối kỳ (`app/api/cuoi_ky.py`,
dùng lại các hàm ở đó) với luật đạt bài / XP của Bài kiểm tra nhanh (`app/api/lessons.py`).

Lỗi testbank không thành 500: chưa cấu hình / mạng / 5xx -> 503, từ chối (4xx) -> 502.
"""
import json
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import cuoi_ky
from app.api.deps import get_current_user
from app.api.lessons import _NGUONG_DAT, _XP_PER_CORRECT, _XP_QUIZ_PASS, _upsert_progress
from app.config import settings
from app.db.models import (
    BlueprintCell, CurriculumTopic, DeCuoiKy, Grade, QuizAttempt, QuizAttemptItem,
    StudentProgress, Subject, User,
)
from app.db.session import get_session
from app.exam import ly_do as ly_do_svc
from app.integrations.testbank.client import TestbankChuaCauHinh, TestbankClient, TestbankLoi
from app.integrations.testbank.noi_dung import lay_cau
from app.lessons import luyen_them as chon_svc
from app.lessons import stats as stats_svc
from app.lessons.ycd_key import chuan_hoa
from app.llm import cache as llm_cache

log = logging.getLogger(__name__)

router = APIRouter(tags=["luyen_them"])

LOAI = "luyen_them"
TOI_DA_CAU = 4
#: Số câu CHẤM ĐƯỢC tối thiểu để lượt được xét đạt / trượt bài (US-25 Q2). Dưới mức
#: này 1/1 hay 2/2 là 100% mà không nói gì về việc em đã hiểu bài.
TOI_THIEU_XET_DAT = 3

_MSG_KHONG_THAY = "Không tìm thấy lượt luyện thêm này."
_MSG_KHO_TRONG = "Kho đề chưa có câu hỏi cho bài này. Thầy cô đã được báo."
_MSG_CHUA_CO_YCD = "Bài này chưa được gắn yêu cầu cần đạt nên chưa rút được câu luyện thêm."
_MSG_KHONG_HO_TRO = "Môn này chưa có kho câu luyện thêm."
_MSG_BAN = "Kho đề đang bận, em thử lại sau ít phút nhé."
_MSG_SU_CO = "Kho đề đang gặp sự cố, chưa rút được câu. Thầy cô đã được báo."
_MSG_CHUA_DU_3 = ("Lượt này chưa đủ 3 câu chấm tự động nên không tính đạt bài, "
                  "em vẫn luyện và xem lời giải được.")


def _loi_http(e: TestbankLoi) -> HTTPException:
    if isinstance(e, TestbankChuaCauHinh):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, cuoi_ky.MSG_CHUA_NOI_LUYEN_THEM)
    if e.tam_thoi:
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _MSG_BAN)
    # 4xx / sai tài khoản: thử lại không khỏi — 502 để giám sát thấy khác 503.
    return HTTPException(status.HTTP_502_BAD_GATEWAY, _MSG_SU_CO)


# ── Hạn mức ─────────────────────────────────────────────────────────────────
def _khoa_han_muc(user: User) -> str:
    # Khoá riêng, KHÔNG bắt đầu bằng "dequota:" (của đề cuối kỳ) — hạn mức riêng (Q6).
    return f"ltquota:{user.id}:{datetime.now(timezone.utc):%Y%m%d}"


_TTL_HAN_MUC = 60 * 60 * 26


async def _dat_cho(user: User) -> str | None:
    """Giữ một lượt trong hạn mức ngày TRƯỚC khi gọi testbank. Trả khoá đã đếm (để lỡ
    rút hỏng còn trả lại) hoặc None nếu không đếm (admin, không giới hạn, Redis lỗi
    -> fail-open).

    Đếm trước rồi hoàn lại khi rút không thành, thay vì đọc rồi tăng sau: hai request
    đồng thời cùng đọc "19" rồi cùng qua thì vượt hạn mức."""
    limit = settings.luyen_them_daily_limit
    if user.role == "admin" or limit <= 0:
        return None
    key = _khoa_han_muc(user)
    try:
        used = await llm_cache.incr_quota(key, ttl=_TTL_HAN_MUC)
    except Exception:  # noqa: BLE001
        return None
    if used > limit:
        await llm_cache.giam_quota(key, _TTL_HAN_MUC)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Hôm nay em đã luyện thêm {limit} lượt rồi, mai làm tiếp nhé!")
    return key


# ── Rút câu ─────────────────────────────────────────────────────────────────
async def _ma_testbank(session: AsyncSession, topic: CurriculumTopic) -> tuple[str, str] | None:
    """(môn, lớp) theo mã testbank ("TO", "06"); None nếu chưa có kho cho môn/lớp này."""
    ten_mon = await session.scalar(select(Subject.name).where(Subject.id == topic.subject_id))
    ten_lop = await session.scalar(select(Grade.name).where(Grade.id == topic.grade_id))
    ma_mon = next((m for m, t in cuoi_ky._MON.items() if t == ten_mon), None)
    so_lop = (ten_lop or "").replace("Lớp", "").strip()
    if ma_mon is None or not so_lop.isdigit():
        return None
    return ma_mon, f"{int(so_lop):02d}"


def _thong_bao(so_cau: int, so_cham: int) -> list[str]:
    tb = []
    if so_cau < TOI_DA_CAU:
        tb.append(f"Kho đề mới có {so_cau} câu cho bài này.")
    if so_cham < TOI_THIEU_XET_DAT:
        tb.append(_MSG_CHUA_DU_3)
    return tb


def _rong(thong_bao: str) -> dict:
    return {"de_id": None, "cau": [], "du_cau": False, "thong_bao": thong_bao,
            "so_cau_cham_duoc": 0, "xet_dat": False}


@router.post("/lessons/{topic_id}/luyen-them")
async def rut(
    topic_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    tb: TestbankClient = Depends(cuoi_ky.lay_testbank),
) -> dict:
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy bài học")
    ten_bai = (topic.don_vi_kien_thuc or "").strip()
    ycds = list(dict.fromkeys(await session.scalars(
        select(BlueprintCell.yeu_cau_can_dat).where(BlueprintCell.topic_id == topic_id)
        .order_by(BlueprintCell.id))))
    if not ycds:
        return _rong(_MSG_CHUA_CO_YCD)          # chưa có YCCĐ -> không có gì để hỏi kho
    ma = await _ma_testbank(session, topic)
    if ma is None:
        return _rong(_MSG_KHONG_HO_TRO)
    mon, lop = ma
    khoa_ycd = {chuan_hoa(y) for y in ycds}

    khoa_da_dem = await _dat_cho(user)
    thanh_cong = False
    try:
        try:
            pool = await tb.lay("content", "/pool", {"subject": mon, "grade": lop, "limit": 2000})
            items = pool.get("items") or []
            if pool.get("truncated"):
                log.warning("Pool testbank %s%s bị cắt ở %s câu — có thể thiếu câu", mon, lop, len(items))
            # `/pool` chỉ có ar_id, không có nguyên văn YCCĐ -> phải resolve để khớp
            # nguyên văn với YCCĐ của bài. Resolve cả pool một lần (không đoán theo ar_id).
            caus = await lay_cau(tb, [x["qid"] for x in items]) if items else []
        except TestbankLoi as e:
            raise _loi_http(e) from e

        co = {c["qid"]: c for c in caus}
        if len(co) < len(items):
            log.warning("Testbank resolve trả thiếu %d/%d câu", len(items) - len(co), len(items))
        ban_do = await cuoi_ky._ban_do_yccd(session, mon, lop)
        ar_cua_bai, la = set(), {}
        for c in caus:
            k = chuan_hoa(c.get("yccd_text") or "")
            if k in khoa_ycd:
                ar_cua_bai.add(c.get("ar_id"))
            elif k not in ban_do:
                # Không khớp YCCĐ của BÀI NÀO — không đoán theo độ giống, chỉ ghi lại để
                # quản trị đối soát (câu của bài khác thì bình thường, không ghi).
                la[c.get("ar_id")] = c.get("yccd_text")
        if la:
            log.error("YCCĐ testbank không khớp ma trận của mình (không đoán): %s", la)

        seed = secrets.randbelow(2**31)
        chon = chon_svc.chon_cau([x for x in items if x["qid"] in co], ar_cua_bai,
                                 toi_da=TOI_DA_CAU, seed=seed)
        if not chon:
            log.warning("Kho đề thiếu câu cho bài '%s' (id=%s). YCCĐ: %s", ten_bai, topic_id, ycds)
            return _rong(_MSG_KHO_TRONG)

        chon_caus = [co[q] for q in chon]
        for c in chon_caus:
            c["_topic_id"], c["_don_vi"] = topic_id, ten_bai
        # Sinh SẴN lý do (chỉ cho câu được chọn) — lúc nộp không ai phải chờ model.
        ly_do = await ly_do_svc.dam_bao_ly_do(session, chon_caus)
        for c in chon_caus:
            c["_ly_do"] = ly_do.get(c["qid"], {})

        cong_khai = cuoi_ky._de_cong_khai(chon_caus)
        so_cham = sum(1 for p in cong_khai if p["tu_cham"])
        thong_bao = _thong_bao(len(chon_caus), so_cham)
        de_id = secrets.token_urlsafe(12)
        session.add(DeCuoiKy(
            id=de_id, user_id=user.id, loai=LOAI, topic_id=topic_id,
            tham_so_json=json.dumps({"topic_id": topic_id, "seed": seed}),
            thong_bao=" ".join(thong_bao), cau_json=json.dumps(chon_caus, ensure_ascii=False),
            created_at=func.clock_timestamp()))
        out = {"de_id": de_id, "cau": cong_khai,
               "du_cau": len(chon_caus) >= TOI_DA_CAU, "thong_bao": " ".join(thong_bao),
               "so_cau_cham_duoc": so_cham, "xet_dat": so_cham >= TOI_THIEU_XET_DAT}
        await session.commit()
        thanh_cong = True
        return out
    finally:
        # Chỉ TRỪ lượt khi rút được lượt thật (US-25 KB24): kho lỗi / kho trống thì trả lại.
        # (Dùng khoá đã tính sẵn: sau commit không đọc được thuộc tính của `user` nữa.)
        if khoa_da_dem and not thanh_cong:
            await llm_cache.giam_quota(khoa_da_dem, _TTL_HAN_MUC)


# ── Nộp bài ─────────────────────────────────────────────────────────────────
class SubmitBody(BaseModel):
    de_id: str = Field(min_length=1, max_length=64)
    #: qid -> nhãn đã chọn ("B", "A,C", "Đ,S,Đ,S") hoặc đáp số đã điền.
    tra_loi: dict[str, str] = Field(default_factory=dict, max_length=200)


@router.post("/lessons/luyen-them/submit")
async def submit(
    body: SubmitBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # FOR UPDATE: hai request nộp cùng lúc (hai thẻ trình duyệt, bấm đúp) xếp hàng ở
    # đây; request sau thấy `ket_qua_json` của request trước và trả lại, không ghi lần hai.
    de = await session.scalar(
        select(DeCuoiKy).where(DeCuoiKy.id == body.de_id).with_for_update()
        .execution_options(populate_existing=True))
    # Lượt của người khác / đề cuối kỳ / id không có: cùng một thông báo, không xác nhận gì.
    if de is None or de.user_id != user.id or de.loai != LOAI:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _MSG_KHONG_THAY)
    if de.ket_qua_json:
        return json.loads(de.ket_qua_json)

    topic_id = de.topic_id
    caus = json.loads(de.cau_json)
    ket_qua = [{**cuoi_ky._cham_cau(c, (body.tra_loi.get(c["qid"]) or "").strip()[:255], i),
                "phan": "kien_thuc"}
               for i, c in enumerate(caus, start=1)]
    cham_duoc = [k for k in ket_qua if k["cham_duoc"]]
    diem, tong = sum(1 for k in cham_duoc if k["dung"]), len(cham_duoc)
    xet_dat = tong >= TOI_THIEU_XET_DAT
    dat = xet_dat and diem / tong >= _NGUONG_DAT

    # `dat` của lượt = đạt thật; lượt không xét đạt luôn False (không phải "chưa đạt").
    attempt = QuizAttempt(user_id=user.id, topic_id=topic_id, diem=diem, tong=tong, dat=dat,
                          nguon=LOAI)
    session.add(attempt)
    await session.flush()
    # Chỉ câu chấm được vào thống kê YCCĐ — câu tự luận không có đúng/sai.
    for k in cham_duoc:
        session.add(QuizAttemptItem(
            attempt_id=attempt.id, ycd_key=chuan_hoa(k["ycd"]), ycd_text=k["ycd"],
            ar_id=k["ar_id"] or None, qid=k["qid"], phan="kien_thuc", muc_do=k["muc_do"],
            chon=k["chon"], dap_an=k["dap_an"], dung=k["dung"]))
    if xet_dat:
        # Cùng luật với Kiểm tra nhanh: đạt thì "dat", trượt thì "dang", đã "dat" không hạ.
        await _upsert_progress(session, user.id, topic_id, "dat" if dat else "dang")
    await session.flush()
    row = await session.scalar(select(StudentProgress).filter_by(user_id=user.id, topic_id=topic_id))
    trang_thai = row.trang_thai if row else "chua"

    xp = diem * _XP_PER_CORRECT + (_XP_QUIZ_PASS if dat else 0)
    await stats_svc.award(session, user.id, xp)
    out = {"de_id": de.id, "cau": ket_qua, "diem": diem, "tong": tong,
           "khong_cham": len(ket_qua) - tong, "xet_dat": xet_dat, "dat_yeu_cau": dat,
           "trang_thai": trang_thai, "xp": xp,
           "ghi_chu": "" if xet_dat else (f"Lượt này chỉ có {tong} câu chấm tự động "
                                          f"(cần ít nhất {TOI_THIEU_XET_DAT}) nên không tính đạt bài.")}
    de.ket_qua_json = json.dumps(out, ensure_ascii=False)
    de.attempt_id = attempt.id
    de.nop_luc = func.clock_timestamp()
    await session.commit()
    return out
