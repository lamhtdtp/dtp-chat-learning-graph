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

DATA_ROOT = Path("data/books/maths")
CACHE_ROOT = Path("data_processed")


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
            book_dir / f"{page_no}.png", cache_dir / f"{page_no}.md", force=force_ocr
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
    book_dir = DATA_ROOT / khoi.removeprefix("lop_") / str(tap)
    cache_dir = CACHE_ROOT / f"tap{tap}"
    chunks = await build_chunks_for_book(
        mon=mon, khoi=khoi, sach=sach, tap=tap,
        book_dir=book_dir, cache_dir=cache_dir, pages=pages, force_ocr=force_ocr,
    )
    return await upsert_chunks(chunks)
