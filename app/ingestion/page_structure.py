"""Suy chương/bài cho từng trang SGK.

Ảnh trang đặt tên tuần tự theo số trang (1.png, 2.png, ...), KHÔNG mang metadata
chương/bài. Sau khi OCR ra markdown, ta nhận diện heading "Chương N" / "Bài N"
xuất hiện trên trang rồi **forward-fill theo thứ tự trang** — trang không có
heading kế thừa chương/bài của trang gần nhất phía trước (cùng tư duy forward-
fill như matrix_parser nhưng theo chiều trang). Đây là logic deterministic sau
khi đã có markdown, nên TDD được (xem tests/ingestion/test_page_structure.py).
"""

import re

from pydantic import BaseModel

# Anchor trên TỪ "Chương"/"Bài" nên "## 1. TẬP HỢP", "HOẠT ĐỘNG 1", "VÍ DỤ 2"
# (có số nhưng không có từ này) không bị nhận nhầm là heading chương/bài.
# Cho phép: markdown # tuỳ ý ở đầu, dấu ":" hoặc khoảng trắng ngăn số với tên.
_CHUONG_RE = re.compile(r"^\s*#*\s*ch[uư]ơng\s+(\d+)\s*[:.]?\s*(.*)$", re.IGNORECASE)
_BAI_RE = re.compile(r"^\s*#*\s*bài\s+(\d+)\s*[:.]?\s*(.*)$", re.IGNORECASE)


def _detect(pattern: re.Pattern, markdown: str) -> tuple[int, str] | None:
    for line in markdown.splitlines():
        m = pattern.match(line)
        if m:
            return int(m.group(1)), m.group(2).strip()
    return None


def detect_chuong(markdown: str) -> tuple[int, str] | None:
    return _detect(_CHUONG_RE, markdown)


def detect_bai(markdown: str) -> tuple[int, str] | None:
    return _detect(_BAI_RE, markdown)


class PageStructure(BaseModel):
    page_no: int
    chuong_so: int | None
    chuong_ten: str | None
    bai_so: int | None
    bai_ten: str | None


def gan_chuong_bai_theo_trang(pages: list[tuple[int, str]]) -> list[PageStructure]:
    """`pages` là danh sách (page_no, markdown) THEO ĐÚNG THỨ TỰ TRANG. Trả về
    mỗi trang 1 PageStructure đã forward-fill chương/bài. Trang trước heading
    đầu tiên (bìa, mục lục) có chương/bài = None."""
    cur_chuong: tuple[int, str] | None = None
    cur_bai: tuple[int, str] | None = None
    records: list[PageStructure] = []

    for page_no, markdown in pages:
        chuong = detect_chuong(markdown)
        if chuong is not None and (cur_chuong is None or chuong[0] != cur_chuong[0]):
            # So sánh theo SỐ chương, không theo cả (số, tên): chân trang các
            # trang nội dung in "Chương 1 - Số tự nhiên" cũng khớp regex nhưng
            # tên hơi khác opener ("- Số tự nhiên") — nếu so cả tuple sẽ tưởng
            # nhầm là chương mới và xoá oan bài đang học (bug gặp thật ở pilot).
            # Sang chương mới thật thì xoá bài cũ: bài đánh số LẠI theo từng
            # chương (Chương 2 bắt đầu "Bài 1" — đã kiểm chứng trên sách thật).
            cur_chuong = chuong
            cur_bai = None
        bai = detect_bai(markdown)
        if bai is not None:
            cur_bai = bai

        records.append(
            PageStructure(
                page_no=page_no,
                chuong_so=cur_chuong[0] if cur_chuong else None,
                chuong_ten=cur_chuong[1] if cur_chuong else None,
                bai_so=cur_bai[0] if cur_bai else None,
                bai_ten=cur_bai[1] if cur_bai else None,
            )
        )
    return records
