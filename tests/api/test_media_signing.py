"""Bảo vệ media bằng URL ký (HMAC có hạn): video + ảnh SGK chỉ tải được khi có
chữ ký hợp lệ, chưa hết hạn."""

import uuid

from app.api import security


# ── Unit: sign/verify ──
def test_sign_verify_roundtrip():
    signed = security.sign_media("/video/files/x.mp4", now=1000, ttl=3600)
    exp = signed.split("exp=")[1].split("&")[0]
    sig = signed.split("sig=")[1]
    assert security.verify_media("/video/files/x.mp4", exp, sig, now=2000) is True   # còn hạn
    assert security.verify_media("/video/files/x.mp4", exp, sig, now=99999) is False  # hết hạn


def test_verify_tu_choi_khi_thieu_hoac_sai_chu_ky():
    assert security.verify_media("/video/files/x.mp4", None, None) is False
    signed = security.sign_media("/books/pages/1/6", now=1000)
    exp = signed.split("exp=")[1].split("&")[0]
    assert security.verify_media("/books/pages/1/6", exp, "deadbeef", now=1500) is False   # sig sai
    # đổi path -> chữ ký không khớp
    sig = signed.split("sig=")[1]
    assert security.verify_media("/books/pages/1/7", exp, sig, now=1500) is False


# ── API ──
async def _auth(client) -> dict:
    email = f"media-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_video_file_khong_chu_ky_bi_403(client):
    r = await client.get("/video/files/x.mp4")
    assert r.status_code == 403


async def test_video_file_chu_ky_hop_le_duoc_phuc_vu(client, mocker, tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"\x00\x00fake-mp4")
    mocker.patch("app.api.video.storage.resolve_url", return_value=f)
    signed = security.sign_media("/video/files/x.mp4")   # /video/files/x.mp4?exp=..&sig=..

    r = await client.get(signed)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("video/mp4")


async def test_book_page_khong_chu_ky_bi_403(client):
    r = await client.get("/books/pages/1/6")
    assert r.status_code == 403


async def test_book_pages_url_can_auth_va_tra_link_ky(client):
    # thiếu token -> 401
    assert (await client.get("/books/pages-url/1/6")).status_code == 401
    # có token -> trả URL đã ký
    h = await _auth(client)
    r = await client.get("/books/pages-url/1/6", headers=h)
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("/books/pages/1/6?") and "sig=" in url
