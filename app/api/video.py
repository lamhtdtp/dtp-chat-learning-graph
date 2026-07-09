"""API video AI (Epic-09): tra trạng thái job, phục vụ file mp4, và WebSocket
đẩy trạng thái khi job xong (US-16). Text trả lời KHÔNG phụ thuộc các endpoint
này — video chỉ là bổ sung."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VideoJob
from app.db.session import async_session_factory, get_session
from app.video import storage

router = APIRouter(prefix="/video", tags=["video"])

_TERMINAL = {"DONE", "FAILED"}


class VideoStatus(BaseModel):
    job_id: int
    status: str
    video_url: str | None = None
    title: str | None = None
    duration_sec: float | None = None


def _to_status(job: VideoJob) -> VideoStatus:
    return VideoStatus(
        job_id=job.id, status=job.status, video_url=job.video_url,
        title=job.title, duration_sec=job.duration_sec,
    )


@router.get("/jobs/{job_id}", response_model=VideoStatus)
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)) -> VideoStatus:
    job = await session.scalar(select(VideoJob).where(VideoJob.id == job_id))
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy job video")
    return _to_status(job)


@router.get("/files/{name}")
async def get_file(name: str) -> FileResponse:
    path = storage.resolve_url(f"/video/files/{name}")
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video không tồn tại")
    return FileResponse(path, media_type="video/mp4")


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
