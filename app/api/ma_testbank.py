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

Mức 1 (US-30, `TESTBANK_DOI_TAC_BAT`): máy chủ vào thi bằng đường ĐỐI TÁC (`/doi-tac/*`, token tài khoản
dịch vụ), không giữ khoá bài làm. Mức của từng bài CỐ ĐỊNH lúc tạo (`de_cuoi_ky.muc`): bật / tắt cờ sau đó
không đổi đường đi của bài đã có, và lỗi đường đối tác không bao giờ rơi về mức 0 (sẽ ra bài thứ hai).
Chi tiết sau nộp / giai đoạn 1-2: `app/exam/bai_ma_chi_tiet.py`.

Bài mức 0: Testbank không gửi đáp án / lời giải nên kết quả chỉ có điểm + Đúng/Sai từng câu; KHÔNG ghi
`quiz_attempts` (không đoán YCCĐ — KB 20).

Lỗi Testbank không thành 500: mạng / 5xx -> 503, 4xx lạ -> 502, thông điệp tiếng Việt.
"""
import json
import logging
import math
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cuoi_ky import lay_testbank_tuy_chon
from app.api.deps import get_current_user
from app.config import settings
from app.db.models import DeCuoiKy, User
from app.db.session import get_session
from app.exam import bai_ma_chi_tiet as ct_svc
from app.exam import ly_do_to_de
from app.exam.ma_de import chuan_hoa_ma
from app.integrations.testbank import delivery as dl_mod
from app.integrations.testbank import doi_tac as dt_mod
from app.integrations.testbank.client import TestbankClient
from app.integrations.testbank.delivery import DeliveryClient, DeliveryLoi
from app.integrations.testbank.doi_tac import DoiTacClient
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


def lay_doi_tac(tb: TestbankClient | None = Depends(lay_testbank_tuy_chon)) -> DoiTacClient | None:
    """Client đường đối tác (mức 1). None = chưa đủ cấu hình (tài khoản dịch vụ hoặc gốc phát đề). Dùng
    chung token tài khoản dịch vụ với mọi lời gọi Testbank khác. Test thay bằng client dùng `MockTransport`."""
    goc = (settings.testbank_delivery_url or "").strip()
    return DoiTacClient(goc, tb) if tb is not None and goc else None


async def _hoc_sinh(user: User = Depends(get_current_user)) -> User:
    # Khai TRƯỚC `lay_delivery` ở chỗ dùng: giáo viên gọi thẳng nhận 403, không động tới Testbank.
    if user.role != "hoc_sinh":
        raise HTTPException(status.HTTP_403_FORBIDDEN, MSG_CHI_HOC_SINH)
    return user


def _can_delivery(dl: DeliveryClient | DoiTacClient | None, msg: str):
    if dl is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, msg)
    return dl


def _client_cua(row: DeCuoiKy, dl: DeliveryClient | None, dc: DoiTacClient | None, msg: str):
    """Client đúng mức của bài: mức 0 -> đường học sinh, mức 1 -> đường đối tác. Hai đường KHÔNG đọc
    được bài của nhau (Testbank trả "không tìm thấy bài"), nên không bao giờ dùng nhầm."""
    return _can_delivery(dc if row.muc == 1 else dl, msg)


def _dinh_danh(row: DeCuoiKy) -> str:
    """Thứ đã định danh bài trên Testbank: khoá bài làm (mức 0) hoặc mã bài làm (mức 1) — BÍ MẬT cả hai."""
    return row.bai_lam_tb_id if row.muc == 1 else row.khoa_bai_lam


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
    """Thứ DUY NHẤT của bài theo mã đi ra trình duyệt (cùng với `_xuat`). Không có khoá bài làm / mã bài
    làm Testbank; không có đáp án: bài mức 0 learning không bao giờ có, bài mức 1 chỉ qua `_xuat`."""
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
        # US-30: 0 = chưa có chi tiết sau nộp (bài mức 0, cờ tắt, hoặc chưa lấy được) · 1 = chờ thầy cô
        # đóng bài · 2 = đã có đáp án. `ghi_chu` là các dòng trạng thái giao diện hiện nguyên văn.
        "giai_doan": 0, "co_chi_tiet": False, "ghi_chu": [],
    }


async def _xuat(session: AsyncSession, row: DeCuoiKy, bai: dict | None, *, tb: TestbankClient | None,
                bg: BackgroundTasks, kiem: str | None = None) -> dict:
    """Phản hồi của một bài. Bài mức 1 đã nộp: kết quả theo YCCĐ + Đề xuất (+ đáp án khi lượt đã đóng).
    Gọi TRƯỚC `commit` (đọc thuộc tính ORM sau commit là MissingGreenlet)."""
    out = _ra(row, bai)
    if row.muc == 1 and row.ket_qua_json:
        out["ket_qua"], viec = await ct_svc.dung_ket_qua(session, row, tb)
        out["giai_doan"] = ct_svc.giai_doan(row)
        out["co_chi_tiet"] = out["giai_doan"] >= 1
        out["ghi_chu"] = ct_svc.ghi_chu(row, kiem)
        if viec:
            # Lý do từng phương án sinh SAU khi đã trả bài: học sinh thấy đáp án + lời giải ngay (KB 18).
            bg.add_task(ly_do_to_de.sinh_nen, viec)
    return out


async def _sau_nop(session: AsyncSession, row: DeCuoiKy, dc: DoiTacClient | None) -> str | None:
    """Vừa biết bài mức 1 đã nộp (học sinh nộp, hoặc Testbank tự nộp): lấy chi tiết sau nộp ngay lần này."""
    if row.muc == 1 and row.ket_qua_json:
        return await ct_svc.thu_chi_tiet(session, row, dc)
    return None


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
    # G3: XP như đề cuối kỳ tự rút, theo số câu đúng Testbank chấm. Chỉ ở ĐÂY: có chi tiết sau nộp hay
    # mở đáp án về sau cũng không cộng thêm (US-30 KB 9).
    xp = kq["so_cau_dung"] * _XP_MOI_CAU + (_XP_DAT if kq["dat_yeu_cau"] else 0)
    await stats_svc.award(session, row.user_id, xp)


async def _hoi_testbank(session: AsyncSession, row: DeCuoiKy, dl, dc, *, tb, bg) -> dict:
    """Đọc bài từ Testbank rồi đồng bộ + commit. Gọi khi `row` đã bị khoá và chưa nộp."""
    cl = _client_cua(row, dl, dc, MSG_CHUA_MO)
    try:
        bai = await cl.xem(_dinh_danh(row))
    except DeliveryLoi as e:
        if e.status == 410:
            raise HTTPException(status.HTTP_410_GONE, MSG_QUA_HAN_XEM) from e
        raise _loi(e, MSG_CHUA_MO) from e
    await _dong_bo(session, row, bai)
    kiem = await _sau_nop(session, row, dc)
    out = await _xuat(session, row, bai, tb=tb, bg=bg, kiem=kiem)
    await session.commit()
    return out


def _can_hoi_chi_tiet(row: DeCuoiKy) -> bool:
    """Bài mức 1 đã nộp còn phải/được hỏi Testbank về chi tiết không (chưa có đáp án, chưa quá hạn)."""
    return (row.muc == 1 and settings.testbank_chi_tiet_sau_nop_bat
            and not row.dap_an_mo and not row.het_han_dap_an)


async def _mo(session: AsyncSession, uid: int, row: DeCuoiKy, dl, dc, *, tb, bg) -> dict:
    if row.ket_qua_json and not _can_hoi_chi_tiet(row):
        # Đã nộp và không còn gì để hỏi: bản chép ở learning. KHÔNG hỏi Testbank — lượt phát đóng 3
        # ngày rồi vẫn xem được (KB 11), Testbank khoá đọc kết quả sau 30 ngày, bài đủ đáp án không bao
        # giờ đọc lại (US-30 KB 14, 20).
        return await _xuat(session, row, None, tb=tb, bg=bg)
    de_id = row.id
    # Khoá hàng: mở cùng lúc từ hai thiết bị thì một bên chờ rồi thấy bài đã đồng bộ.
    row = await _bai_hoac_404(session, uid, de_id, khoa=True)
    if row.ket_qua_json:
        kiem = await ct_svc.thu_chi_tiet(session, row, dc) if _can_hoi_chi_tiet(row) else None
        out = await _xuat(session, row, None, tb=tb, bg=bg, kiem=kiem)
        await session.commit()
        return out
    return await _hoi_testbank(session, row, dl, dc, tb=tb, bg=bg)


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


def _loi_vao_muc_1(e: DeliveryLoi, uid: int) -> HTTPException:
    """Lỗi vào thi bằng đường đối tác (US-30 KB 6). Chỉ "mã sai / đã đóng" mới tính vào bộ đếm sai mã.
    KHÔNG tự chuyển sang mức 0: Testbank đã có thể tạo bài ở đường này, rơi xuống mức 0 là bài thứ hai."""
    if e.status == 404 and e.ma == dt_mod.MA_KHONG_DUNG:
        return HTTPException(status.HTTP_404_NOT_FOUND, MSG_MA_SAI)
    if e.status == 429:
        if e.ma == dt_mod.MA_DOI_TAC_NHAP_SAI_NHIEU:
            log.warning("CANH_BAO testbank_chan_nhap_ma_doi_tac retry_after=%s hs=%s", e.retry_after, uid)
            return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _msg_khoa_nhap_ma(e.retry_after or 600))
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MSG_CHAN_DO)
    log.warning("CANH_BAO testbank_doi_tac_vao_thi_loi status=%s ma=%s hs=%s", e.status, e.ma, uid)
    return _loi(e, MSG_CHUA_MO)


@router.post("/vao")
async def vao(
    body: VaoBody,
    bg: BackgroundTasks,
    hs: User = Depends(_hoc_sinh),
    session: AsyncSession = Depends(get_session),
    dl: DeliveryClient | None = Depends(lay_delivery),
    dc: DoiTacClient | None = Depends(lay_doi_tac),
    tb: TestbankClient | None = Depends(lay_testbank_tuy_chon),
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
        # Bài đã có giữ nguyên mức của nó, bất kể cờ đang bật hay tắt (US-30 KB 4, 5).
        return await _mo(session, uid, row, dl, dc, tb=tb, bg=bg)

    if settings.testbank_doi_tac_bat:
        # Mức 1: mã học sinh = mã tài khoản learning, họ tên thuần (không hậu tố "· HS<số>": nhãn
        # "Gia sư DTP · HS<mã>" trên bảng kết quả do Testbank tự dựng). Mất phản hồi giữa chừng thì lần
        # nhập sau gọi lại và nhận đúng bài đã tạo — Testbank bảo đảm mỗi học sinh một bài.
        try:
            bai_id, _vao_lai, bai = await _can_delivery(dc, MSG_CHUA_MO).vao_thi(
                ma, str(uid), dl_mod.ho_ten_thuan(ten))
        except DeliveryLoi as e:
            err = _loi_vao_muc_1(e, uid)
            if err.status_code == status.HTTP_404_NOT_FOUND:
                await _ghi_sai(uid)
            raise err from e
        khoa_bai = dict(muc=1, bai_lam_tb_id=bai_id, khoa_bai_lam=None)
    else:
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
        khoa_bai = dict(muc=0, khoa_bai_lam=khoa)

    row = DeCuoiKy(
        id=secrets.token_urlsafe(12), user_id=uid, loai=LOAI, ma_testbank=ma,
        tieu_de=bai.get("tieu_de") or "", cau_json="[]",
        tham_so_json=json.dumps({"exam": None, "nguon": "testbank", "ma": ma}),
        created_at=func.clock_timestamp(), **khoa_bai)
    session.add(row)
    await _dong_bo(session, row, bai)
    kiem = await _sau_nop(session, row, dc)
    out = await _xuat(session, row, bai, tb=tb, bg=bg, kiem=kiem)
    await session.commit()
    return out


@router.get("/{de_id}")
async def mo_lai(
    de_id: str,
    bg: BackgroundTasks,
    hs: User = Depends(_hoc_sinh),
    session: AsyncSession = Depends(get_session),
    dl: DeliveryClient | None = Depends(lay_delivery),
    dc: DoiTacClient | None = Depends(lay_doi_tac),
    tb: TestbankClient | None = Depends(lay_testbank_tuy_chon),
) -> dict:
    uid = hs.id
    row = await _bai_hoac_404(session, uid, de_id)
    return await _mo(session, uid, row, dl, dc, tb=tb, bg=bg)


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
    bg: BackgroundTasks,
    hs: User = Depends(_hoc_sinh),
    session: AsyncSession = Depends(get_session),
    dl: DeliveryClient | None = Depends(lay_delivery),
    dc: DoiTacClient | None = Depends(lay_doi_tac),
    tb: TestbankClient | None = Depends(lay_testbank_tuy_chon),
) -> dict:
    uid = hs.id
    row = await _bai_hoac_404(session, uid, de_id)
    if row.ket_qua_json:
        return {"da_nop": True, "bai": await _mo(session, uid, row, dl, dc, tb=tb, bg=bg)}
    cl = _client_cua(row, dl, dc, MSG_GUI_LOI)
    try:
        out = await cl.luu(_dinh_danh(row), _goi_len(row, body.cau))
    except DeliveryLoi as e:
        if e.status == 409:
            # Đã nộp (em nộp từ máy khác / thầy cô đóng bài) hoặc hết giờ: Testbank đã nộp hộ.
            # Lấy kết quả thật về thay vì để em tiếp tục sửa một bài đã khoá.
            row = await _bai_hoac_404(session, uid, de_id, khoa=True)
            if row.ket_qua_json:
                return {"da_nop": True, "bai": await _mo(session, uid, row, dl, dc, tb=tb, bg=bg)}
            return {"da_nop": True, "bai": await _hoi_testbank(session, row, dl, dc, tb=tb, bg=bg)}
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
    bg: BackgroundTasks,
    hs: User = Depends(_hoc_sinh),
    session: AsyncSession = Depends(get_session),
    dl: DeliveryClient | None = Depends(lay_delivery),
    dc: DoiTacClient | None = Depends(lay_doi_tac),
    tb: TestbankClient | None = Depends(lay_testbank_tuy_chon),
) -> dict:
    uid = hs.id
    # Khoá hàng: hai thiết bị nộp cùng lúc thì bên sau chờ rồi trả đúng kết quả bên trước đã ghi
    # (KB 19) — Testbank cũng chỉ ghi một lần, đây là để hai bên thấy cùng một bản.
    row = await _bai_hoac_404(session, uid, de_id, khoa=True)
    if row.ket_qua_json:
        kiem = await ct_svc.thu_chi_tiet(session, row, dc) if _can_hoi_chi_tiet(row) else None
        out = await _xuat(session, row, None, tb=tb, bg=bg, kiem=kiem)
        await session.commit()
        return out
    cl = _client_cua(row, dl, dc, MSG_GUI_LOI)
    try:
        bai = await cl.nop(_dinh_danh(row), _goi_len(row, body.cau))
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
    kiem = await _sau_nop(session, row, dc)
    out = await _xuat(session, row, bai, tb=tb, bg=bg, kiem=kiem)
    await session.commit()
    return out
