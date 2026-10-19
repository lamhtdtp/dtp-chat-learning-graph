"""Đề cuối kỳ rút từ DTP Testbank (docs/STEPS-demo-4-buoc.md, bước ② ③ ④).

- POST /exam/cuoi-ky/generate — rút đề (testbank `exams:preview`), lấy nội dung
  (`questions:resolve`), sinh SẴN lý do từng phương án, lưu đề phía máy chủ. Trả
  đề bài + phương án, KHÔNG kèm đáp án, lời giải hay lý do.
- POST /exam/cuoi-ky/submit   — chấm ở máy chủ bằng đúng bản đã lưu, ghi lịch sử
  theo YCCĐ, trả kết quả từng câu + kết quả theo YCCĐ + gợi ý bài làm mới.
- GET  /exam/cuoi-ky/{de_id}  — mở lại đề (chưa nộp: như generate; đã nộp: kèm kết quả).

Đáp án chỉ ở máy chủ: `answer_key`, `explanation` và lý do từng phương án (lý do
"vì sao đúng" cũng là lộ đáp án) chỉ ra ngoài SAU khi nộp.

Lỗi testbank không thành 500: chưa cấu hình / mạng / 5xx -> 503, testbank từ chối
(4xx, sai tài khoản) -> 502. Thông điệp tiếng Việt, chi tiết nằm ở log.
"""
import json
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import cast, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import (
    BlueprintCell, CurriculumTopic, DeCuoiKy, Grade, QuizAttempt, QuizAttemptItem, Subject, User,
)
from app.db.session import get_session
from app.exam import ly_do as ly_do_svc
from app.integrations.testbank import cham as cham_svc
from app.integrations.testbank.client import (
    TestbankChuaCauHinh, TestbankClient, TestbankLoi, tao_client,
)
from app.integrations.testbank.exam import rut_de
from app.integrations.testbank.hien_thi import sang_html
from app.integrations.testbank.noi_dung import lay_cau
from app.lessons import stats as stats_svc
from app.lessons import ycd_thong_ke as ycd_tk_svc
from app.lessons.ycd_key import chuan_hoa
from app.llm import cache as llm_cache

log = logging.getLogger(__name__)

router = APIRouter(prefix="/exam/cuoi-ky", tags=["cuoi_ky"])

#: Mã môn / lớp của testbank -> tên trong danh mục của mình, để khớp YCCĐ về bài.
_MON = {"TO": "Toán", "NN": "Tiếng Anh"}
#: Cùng ngưỡng đạt với Kiểm tra nhanh (`_NGUONG_DAT` ở app/api/lessons.py).
_NGUONG_DAT = 0.7
_XP_MOI_CAU = 5
_XP_DAT = 10
#: Bao nhiêu lần nộp gần nhất dùng để chọn YCCĐ còn yếu — bám trình độ HIỆN TẠI.
_GAN_DAY = 5

_MSG_CHUA_NOI = ("Đề cuối kỳ chưa được kết nối với kho câu hỏi. "
                 "Em làm bài kiểm tra nhanh trong từng bài trước nhé!")
_MSG_BAN = "Kho đề đang bận, em thử lại sau ít phút nhé."
_MSG_SU_CO = "Kho đề đang gặp sự cố, chưa rút được đề. Thầy cô đã được báo."


def lay_testbank() -> TestbankClient:
    """Dependency — test thay bằng testbank giả qua `app.dependency_overrides`."""
    try:
        return tao_client()
    except TestbankChuaCauHinh as e:
        log.warning("%s", e)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _MSG_CHUA_NOI) from e


def _loi_http(e: TestbankLoi) -> HTTPException:
    if isinstance(e, TestbankChuaCauHinh):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _MSG_CHUA_NOI)
    if e.tam_thoi:
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _MSG_BAN)
    # 4xx / sai tài khoản: thử lại không khỏi — 502 để giám sát thấy khác 503.
    return HTTPException(status.HTTP_502_BAD_GATEWAY, _MSG_SU_CO)


