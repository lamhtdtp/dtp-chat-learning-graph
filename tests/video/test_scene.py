"""Test ảnh nền cảnh: slug bỏ dấu, cache trên đĩa, và fallback khi API lỗi ->
vẫn có ảnh (nhân vật) thay vì mất về nền gradient."""

import pytest
from PIL import Image

from app.video import scene


def test_slug_bo_dau():
    assert scene._slug("Số nguyên âm") == "so_nguyen_am"
    assert scene._slug("Ước & Bội!!") == "uoc_boi"
    assert scene._slug("") == "scene"


async def test_cache_hit_khong_goi_api(mocker, tmp_path):
    img = Image.new("RGB", (1280, 720), (200, 210, 230))
    img.save(tmp_path / "so_nguyen_am.png")
    mocker.patch.object(scene, "_CACHE_DIR", tmp_path)
    gen = mocker.patch.object(scene.gateway, "generate_image", mocker.AsyncMock())

    out = await scene.fetch_scene("Số nguyên âm")

    assert out.size == (1280, 720)
    gen.assert_not_called()  # đã có cache -> không đốt quota


async def test_api_loi_dung_anh_lui(mocker, tmp_path):
    """Sinh mới lỗi (hết quota) nhưng có ảnh cache cũ -> tái dùng, không raise."""
    (tmp_path / "cu.png").write_bytes(_png_bytes())
    mocker.patch.object(scene, "_CACHE_DIR", tmp_path)
    mocker.patch.object(scene.gateway, "generate_image",
                        mocker.AsyncMock(side_effect=RuntimeError("429")))

    out = await scene.fetch_scene("Khái niệm mới chưa cache")

    assert out.size == (1280, 720)  # có nhân vật (ảnh lùi), không phải None


def _png_bytes() -> bytes:
    import io
    buf = io.BytesIO()
    Image.new("RGB", (1280, 720), (180, 190, 210)).save(buf, "PNG")
    return buf.getvalue()
