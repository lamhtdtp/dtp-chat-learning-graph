"""Cache video theo khái niệm + idempotency job (US-19).

1 (concept_key, sgk_version) -> tối đa 1 VideoJob. Yêu cầu video cho khái niệm
đang có job chạy KHÔNG tạo job thứ hai — chờ job hiện tại (Scenario 4). Ràng
buộc UNIQUE(concept_key, sgk_version) ở DB là chốt chặn cuối chống render trùng
kể cả khi 2 request chạy song song.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VideoJob

DONE = "DONE"
FAILED = "FAILED"
QUEUED = "QUEUED"
RENDERING = "RENDERING"
_ACTIVE = (QUEUED, RENDERING)


async def get_done_video(
    session: AsyncSession, concept_key: str, sgk_version: str
) -> VideoJob | None:
    """Video đã sẵn sàng cho khái niệm (cache hit) — None nếu chưa có/đang tạo."""
    return await session.scalar(
        select(VideoJob).filter_by(
            concept_key=concept_key, sgk_version=sgk_version, status=DONE
        )
    )


async def get_or_create_job(
    session: AsyncSession, concept_key: str, sgk_version: str
) -> tuple[VideoJob, bool]:
    """Trả (job, created). created=True nếu vừa tạo job QUEUED mới; False nếu đã
    có job (bất kỳ trạng thái) cho khái niệm này -> tái dùng, không render trùng.

    Job FAILED được reset về QUEUED để có thể retry (US-18 Scenario 4)."""
    existing = await session.scalar(
        select(VideoJob).filter_by(concept_key=concept_key, sgk_version=sgk_version)
    )
    if existing is not None:
        if existing.status == FAILED:
            existing.status = QUEUED
            existing.error = None
            await session.flush()
            return existing, True
        return existing, False

    job = VideoJob(concept_key=concept_key, sgk_version=sgk_version, status=QUEUED)
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        # Race: request khác vừa tạo job cùng khái niệm -> lấy lại của họ.
        await session.rollback()
        job = await session.scalar(
            select(VideoJob).filter_by(concept_key=concept_key, sgk_version=sgk_version)
        )
        return job, False
    return job, True
