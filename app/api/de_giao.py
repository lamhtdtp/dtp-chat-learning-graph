"""Giáo viên giao đề cuối kỳ bằng mã (US-26, docs/contracts/US-26-giao-de-bang-ma.md).

Phía giáo viên (CMS; vai giáo viên / chuyên gia / admin):
- POST   /de-giao/xem-truoc        — rút đề (testbank `exams:preview`, 40/30/30) + lấy nội dung
                                     + sinh SẴN lý do, lưu bản NHÁP (chưa có mã), trả kèm đáp án.
- POST   /de-giao/{id}/cap-ma      — cấp mã 6 ký tự cho bản nháp (gọi lại -> đúng mã cũ).
- DELETE /de-giao/{id}             — huỷ bản nháp (đề đã cấp mã chỉ đóng được, không xoá).
- GET    /de-giao                  — đề giao đã cấp mã của tôi (admin: của mọi người).
- GET    /de-giao/{id}             — xem lại đề kèm đáp án; không tạo bài làm.
- GET    /de-giao/{id}/ket-qua     — bảng kết quả theo học sinh + theo YCCĐ.
- GET    /de-giao/{id}/bai/{uid}   — bài của một em.
- POST   /de-giao/{id}/dong        — đóng mã (không mở lại).

Phía học sinh:
- POST /de-giao/vao   — nhập mã -> nhận bản chép đóng băng của đề (KHÔNG đáp án / lời giải / lý do).
- POST /de-giao/nop   — chấm ở máy chủ bằng đúng bản đã chép; mỗi em một lần cho mỗi mã.

Máy rút đề / hiển thị / chấm / lý do dùng LẠI của `app/api/cuoi_ky.py` — bài theo mã là một
dòng `de_cuoi_ky` (loai="de_giao"), nên lịch sử, mở lại, thống kê YCCĐ đi chung đường.

Sau khi cấp mã, mở đề và nộp bài KHÔNG gọi testbank: đề đã đóng băng trong `de_giao.cau_json`.
"""
import json
import logging
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import cuoi_ky
from app.api.cuoi_ky import lay_testbank
from app.api.deps import get_current_user
from app.config import settings
from app.db.models import DeCuoiKy, DeGiao, User
from app.db.session import get_session
from app.exam.ma_de import chuan_hoa_ma, sinh_ma
from app.integrations.testbank.client import TestbankChuaCauHinh, TestbankClient, TestbankLoi
from app.llm import cache as llm_cache

log = logging.getLogger(__name__)

router = APIRouter(prefix="/de-giao", tags=["de_giao"])

_VAI_GIAO_DE = {"giao_vien", "chuyen_gia", "admin"}
#: Ngày của hạn mức tính theo GIỜ VIỆT NAM: tính theo UTC thì "ngày mới" bắt đầu lúc
#: 07:00 sáng, giáo viên vừa hết hạn mức lúc 23:00 phải chờ tới sáng.
_GIO_VN = timezone(timedelta(hours=7))
_TTL_HAN_MUC = 60 * 60 * 26
#: Chặn dò mã (Q9): 10 mã đúng định dạng mà không tồn tại trong 10 phút -> chặn tới hết 10 phút.
_DO_MA_TOI_DA = 10
_DO_MA_GIAY = 10 * 60
_THU_SINH_MA = 10
_GHI_CHU = "Đề thầy cô giao"

MSG_KHONG_QUYEN = "Bạn không có quyền giao đề"
MSG_KHONG_THAY_DE = "Không tìm thấy đề giao này"
MSG_KHONG_THAY_BAI = "Không tìm thấy bài làm này"
MSG_SO_CAU = "Số câu phải từ 1 đến 40"
MSG_KHO_RONG = "Kho chưa có câu nào cho đề này."
MSG_DA_CAP_MA = "Đề giao đã cấp mã không xoá được, chỉ đóng được"
MSG_CHI_HOC_SINH = "Chỉ tài khoản học sinh làm bài theo mã"
#: US-26 mục 7 (KB 40-41): giáo viên soạn và phát mã trên Testbank, học sinh nhập mã Testbank ở màn
#: đề cuối kỳ (US-29). Ba chỗ cấp / nhận mã của learning trả 410 thay vì 500 hay im lặng.
MSG_NGUNG_TAO = "Đề giao mới tạo trên Testbank"
MSG_NGUNG_NHAP = ("Mã này không dùng ở đây nữa. Em nhập mã thầy cô phát trên Testbank "
                  "ở màn Đề cuối kỳ nhé")
