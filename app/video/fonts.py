"""Chọn font vẽ chữ (tiếng Việt + ký hiệu toán) cho video — chạy được cả macOS
(dev) lẫn Linux (container render). Lấy font ĐẦU TIÊN tồn tại trong danh sách
ứng viên; không có thì trả ứng viên đầu (Pillow sẽ tự load_default nếu mở lỗi).

Trên Linux, image video (infra/video.Dockerfile) cài `fonts-dejavu-core` (và
Noto) — DejaVu Sans phủ đủ tiếng Việt.
"""

from pathlib import Path

_CANDIDATES = [
    "/Library/Fonts/Arial Unicode.ttf",                        # macOS (dev)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",         # Debian/Ubuntu: fonts-dejavu-core
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",     # fonts-noto-core
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _resolve() -> str:
    for p in _CANDIDATES:
        if Path(p).exists():
            return p
    return _CANDIDATES[0]


FONT_PATH = _resolve()
