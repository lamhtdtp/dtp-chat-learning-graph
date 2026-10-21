"""CMS kho học liệu có mã (US-27, docs/contracts/US-27-kho-hoc-lieu-va-de-xuat.md §2).

Chuyên gia / giáo viên / admin thêm, sửa, xoá học liệu (video, SGK, SBT, BTTC) và gắn vào
một YCCĐ, tuỳ chọn thu hẹp theo một câu và một phương án. Học sinh không vào được (403).

- GET    /cms/hoc-lieu                  — danh sách (chưa xoá, mới sửa trước), lọc ycd / loai / q
- POST   /cms/hoc-lieu                  — thêm
- PATCH  /cms/hoc-lieu/{id}             — sửa (trừ mã)
- DELETE /cms/hoc-lieu/{id}             — xoá MỀM (mã không dùng lại được)
- GET    /cms/hoc-lieu/ycd              — danh mục YCCĐ Toán 6 để chọn
- GET    /cms/hoc-lieu/video-noi-bo     — video AI nội bộ đã xong để chọn
- GET    /cms/hoc-lieu/ma-ke-tiep       — gợi ý mã kế tiếp theo tiền tố loại

Mọi `detail` lỗi là CHUỖI tiếng Việt đúng chữ trong US (biểu mẫu hiện nguyên văn), nên body
nhận dạng `dict` rồi tự kiểm thay vì để pydantic trả danh sách lỗi tiếng Anh. Quyền kiểm
TRƯỚC khi đọc body: học sinh gửi body rác vẫn nhận 403, không phải 422.
"""
import logging
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import cuoi_ky
from app.api.deps import get_current_user
from app.db.models import HocLieu, User, VideoJob
from app.db.session import get_session
from app.integrations.testbank.client import TestbankChuaCauHinh, TestbankClient, TestbankLoi
from app.integrations.testbank.noi_dung import lay_cau
from app.lessons import de_xuat as de_xuat_svc
from app.lessons.ycd_key import chuan_hoa
from app.video import storage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cms/hoc-lieu", tags=["hoc_lieu"])

_VAI_QUAN_TRI = {"chuyen_gia", "giao_vien", "admin"}
LOAI = ("VIDEO", "SGK", "SBT", "BTTC")
MUC_DICH = ("on_lai", "cung_co")
_TIEN_TO = {"VIDEO": "VD", "SGK": "SGK", "SBT": "SBT", "BTTC": "BTTC"}
_MA_HOP_LE = re.compile(r"^[A-Za-z0-9-]+$")
_NOI_BO = re.compile(r"^/video/files/[A-Za-z0-9._-]+$")
_TIEN_TO_NOI_BO = "/video/files/"
#: Khoảng trắng, xuống dòng, ký tự điều khiển và ký tự phá thuộc tính HTML: URL này sẽ thành
#: `href` cho học sinh bấm, mà hệ thống KHÔNG mở thử link khi lưu — bộ lọc hình thức là hàng rào duy nhất.
_KY_TU_CAM = re.compile(r"[\s\x00-\x1f\x7f<>\"'\\`]")
_MA_TOI_DA, _NHAN_TOI_DA, _URL_TOI_DA = 64, 255, 1024

MSG_KHONG_QUYEN = "Bạn không có quyền quản trị kho học liệu"
MSG_KHONG_THAY = "Không tìm thấy học liệu này"
MSG_KHONG_SUA_MA = "Không sửa được mã học liệu"
MSG_YCD_NGOAI_DANH_MUC = "Yêu cầu cần đạt không có trong danh mục"
MSG_BAN = "Kho đề đang bận, thử lại sau ít phút"
MSG_VIDEO_NOI_BO = "Video nội bộ không tồn tại"
MSG_KHONG_CO_CAU = "Không tìm thấy câu này trong kho đề"


def _loi422(msg: str) -> HTTPException:
    return HTTPException(422, msg)


async def _quan_tri(user: User = Depends(get_current_user)) -> User:
    # Chưa đăng nhập -> 401 từ `get_current_user`; học sinh -> 403. Khai làm dependency để chạy
    # TRƯỚC khi FastAPI đọc body.
    if user.role not in _VAI_QUAN_TRI:
        raise HTTPException(status.HTTP_403_FORBIDDEN, MSG_KHONG_QUYEN)
    return user


