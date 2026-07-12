"""Serve ảnh trang SGK gốc (để UI mở modal "xem trang sách" khi bấm citation).

Ảnh nằm trên đĩa: data/books/maths/6/{tap}/{page}.png (Toán lớp 6).

Bảo vệ: thẻ <img> không gửi được header Authorization, nên dùng URL KÝ (HMAC có
hạn). Client (đã đăng nhập) gọi GET /books/pages-url/{tap}/{page} bằng Bearer để
lấy link ký, rồi gán vào <img>. GET /books/pages/... chỉ phục vụ khi chữ ký hợp
lệ + chưa hết hạn -> không tải được bằng URL đoán mò. Vẫn chặn path traversal.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api import security
from app.api.deps import get_current_user
from app.db.models import User

router = APIRouter(prefix="/books", tags=["books"])

# Hiện chỉ có Toán lớp 6; mở rộng mon/khoi khi có sách khác.
_BOOK_ROOT = Path("data/books/maths/6").resolve()


@router.get("/pages-url/{tap}/{page}")
async def get_page_url(tap: int, page: int, user: User = Depends(get_current_user)) -> dict:
    """Cấp URL ký (có hạn) cho 1 trang SGK — chỉ user đã đăng nhập. UI gán vào <img>."""
    if tap not in (1, 2) or page < 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trang không hợp lệ")
    return {"url": security.sign_media(f"/books/pages/{tap}/{page}")}


@router.get("/pages/{tap}/{page}")
async def get_page_image(
    tap: int, page: int, exp: str | None = None, sig: str | None = None
) -> FileResponse:
    if not security.verify_media(f"/books/pages/{tap}/{page}", exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Link ảnh không hợp lệ hoặc đã hết hạn")
    if tap not in (1, 2) or page < 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trang không hợp lệ")
    path = (_BOOK_ROOT / str(tap) / f"{page}.png").resolve()
    # chặn path traversal: file phải nằm trong _BOOK_ROOT
    if _BOOK_ROOT not in path.parents or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy trang")
    return FileResponse(path, media_type="image/png")