MSG_SAI_DINH_DANG = "Mã gồm 6 chữ và số, em kiểm tra lại nhé"
MSG_KHONG_THAY_MA = "Không tìm thấy mã này, em hỏi lại thầy cô nhé"
MSG_CHAN_DO = "Em nhập sai mã nhiều lần, thử lại sau 10 phút nhé"
MSG_NOP_SAU_DONG = "Thầy cô đã đóng mã trước khi em nộp, bài này không được tính"
_MSG_KHONG_THAY_DE_HS = "Không tìm thấy đề này."
_MSG_BAN = "Kho đề đang bận, thầy cô thử lại sau ít phút."
_MSG_SU_CO = "Kho đề đang gặp sự cố, chưa rút được đề. Thầy cô báo quản trị viên giúp nhé."
_MSG_KHONG_CAP_DUOC = "Chưa cấp được mã, thầy cô bấm lại giúp nhé."


def _loi_kho(e: TestbankLoi) -> HTTPException:
    """Lời cho GIÁO VIÊN (khác `cuoi_ky._loi_http` nói với học sinh)."""
    if isinstance(e, TestbankChuaCauHinh):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, cuoi_ky.MSG_CHUA_NOI_DE_GIAO)
    if e.tam_thoi:
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _MSG_BAN)
    # 4xx / sai tài khoản: thử lại không khỏi — 502 để giám sát thấy khác 503.
    return HTTPException(status.HTTP_502_BAD_GATEWAY, _MSG_SU_CO)


# ── Phân quyền ──────────────────────────────────────────────────────────────
async def _giao_vien(user: User = Depends(get_current_user)) -> User:
    # Chưa đăng nhập -> 401 từ `get_current_user`; chữ này chỉ dành cho người đã đăng nhập mà thiếu vai.
    if user.role not in _VAI_GIAO_DE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, MSG_KHONG_QUYEN)
    return user


async def _hoc_sinh(user: User = Depends(get_current_user)) -> User:
    if user.role != "hoc_sinh":
        raise HTTPException(status.HTTP_403_FORBIDDEN, MSG_CHI_HOC_SINH)
    return user


# Chốt "Ẩn" của US-26 (KB 40-41). Đặt SAU kiểm vai: học sinh gọi đường của giáo viên vẫn nhận 403,
# không biết gì thêm. Chạy TRƯỚC `lay_testbank` / hạn mức / LLM nên bị từ chối là chưa tốn gì.
async def _giao_vien_tao(gv: User = Depends(_giao_vien)) -> User:
    if not settings.de_giao_learning_bat:
        raise HTTPException(status.HTTP_410_GONE, MSG_NGUNG_TAO)
    return gv


async def _hoc_sinh_nhap_ma_cu(hs: User = Depends(_hoc_sinh)) -> User:
    if not settings.de_giao_learning_bat:
        raise HTTPException(status.HTTP_410_GONE, MSG_NGUNG_NHAP)
    return hs


_INT32_MAX = 2**31 - 1


async def _lay_de(session: AsyncSession, de_id: int, user: User, *, nhap: bool | None = None,
                  khoa: bool = False) -> DeGiao:
    """Đề giao của mình (admin: của ai cũng được). Không tìm thấy / của người khác đều
    trả CÙNG một 404 — giáo viên khác không dò được mã nào có thật (KB 35).

    `nhap`: True chỉ nhận bản nháp, False chỉ nhận đề đã cấp mã, None cả hai.
    `populate_existing`: đọc lại từ DB kể cả khi session đã giữ bản cũ (đóng mã xong
    mà vẫn thấy "đang mở" là sai)."""
    giao = None
    if 1 <= de_id <= _INT32_MAX:
        q = select(DeGiao).where(DeGiao.id == de_id).execution_options(populate_existing=True)
        giao = await session.scalar(q.with_for_update() if khoa else q)
    if (giao is None or (user.role != "admin" and giao.nguoi_tao_id != user.id)
            or (nhap is not None and (giao.trang_thai == "nhap") != nhap)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, MSG_KHONG_THAY_DE)
    return giao


