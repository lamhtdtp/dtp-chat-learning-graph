"""Hàm async chạy job video (dùng session DB riêng, commit khi xong). Celery
task đồng bộ (app/ingestion/celery_app.py) bọc hàm này bằng asyncio.run.

Tách khỏi celery_app để test được mà không cần Celery, và để chạy trực tiếp
trên host (worker Docker Linux không có `say`/node — TTS/KaTeX là công cụ host).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import VideoJob
from app.video.pipeline import build_video_for_job


async def render_video(job_id: int) -> str | None:
    """Chạy pipeline cho job_id, commit. Trả video_url nếu DONE, None nếu FAILED.

    Tạo engine RIÊNG trong hàm (không dùng engine module dùng chung): Celery bọc
    hàm này bằng asyncio.run -> mỗi task 1 event loop mới; asyncpg pool của engine
    dùng chung gắn với loop cũ sẽ lỗi 'attached to a different loop'. Engine cục
    bộ gắn đúng loop đang chạy, dispose khi xong."""
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            job = await session.scalar(select(VideoJob).where(VideoJob.id == job_id))
            if job is None:
                return None
            await build_video_for_job(session, job)
            await session.commit()
            return job.video_url
    finally:
        await engine.dispose()