async def _han_muc(user: User) -> None:
    """Chặn TRƯỚC khi gọi testbank. Redis lỗi -> cho qua (fail-open, như trợ lý)."""
    limit = settings.de_cuoi_ky_daily_limit
    if user.role == "admin" or limit <= 0:
        return
    key = f"dequota:{user.id}:{datetime.now(timezone.utc):%Y%m%d}"
    try:
        used = await llm_cache.incr_quota(key, ttl=60 * 60 * 26)
    except Exception:  # noqa: BLE001
        return
    if used > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Hôm nay em đã rút {limit} đề rồi, mai làm tiếp nhé!")


async def _ban_do_yccd(session: AsyncSession, subject: str, grade: str) -> dict[str, tuple[int, str]]:
    """ycd_key -> (topic_id, tên đơn vị) theo ma trận của mình (B5).

    Khớp NGUYÊN VĂN đã chuẩn hoá (`ycd_key.chuan_hoa`, chép đúng quy tắc của
    testbank). Không khớp thì KHÔNG đoán theo độ giống — gắn câu vào sai bài mà
    không ai biết còn tệ hơn không gắn. Một YCCĐ nằm ở nhiều bài (mục lục có bài
    trùng) thì lấy bài đứng trước trong mục lục, cố định giữa các lần gọi."""
    mon = _MON.get(subject)
    if mon is None or not grade.isdigit():
        return {}
    rows = (await session.execute(
        select(BlueprintCell.yeu_cau_can_dat, CurriculumTopic.id, CurriculumTopic.don_vi_kien_thuc)
        .join(CurriculumTopic, CurriculumTopic.id == BlueprintCell.topic_id)
        .join(Subject, Subject.id == CurriculumTopic.subject_id)
        .join(Grade, Grade.id == CurriculumTopic.grade_id)
        .where(Subject.name == mon, Grade.name == f"Lớp {int(grade)}")
        .order_by(CurriculumTopic.order_index, CurriculumTopic.id))).all()
    out: dict[str, tuple[int, str]] = {}
    for ycd, tid, dv in rows:
        out.setdefault(chuan_hoa(ycd), (tid, (dv or "").strip()))
    return out


# ── Hiển thị ────────────────────────────────────────────────────────────────
def _cong_khai(c: dict, stt: int, hien_du_kien: bool) -> dict:
    """MỘT câu cho trình duyệt TRƯỚC khi nộp — không đáp án, không lý do."""
    goc, a, sz = settings.testbank_content_url, c.get("assets") or {}, c.get("asset_sizes") or {}
    return {
        "stt": stt, "qid": c["qid"], "dang": c["format_code"], "muc_do": c.get("difficulty") or "",
        "ar_id": c.get("ar_id") or "", "ycd": c.get("yccd_text") or "",
        "topic_id": c.get("_topic_id"), "don_vi": c.get("_don_vi") or "",
        "de_html": sang_html(c.get("stem"), a, sz, goc=goc),
        "phuong_an": [{"key": o["key"], "html": sang_html(o.get("text"), a, sz, goc=goc)}
                      for o in c.get("options") or []],
        # Dữ kiện chung của nhóm: hiện MỘT lần trước câu đầu của nhóm.
        "du_kien_html": sang_html(c.get("stimulus"), a, sz, goc=goc) if hien_du_kien else "",
        "cau_dan": (c.get("stimulus_lead") or "") if hien_du_kien else "",
        # Biết trước câu nào không chấm tự động để giao diện nói rõ, khỏi để học
        # sinh tưởng mình bị chấm sai. Chỉ nói "có/không", không lộ đáp án.
        "tu_cham": cham_svc.cham(c["format_code"], c.get("answer_key"), "x").cham_duoc,
    }


