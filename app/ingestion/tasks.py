"""Orchestration luồng ingest offline: ảnh trang -> OCR -> chương/bài ->
chunk -> embed -> Qdrant.

Hiện là hàm async chạy trực tiếp (qua CLI). Bọc Celery task sau khi có broker
Redis cấu hình cho worker — chữ ký `ingest_book` giữ nguyên để bọc không phải
sửa. Chạy thử vài trang trước khi chạy cả sách (OCR tốn token — xem CLI --pages).
"""

from pathlib import Path

from app.ingestion.chunking import Chunk, chunk_page
from app.ingestion.loaders.vision_page_loader import load_or_ocr_page
from app.ingestion.page_structure import gan_chuong_bai_theo_trang
from app.ingestion.qdrant_store import upsert_chunks

DATA_ROOT = Path("data/books")
CACHE_ROOT = Path("data_processed")

# mon -> thư mục ảnh dưới data/books/. Thêm môn mới = thêm 1 dòng ở đây.
_SUBJECT_FOLDER = {
    "toan": "maths", "maths": "maths",
    "tieng_anh": "english", "english": "english", "anh": "english",
}


def _book_dir(mon: str, khoi: str, tap: int) -> Path:
    """Thư mục ảnh trang của (môn, khối, tập). Hỗ trợ 2 kiểu bố cục:
    - có thư mục tập:  data/books/<folder>/<khối>/<tap>/*.png  (vd Toán: maths/6/1)
    - phẳng (1 tập):   data/books/<folder>/<khối>/*.png         (vd Anh: english/6)
    """
    folder = _SUBJECT_FOLDER.get(mon, mon)
    base = DATA_ROOT / folder / khoi.removeprefix("lop_")
    sub = base / str(tap)
    return sub if sub.is_dir() else base


def _page_numbers(book_dir: Path) -> list[int]:
    return sorted(int(p.stem) for p in book_dir.glob("*.png"))


async def build_chunks_for_book(
    *,
    mon: str,
    khoi: str,
    sach: str,
    tap: int,
    book_dir: Path,
    cache_dir: Path,
    pages: list[int] | None = None,
    force_ocr: bool = False,
) -> list[Chunk]:
    """OCR + suy chương/bài + chunk cho các trang chỉ định (mặc định: tất cả).
    KHÔNG ghi Qdrant — tách để test/preview được trước khi tốn ghi vector."""
    all_pages = _page_numbers(book_dir)
    target = pages if pages is not None else all_pages

    # Suy chương/bài PHẢI theo đúng thứ tự toàn bộ trang đã OCR (forward-fill);
    # nếu chỉ OCR một dải trang giữa sách, chương/bài có thể thiếu ngữ cảnh
    # trang mở đầu — chấp nhận cho pilot, ghi rõ khi chạy dải hẹp.
    pairs = []
    for page_no in target:
        md = await load_or_ocr_page(
            book_dir / f"{page_no}.png", cache_dir / f"{page_no}.md", force=force_ocr, mon=mon
        )
        pairs.append((page_no, md))

    structures = {s.page_no: s for s in gan_chuong_bai_theo_trang(pairs)}

    chunks: list[Chunk] = []
    for page_no, md in pairs:
        chunks.extend(
            chunk_page(md, structures[page_no], mon=mon, khoi=khoi, sach=sach, tap=tap)
        )
    return chunks


async def ingest_book(
    *,
    mon: str = "toan",
    khoi: str = "lop_6",
    tap: int,
    sach: str,
    pages: list[int] | None = None,
    force_ocr: bool = False,
) -> int:
    """Chạy trọn luồng cho 1 tập sách -> ghi Qdrant. Trả về số chunk đã ghi."""
    book_dir = _book_dir(mon, khoi, tap)
    # Cache OCR tách theo môn để Anh/Toán không đè nhau (trước chỉ theo tap).
    cache_dir = CACHE_ROOT / _SUBJECT_FOLDER.get(mon, mon) / f"tap{tap}"
    chunks = await build_chunks_for_book(
        mon=mon, khoi=khoi, sach=sach, tap=tap,
        book_dir=book_dir, cache_dir=cache_dir, pages=pages, force_ocr=force_ocr,
    )
    return await upsert_chunks(chunks)
