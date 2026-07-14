"""Pre-generate video cho các khái niệm trọng tâm (US-19 Scenario 3).

Sinh sẵn (nền) video cho mọi khái niệm trong CONCEPT_QUERY -> phần lớn câu hỏi
của học sinh về sau là CACHE HIT, hiện video ngay, không phải chờ.

Dùng:
    # enqueue tất cả cho worker video (host) dựng nền — KHÔNG chặn:
    python -m app.video.pregenerate
    # chỉ 1 môn (vd chỉ Toán, bỏ Tiếng Anh):
    python -m app.video.pregenerate --mon toan
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
from app.video.concept import CONCEPT_MON, CONCEPT_QUERY
from app.video.pipeline import build_video_for_job


def _slugs(mon: str | None) -> list[str]:
    """Danh sách slug cần sinh; lọc theo môn nếu có (`toan`/`tieng_anh`)."""
    return [s for s in CONCEPT_QUERY if mon is None or CONCEPT_MON.get(s) == mon]


async def _enqueue_all(mon: str | None = None) -> int:
    """Tạo job (idempotent) + đẩy hàng đợi cho khái niệm (đã lọc môn). Trả số job."""
    from app.ingestion.celery_app import render_video_task

    pushed = 0
    async with async_session_factory() as session:
        for slug in _slugs(mon):
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


async def _inline_all(mon: str | None = None) -> None:
    """Dựng ngay tại chỗ (tuần tự, đã lọc môn) — khi không chạy worker/broker."""
    for slug in _slugs(mon):
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
    ap.add_argument("--mon", choices=["toan", "tieng_anh"], default=None,
                    help="chỉ sinh cho môn này (mặc định: tất cả)")
    args = ap.parse_args()
    asyncio.run(_inline_all(args.mon) if args.inline else _enqueue_all(args.mon))


if __name__ == "__main__":
    main()