# ── Kiểm tra dữ liệu nhập ───────────────────────────────────────────────────
def _chuoi(v: Any, ten: str = "Giá trị") -> str:
    """None -> rỗng (không gửi); chuỗi -> bỏ khoảng trắng hai đầu; kiểu khác (số, danh sách…) -> 422.
    Trước đây kiểu sai bị coi như "không gửi", nên `"qid": 5` lưu thành NULL mà vẫn 201."""
    if v is None:
        return ""
    if not isinstance(v, str):
        raise _loi422(f"{ten} phải là chuỗi")
    return v.strip()


def _lay_body(body: Any) -> dict[str, Any]:
    """Body phải là một object JSON; không thì 422 với chuỗi tiếng Việt (không phải danh sách pydantic)."""
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise _loi422("Dữ liệu gửi lên không hợp lệ")
    return body


def kiem_ma(v: Any) -> str:
    ma = _chuoi(v, "Mã")
    if not ma:
        raise _loi422("Cần nhập mã học liệu")
    if not _MA_HOP_LE.match(ma):
        raise _loi422("Mã chỉ gồm chữ không dấu, số và dấu gạch ngang")
    if len(ma) > _MA_TOI_DA:
        raise _loi422(f"Mã dài tối đa {_MA_TOI_DA} ký tự")
    return ma.upper()


def kiem_loai(v: Any) -> str:
    loai = _chuoi(v, "Loại").upper()
    if loai not in LOAI:
        raise _loi422("Loại phải là VIDEO, SGK, SBT hoặc BTTC")
    return loai


def kiem_nhan(v: Any) -> str:
    nhan = _chuoi(v, "Nhãn")
    if not nhan:
        raise _loi422("Cần nhập nhãn")
    if len(nhan) > _NHAN_TOI_DA:
        raise _loi422(f"Nhãn dài tối đa {_NHAN_TOI_DA} ký tự")
    return nhan


def kiem_url(v: Any) -> str:
    """Bỏ khoảng trắng ĐẦU/CUỐI rồi mới kiểm. Nhận http(s) hoặc đường video nội bộ chọn từ
    danh sách (`/video/files/...`)."""
    url = _chuoi(v, "Đường dẫn")
    if not url:
        raise _loi422("Cần nhập đường dẫn")
    if url.startswith(_TIEN_TO_NOI_BO):
        # Chỉ tên tệp hợp lệ (không `..`, không toàn dấu chấm); có thật hay không thì `kiem_noi_bo` kiểm.
        ten = url[len(_TIEN_TO_NOI_BO):]
        if not _NOI_BO.match(url) or set(ten) <= {"."} or ".." in ten:
            raise _loi422(MSG_VIDEO_NOI_BO)
        return url
    thap = url.lower()
    if not (thap.startswith("http://") or thap.startswith("https://")):
        raise _loi422("Đường dẫn phải bắt đầu bằng http:// hoặc https://")
    # Dài quá mới báo độ dài; còn lại là khoảng trắng giữa chừng / thiếu máy chủ.
    if len(url) > _URL_TOI_DA:
        raise _loi422(f"Đường dẫn dài tối đa {_URL_TOI_DA} ký tự")
    sau = url.split("://", 1)[1]
    may_chu = re.split(r"[/?#]", sau, maxsplit=1)[0]
    if _KY_TU_CAM.search(url) or not may_chu or may_chu.startswith((".", ":", "@")):
        raise _loi422("Đường dẫn không hợp lệ")
    return url


async def kiem_noi_bo(session: AsyncSession, url: str) -> None:
    """Đường nội bộ phải trỏ tới video CÓ THẬT: job DONE mang đúng đường này, hoặc tệp có trong kho video."""
    if not url.startswith(_TIEN_TO_NOI_BO):
        return
    co_job = await session.scalar(select(VideoJob.id).where(VideoJob.status == "DONE", VideoJob.video_url == url))
    if co_job is None and storage.resolve_url(url) is None:
        raise _loi422(MSG_VIDEO_NOI_BO)


def kiem_muc_dich(v: Any) -> str:
    if v not in MUC_DICH:
        raise _loi422("Chọn mục đích Ôn lại hoặc Củng cố")
    return v


def pham_vi(ycd_text: str, qid: str | None, option_key: str | None) -> str:
    """Chuỗi CỐ ĐỊNH theo US KB 7 (chữ "YCCĐ", không phải nguyên văn)."""
    out = "YCCĐ"
    if qid:
        out += f" · câu {qid}"
        if option_key:
            out += f" · phương án {option_key}"
    return out