def _de_cong_khai(cau: list[dict]) -> list[dict]:
    out, da_co_nhom = [], set()
    for i, c in enumerate(cau, start=1):
        g = c.get("group_id")
        out.append(_cong_khai(c, i, hien_du_kien=bool(g) and g not in da_co_nhom))
        if g:
            da_co_nhom.add(g)
    return out


class GenerateBody(BaseModel):
    subject: str = Field("TO", pattern=r"^[A-Z]{2}$")
    grade: str = Field("06", pattern=r"^\d{2}$")
    exam: str | None = Field("CK1", pattern=r"^[A-Z0-9+]{2,4}$")
    total: int = Field(12, ge=1, le=40)
    #: Giới hạn trong các YCCĐ này — "bài làm mới" chỉ ôn chỗ còn yếu.
    ar_ids: list[str] | None = Field(None, max_length=20)
    #: Cố định để demo lặp lại được; bỏ trống -> ngẫu nhiên, mỗi lần một đề.
    seed: int | None = Field(None, ge=0, le=2**31 - 1)


@router.post("/generate")
async def generate(
    body: GenerateBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    tb: TestbankClient = Depends(lay_testbank),
) -> dict:
    await _han_muc(user)
    seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
    try:
        de = await rut_de(tb, subject=body.subject, grade=body.grade, exam=body.exam,
                          total=body.total, ar_ids=body.ar_ids, seed=seed)
        caus = await lay_cau(tb, [x.qid for x in de.items]) if de.items else []
    except TestbankLoi as e:
        raise _loi_http(e) from e

    thong_bao = [] if de.is_complete else [de.message or "Kho chưa đủ câu cho đề này."]
    if len(caus) < len(de.items):
        # resolve bỏ qua LẶNG LẼ câu không thuộc kho mình thấy — phải tự so.
        thieu = len(de.items) - len(caus)
        log.warning("Testbank resolve trả thiếu %d/%d câu", thieu, len(de.items))
        thong_bao.append(f"Kho trả thiếu {thieu} câu so với đề đã rút.")

    ban_do = await _ban_do_yccd(session, body.subject, body.grade)
    khong_khop = set()
    for c in caus:
        tid, dv = ban_do.get(chuan_hoa(c.get("yccd_text") or ""), (None, ""))
        if tid is None:
            khong_khop.add(c.get("ar_id"))
        c["_topic_id"], c["_don_vi"] = tid, dv
    if khong_khop and ban_do:
        log.error("YCCĐ testbank không khớp ma trận của mình (không đoán): %s", sorted(khong_khop))

    # Sinh SẴN lý do từng phương án — lúc nộp không còn ai phải chờ model.
    ly_do = await ly_do_svc.dam_bao_ly_do(session, caus)
    for c in caus:
        c["_ly_do"] = ly_do.get(c["qid"], {})

    if not caus:
        await session.commit()
        return {"de_id": None, "cau": [], "du_cau": False,
                "thong_bao": " ".join(thong_bao) or "Kho chưa có câu nào cho đề này."}

    de_id = secrets.token_urlsafe(12)
    tham_so = {**body.model_dump(), "seed": seed}
    session.add(DeCuoiKy(id=de_id, user_id=user.id, tham_so_json=json.dumps(tham_so),
                         thong_bao=" ".join(thong_bao),
                         cau_json=json.dumps(caus, ensure_ascii=False),
                         # clock_timestamp chứ không phải now(): now() là mốc BẮT ĐẦU
                         # transaction, hai đề rút sát nhau trùng giờ và danh sách
                         # "mới nhất trước" sắp tuỳ ý.
                         created_at=func.clock_timestamp()))
    out = {"de_id": de_id, "cau": _de_cong_khai(caus), "du_cau": not thong_bao,
           "thong_bao": " ".join(thong_bao), "seed": seed}
    await session.commit()
    return out


