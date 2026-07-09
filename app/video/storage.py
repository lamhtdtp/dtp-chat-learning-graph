"""Object storage cho video (US-18: lưu mp4, trả địa chỉ truy cập).

Dev: thư mục cục bộ (settings.video_storage_dir), phục vụ qua endpoint
/video/files/{name}. Prod: thay bằng S3/MinIO — chỉ đổi 2 hàm này, phần còn
lại của pipeline không đổi (đúng nguyên tắc object storage của kiến trúc).
"""

import shutil
from pathlib import Path

from app.config import settings

_URL_PREFIX = "/video/files"


def _dir() -> Path:
    return Path(settings.video_storage_dir)


def save_video(local_path: str | Path, name: str) -> str:
    """Đưa file mp4 vào storage, trả URL truy cập. Chỉ hàm này tạo thư mục —
    phía chỉ-đọc (api mount read-only) không được mkdir."""
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / name
    if Path(local_path).resolve() != dest.resolve():
        shutil.copyfile(local_path, dest)
    return f"{_URL_PREFIX}/{name}"


def resolve_url(url: str) -> Path | None:
    """URL -> đường dẫn file thật (chống path traversal). None nếu không hợp lệ."""
    if not url.startswith(f"{_URL_PREFIX}/"):
        return None
    name = url.removeprefix(f"{_URL_PREFIX}/")
    if "/" in name or ".." in name:
        return None
    path = _dir() / name
    return path if path.is_file() else None
