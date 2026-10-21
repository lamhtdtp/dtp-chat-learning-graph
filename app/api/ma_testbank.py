"""Học sinh làm bài theo MÃ DO GIÁO VIÊN PHÁT TRÊN TESTBANK, ngay trong app learning (US-29).

- GET  /exam/ma/cau-hinh        — chế độ ô nhập mã: tích hợp / dự phòng (mở web-student) / tắt.
- POST /exam/ma/vao             — nhập mã: vào thi (lần đầu) hoặc mở lại đúng bài cũ.
- GET  /exam/ma/{de_id}         — mở lại một bài (từ lịch sử): đang làm -> hỏi Testbank; đã nộp -> bản chép.
- PUT  /exam/ma/{de_id}/tra-loi — lưu dần các lựa chọn lên Testbank.
- POST /exam/ma/{de_id}/nop     — nộp bài.

Mức 0: máy chủ learning THAY học sinh gọi `/hs/*` của Testbank (app/integrations/testbank/delivery.py).
Khoá bài làm Testbank cấp nằm ở cột `de_cuoi_ky.khoa_bai_lam`, KHÔNG BAO GIỜ ra khỏi máy chủ.
Mỗi mã vào thi một bài làm MỚI trên Testbank, nên "mỗi em một bài cho mỗi mã" do đây chốt:
khoá advisory theo (học sinh, mã) + unique DB; không gọi `vao-thi` lần hai.

Đáp án / lời giải không có ở learning (Testbank không gửi trước hay sau khi nộp — chưa có T5), nên
kết quả chỉ có điểm + Đúng/Sai từng câu; KHÔNG ghi `quiz_attempts` (không đoán YCCĐ — KB 20).

Lỗi Testbank không thành 500: mạng / 5xx -> 503, 4xx lạ -> 502, thông điệp tiếng Việt.
"""
import json
import logging
import math
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import DeCuoiKy, User
from app.db.session import get_session
from app.exam.ma_de import chuan_hoa_ma
from app.integrations.testbank import delivery as dl_mod
from app.integrations.testbank.delivery import DeliveryClient, DeliveryLoi
from app.lessons import stats as stats_svc
from app.llm import cache as llm_cache

log = logging.getLogger(__name__)

router = APIRouter(prefix="/exam/ma", tags=["ma_testbank"])

LOAI = "testbank"
#: Chặn dò mã theo TÀI KHOẢN (Q3): 5 mã đúng định dạng mà Testbank báo không có / đã đóng trong
#: 10 phút -> chặn tới hết 10 phút. Thấp hơn ngưỡng 10 của Testbank (đếm theo IP, mà mọi học sinh
#: learning cùng một IP) để một em không khoá cả trường.
_SAI_TOI_DA = 5
_SAI_GIAY = 10 * 60
_XP_MOI_CAU = 5
_XP_DAT = 10

MSG_CHI_HOC_SINH = "Chỉ tài khoản học sinh làm bài theo mã"
MSG_SAI_DINH_DANG = "Mã gồm 6 chữ và số, em kiểm tra lại nhé"
MSG_MA_SAI = "Mã không đúng hoặc bài đã đóng, em hỏi lại thầy cô nhé"
MSG_CHAN_DO = "Em nhập sai mã nhiều lần, thử lại sau 10 phút nhé"
MSG_CHUA_MO = "Chưa mở được đề, em thử lại sau ít phút nhé"
MSG_GUI_LOI = "Chưa gửi được bài, em đừng đóng app, bấm Nộp lại sau ít phút"
MSG_KHONG_THAY = "Không tìm thấy bài này."
MSG_CAU_SAI = "Có câu trả lời không hợp lệ, chưa nộp được"
MSG_QUA_HAN_XEM = "Bài này đã quá hạn xem kết quả, em hỏi lại thầy cô nhé"
_THONG_BAO_NOP = {
    "HET_GIO": "Bài đã tự nộp khi hết giờ",
    "DONG_LUOT_PHAT": "Thầy cô đã đóng bài, bài của em đã được nộp với các câu đã lưu",
}


def _msg_khoa_nhap_ma(giay: int) -> str:
    phut = max(1, math.ceil(giay / 60))
    return f"Hệ thống đang tạm khoá nhập mã, em thử lại sau {phut} phút"


