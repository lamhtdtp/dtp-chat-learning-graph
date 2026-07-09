"""CLI ingest SGK. OCR tốn token -> luôn chạy thử vài trang trước khi chạy hết.

Ví dụ:
    python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8
    python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1        # cả tập, chạy inline
    python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1 --queue  # đẩy vào Celery

Mặc định chạy INLINE (tiện dev/pilot). `--queue` đẩy vào Celery worker (đúng
nguyên tắc vàng #2: nạp cả sách chạy nền, không chặn chat). Cần worker chạy:
    celery -A app.ingestion.celery_app worker --loglevel=info
"""

import argparse
import asyncio

from app.ingestion.tasks import ingest_book


def _parse_pages(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            pages.extend(range(int(lo), int(hi) + 1))
        else:
            pages.append(int(part))
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SGK vào Qdrant")
    parser.add_argument("--mon", default="toan")
    parser.add_argument("--khoi", default="lop_6")
    parser.add_argument("--tap", type=int, required=True)
    parser.add_argument("--sach", required=True, help="id sách, vd cung_kham_pha_tap_1")
    parser.add_argument("--pages", help="vd '5-8' hoặc '5,6,10'; bỏ trống = cả tập")
    parser.add_argument("--force-ocr", action="store_true", help="OCR lại, bỏ qua cache")
    parser.add_argument("--queue", action="store_true", help="đẩy vào Celery worker thay vì chạy inline")
    args = parser.parse_args()

    pages = _parse_pages(args.pages)
    kwargs = dict(mon=args.mon, khoi=args.khoi, tap=args.tap, sach=args.sach,
                  pages=pages, force_ocr=args.force_ocr)

    if args.queue:
        from app.ingestion.celery_app import ingest_book_task

        result = ingest_book_task.delay(**kwargs)
        print(f"Đã đẩy vào hàng đợi Celery, task id: {result.id}")
        return

    n = asyncio.run(ingest_book(**kwargs))
    print(f"Đã ghi {n} chunk vào Qdrant.")


if __name__ == "__main__":
    main()
