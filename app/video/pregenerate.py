"""Pre-generate video cho các khái niệm trọng tâm (US-19 Scenario 3).

Sinh sẵn (nền) video cho mọi khái niệm trong CONCEPT_QUERY -> phần lớn câu hỏi
của học sinh về sau là CACHE HIT, hiện video ngay, không phải chờ.

Dùng:
    # enqueue tất cả cho worker video (host) dựng nền — KHÔNG chặn:
    python -m app.video.pregenerate
    # chỉ 1 môn (vd chỉ Toán, bỏ Tiếng Anh):
    python -m app.video.pregenerate --mon toan
    # RENDER ĐÈ cả video đã DONE (vd làm mới sau khi thêm hình 3D):
    python -m app.video.pregenerate --mon toan --force
    # hoặc dựng ngay tại chỗ (đồng bộ, không cần worker/broker):
    python -m app.video.pregenerate --inline
    # CỨU HỘ: đẩy lại mọi job đang QUEUED (broker chết lúc tạo -> job mồ côi):
    python -m app.video.pregenerate --requeue
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


def _reset(job) -> None:
    """Đưa job về QUEUED để render ĐÈ (xoá video/lỗi cũ) — dùng khi --force."""
    job.status = cache.QUEUED
    job.error = None
    job.video_url = None


async def _enqueue_all(mon: str | None = None, force: bool = False) -> int:
    """Tạo job + đẩy hàng đợi cho khái niệm (đã lọc môn). force=True: render ĐÈ
    cả job đã DONE. Trả số job đã đẩy."""
    from app.ingestion.celery_app import render_video_task

    pushed = 0
    async with async_session_factory() as session:
        for slug in _slugs(mon):
            ck = f"{slug}::{settings.sgk_version}"
            job, created = await cache.get_or_create_job(session, ck, settings.sgk_version)
            if not created and force:  # đã có -> ép về QUEUED để dựng lại
                _reset(job)
                created = True
            await session.commit()
            if created:
                render_video_task.delay(job_id=job.id)
                pushed += 1
                print(f"  enqueue {slug} (job {job.id})" + (" [render đè]" if force else ""))
            else:
                print(f"  bỏ qua {slug} (đã có job {job.id}, {job.status})")
    print(f"Đã đẩy {pushed} job video.")
    return pushed


async def _requeue_orphans() -> int:
    """Đẩy lại MỌI job đang QUEUED — cứu job mồ côi khi broker chết lúc tạo.

    Vì sao cần: `request_video`/`/video/generate` ghi job vào Postgres TRƯỚC rồi
    mới `.delay()`. Broker hỏng (vd Redis bật mật khẩu mà REDIS_URL chưa có) thì
    job nằm lại QUEUED nhưng KHÔNG có message nào trong hàng đợi — worker bật lại
    cũng không có gì để nhận, và không có beat/bộ quét nào tự tìm ra. Không có
    lệnh này thì mỗi lần broker chập là mất vĩnh viễn ngần ấy video, âm thầm.

    Phạm vi: CHỈ job đang QUEUED. Job DONE không bị đụng tới — quan trọng, vì
    `render_video` render lại vô điều kiện chứ không tự bỏ qua job đã xong.
    Job kẹt ở RENDERING (worker chết giữa chừng) cũng KHÔNG được cứu ở đây; muốn
    dựng lại thì đặt tay về QUEUED rồi chạy lệnh này.

    Chạy lại nhiều lần: job còn QUEUED sẽ bị đẩy trùng message -> render hai lần,
    tốn công chứ không hỏng dữ liệu (cùng ghi vào một dòng job)."""
    from app.ingestion.celery_app import render_video_task

    async with async_session_factory() as session:
        jobs = list(await session.scalars(
            select(VideoJob).where(VideoJob.status == cache.QUEUED).order_by(VideoJob.id)))
        ids = [(j.id, j.concept_key) for j in jobs]   # lấy trước khi rời session

    if not ids:
        print("Không có job QUEUED nào — không cần đẩy lại.")
        return 0
    for jid, ck in ids:
        render_video_task.delay(job_id=jid)
        print(f"  đẩy lại job {jid} ({ck[:40]})")
    print(f"Đã đẩy lại {len(ids)} job. Nhớ worker queue 'video' phải đang chạy trên HOST.")
    return len(ids)


async def _inline_all(mon: str | None = None, force: bool = False) -> None:
    """Dựng ngay tại chỗ (tuần tự, đã lọc môn). force=True: dựng lại cả job DONE."""
    for slug in _slugs(mon):
        ck = f"{slug}::{settings.sgk_version}"
        async with async_session_factory() as session:
            if not force and await cache.get_done_video(session, ck, settings.sgk_version) is not None:
                print(f"  {slug}: đã có (bỏ qua)")
                continue
            job, _ = await cache.get_or_create_job(session, ck, settings.sgk_version)
            if force:
                _reset(job)
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
    ap.add_argument("--force", action="store_true",
                    help="render ĐÈ cả video đã DONE (làm mới, vd sau khi thêm 3D)")
    ap.add_argument("--requeue", action="store_true",
                    help="đẩy lại mọi job đang QUEUED (cứu job mồ côi khi broker chết lúc tạo)")
    args = ap.parse_args()
    if args.requeue:
        asyncio.run(_requeue_orphans())
        return
    asyncio.run(_inline_all(args.mon, args.force) if args.inline
                else _enqueue_all(args.mon, args.force))


if __name__ == "__main__":
    main()