# ── Hạn mức tạo đề ──────────────────────────────────────────────────────────
async def _dat_cho(user: User) -> str | None:
    """Giữ một lượt trong hạn mức ngày TRƯỚC khi gọi testbank / LLM. Trả khoá đã đếm (để
    trả lại khi rút hỏng) hoặc None nếu không đếm (admin, không giới hạn, Redis lỗi).

    Đếm trước rồi hoàn lại thay vì đọc rồi tăng sau: hai request đồng thời cùng đọc
    "19" rồi cùng qua thì vượt hạn mức."""
    limit = settings.de_giao_daily_limit
    if user.role == "admin" or limit <= 0:
        return None
    key = f"degiao:{user.id}:{datetime.now(_GIO_VN):%Y%m%d}"
    try:
        used = await llm_cache.incr_quota(key, ttl=_TTL_HAN_MUC)
    except Exception:  # noqa: BLE001 — Redis chết: không chặn giáo viên vì hạ tầng phụ.
        return None
    if used > limit:
        await _tra_cho(key)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Hôm nay thầy cô đã tạo {limit} đề giao, ngày mai tạo tiếp được nhé")
    return key


async def _tra_cho(key: str) -> None:
    try:
        await llm_cache.giam_quota(key, _TTL_HAN_MUC)
    except Exception:  # noqa: BLE001
        pass


# ── Hiển thị cho giáo viên ──────────────────────────────────────────────────
def _cau_cho_giao_vien(caus: list[dict]) -> list[dict]:
    """Câu công khai + đáp án, lời giải, lý do (người tạo được xem; học sinh thì không)."""
    out = []
    for cong_khai, c in zip(cuoi_ky._de_cong_khai(caus), caus):
        kq = cuoi_ky._cham_cau(c, "", cong_khai["stt"])
        out.append({**cong_khai, **{k: kq[k] for k in ("dap_an", "dap_an_html", "giai_html", "ly_do")}})
    return out


class XemTruocBody(BaseModel):
    exam: Literal["CK1", "CK2"]
    #: Kiểu `Any` để tự kiểm: 0, âm, số thực, > 40 đều phải ra ĐÚNG câu "Số câu phải từ 1 đến 40".
    total: Any = 12


def _so_cau_hop_le(total: Any) -> bool:
    return isinstance(total, int) and not isinstance(total, bool) and 1 <= total <= 40


@router.post("/xem-truoc")
async def xem_truoc(
    body: XemTruocBody,
    gv: User = Depends(_giao_vien_tao),            # khai TRƯỚC `tb`: học sinh nhận 403, không phải lỗi cấu hình kho
    session: AsyncSession = Depends(get_session),
    tb: TestbankClient = Depends(lay_testbank),
) -> dict:
    if not _so_cau_hop_le(body.total):
        raise HTTPException(422, MSG_SO_CAU)
    total: int = body.total
    khoa = await _dat_cho(gv)
    tinh = False
    try:
        seed = secrets.randbelow(2**31)
        try:
            caus, thong_bao = await cuoi_ky.rut_va_chuan_bi(
                session, tb, subject="TO", grade="06", exam=body.exam, total=total,
                ar_ids=None, seed=seed)
        except TestbankLoi as e:
            raise _loi_kho(e) from e

        if not caus:
            # Kho rỗng: không lưu gì, không có nút "Cấp mã", không tính hạn mức.
            return {"nhap_id": None, "exam": body.exam, "total": total, "so_cau": 0,
                    "du_cau": False, "co_the_cap_ma": False, "cau": [],
                    "thong_bao": " ".join([MSG_KHO_RONG, *thong_bao])}

        giao = DeGiao(
            nguoi_tao_id=gv.id, exam=body.exam, total=total, so_cau=len(caus),
            tham_so_json=json.dumps({"subject": "TO", "grade": "06", "exam": body.exam,
                                     "total": total, "seed": seed}),
            thong_bao=" ".join(thong_bao), cau_json=json.dumps(caus, ensure_ascii=False),
            trang_thai="nhap", created_at=func.clock_timestamp())
        session.add(giao)
        await session.flush()
        out = {"nhap_id": giao.id, "exam": body.exam, "total": total, "so_cau": len(caus),
               "du_cau": not thong_bao, "co_the_cap_ma": True,
               "thong_bao": " ".join(thong_bao), "cau": _cau_cho_giao_vien(caus)}
        await session.commit()
        tinh = True
        return out
    finally:
        # Rút hỏng (kho lỗi / kho rỗng / lỗi bất ngờ) thì trả lại lượt đã giữ.
        if khoa and not tinh:
            await _tra_cho(khoa)


