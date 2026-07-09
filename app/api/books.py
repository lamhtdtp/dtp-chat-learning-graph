"""Serve ảnh trang SGK gốc (để UI mở modal "xem trang sách" khi bấm citation).

Ảnh nằm trên đĩa: data/books/maths/6/{tap}/{page}.png (Toán lớp 6). Endpoint
KHÔNG yêu cầu auth để dùng trực tiếp trong thẻ <img> (thẻ img không gửi được
header Authorization). Chỉ nhận tham số số nguyên + kiểm file nằm đúng thư mục
-> không có path traversal.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(prefix="/books", tags=["books"])

# Hiện chỉ có Toán lớp 6; mở rộng mon/khoi khi có sách khác.
_BOOK_ROOT = Path("data/books/maths/6").resolve()


@router.get("/pages/{tap}/{page}")
async def get_page_image(tap: int, page: int) -> FileResponse:
    if tap not in (1, 2) or page < 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trang không hợp lệ")
    path = (_BOOK_ROOT / str(tap) / f"{page}.png").resolve()
    # chặn path traversal: file phải nằm trong _BOOK_ROOT
    if _BOOK_ROOT not in path.parents or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy trang")
    return FileResponse(path, media_type="image/png")