# ── Nộp bài ─────────────────────────────────────────────────────────────────
class SubmitBody(BaseModel):
    de_id: str = Field(min_length=1, max_length=64)
    #: qid -> nhãn đã chọn ("B", "A,C", "Đ,S,Đ,S") hoặc đáp số đã điền.
    tra_loi: dict[str, str] = Field(default_factory=dict, max_length=200)


async def _de_cua(session: AsyncSession, de_id: str, user: User) -> DeCuoiKy:
    de = await session.get(DeCuoiKy, de_id)
    # Đề của người khác cũng trả 404 như đề không tồn tại — không xác nhận id nào có thật.
    if de is None or de.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề này.")
    return de


def _cham_cau(c: dict, chon: str, stt: int) -> dict:
    goc, a, sz = settings.testbank_content_url, c.get("assets") or {}, c.get("asset_sizes") or {}
    kq = cham_svc.cham(c["format_code"], c.get("answer_key"), chon)
    dung_sai = ly_do_svc.dung_sai(c) if c.get("options") else {}
    return {
        "stt": stt, "qid": c["qid"], "version": c.get("version") or "",
        "dang": c["format_code"], "ar_id": c.get("ar_id") or "",
        "ycd": c.get("yccd_text") or "", "muc_do": c.get("difficulty") or "",
        "topic_id": c.get("_topic_id"), "don_vi": c.get("_don_vi") or "",
        "chon": chon, "dap_an": c.get("answer_key") or "",
        "dap_an_html": sang_html(c.get("answer_key"), a, sz, goc=goc),
        "cham_duoc": kq.cham_duoc, "dung": kq.dung,
        "so_y_dung": kq.so_y_dung, "so_y": kq.so_y,
        "giai_html": sang_html(c.get("explanation"), a, sz, goc=goc),
        # Lý do theo phương án + phương án đó đúng hay sai (để giao diện gắn nhãn
        # "vì sao đúng / vì sao sai" mà không phải tự suy từ đáp án).
        "ly_do": {k: {**v, "dung": dung_sai.get(k, False)}
                  for k, v in (c.get("_ly_do") or {}).items()},
    }


def _theo_ycd(ket_qua: list[dict]) -> list[dict]:
    """Kết quả theo YCCĐ, đúng thứ tự mã YCCĐ (thứ tự trong ma trận đặc tả)."""
    gom: dict[str, dict] = {}
    for k in ket_qua:
        if not k["cham_duoc"] or not k["ar_id"]:
            continue
        g = gom.setdefault(k["ar_id"], {"ar_id": k["ar_id"], "ycd": k["ycd"], "dung": 0, "tong": 0,
                                        "topic_id": k["topic_id"], "don_vi": k["don_vi"]})
        g["tong"] += 1
        g["dung"] += 1 if k["dung"] else 0
    for g in gom.values():
        g["trang"] = "dat" if g["dung"] == g["tong"] else ("chua" if g["dung"] == 0 else "dang")
    return [gom[a] for a in sorted(gom)]


