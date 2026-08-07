"""API video AI (Epic-09): tra trạng thái job, phục vụ file mp4, và WebSocket
đẩy trạng thái khi job xong (US-16). Text trả lời KHÔNG phụ thuộc các endpoint
này — video chỉ là bổ sung."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.api.deps import get_current_user
from app.config import settings
from app.db.models import User, VideoJob
from app.db.session import async_session_factory, get_session
from app.video import cache as video_cache
from app.video import storage
from app.video.concept import is_known_concept_key

router = APIRouter(prefix="/video", tags=["video"])

_TERMINAL = {"DONE", "FAILED"}


class VideoStatus(BaseModel):
    job_id: int
    status: str
    video_url: str | None = None
    title: str | None = None
    duration_sec: float | None = None


class GenerateRequest(BaseModel):
    concept_key: str


def _to_status(job: VideoJob) -> VideoStatus:
    # Ký URL video khi trả client (bắt buộc để GET /video/files được phục vụ).
    url = security.sign_media(job.video_url) if job.video_url else None
    return VideoStatus(
        job_id=job.id, status=job.status, video_url=url,
        title=job.title, duration_sec=job.duration_sec,
    )


@router.post("/generate", response_model=VideoStatus)
async def generate_video(
    body: GenerateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> VideoStatus:
    """Học sinh bấm "Tạo video" -> tạo job + đẩy hàng đợi (on-demand). Idempotent:
    khái niệm đã có job thì tái dùng, không render trùng."""
    if not is_known_concept_key(body.concept_key, settings.sgk_version):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "concept_key không hợp lệ")

    job, created = await video_cache.get_or_create_job(
        session, body.concept_key, settings.sgk_version
    )
    await session.commit()

    if created:  # job mới (hoặc FAILED được reset) -> enqueue render
        try:
            from app.ingestion.celery_app import render_video_task

            render_video_task.delay(job_id=job.id)
        except Exception:  # noqa: BLE001 - broker down không được làm vỡ request
            pass
    return _to_status(job)


@router.get("/jobs/{job_id}", response_model=VideoStatus)
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)) -> VideoStatus:
    job = await session.scalar(select(VideoJob).where(VideoJob.id == job_id))
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy job video")
    return _to_status(job)


@router.get("/files/{name}")
async def get_file(name: str, exp: str | None = None, sig: str | None = None) -> FileResponse:
    # Chỉ phục vụ khi có chữ ký hợp lệ (chống tải trực tiếp bằng URL đoán được).
    if not security.verify_media(f"/video/files/{name}", exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Link media không hợp lệ hoặc đã hết hạn")
    path = storage.resolve_url(f"/video/files/{name}")
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media không tồn tại")
    # Storage này giữ cả mp4 lẫn ảnh minh hoạ AI -> content-type theo đuôi file,
    # không cứng video/mp4 (trả sai type làm <img> không hiện).
    return FileResponse(path, media_type=storage.media_type_for(name))


@router.websocket("/ws/{job_id}")
async def ws_job(websocket: WebSocket, job_id: int) -> None:
    """Đẩy trạng thái job tới client tới khi DONE/FAILED rồi đóng. Poll DB nhẹ
    (video là tác vụ vài giây–phút, không cần realtime mili-giây)."""
    await websocket.accept()
    try:
        last = None
        while True:
            async with async_session_factory() as session:
                job = await session.scalar(select(VideoJob).where(VideoJob.id == job_id))
            if job is None:
                await websocket.send_json({"job_id": job_id, "status": "NOT_FOUND"})
                return
            if job.status != last:
                await websocket.send_json(_to_status(job).model_dump())
                last = job.status
            if job.status in _TERMINAL:
                return
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
