import uuid

from app.db.models import VideoJob
from app.video import cache


def _key() -> str:
    return f"concept-{uuid.uuid4().hex[:8]}"


async def test_get_or_create_lan_dau_tao_job_queued(db_session):
    ck = _key()
    job, created = await cache.get_or_create_job(db_session, ck, "v1")
    assert created is True
    assert job.status == "QUEUED"


async def test_khong_render_trung_khi_da_co_job(db_session):
    # US-19 Scenario 4: yêu cầu thứ hai cho cùng khái niệm KHÔNG tạo job mới.
    ck = _key()
    job1, c1 = await cache.get_or_create_job(db_session, ck, "v1")
    job2, c2 = await cache.get_or_create_job(db_session, ck, "v1")
    assert c1 is True and c2 is False
    assert job1.id == job2.id


async def test_job_failed_duoc_reset_de_retry(db_session):
    ck = _key()
    job, _ = await cache.get_or_create_job(db_session, ck, "v1")
    job.status = "FAILED"
    job.error = "ffmpeg lỗi"
    await db_session.flush()

    again, created = await cache.get_or_create_job(db_session, ck, "v1")
    assert created is True                 # cho phép retry
    assert again.id == job.id
    assert again.status == "QUEUED" and again.error is None


async def test_get_done_video_chi_tra_khi_done(db_session):
    ck = _key()
    job, _ = await cache.get_or_create_job(db_session, ck, "v1")
    assert await cache.get_done_video(db_session, ck, "v1") is None  # đang QUEUED

    job.status = "DONE"
    job.video_url = "/video/files/x.mp4"
    await db_session.flush()
    hit = await cache.get_done_video(db_session, ck, "v1")
    assert hit is not None and hit.video_url.endswith("x.mp4")