@router.post("/{nhap_id}/cap-ma")
async def cap_ma(
    nhap_id: int,
    gv: User = Depends(_giao_vien_tao),
    session: AsyncSession = Depends(get_session),
) -> dict:
    giao = await _lay_de(session, nhap_id, gv, khoa=True)    # khoá hàng: bấm hai lần không ra hai mã
    giao_id, so_cau, total, ma = giao.id, giao.so_cau, giao.total, giao.ma
    if giao.trang_thai == "nhap":
        for _ in range(_THU_SINH_MA):
            moi = sinh_ma()
            if await session.scalar(select(DeGiao.id).where(DeGiao.ma == moi)):
                continue
            try:
                # Unique trong DB là chốt cuối: hai giáo viên cùng bốc trúng một mã trong
                # cùng một khoảnh khắc thì một bên nổ IntegrityError và sinh lại.
                async with session.begin_nested():
                    await session.execute(update(DeGiao).where(DeGiao.id == giao_id)
                                          .values(ma=moi, trang_thai="mo"))
            except IntegrityError:
                continue
            ma = moi
            break
        else:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _MSG_KHONG_CAP_DUOC)
    await session.commit()
    return {"id": giao_id, "ma": ma, "trang_thai": "mo", "so_cau": so_cau, "total": total}


@router.delete("/{nhap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def huy_nhap(
    nhap_id: int,
    gv: User = Depends(_giao_vien),
    session: AsyncSession = Depends(get_session),
) -> Response:
    giao = await _lay_de(session, nhap_id, gv, khoa=True)
    if giao.trang_thai != "nhap":
        # Xoá đề đã cấp mã phải quyết luôn số phận bài làm của học sinh và thống kê YCCĐ (Q10).
        raise HTTPException(status.HTTP_409_CONFLICT, MSG_DA_CAP_MA)
    await session.delete(giao)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("")
