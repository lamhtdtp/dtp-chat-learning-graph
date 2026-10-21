"""SSO giáo viên sang DTP Testbank (US-28).

- POST /auth/sso/testbank              — giáo viên / chuyên gia / admin xin liên kết mở Testbank.
- GET  /auth/.well-known/jwks.json     — khoá công khai để Testbank kiểm chữ ký phiếu.

Đặt dưới tiền tố `/auth` ĐÃ CÓ trong nginx của server: thêm tiền tố mới là phải sửa file nginx
chép tay trên server, đã mất hai lần vì quên.

Hai chế độ (`SSO_TESTBANK_BAT`): bật -> cấp phiếu, mở `<web-teacher>/sso#phieu=…`; tắt (Testbank
chưa xong T3) -> KHÔNG cấp phiếu nào, chỉ mở trang giáo viên của Testbank (tự chuyển tới đăng
nhập mật khẩu). Nút trên CMS giữ nguyên ở cả hai chế độ.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import NhatKySsoTestbank, User
from app.db.session import get_session
from app.sso import testbank as sso

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["sso"])

MSG_CHI_THAY_CO = "Chỉ thầy cô dùng được Testbank"
MSG_CHUA_NOI = "Chưa kết nối Testbank, thầy cô báo quản trị viên giúp nhé"


async def _ghi_nhat_ky(session: AsyncSession, user: User, ket_qua: str, jti: str | None = None) -> None:
    """Một dòng ở DB (tra theo email — KB 13) và một dòng ở log. Có `sub`, `jti`, kết quả;
    KHÔNG BAO GIỜ có nguyên phiếu. Đọc thuộc tính trước commit để tránh MissingGreenlet."""
    uid, email, vai = user.id, user.email, user.role
    session.add(NhatKySsoTestbank(user_id=uid, email=sso.chuan_hoa_email(email), vai=vai, jti=jti,
                                  ket_qua=ket_qua))
    await session.commit()
    log.info("sso_testbank ket_qua=%s sub=%s email=%s vai=%s jti=%s", ket_qua, uid,
             sso.chuan_hoa_email(email), vai, jti)


@router.post("/sso/testbank")
async def xin_lien_ket_testbank(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if user.role not in sso.VAI_DUOC_SSO:
        await _ghi_nhat_ky(session, user, "tu_choi_vai")
        raise HTTPException(status.HTTP_403_FORBIDDEN, MSG_CHI_THAY_CO)
    goc = (settings.testbank_web_teacher_url or "").strip()
    if not goc:
        await _ghi_nhat_ky(session, user, "chua_cau_hinh")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_CHUA_NOI)

    if not settings.sso_testbank_bat:
        # Phương án tối thiểu: không phiếu. Giáo viên tự đăng nhập Testbank bằng mật khẩu.
        await _ghi_nhat_ky(session, user, "mo_dang_nhap")
        return {"che_do": "dang_nhap", "url": sso.url_mo_testbank(goc, None)}

    try:
        khoa = sso.KhoaKy.tu_settings()
    except sso.SsoChuaCauHinh as exc:
        log.error("SSO Testbank bật nhưng chưa cấu hình được khoá: %s", exc)
        await _ghi_nhat_ky(session, user, "chua_cau_hinh")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_CHUA_NOI) from exc
    # Đọc TRƯỚC commit trong `_ghi_nhat_ky` (MissingGreenlet).
    phieu, than = sso.tao_phieu(khoa, user_id=user.id, email=user.email, ten=user.name, vai=user.role)
    await _ghi_nhat_ky(session, user, "da_cap", jti=than["jti"])
    return {"che_do": "sso", "url": sso.url_mo_testbank(goc, phieu)}


@router.get("/.well-known/jwks.json")
async def jwks() -> dict:
    try:
        return sso.jwks(sso.KhoaKy.tu_settings())
    except sso.SsoChuaCauHinh as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_CHUA_NOI) from exc
