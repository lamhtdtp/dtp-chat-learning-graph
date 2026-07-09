"""Celery app cho luồng OFFLINE (ingest sách). Nguyên tắc vàng #2: nạp sách
chạy nền qua hàng đợi, KHÔNG chặn đường phục vụ chat (nạp 1 cuốn có thể mất
phút–giờ vì OCR + embed hàng loạt).

Broker + backend dùng Redis (settings.redis_url) — cùng Redis Stack với
checkpointer/cache. Worker chạy riêng:
    celery -A app.ingestion.celery_app worker --loglevel=info
"""

import asyncio

from celery import Celery

from app.config import settings

celery_app = Celery(
    "chat_learning_ingest",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)


@celery_app.task(name="ingest_book")
def ingest_book_task(
    *,
    tap: int,
    sach: str,
    mon: str = "toan",
    khoi: str = "lop_6",
    pages: list[int] | None = None,
    force_ocr: bool = False,
) -> int:
    """Task đồng bộ bọc hàm async ingest_book (Celery worker là tiến trình sync
    -> chạy coroutine bằng asyncio.run). Trả về số chunk đã ghi Qdrant."""
    from app.ingestion.tasks import ingest_book

    return asyncio.run(
        ingest_book(mon=mon, khoi=khoi, tap=tap, sach=sach, pages=pages, force_ocr=force_ocr)
    )
