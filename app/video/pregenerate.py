"""Pre-generate video cho các khái niệm trọng tâm (US-19 Scenario 3).

Sinh sẵn (nền) video cho mọi khái niệm trong CONCEPT_QUERY -> phần lớn câu hỏi
của học sinh về sau là CACHE HIT, hiện video ngay, không phải chờ.

Dùng:
    # enqueue tất cả cho worker video (host) dựng nền — KHÔNG chặn:
    python -m app.video.pregenerate
    # hoặc dựng ngay tại chỗ (đồng bộ, không cần worker/broker):
    python -m app.video.pregenerate --inline
"""

import argparse
import asyncio

from sqlalchemy import select

from app.config import settings
from app.db.models import VideoJob
from app.db.session import async_session_factory
from app.video import cache
from app.video.concept import CONCEPT_QUERY
from app.video.pipeline import build_video_for_job


async def _enqueue_all() -> int:
    """Tạo job (idempotent) + đẩy hàng đợi cho mọi khái niệm. Trả số job đã đẩy."""
    from app.ingestion.celery_app import render_video_task

    pushed = 0
    async with async_session_factory() as session:
        for slug in CONCEPT_QUERY:
            ck = f"{slug}::{settings.sgk_version}"
            job, created = await cache.get_or_create_job(session, ck, settings.sgk_version)
            await session.commit()
            if created:  # bỏ qua khái niệm đã có/đang dựng -> không render trùng
                render_video_task.delay(job_id=job.id)
                pushed += 1
                print(f"  enqueue {slug} (job {job.id})")
            else:
                print(f"  bỏ qua {slug} (đã có job {job.id}, {job.status})")
    print(f"Đã đẩy {pushed} job video.")
    return pushed


async def _inline_all() -> None:
    """Dựng ngay tại chỗ (tuần tự) — dùng khi không chạy worker/broker."""
    for slug in CONCEPT_QUERY:
        ck = f"{slug}::{settings.sgk_version}"
        async with async_session_factory() as session:
            done = await cache.get_done_video(session, ck, settings.sgk_version)
            if done is not None:
                print(f"  {slug}: đã có (bỏ qua)")
                continue
            job, _ = await cache.get_or_create_job(session, ck, settings.sgk_version)
            await session.commit()
            jid = job.id
        async with async_session_factory() as session:
            job = await session.scalar(select(VideoJob).where(VideoJob.id == jid))
            await build_video_for_job(session, job)
            await session.commit()
            print(f"  {slug}: {job.status}"
                  + (f" -> {job.video_url}" if job.video_url else f" ({(job.error or '')[:80]})"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inline", action="store_true", help="dựng ngay, không qua hàng đợi")
    args = ap.parse_args()
    asyncio.run(_inline_all() if args.inline else _enqueue_all())


if __name__ == "__main__":
    main()