# ── Phụ thuộc ───────────────────────────────────────────────────────────────
def lay_delivery() -> DeliveryClient | None:
    """None = chưa cấu hình dịch vụ phát đề. Test thay bằng client trỏ vào `httpx.MockTransport`."""
    try:
        return dl_mod.tao_delivery_client()
    except dl_mod.DeliveryChuaCauHinh as exc:
        log.warning("%s", exc)
        return None


async def _hoc_sinh(user: User = Depends(get_current_user)) -> User:
    # Khai TRƯỚC `lay_delivery` ở chỗ dùng: giáo viên gọi thẳng nhận 403, không động tới Testbank.
    if user.role != "hoc_sinh":
        raise HTTPException(status.HTTP_403_FORBIDDEN, MSG_CHI_HOC_SINH)
    return user


def _can_delivery(dl: DeliveryClient | None, msg: str) -> DeliveryClient:
    if dl is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, msg)
    return dl


def _loi(e: DeliveryLoi, msg: str) -> HTTPException:
    """Lỗi chung (không phải mã sai / bị chặn): tạm thời -> 503, còn lại 502 — mình gọi sai hoặc
    Testbank đổi hợp đồng, thử lại không khỏi nên để giám sát thấy khác 503."""
    if e.tam_thoi:
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, msg)
    log.error("Testbank phát đề trả %s (%s): %s", e.status, e.ma, e.thong_diep)
    return HTTPException(status.HTTP_502_BAD_GATEWAY, msg)


# ── Chặn dò mã ──────────────────────────────────────────────────────────────
def _khoa_do(uid: int) -> str:
    return f"domatb:{uid}"


async def _bi_chan(uid: int) -> bool:
    try:
        v = await llm_cache.get(_khoa_do(uid))
    except Exception:  # noqa: BLE001 — Redis chết: không chặn học sinh vì hạ tầng phụ.
        return False
    return bool(v) and int(v) >= _SAI_TOI_DA


async def _ghi_sai(uid: int) -> None:
    """Một mã đúng định dạng mà Testbank báo không có / đã đóng. TTL đặt ở lần đầu nên cửa sổ 10
    phút tính từ lần sai đầu tiên. Mã sai định dạng, Testbank chặn / chết KHÔNG đi qua đây."""
    try:
        await llm_cache.incr_quota(_khoa_do(uid), ttl=_SAI_GIAY)
    except Exception:  # noqa: BLE001
        pass


# ── Bài làm ─────────────────────────────────────────────────────────────────
async def _bai_cua_em(session: AsyncSession, uid: int, ma: str | None = None, de_id: str | None = None,
                      *, khoa: bool = False) -> DeCuoiKy | None:
    q = select(DeCuoiKy).where(DeCuoiKy.user_id == uid, DeCuoiKy.loai == LOAI)
    q = q.where(DeCuoiKy.ma_testbank == ma) if ma is not None else q.where(DeCuoiKy.id == de_id)
    q = q.execution_options(populate_existing=True)
    return await session.scalar(q.with_for_update() if khoa else q)


async def _bai_hoac_404(session: AsyncSession, uid: int, de_id: str, *, khoa: bool = False) -> DeCuoiKy:
    # Bài của người khác và bài không có là CÙNG một 404.
    row = await _bai_cua_em(session, uid, de_id=de_id, khoa=khoa)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MSG_KHONG_THAY)
    return row