async def danh_sach(
    gv: User = Depends(_giao_vien),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Đề giao ĐÃ CẤP MÃ, mới tạo trước. Không đọc `cau_json` (nặng) — `so_cau` là cột riêng."""
    dem = (select(DeCuoiKy.de_giao_id.label("gid"),
                  func.count().filter(DeCuoiKy.ket_qua_json.is_not(None)).label("da_nop"),
                  func.count().filter(DeCuoiKy.ket_qua_json.is_(None)).label("chua_nop"))
           .where(DeCuoiKy.loai == "de_giao").group_by(DeCuoiKy.de_giao_id).subquery())
    q = (select(DeGiao.id, DeGiao.ma, DeGiao.exam, DeGiao.so_cau, DeGiao.total, DeGiao.created_at,
                DeGiao.trang_thai, DeGiao.dong_luc, User.name, dem.c.da_nop, dem.c.chua_nop)
         .join(User, User.id == DeGiao.nguoi_tao_id)
         .outerjoin(dem, dem.c.gid == DeGiao.id)
         .where(DeGiao.trang_thai != "nhap")
         .order_by(DeGiao.created_at.desc(), DeGiao.id.desc()))
    if gv.role != "admin":
        q = q.where(DeGiao.nguoi_tao_id == gv.id)
    rows = (await session.execute(q)).all()
    return {"de_giao": [{
        "id": i, "ma": ma, "exam": exam, "so_cau": so_cau, "total": total,
        "created_at": tao.isoformat(), "trang_thai": tt,
        "dong_luc": dong.isoformat() if dong else None,
        "so_da_nop": da_nop or 0,
        # Mã đã đóng thì bài chưa nộp không còn "đang làm" (nộp sẽ bị từ chối) — cùng luật với bảng kết quả.
        "so_dang_lam": (chua or 0) if tt == "mo" else 0,
        "nguoi_tao": ten,
    } for i, ma, exam, so_cau, total, tao, tt, dong, ten, da_nop, chua in rows]}


@router.get("/{de_id}")
async def xem_lai(
    de_id: int,
    gv: User = Depends(_giao_vien),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Đúng bộ câu học sinh sẽ làm, cùng thứ tự, kèm đáp án. KHÔNG tạo bài làm nào."""
    giao = await _lay_de(session, de_id, gv, nhap=False)
    return {"id": giao.id, "ma": giao.ma, "exam": giao.exam, "total": giao.total,
            "so_cau": giao.so_cau, "du_cau": not giao.thong_bao, "thong_bao": giao.thong_bao,
            "trang_thai": giao.trang_thai, "created_at": giao.created_at.isoformat(),
            "dong_luc": giao.dong_luc.isoformat() if giao.dong_luc else None,
            "cau": _cau_cho_giao_vien(json.loads(giao.cau_json))}


# ── Kết quả ─────────────────────────────────────────────────────────────────
def _khoa_ten(ten: str, uid: int) -> tuple[str, str, int]:
    """Xếp tên A→Z không phân biệt hoa thường VÀ dấu: nếu so thẳng mã Unicode thì "Ánh"
    đứng sau "Zung" (Á = U+00C1)."""
    bo_dau = "".join(c for c in unicodedata.normalize("NFD", ten.replace("đ", "d").replace("Đ", "D"))
                     if not unicodedata.combining(c))
    return bo_dau.casefold(), ten, uid


def _theo_ycd_ca_ma(da_nop: list[dict]) -> list[dict]:
    """Mỗi YCCĐ trong đề một dòng, theo thứ tự mã. Chỉ tính bài ĐÃ NỘP và câu chấm được;
    `ti_le_dung` tính trên tổng LƯỢT trả lời (câu × em), không phải trên số em."""
    gom: dict[str, dict] = {}
    for kq in da_nop:
        rieng: dict[str, list[bool]] = {}
        for c in kq["cau"]:
            if c["cham_duoc"] and c["ar_id"]:
                rieng.setdefault(c["ar_id"], []).append(bool(c["dung"]))
                gom.setdefault(c["ar_id"], {"ycd": c["ycd"], "dung_het": 0, "luot": 0, "luot_dung": 0})
        for ar, ds in rieng.items():
            g = gom[ar]
            g["luot"] += len(ds)
            g["luot_dung"] += sum(ds)
            g["dung_het"] += 1 if all(ds) else 0
    return [{"ar_id": ar, "ycd": g["ycd"], "so_hs_dung_het": g["dung_het"],
             "so_hs_da_nop": len(da_nop), "ti_le_dung": round(g["luot_dung"] / g["luot"], 3)}
            for ar, g in sorted(gom.items())]


@router.get("/{de_id}/ket-qua")
async def ket_qua(
    de_id: int,
    gv: User = Depends(_giao_vien),
    session: AsyncSession = Depends(get_session),
) -> dict:
    giao = await _lay_de(session, de_id, gv, nhap=False)
    dong = giao.trang_thai == "dong"
    rows = (await session.execute(
        select(DeCuoiKy.user_id, User.name, DeCuoiKy.ket_qua_json, DeCuoiKy.nop_luc)
        .join(User, User.id == DeCuoiKy.user_id)
        .where(DeCuoiKy.de_giao_id == giao.id, DeCuoiKy.loai == "de_giao"))).all()
    hoc_sinh, da_nop = [], []
    for uid, ten, kq_json, nop_luc in sorted(rows, key=lambda r: _khoa_ten(r[1], r[0])):
        if kq_json:
            kq = json.loads(kq_json)
            da_nop.append(kq)
            hoc_sinh.append({"user_id": uid, "ten": ten, "trang_thai": "da_nop", "diem": kq["diem"],
                             "tong": kq["tong"], "dat": kq["dat_yeu_cau"],
                             "nop_luc": nop_luc.isoformat() if nop_luc else None})
        else:
            hoc_sinh.append({"user_id": uid, "ten": ten,
                             "trang_thai": "chua_nop_ma_dong" if dong else "dang_lam",
                             "diem": None, "tong": None, "dat": None, "nop_luc": None})
    return {
        "tong": {"da_nop": len(da_nop), "dat": sum(1 for k in da_nop if k["dat_yeu_cau"]),
                 "dang_lam": sum(1 for h in hoc_sinh if h["trang_thai"] == "dang_lam")},
        "hoc_sinh": hoc_sinh,
        "theo_ycd": _theo_ycd_ca_ma(da_nop),
    }


@router.get("/{de_id}/bai/{user_id}")
async def bai_cua_em(
    de_id: int,
    user_id: int,
    gv: User = Depends(_giao_vien),
    session: AsyncSession = Depends(get_session),
) -> dict:
    giao = await _lay_de(session, de_id, gv, nhap=False)
    row = None
    if 1 <= user_id <= _INT32_MAX:
        row = (await session.execute(
            select(DeCuoiKy.ket_qua_json, DeCuoiKy.nop_luc, User.name)
            .join(User, User.id == DeCuoiKy.user_id)
            .where(DeCuoiKy.de_giao_id == giao.id, DeCuoiKy.user_id == user_id,
                   DeCuoiKy.loai == "de_giao"))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MSG_KHONG_THAY_BAI)
    kq_json, nop_luc, ten = row
    if not kq_json:
        return {"da_nop": False, "thong_bao": "Em chưa nộp bài"}
    kq = json.loads(kq_json)
    kq.pop("goi_y", None)          # gợi ý ôn tập là của riêng em, không phải thứ giáo viên cần ở đây
    return {**kq, "da_nop": True, "hoc_sinh": {"id": user_id, "ten": ten},
            "nop_luc": nop_luc.isoformat() if nop_luc else None}


@router.post("/{de_id}/dong")
async def dong_ma(
    de_id: int,
    gv: User = Depends(_giao_vien),
    session: AsyncSession = Depends(get_session),
) -> dict:
    giao = await _lay_de(session, de_id, gv, nhap=False, khoa=True)
    if giao.trang_thai == "mo":
        giao.trang_thai = "dong"
        # Giờ của POSTGRES (cùng nguồn mọi cột thời gian khác), và là mốc để phân biệt bài
        # nộp trước / sau lúc đóng: `nop` giữ khoá đọc của hàng này nên không lọt khe giữa.
        giao.dong_luc = func.clock_timestamp()
        await session.flush()
        await session.refresh(giao)
    out = {"trang_thai": giao.trang_thai, "dong_luc": giao.dong_luc.isoformat()}
    await session.commit()
    return out


# ── Học sinh ────────────────────────────────────────────────────────────────
class VaoBody(BaseModel):
    ma: str


async def _bi_chan_do_ma(hs: User) -> bool:
    try:
        v = await llm_cache.get(f"domama:{hs.id}")
    except Exception:  # noqa: BLE001 — Redis chết: không chặn học sinh.
        return False
    return bool(v) and int(v) >= _DO_MA_TOI_DA


async def _ghi_do_ma(hs: User) -> None:
    """Một lần nhập mã đúng định dạng mà không tồn tại. TTL chỉ đặt ở lần đầu nên cửa sổ 10
    phút tính từ lần sai đầu tiên; mã đóng / mã đúng không đi qua đây nên không bị tính."""
    try:
        await llm_cache.incr_quota(f"domama:{hs.id}", ttl=_DO_MA_GIAY)
    except Exception:  # noqa: BLE001
        pass


async def _bai_cua_em(session: AsyncSession, giao_id: int, user_id: int) -> DeCuoiKy | None:
    return await session.scalar(
        select(DeCuoiKy).where(DeCuoiKy.de_giao_id == giao_id, DeCuoiKy.user_id == user_id,
                               DeCuoiKy.loai == "de_giao")
        .execution_options(populate_existing=True))


@router.post("/vao")
async def vao(
    body: VaoBody,
    hs: User = Depends(_hoc_sinh_nhap_ma_cu),
    session: AsyncSession = Depends(get_session),
    tb: TestbankClient | None = Depends(cuoi_ky.lay_testbank_tuy_chon),
) -> dict:
    if await _bi_chan_do_ma(hs):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MSG_CHAN_DO)
    ma = chuan_hoa_ma(body.ma)
    if ma is None:
        raise HTTPException(422, MSG_SAI_DINH_DANG)
    giao = await session.scalar(
        select(DeGiao).where(DeGiao.ma == ma, DeGiao.trang_thai != "nhap")
        .execution_options(populate_existing=True))
    if giao is None:
        await _ghi_do_ma(hs)
        raise HTTPException(status.HTTP_404_NOT_FOUND, MSG_KHONG_THAY_MA)
    giao_id, dong, uid = giao.id, giao.trang_thai == "dong", hs.id     # đọc TRƯỚC commit

    bai = await _bai_cua_em(session, giao_id, uid)
    if bai is None or (dong and not bai.ket_qua_json):
        # Đóng rồi mà em chưa nộp: không vào được (kể cả em đã mở dở — nộp sẽ bị từ chối).
        if dong:
            raise HTTPException(status.HTTP_410_GONE, cuoi_ky.MSG_MA_DA_DONG)
        # Chép đề đóng băng cho em. ON CONFLICT: hai thiết bị mở lần đầu cùng lúc vẫn chỉ ra MỘT bài.
        await session.execute(
            pg_insert(DeCuoiKy).values(
                id=secrets.token_urlsafe(12), user_id=uid, loai="de_giao", de_giao_id=giao_id,
                tham_so_json=giao.tham_so_json, thong_bao=giao.thong_bao, cau_json=giao.cau_json,
                created_at=func.clock_timestamp(),
            ).on_conflict_do_nothing(constraint="uq_de_cuoi_ky_de_giao_user"))
        await session.commit()
        bai = await _bai_cua_em(session, giao_id, uid)

    cau = cuoi_ky._de_cong_khai(json.loads(bai.cau_json))
    ket_qua = json.loads(bai.ket_qua_json) if bai.ket_qua_json else None
    if ket_qua:
        ket_qua = await cuoi_ky.gan_de_xuat(session, tb, ket_qua, user_id=uid,
                                            attempt_id=bai.attempt_id)
    # `thong_bao` của đề viết cho GIÁO VIÊN (nhắc kho, ma trận). Học sinh chỉ cần biết số câu.
    thong_bao = f"Đề này có {len(cau)} câu." if bai.thong_bao else ""
    return {"de_id": bai.id, "ma": ma, "exam": json.loads(bai.tham_so_json).get("exam"),
            "ghi_chu": _GHI_CHU, "cau": cau,
            "du_cau": not bai.thong_bao, "thong_bao": thong_bao,
            "ket_qua": ket_qua}


