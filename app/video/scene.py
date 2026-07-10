"""Sinh ảnh NỀN CẢNH cho video kiểu explainer AI (nhân vật + lớp học), giống
phong cách tham chiếu người dùng gửi. Ảnh do model ảnh (gpt-image-1 qua
VNGCloud) sinh; công thức + phụ đề overlay sắc nét sau (app/video/animate.py).

Bố cục cố ý: giáo viên bên PHẢI, chừa mảng trống bên TRÁI để overlay bảng nội
dung — không nhờ AI viết chữ (chữ AI hay sai/méo), ta tự vẽ cho đúng SGK.
"""

import io
import re
import unicodedata
from pathlib import Path

from PIL import Image

from app.llm import gateway

_W, _H = 1280, 720

# Ảnh nền cache trên đĩa: sinh 1 lần / khái niệm rồi tái dùng — vừa tiết kiệm
# quota (VNGCloud ~50 req/ngày), vừa để có ảnh lùi khi API lỗi. `assets/
# default_scene.png` là ảnh mặc định đóng gói sẵn trong repo (luôn có nhân vật),
# `data/scenes/` là cache runtime (host — worker video chạy trên host).
_ASSET_DIR = Path(__file__).resolve().parent / "assets"
_DEFAULT_SCENE = _ASSET_DIR / "default_scene.png"
_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "scenes"

_PROMPT = (
    "Pixar-style 3D animation still, a friendly young Vietnamese female teacher "
    "in a white lab coat standing on the RIGHT side of the frame, smiling warmly. "
    "A large bright classroom with a big empty whiteboard, wooden desks, a window "
    "with soft warm morning sunlight, plants, cozy cinematic lighting. The LEFT "
    "half of the frame is mostly empty background space (wall/whiteboard), "
    "uncluttered, leaving room for text overlay. High quality, clean, no text, "
    "no letters, no writing anywhere in the image."
)


def scene_prompt(title: str) -> str:
    """Prompt cảnh cho 1 bài học. Chủ đề ảnh hưởng nhẹ tông màu, nhưng bố cục
    (giáo viên phải, trống trái) giữ nguyên để overlay ổn định."""
    return f"{_PROMPT} Subject context: dạy Toán lớp 6 — {title}."


def _fit(img: Image.Image) -> Image.Image:
    """Cắt/khớp ảnh về đúng 1280x720 (giữ tỉ lệ, crop giữa)."""
    img = img.convert("RGB")
    scale = max(_W / img.width, _H / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)))
    left = (resized.width - _W) // 2
    top = (resized.height - _H) // 2
    return resized.crop((left, top, left + _W, top + _H))


def _slug(title: str) -> str:
    """Tên file cache từ tiêu đề (bỏ dấu, chỉ giữ [a-z0-9_])."""
    norm = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", norm.lower())).strip("_") or "scene"


def _fallback_scene() -> Image.Image | None:
    """Ảnh lùi khi sinh mới lỗi: tái dùng 1 ảnh đã cache, hoặc ảnh mặc định đóng
    gói. Nhờ vậy nhân vật vẫn xuất hiện thay vì tụt về nền gradient trống."""
    for p in sorted(_CACHE_DIR.glob("*.png")):
        return _fit(Image.open(p))
    if _DEFAULT_SCENE.exists():
        return _fit(Image.open(_DEFAULT_SCENE))
    return None


async def fetch_scene(title: str) -> Image.Image:
    """Trả ảnh nền cảnh cho bài học (giáo viên + lớp học). Ưu tiên cache trên đĩa;
    chưa có thì sinh mới + lưu cache. API lỗi/hết quota -> dùng ảnh lùi (cache cũ
    hoặc ảnh mặc định) để nhân vật vẫn xuất hiện. Chỉ raise nếu KHÔNG có ảnh lùi."""
    cached = _CACHE_DIR / f"{_slug(title)}.png"
    if cached.exists():
        return _fit(Image.open(cached))
    try:
        raw = await gateway.generate_image(scene_prompt(title), size="1536x1024")
        img = _fit(Image.open(io.BytesIO(raw)))
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        img.save(cached, "PNG")
        return img
    except Exception:  # noqa: BLE001 - hết quota/API lỗi -> ảnh lùi, đừng mất nhân vật
        fallback = _fallback_scene()
        if fallback is not None:
            return fallback
        raise
