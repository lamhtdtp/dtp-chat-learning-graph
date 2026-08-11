"""Cứu job video mồ côi (`pregenerate --requeue`).

Bối cảnh: `request_video` ghi job vào Postgres TRƯỚC rồi mới `.delay()`. Broker
hỏng thì job nằm lại QUEUED mà KHÔNG có message nào trong hàng đợi — worker bật
lại cũng không có gì để nhận, và không có beat/bộ quét nào tự tìm ra.

Test dựng theo kiểu TẬP CON, không so bằng: bộ test dùng chung DB dev nên trong
bảng luôn có sẵn job QUEUED của người khác. So bằng thì đỏ vì môi trường, không
phải vì code.
"""
import uuid

from app.db.models import VideoJob
from app.video import pregenerate


class _KhongDong:
    """`async with async_session_factory()` trong test phải dùng LẠI session của
    fixture (transaction sẽ rollback), và KHÔNG được đóng nó ở cuối khối."""

    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *exc):
        return False


def _job(status: str) -> VideoJob:
    return VideoJob(concept_key=f"free:{uuid.uuid4().hex[:10]}",
                    sgk_version="v-requeue-test", status=status)


async def _chay(db_session, mocker, jobs: dict[str, VideoJob]):
    delay = mocker.patch("app.ingestion.celery_app.render_video_task.delay")
    mocker.patch("app.video.pregenerate.async_session_factory",
                 return_value=_KhongDong(db_session))
    db_session.add_all(jobs.values())
    await db_session.flush()
    await pregenerate._requeue_orphans()
    return {c.kwargs["job_id"] for c in delay.call_args_list}


async def test_day_lai_job_dang_queued(db_session, mocker):
    jobs = {"q1": _job("QUEUED"), "q2": _job("QUEUED")}
    da_day = await _chay(db_session, mocker, jobs)
    assert {jobs["q1"].id, jobs["q2"].id} <= da_day


async def test_khong_dung_toi_job_da_xong_hay_dang_dung(db_session, mocker):
    """DONE không được đụng: `render_video` render lại VÔ ĐIỀU KIỆN, đẩy nhầm một
    job đã xong là dựng lại từ đầu — tốn tiền mô hình + TTS.
    RENDERING cũng bỏ qua: worker đang làm dở, đẩy nữa là render song song."""
    jobs = {"xong": _job("DONE"), "dang": _job("RENDERING"), "hong": _job("FAILED")}
    da_day = await _chay(db_session, mocker, jobs)
    assert {j.id for j in jobs.values()}.isdisjoint(da_day)