@router.post("/nop")
async def nop(
    body: cuoi_ky.SubmitBody,
    hs: User = Depends(_hoc_sinh_nhap_ma_cu),
    session: AsyncSession = Depends(get_session),
    tb: TestbankClient | None = Depends(cuoi_ky.lay_testbank_tuy_chon),
) -> dict:
    # Khoá hàng bài làm: hai thiết bị nộp cùng lúc thì request sau chờ, rồi thấy kết quả
    # request trước đã ghi (populate_existing đọc lại sau khi có khoá) và trả đúng bản đó.
    bai = await session.scalar(
        select(DeCuoiKy).where(DeCuoiKy.id == body.de_id).with_for_update()
        .execution_options(populate_existing=True))
    # Đề của người khác / đề tự rút / lượt luyện thêm: cùng một 404 như không tồn tại.
    if bai is None or bai.user_id != hs.id or bai.loai != "de_giao":
        raise HTTPException(status.HTTP_404_NOT_FOUND, _MSG_KHONG_THAY_DE_HS)
    uid = hs.id                                      # đọc TRƯỚC commit
    if bai.ket_qua_json:
        # Nộp lại -> kết quả lần đầu, kể cả khi mã đã đóng; `de_xuat` tính lại theo kho hiện tại.
        return await cuoi_ky.gan_de_xuat(session, tb, json.loads(bai.ket_qua_json),
                                         user_id=uid, attempt_id=bai.attempt_id)
    # Khoá ĐỌC hàng đề giao: giáo viên bấm "Đóng mã" (UPDATE) phải chờ bài đang nộp xong, nên
    # bài nhận trọn vẹn trước lúc đóng thì được tính, sau lúc đóng thì bị từ chối (KB 34).
    giao = await session.scalar(
        select(DeGiao).where(DeGiao.id == bai.de_giao_id).with_for_update(read=True)
        .execution_options(populate_existing=True))
    if giao.trang_thai == "dong":
        raise HTTPException(status.HTTP_409_CONFLICT, MSG_NOP_SAU_DONG)
    out = await cuoi_ky.cham_va_ghi(session, hs, bai, body.tra_loi, nguon="de_giao",
                                    them={"ma": giao.ma})
    attempt_id = bai.attempt_id
    await session.commit()
    return await cuoi_ky.gan_de_xuat(session, tb, out, user_id=uid, attempt_id=attempt_id)
