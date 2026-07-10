"""Test endpoint on-demand POST /video/generate + trạng thái job."""

import uuid
from types import SimpleNamespace

import app.api.video as video_api


async def _auth(client) -> dict:
    email = f"vid-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_generate_thieu_token_401(client):
    r = await client.post("/video/generate", json={"concept_key": "so_nguyen_to::cung_kham_pha_2024"})
    assert r.status_code == 401


async def test_generate_concept_key_khong_hop_le_400(client):
    h = await _auth(client)
    r = await client.post("/video/generate", json={"concept_key": "bịa::x"}, headers=h)
    assert r.status_code == 400


async def test_generate_tao_job_va_enqueue(client, mocker):
    h = await _auth(client)
    mocker.patch("app.api.video.video_cache.get_or_create_job", mocker.AsyncMock(
        return_value=(SimpleNamespace(id=5, status="QUEUED", video_url=None, title=None, duration_sec=None), True)))
    delay = mocker.patch("app.ingestion.celery_app.render_video_task.delay")

    r = await client.post("/video/generate",
                          json={"concept_key": "so_nguyen_to::cung_kham_pha_2024"}, headers=h)

    assert r.status_code == 200
    assert r.json()["status"] == "QUEUED"
    delay.assert_called_once_with(job_id=5)


async def test_generate_idempotent_khong_enqueue_lai(client, mocker):
    # Job đã tồn tại (created=False) -> không enqueue render trùng.
    h = await _auth(client)
    mocker.patch("app.api.video.video_cache.get_or_create_job", mocker.AsyncMock(
        return_value=(SimpleNamespace(id=5, status="RENDERING", video_url=None, title=None, duration_sec=None), False)))
    delay = mocker.patch("app.ingestion.celery_app.render_video_task.delay")

    r = await client.post("/video/generate",
                          json={"concept_key": "so_nguyen_to::cung_kham_pha_2024"}, headers=h)

    assert r.status_code == 200
    delay.assert_not_called()