def _ra(row: DeCuoiKy, bai: dict | None = None) -> dict:
    """Thứ DUY NHẤT của bài theo mã đi ra trình duyệt. Không có khoá bài làm; không có đáp án vì
    learning không bao giờ có (Testbank không gửi)."""
    ket_qua = json.loads(row.ket_qua_json) if row.ket_qua_json else None
    dang_lam = bai is not None and bai.get("trang_thai") == "DANG_LAM" and ket_qua is None
    return {
        "de_id": row.id, "ma": row.ma_testbank, "tieu_de": row.tieu_de or "",
        "nhan": f"Đề thầy cô giao · mã {row.ma_testbank}",
        "trang_thai": "DA_NOP" if ket_qua else "DANG_LAM",
        "cau": json.loads(row.cau_json),
        "tra_loi": json.loads(row.tra_loi_json) if row.tra_loi_json else {},
        # Giờ MÁY CHỦ Testbank: đồng hồ đếm ngược tính theo đây, không theo đồng hồ máy em (KB 14).
        "han_nop_luc": bai.get("han_nop_luc") if dang_lam else None,
        "gio_may_chu": bai.get("gio_may_chu") if dang_lam else None,
        "thoi_gian_phut": bai.get("thoi_gian_phut") if dang_lam else None,
        "ket_qua": ket_qua,
        "thong_bao": _THONG_BAO_NOP.get((ket_qua or {}).get("cach_nop") or "", ""),
        # Testbank chưa trả chi tiết sau nộp (T5): giao diện không hiện đáp án / YCCĐ / Đề xuất.
        "co_chi_tiet": False,
    }


async def _dong_bo(session: AsyncSession, row: DeCuoiKy, bai: dict) -> None:
    """Chép trạng thái Testbank vừa trả vào bản của learning. Chưa commit.

    Đang làm: làm mới câu + câu trả lời đã lưu (Testbank là nguồn chân lý — em có thể đã sửa từ
    thiết bị khác). Đã nộp: chốt kết quả MỘT LẦN (Testbank không trả lại câu / câu trả lời sau
    khi nộp nên phải chép ngay), cộng XP một lần."""
    goc = settings.testbank_content_url
    if bai["trang_thai"] == "DANG_LAM":
        cau = [dl_mod.cau_cong_khai(c, goc) for c in bai["cau"]]
        theo_stt = {c["stt"]: c for c in cau}
        da_chon = {dl_mod.qid_cau(t["so_thu_tu"]): dl_mod.tra_loi_sang_chon(theo_stt[t["so_thu_tu"]], t["tra_loi"])
                   for t in bai.get("tra_loi") or [] if t["so_thu_tu"] in theo_stt}
        row.cau_json = json.dumps(cau, ensure_ascii=False)
        row.tra_loi_json = json.dumps(da_chon, ensure_ascii=False)
        return
    if row.ket_qua_json:
        return
    kq = dl_mod.ket_qua_gon(
        bai["ket_qua"], json.loads(row.cau_json), json.loads(row.tra_loi_json or "{}"),
        cach_nop=bai.get("cach_nop"), nop_luc=bai.get("nop_luc"))
    row.ket_qua_json = json.dumps(kq, ensure_ascii=False)
    # Giờ của POSTGRES như mọi cột thời gian khác của app (DB chạy giờ +07).
    row.nop_luc = func.clock_timestamp()
    # G3: XP như đề cuối kỳ tự rút, theo số câu đúng Testbank chấm.
    xp = kq["so_cau_dung"] * _XP_MOI_CAU + (_XP_DAT if kq["dat_yeu_cau"] else 0)
    await stats_svc.award(session, row.user_id, xp)


async def _hoi_testbank(session: AsyncSession, row: DeCuoiKy, dl: DeliveryClient) -> dict:
    """Đọc bài từ Testbank rồi đồng bộ + commit. Gọi khi `row` đã bị khoá và chưa nộp."""
    try:
        bai = await dl.xem(row.khoa_bai_lam)
    except DeliveryLoi as e:
        if e.status == 410:
            raise HTTPException(status.HTTP_410_GONE, MSG_QUA_HAN_XEM) from e
        raise _loi(e, MSG_CHUA_MO) from e
    await _dong_bo(session, row, bai)
    out = _ra(row, bai)
    await session.commit()
    return out


async def _mo(session: AsyncSession, uid: int, row: DeCuoiKy, dl: DeliveryClient | None) -> dict:
    if row.ket_qua_json:
        # Đã nộp: bản chép ở learning. KHÔNG hỏi Testbank — lượt phát đóng 3 ngày rồi vẫn xem
        # được (KB 11), và Testbank khoá đọc kết quả sau 30 ngày.
        return _ra(row)
    de_id = row.id
    # Khoá hàng: mở cùng lúc từ hai thiết bị thì một bên chờ rồi thấy bài đã đồng bộ.
    row = await _bai_hoac_404(session, uid, de_id, khoa=True)
    if row.ket_qua_json:
        return _ra(row)
    return await _hoi_testbank(session, row, _can_delivery(dl, MSG_CHUA_MO))