@router.post("/submit")
async def submit(
    body: SubmitBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    de = await _de_cua(session, body.de_id, user)
    if de.ket_qua_json:
        # Bấm "Nộp" hai lần (mạng chậm): trả lại kết quả cũ, không thành hai lần làm bài.
        return json.loads(de.ket_qua_json)

    caus = json.loads(de.cau_json)
    ket_qua = [_cham_cau(c, (body.tra_loi.get(c["qid"]) or "").strip()[:255], i)
               for i, c in enumerate(caus, start=1)]
    cham_duoc = [k for k in ket_qua if k["cham_duoc"]]
    diem, tong = sum(1 for k in cham_duoc if k["dung"]), len(cham_duoc)
    dat = bool(tong) and diem / tong >= _NGUONG_DAT

    # Một lần nộp = một QuizAttempt KHÔNG gắn bài (đề phủ cả học kỳ). Chi tiết theo
    # YCCĐ ở quiz_attempt_items — chỉ câu chấm được, để số dòng khớp `tong`.
    attempt = QuizAttempt(user_id=user.id, topic_id=None, diem=diem, tong=tong, dat=dat,
                          nguon="cuoi_ky")
    session.add(attempt)
    await session.flush()
    for k in cham_duoc:
        session.add(QuizAttemptItem(
            attempt_id=attempt.id, ycd_key=chuan_hoa(k["ycd"]), ycd_text=k["ycd"],
            ar_id=k["ar_id"] or None, qid=k["qid"], phan="kien_thuc" if k["topic_id"] else "",
            muc_do=k["muc_do"], chon=k["chon"], dap_an=k["dap_an"], dung=k["dung"]))
    await session.flush()

    theo_ycd = _theo_ycd(ket_qua)
    lich_su = await ycd_tk_svc.theo_ycd(session, user.id, gan_day=_GAN_DAY)
    ar_yeu = ycd_tk_svc.chon_ar_on_lai(lich_su, [(y["ar_id"], y["dung"], y["tong"]) for y in theo_ycd])
    # Tài liệu bổ sung: bài học của các YCCĐ còn sai, khử trùng, theo thứ tự ma trận.
    tai_lieu, da_co = [], set()
    for y in theo_ycd:
        if y["dung"] < y["tong"] and y["topic_id"] and y["topic_id"] not in da_co:
            da_co.add(y["topic_id"])
            tai_lieu.append({"topic_id": y["topic_id"], "don_vi": y["don_vi"], "phan": "kien_thuc",
                             "ycd": y["ycd"], "ar_id": y["ar_id"],
                             "cau": [k["stt"] for k in ket_qua
                                     if k["ar_id"] == y["ar_id"] and k["cham_duoc"] and not k["dung"]]})

    await stats_svc.award(session, user.id, diem * _XP_MOI_CAU + (_XP_DAT if dat else 0))
    tham_so = json.loads(de.tham_so_json)
    out = {"de_id": de.id, "diem": diem, "tong": tong, "dat_yeu_cau": dat,
           "khong_cham": len(ket_qua) - tong, "cau": ket_qua, "theo_ycd": theo_ycd,
           "goi_y": {"ar_ids": ar_yeu, "tai_lieu": tai_lieu,
                     "de_moi": {k: tham_so.get(k) for k in ("subject", "grade", "exam")}}}
    de.ket_qua_json = json.dumps(out, ensure_ascii=False)
    de.attempt_id = attempt.id
    # Giờ của POSTGRES, cùng nguồn với created_at và mọi cột thời gian khác của
    # app. Trước đây lấy datetime.now(utc) của Python: DB chạy giờ +07 nên lịch sử
    # hiện "nộp lúc 11:20" cho bài nộp 18:20 — lệch đúng 7 tiếng.
    de.nop_luc = func.clock_timestamp()
    await session.commit()
    return out


def _loc_ky(exam: str | None):
    """Điều kiện lọc kỳ, chạy TRONG SQL. Lọc sau khi cắt trang thì trang ra thiếu
    đề dù kỳ đó còn nhiều. `tham_so_json` là Text nên ép sang JSONB để đọc khoá."""
    return [cast(DeCuoiKy.tham_so_json, JSONB)["exam"].astext == exam] if exam else []


async def danh_sach_de(session: AsyncSession, user_id: int, *, exam: str | None = None,
                       gioi_han: int = 10, bo_qua: int = 0) -> tuple[list[dict], bool]:
    """Các đề cuối kỳ của một học sinh, mới nhất trước — cả đề đã nộp lẫn đề rút
    rồi bỏ dở — kèm cờ còn trang sau. Dùng chung cho màn đề cuối kỳ và Hồ sơ.

    Chỉ tóm tắt (điểm, đạt, thời điểm) — KHÔNG có nội dung câu hay đáp án."""
    rows = (await session.scalars(
        select(DeCuoiKy).where(DeCuoiKy.user_id == user_id, *_loc_ky(exam))
        # id phá hoà khi hai đề trùng giờ — không thì trang sau lặp/sót đề.
        .order_by(DeCuoiKy.created_at.desc(), DeCuoiKy.id.desc())
        .offset(bo_qua).limit(gioi_han + 1))).all()   # lấy dư 1 để biết còn trang sau
    out = []
    for d in rows[:gioi_han]:
        ts = json.loads(d.tham_so_json)
        kq = json.loads(d.ket_qua_json) if d.ket_qua_json else None
        out.append({
            "de_id": d.id, "exam": ts.get("exam"), "on_lai": bool(ts.get("ar_ids")),
            "so_cau": len(json.loads(d.cau_json)),
            "luc": d.created_at.isoformat(),
            "da_nop": kq is not None,
            "nop_luc": d.nop_luc.isoformat() if d.nop_luc else None,
            "diem": kq["diem"] if kq else None, "tong": kq["tong"] if kq else None,
            "dat": kq["dat_yeu_cau"] if kq else None,
        })
    return out, len(rows) > gioi_han


@router.get("")
async def liet_ke(
    exam: str | None = None,
    gioi_han: int = Query(10, ge=1, le=50),
    bo_qua: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Lịch sử đề cuối kỳ của chính học sinh đang đăng nhập, phân trang."""
    de, con_nua = await danh_sach_de(session, user.id, exam=exam, gioi_han=gioi_han, bo_qua=bo_qua)
    return {"de": de, "con_nua": con_nua}


async def _xoa_han(session: AsyncSession, user_id: int, des: list[DeCuoiKy]) -> int:
    """Xoá HẲN: đề + lần nộp trong quiz_attempts (chi tiết từng câu đi theo bằng
    ON DELETE CASCADE). Thống kê YCCĐ / gợi ý làm bài mới không còn tính bài này,
    giáo viên trên CMS cũng không còn thấy — không khôi phục được.

    XP / chuỗi ngày học đã cộng thì giữ: đó là công sức đã bỏ ra, không phải kết quả."""
    ids_at = [d.attempt_id for d in des if d.attempt_id]
    n = len(des)
    for d in des:
        await session.delete(d)
    await session.flush()
    if ids_at:
        # user_id trong điều kiện: không bao giờ xoá nhầm lần nộp của người khác,
        # kể cả khi attempt_id bị ghi sai.
        await session.execute(delete(QuizAttempt).where(
            QuizAttempt.id.in_(ids_at), QuizAttempt.user_id == user_id,
            QuizAttempt.nguon == "cuoi_ky"))
    return n


@router.delete("", status_code=status.HTTP_200_OK)
async def xoa_tat_ca(
    exam: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Xoá hẳn MỌI đề cuối kỳ của chính mình (lọc theo kỳ nếu có `exam`)."""
    des = list((await session.scalars(
        select(DeCuoiKy).where(DeCuoiKy.user_id == user.id, *_loc_ky(exam)))).all())
    n = await _xoa_han(session, user.id, des)
    await session.commit()
    return {"da_xoa": n}


@router.delete("/{de_id}", status_code=status.HTTP_204_NO_CONTENT)
async def xoa_mot(
    de_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    de = await _de_cua(session, de_id, user)
    await _xoa_han(session, user.id, [de])
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{de_id}")
async def mo_lai(
    de_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    de = await _de_cua(session, de_id, user)
    out = {"de_id": de.id, "cau": _de_cong_khai(json.loads(de.cau_json)),
           "du_cau": not de.thong_bao, "thong_bao": de.thong_bao,
           "on_lai": bool(json.loads(de.tham_so_json).get("ar_ids")),
           "ket_qua": json.loads(de.ket_qua_json) if de.ket_qua_json else None}
    return out
