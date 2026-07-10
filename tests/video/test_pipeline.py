"""Test orchestration pipeline (mock media + LLM): trạng thái job đúng, guard
chặn -> FAILED, lỗi bước bất kỳ -> FAILED (không phát hành video hỏng)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.video import pipeline
from app.video.script import Slide, Storyboard


def _job():
    return SimpleNamespace(
        id=1, concept_key="so_nguyen_to::v1", sgk_version="v1",
        status="QUEUED", video_url=None, error=None, title=None, duration_sec=None,
    )


def _mock_media(mocker):
    mocker.patch("app.video.animate.render_storyboard", return_value=40.0)
    mocker.patch("app.video.storage.save_video", return_value="/video/files/x.mp4")


async def test_pipeline_thanh_cong_job_done(mocker):
    mocker.patch.object(pipeline, "_grounded_answer",
                        mocker.AsyncMock(return_value=("Số nguyên tố có hai ước.", "src")))
    mocker.patch.object(pipeline, "generate_script", mocker.AsyncMock(return_value=Storyboard(
        tieu_de="Số nguyên tố",
        slides=[Slide(tieu_de="Định nghĩa", y_chinh=["2 ước"], cong_thuc=[], loi_thoai="Số nguyên tố...")],
    )))
    _mock_media(mocker)
    session = mocker.AsyncMock()
    job = _job()

    await pipeline.build_video_for_job(session, job)

    assert job.status == "DONE"
    assert job.video_url == "/video/files/x.mp4"
    assert job.duration_sec == 40.0


async def test_pipeline_guard_chan_thi_failed(mocker):
    mocker.patch.object(pipeline, "_grounded_answer",
                        mocker.AsyncMock(return_value=("Đáp án: $2^3=8$", "src")))
    # kịch bản sai công thức số học (cùng vế trái, vế phải khác) -> guard chặn
    mocker.patch.object(pipeline, "generate_script", mocker.AsyncMock(return_value=Storyboard(
        slides=[Slide(cong_thuc=["2^3=9"], loi_thoai="sai")],
    )))
    _mock_media(mocker)
    session = mocker.AsyncMock()
    job = _job()

    await pipeline.build_video_for_job(session, job)

    assert job.status == "FAILED"
    assert "Guard" in job.error


async def test_pipeline_loi_render_thi_failed(mocker):
    mocker.patch.object(pipeline, "_grounded_answer",
                        mocker.AsyncMock(return_value=("Số nguyên tố có hai ước.", "src")))
    mocker.patch.object(pipeline, "generate_script", mocker.AsyncMock(return_value=Storyboard(
        slides=[Slide(y_chinh=["x"], loi_thoai="ok")],
    )))
    mocker.patch("app.video.animate.render_storyboard", side_effect=RuntimeError("ffmpeg lỗi"))
    session = mocker.AsyncMock()
    job = _job()

    await pipeline.build_video_for_job(session, job)

    assert job.status == "FAILED"          # không crash, không phát hành video hỏng
    assert job.video_url is None