@router.get("/cau-hinh")
async def cau_hinh(_: User = Depends(get_current_user)) -> dict:
    """Ô nhập mã làm gì: `tich_hop` (làm trong app) · `du_phong` (mở web-student của Testbank ở tab
    mới, mã điền sẵn — Testbank chưa nối phát đề) · `tat` (không có gì để mở)."""
    if (settings.testbank_delivery_url or "").strip():
        return {"che_do": "tich_hop", "url_du_phong": None}
    goc = (settings.testbank_web_student_url or "").strip()
    return {"che_do": "du_phong" if goc else "tat", "url_du_phong": goc or None}


class VaoBody(BaseModel):
    ma: str = Field(max_length=64)


@router.post("/vao")
async def vao(
    body: VaoBody,
    hs: User = Depends(_hoc_sinh),
    session: AsyncSession = Depends(get_session),
    dl: DeliveryClient | None = Depends(lay_delivery),
) -> dict:
    ma = chuan_hoa_ma(body.ma)
    if ma is None:
        # Không hỏi Testbank, không tính lần sai (KB 6).
        raise HTTPException(422, MSG_SAI_DINH_DANG)
    uid, ten = hs.id, hs.name                       # đọc TRƯỚC commit
    if await _bi_chan(uid):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MSG_CHAN_DO)

    # Khoá theo (học sinh, mã) tới hết transaction: hai thiết bị nhập cùng lúc lần đầu thì một
    # bên chờ rồi thấy bài của bên kia — không bao giờ có hai lần `vao-thi` cho cùng cặp.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                          {"k": f"matb:{uid}:{ma}"})
    row = await _bai_cua_em(session, uid, ma=ma)
    if row is not None:
        return await _mo(session, uid, row, dl)

    dl = _can_delivery(dl, MSG_CHUA_MO)
    try:
        khoa, bai = await dl.vao_thi(ma, dl_mod.ho_ten_gui(ten, uid))
    except DeliveryLoi as e:
        if e.status == 404:
            await _ghi_sai(uid)
            raise HTTPException(status.HTTP_404_NOT_FOUND, MSG_MA_SAI) from e
        if e.status == 429:
            # Testbank chặn nhập mã (đếm theo IP của cả learning): báo chung, KHÔNG tính vào bộ
            # đếm của em này, và để lại dấu cho người vận hành (KB 9).
            log.warning("CANH_BAO testbank_chan_nhap_ma retry_after=%s hs=%s", e.retry_after, uid)
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                _msg_khoa_nhap_ma(e.retry_after or 600)) from e
        raise _loi(e, MSG_CHUA_MO) from e

    row = DeCuoiKy(
        id=secrets.token_urlsafe(12), user_id=uid, loai=LOAI, ma_testbank=ma, khoa_bai_lam=khoa,
        tieu_de=bai.get("tieu_de") or "", cau_json="[]",
        tham_so_json=json.dumps({"exam": None, "nguon": "testbank", "ma": ma}),
        created_at=func.clock_timestamp())
    session.add(row)
    await _dong_bo(session, row, bai)
    out = _ra(row, bai)
    await session.commit()
    return out


@router.get("/{de_id}")
async def mo_lai(
    de_id: str,
    hs: User = Depends(_hoc_sinh),
    session: AsyncSession = Depends(get_session),
    dl: DeliveryClient | None = Depends(lay_delivery),
) -> dict:
    uid = hs.id
    row = await _bai_hoac_404(session, uid, de_id)
    return await _mo(session, uid, row, dl)


class TraLoiMot(BaseModel):
    stt: int
    #: Chuỗi như giao diện giữ: "B", "A,C", "Đ,S,,", đáp số, đoạn chữ. "" = bỏ chọn.
    chon: str = Field("", max_length=20000)
    #: Tăng sau mỗi lần sửa câu này — Testbank bỏ lần gửi cũ tới muộn.
    seq: int = Field(0, ge=0, le=2**62)


class LuuBody(BaseModel):
    cau: list[TraLoiMot] = Field(max_length=200)