async def _kiem_ycd(session: AsyncSession, v: Any) -> de_xuat_svc.MucYcd:
    text = _chuoi(v, "Yêu cầu cần đạt")
    if not text:
        raise _loi422("Cần gắn học liệu vào một yêu cầu cần đạt")
    muc = (await de_xuat_svc.doc_danh_muc(session)).tim(chuan_hoa(text))
    if muc is None:
        raise _loi422(MSG_YCD_NGOAI_DANH_MUC)
    return muc


async def _kiem_cau(tb: TestbankClient | None, qid: str, option_key: str | None, ycd_key: str) -> None:
    """Câu phải có trong kho đề, thuộc đúng YCCĐ và có phương án đó. Hỏi testbank KHÔNG xin đáp án:
    CMS chỉ cần biết câu thuộc YCCĐ nào và có những phương án nào."""
    if tb is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_BAN)
    try:
        caus = await lay_cau(tb, [qid], include_answers=False)
    except TestbankChuaCauHinh as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_BAN) from e
    except TestbankLoi as e:
        if e.tam_thoi:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_BAN) from e
        # 4xx / sai tài khoản: thử lại không khỏi — 502 để giám sát thấy khác 503.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Kho đề đang gặp sự cố, chưa kiểm tra được câu") from e
    cau = next((c for c in caus if c.get("qid") == qid), None)
    if cau is None:
        raise _loi422(MSG_KHONG_CO_CAU)
    if chuan_hoa(cau.get("yccd_text") or "") != ycd_key:
        raise _loi422("Câu này không thuộc yêu cầu cần đạt đã chọn")
    if option_key:
        co = {str(o.get("key") or "").upper() for o in cau.get("options") or []}
        if option_key not in co:
            raise _loi422(f"Câu này không có phương án {option_key}")


async def _chuan_hoa_pham_vi(session: AsyncSession, tb: TestbankClient | None, du_lieu: dict) -> dict:
    """Kiểm YCCĐ / câu / phương án / mục đích của một học liệu (thêm hoặc sau khi trộn dữ liệu sửa)."""
    muc = await _kiem_ycd(session, du_lieu.get("ycd"))
    qid = _chuoi(du_lieu.get("qid"), "Mã câu") or None
    option_key = _chuoi(du_lieu.get("option_key"), "Phương án").upper() or None
    if option_key and not qid:
        raise _loi422("Chọn câu trước khi gắn phương án")
    if option_key and du_lieu["muc_dich"] != "on_lai":
        raise _loi422("Học liệu gắn theo phương án chỉ dùng mục đích Ôn lại")
    if qid:
        await _kiem_cau(tb, qid, option_key, muc.ycd_key)
    return {"ycd_key": muc.ycd_key, "ycd_text": muc.ycd_text, "qid": qid, "option_key": option_key}


# ── Hiển thị ────────────────────────────────────────────────────────────────
def _dang_json(r: HocLieu, ten: dict[int, str]) -> dict:
    return {
        "id": r.id, "ma": r.ma, "loai": r.loai, "nhan": r.nhan, "url": r.url, "muc_dich": r.muc_dich,
        "ycd": r.ycd_text, "ycd_key": r.ycd_key, "qid": r.qid, "option_key": r.option_key,
        "pham_vi": pham_vi(r.ycd_text, r.qid, r.option_key),
        "nguoi_tao": ten.get(r.nguoi_tao_id, "") if r.nguoi_tao_id else "",
        "tao_luc": r.tao_luc.isoformat(),
        "nguoi_sua": ten.get(r.nguoi_sua_id, "") if r.nguoi_sua_id else "",
        "sua_luc": r.sua_luc.isoformat() if r.sua_luc else None,
    }


async def _ten_nguoi(session: AsyncSession, rows: list[HocLieu]) -> dict[int, str]:
    ids = {i for r in rows for i in (r.nguoi_tao_id, r.nguoi_sua_id) if i}
    if not ids:
        return {}
    return dict((await session.execute(select(User.id, User.name).where(User.id.in_(ids)))).all())


async def _lay(session: AsyncSession, hid: int) -> HocLieu:
    r = None
    if 1 <= hid <= 2**31 - 1:
        r = await session.scalar(select(HocLieu).where(HocLieu.id == hid, HocLieu.xoa_luc.is_(None))
                                 .execution_options(populate_existing=True))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MSG_KHONG_THAY)
    return r


