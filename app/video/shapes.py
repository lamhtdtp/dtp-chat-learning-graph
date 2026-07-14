"""Overlay vật thể 3D minh hoạ vào góc bảng video (Epic-09, phần hình 3D).

Clip 3D nền trong suốt (.mov, alpha) render sẵn bằng scripts/shapes_toan.py, đặt
ở app/video/assets/shapes3d/<key>.mov (đóng gói) hoặc data/shapes3d/<key>.mov
(scp lên server, ưu tiên). Mỗi khái niệm map tới 1 clip (nhiều khái niệm dùng
chung). Module này chỉ GHÉP ẢNH (Pillow) — server không cần manim.
"""
from functools import lru_cache
from pathlib import Path
import subprocess

from PIL import Image

_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "shapes3d"
_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "shapes3d"  # scp override

# slug khái niệm -> key file clip (khớp SHAPE_KEY trong scripts/shapes_toan.py)
_SLUG_TO_KEY = {
    "so_nguyen_to": "prime_cubes",
    "uoc_va_boi": "count_cubes", "uoc_chung_lon_nhat": "count_cubes",
    "boi_chung_nho_nhat": "count_cubes", "dau_hieu_chia_het": "count_cubes",
    "luy_thua": "power_cubes",
    "tap_hop": "set_spheres",
    "so_nguyen_am": "number_line", "so_thap_phan": "number_line",
    "doan_thang_trung_diem": "number_line",
    "phan_so": "fraction_bar", "ti_so_phan_tram": "fraction_bar",
    "tam_giac_deu": "tri_shape",
    "chu_vi_dien_tich": "box_prism",
    "goc": "angle_rays",
}


def _clip_path(key: str) -> Path | None:
    for d in (_DATA_DIR, _ASSET_DIR):
        p = d / f"{key}.mov"
        if p.is_file():
            return p
    return None


def _decode(path: Path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    raw = subprocess.run(
        ["ffmpeg", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True).stdout
    fs = w * h * 4
    frames = [Image.frombytes("RGBA", (w, h), raw[i * fs:(i + 1) * fs])
              for i in range(len(raw) // fs)]
    return frames, w, h


@lru_cache(maxsize=8)
def load_frames(slug: str, zone_w: int, zone_h: int):
    """Trả list RGBA frame đã crop theo alpha + scale vừa (zone_w, zone_h); None
    nếu khái niệm không có clip. Kết quả cache theo (slug, zone)."""
    key = _SLUG_TO_KEY.get(slug or "")
    if not key:
        return None
    path = _clip_path(key)
    if path is None:
        return None
    try:
        frames, w, h = _decode(path)
    except Exception:  # noqa: BLE001 - hình 3D là phụ, lỗi không được làm hỏng video
        return None
    if not frames:
        return None
    # Union bbox alpha (mẫu ~12 frame) -> crop nhất quán khi xoay -> scale vừa zone.
    ux0, uy0, ux1, uy1 = w, h, 0, 0
    for f in frames[:: max(1, len(frames) // 12)]:
        bb = f.getbbox()
        if bb:
            ux0, uy0 = min(ux0, bb[0]), min(uy0, bb[1])
            ux1, uy1 = max(ux1, bb[2]), max(uy1, bb[3])
    if ux1 <= ux0 or uy1 <= uy0:
        return None
    pad = 8
    box = (max(0, ux0 - pad), max(0, uy0 - pad), min(w, ux1 + pad), min(h, uy1 + pad))
    cw, ch = box[2] - box[0], box[3] - box[1]
    scale = min(zone_w / cw, zone_h / ch)
    size = (max(1, int(cw * scale)), max(1, int(ch * scale)))
    return [f.crop(box).resize(size) for f in frames]
