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
    # Video (Epic-09) đi queue riêng "video": worker Docker (Linux) KHÔNG có
    # công cụ media host (`say`/node/ffmpeg) nên KHÔNG được nhận task này. Chạy
    # 1 worker trên HOST: celery -A app.ingestion.celery_app worker -Q video
    task_routes={"render_video": {"queue": "video"}},
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


@celery_app.task(name="render_video")
def render_video_task(*, job_id: int) -> str | None:
    """Sinh video AI cho 1 job (Epic-09). Chạy nền, KHÔNG chặn đường chat.

    LƯU Ý VẬN HÀNH: worker này cần công cụ media của HOST (TTS `say`, node+KaTeX,
    ffmpeg) — chạy trên host, không phải trong container Linux:
        celery -A app.ingestion.celery_app worker -Q video --loglevel=info
    """
    from app.video.tasks import render_video

    return asyncio.run(render_video(job_id=job_id))