# ── Danh sách / danh mục ────────────────────────────────────────────────────
@router.get("")
async def liet_ke(
    ycd: str | None = None, loai: str | None = None, q: str | None = None,
    _u: User = Depends(_quan_tri), session: AsyncSession = Depends(get_session),
) -> dict:
    """Học liệu chưa xoá, mới sửa trước. `ycd` lọc theo khoá chuẩn hoá (khác hoa thường /
    khoảng trắng vẫn khớp)."""
    cau = select(HocLieu).where(HocLieu.xoa_luc.is_(None))
    if _chuoi(ycd):
        cau = cau.where(HocLieu.ycd_key == chuan_hoa(ycd))
    if _chuoi(loai):
        cau = cau.where(HocLieu.loai == _chuoi(loai).upper())
    if _chuoi(q):
        tho = _chuoi(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        mau = f"%{tho}%"
        cau = cau.where(or_(HocLieu.ma.ilike(mau, escape="\\"), HocLieu.nhan.ilike(mau, escape="\\")))
    # Thứ tự theo giờ Postgres (clock_timestamp), id phá hoà khi hai dòng trùng giờ.
    rows = list((await session.scalars(cau.order_by(
        func.coalesce(HocLieu.sua_luc, HocLieu.tao_luc).desc(), HocLieu.id.desc()))).all())
    ten = await _ten_nguoi(session, rows)
    return {"hoc_lieu": [_dang_json(r, ten) for r in rows]}


@router.get("/ycd")
async def danh_muc_ycd(_u: User = Depends(_quan_tri), session: AsyncSession = Depends(get_session)) -> dict:
    dm = await de_xuat_svc.doc_danh_muc(session)
    return {"ycd": [{"ycd": m.ycd_text, "ycd_key": m.ycd_key, "don_vi": m.don_vi, "topic_id": m.topic_id}
                    for m in dm.duy_nhat()]}


@router.get("/video-noi-bo")
async def video_noi_bo(_u: User = Depends(_quan_tri), session: AsyncSession = Depends(get_session)) -> dict:
    """Video AI nội bộ đã xong (không gõ tay đường dẫn). `url` là đường THÔ đã lưu trong job; khi
    đưa tới học sinh mới ký (link ký hết hạn sau 12 giờ, không được nằm trong kho)."""
    rows = (await session.execute(
        select(VideoJob.video_url, VideoJob.title, VideoJob.concept_key)
        .where(VideoJob.status == "DONE", VideoJob.video_url.is_not(None))
        .order_by(VideoJob.title, VideoJob.id))).all()
    return {"video": [{"url": u, "tieu_de": t or k} for u, t, k in rows if u.startswith("/video/files/")]}


@router.get("/ma-ke-tiep")
async def ma_ke_tiep(loai: str = "VIDEO", _u: User = Depends(_quan_tri),
                     session: AsyncSession = Depends(get_session)) -> dict:
    """Gợi ý mã kế tiếp: tiền tố loại + `TO06-` + 3 chữ số (lớn nhất hiện có + 1, kể cả mã đã
    xoá — mã đã dùng không dùng lại). Quản trị viên được gõ đè."""
    tien_to = _TIEN_TO[kiem_loai(loai)] + "-TO06-"
    cac_ma = (await session.scalars(select(HocLieu.ma).where(HocLieu.ma.like(tien_to + "%")))).all()
    so = [int(m[len(tien_to):]) for m in cac_ma if m[len(tien_to):].isdigit()]
    return {"ma": f"{tien_to}{max(so, default=0) + 1:03d}"}


# ── Thêm / sửa / xoá ────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_201_CREATED)
async def them(
    body: Any = Body(default=None),
    user: User = Depends(_quan_tri), session: AsyncSession = Depends(get_session),
    tb: TestbankClient | None = Depends(cuoi_ky.lay_testbank_tuy_chon),
) -> dict:
    body = _lay_body(body)
    ma = kiem_ma(body.get("ma"))
    du_lieu = {"loai": kiem_loai(body.get("loai")), "nhan": kiem_nhan(body.get("nhan")),
               "url": kiem_url(body.get("url")), "muc_dich": kiem_muc_dich(body.get("muc_dich")),
               "ycd": body.get("ycd"), "qid": body.get("qid"), "option_key": body.get("option_key")}
    await kiem_noi_bo(session, du_lieu["url"])
    gan = await _chuan_hoa_pham_vi(session, tb, du_lieu)
    trung = f"Mã {ma} đã tồn tại"
    if await session.scalar(select(HocLieu.id).where(func.upper(HocLieu.ma) == ma)):
        raise HTTPException(status.HTTP_409_CONFLICT, trung)
    uid = user.id
    hl = HocLieu(ma=ma, loai=du_lieu["loai"], nhan=du_lieu["nhan"], url=du_lieu["url"],
                 muc_dich=du_lieu["muc_dich"], nguoi_tao_id=uid, **gan)
    try:
        # SAVEPOINT: hai người thêm cùng một mã cùng lúc cùng vượt qua bước kiểm ở trên; UNIQUE trong
        # DB là chốt cuối — thua cuộc đua thì 409 như bình thường, không phải 500.
        async with session.begin_nested():
            session.add(hl)
            await session.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, trung) from e
    await session.refresh(hl)
    out = _dang_json(hl, await _ten_nguoi(session, [hl]))
    await session.commit()
    return out