def _goi_len(row: DeCuoiKy, cau: list[TraLoiMot]) -> list[dict]:
    theo_stt = {c["stt"]: c for c in json.loads(row.cau_json)}
    return [{"so_thu_tu": c.stt, "seq": c.seq,
             "tra_loi": dl_mod.chon_sang_tra_loi(theo_stt[c.stt], c.chon) if c.stt in theo_stt else c.chon}
            for c in cau]


@router.put("/{de_id}/tra-loi")
async def luu_tra_loi(
    de_id: str,
    body: LuuBody,
    hs: User = Depends(_hoc_sinh),
    session: AsyncSession = Depends(get_session),
    dl: DeliveryClient | None = Depends(lay_delivery),
) -> dict:
    uid = hs.id
    row = await _bai_hoac_404(session, uid, de_id)
    if row.ket_qua_json:
        return {"da_nop": True, "bai": _ra(row)}
    dl = _can_delivery(dl, MSG_GUI_LOI)
    try:
        out = await dl.luu(row.khoa_bai_lam, _goi_len(row, body.cau))
    except DeliveryLoi as e:
        if e.status == 409:
            # Đã nộp (em nộp từ máy khác / thầy cô đóng bài) hoặc hết giờ: Testbank đã nộp hộ.
            # Lấy kết quả thật về thay vì để em tiếp tục sửa một bài đã khoá.
            row = await _bai_hoac_404(session, uid, de_id, khoa=True)
            if row.ket_qua_json:
                return {"da_nop": True, "bai": _ra(row)}
            return {"da_nop": True, "bai": await _hoi_testbank(session, row, dl)}
        raise _loi(e, MSG_GUI_LOI) from e

    da_chon = json.loads(row.tra_loi_json or "{}")
    for c in body.cau:
        if c.stt in out.get("da_luu", []):
            da_chon[dl_mod.qid_cau(c.stt)] = c.chon
    row.tra_loi_json = json.dumps(da_chon, ensure_ascii=False)
    await session.commit()
    return {"da_nop": False, "da_luu": out.get("da_luu", []), "loi": out.get("loi", []),
            "luu_luc": out.get("luu_luc")}


class NopBody(BaseModel):
    #: Các lựa chọn giao diện đang giữ — gửi kèm để chắc chắn đủ trước khi chấm (có thể chưa kịp lưu).
    cau: list[TraLoiMot] = Field(default_factory=list, max_length=200)


@router.post("/{de_id}/nop")
async def nop(
    de_id: str,
    body: NopBody,
    hs: User = Depends(_hoc_sinh),
    session: AsyncSession = Depends(get_session),
    dl: DeliveryClient | None = Depends(lay_delivery),
) -> dict:
    uid = hs.id
    # Khoá hàng: hai thiết bị nộp cùng lúc thì bên sau chờ rồi trả đúng kết quả bên trước đã ghi
    # (KB 19) — Testbank cũng chỉ ghi một lần, đây là để hai bên thấy cùng một bản.
    row = await _bai_hoac_404(session, uid, de_id, khoa=True)
    if row.ket_qua_json:
        return _ra(row)
    dl = _can_delivery(dl, MSG_GUI_LOI)
    try:
        bai = await dl.nop(row.khoa_bai_lam, _goi_len(row, body.cau))
    except DeliveryLoi as e:
        if e.status == 422:
            raise HTTPException(422, MSG_CAU_SAI) from e
        # Không tạo kết quả hay điểm nào khi chưa gửi được (KB 24).
        raise _loi(e, MSG_GUI_LOI) from e

    if bai.get("cach_nop") == "TAY":
        # Nộp bằng tay: các lựa chọn gửi kèm đã được Testbank ghi trước khi chấm.
        da_chon = json.loads(row.tra_loi_json or "{}")
        theo_stt = {c.stt: c.chon for c in body.cau}
        for stt, chon in theo_stt.items():
            da_chon[dl_mod.qid_cau(stt)] = chon
        row.tra_loi_json = json.dumps(da_chon, ensure_ascii=False)
    # Hết giờ / thầy cô đóng bài trước lúc nộp: chỉ các câu ĐÃ LƯU được tính -> giữ nguyên bản đã lưu.
    await _dong_bo(session, row, bai)
    out = _ra(row, bai)
    await session.commit()
    return out