@router.patch("/{hoc_lieu_id}")
async def sua(
    hoc_lieu_id: int, body: Any = Body(default=None),
    user: User = Depends(_quan_tri), session: AsyncSession = Depends(get_session),
    tb: TestbankClient | None = Depends(cuoi_ky.lay_testbank_tuy_chon),
) -> dict:
    body = _lay_body(body)
    hl = await _lay(session, hoc_lieu_id)
    if "ma" in body and _chuoi(body["ma"], "Mã").upper() != hl.ma:
        raise _loi422(MSG_KHONG_SUA_MA)
    # Trộn dữ liệu cũ + dữ liệu gửi lên rồi kiểm LẠI toàn bộ như khi thêm: sửa là cửa sau của mọi
    # luật KB 4-6 (nếu PATCH không kiểm lại thì `javascript:` lọt vào kho qua đây).
    cu = {"loai": hl.loai, "nhan": hl.nhan, "url": hl.url, "muc_dich": hl.muc_dich,
          "ycd": hl.ycd_text, "qid": hl.qid, "option_key": hl.option_key}
    moi = {**cu, **{k: v for k, v in body.items() if k in cu}}
    du_lieu = {"loai": kiem_loai(moi["loai"]), "nhan": kiem_nhan(moi["nhan"]),
               "url": kiem_url(moi["url"]), "muc_dich": kiem_muc_dich(moi["muc_dich"]),
               "ycd": moi["ycd"], "qid": moi["qid"], "option_key": moi["option_key"]}
    if du_lieu["url"] != hl.url:                       # video đã lưu có thể bị gỡ sau này: sửa nhãn vẫn được
        await kiem_noi_bo(session, du_lieu["url"])
    # Đổi câu / phương án / YCCĐ thì phải hỏi lại kho đề; không đổi thì khỏi (biểu mẫu sửa luôn gửi
    # cả phạm vi cũ, và testbank có thể đang bận).
    doi_pham_vi = (chuan_hoa(_chuoi(moi["ycd"], "Yêu cầu cần đạt")) != hl.ycd_key
                   or (_chuoi(moi["qid"], "Mã câu") or None) != hl.qid
                   or (_chuoi(moi["option_key"], "Phương án").upper() or None) != hl.option_key)
    if doi_pham_vi:
        gan = await _chuan_hoa_pham_vi(session, tb, du_lieu)
    else:
        if du_lieu["option_key"] and du_lieu["muc_dich"] != "on_lai":
            raise _loi422("Học liệu gắn theo phương án chỉ dùng mục đích Ôn lại")
        gan = {"ycd_key": hl.ycd_key, "ycd_text": hl.ycd_text, "qid": hl.qid, "option_key": hl.option_key}
    hl.loai, hl.nhan, hl.url, hl.muc_dich = (du_lieu[k] for k in ("loai", "nhan", "url", "muc_dich"))
    hl.ycd_key, hl.ycd_text, hl.qid, hl.option_key = (gan[k] for k in ("ycd_key", "ycd_text", "qid", "option_key"))
    hl.nguoi_sua_id = user.id
    hl.sua_luc = func.clock_timestamp()                # giờ của POSTGRES, không phải datetime.now() của Python
    await session.flush()
    await session.refresh(hl)
    out = _dang_json(hl, await _ten_nguoi(session, [hl]))
    await session.commit()
    return out


@router.delete("/{hoc_lieu_id}", status_code=status.HTTP_204_NO_CONTENT)
async def xoa(
    hoc_lieu_id: int, user: User = Depends(_quan_tri), session: AsyncSession = Depends(get_session),
) -> Response:
    """Xoá MỀM: dòng ở lại (mã không dùng lại được), học sinh không còn thấy ở mọi kết quả —
    kể cả bài đã nộp từ trước, vì khối Đề xuất tính lại theo kho hiện tại."""
    hl = await _lay(session, hoc_lieu_id)
    hl.xoa_luc = func.clock_timestamp()
    hl.nguoi_sua_id = user.id
    hl.sua_luc = func.clock_timestamp()
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
