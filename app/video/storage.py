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


def save_image(data: bytes, name: str) -> str:
    """Ghi ảnh (bytes từ gateway.generate_image) vào CÙNG storage với video, trả URL.

    Dùng chung thư mục + chung prefix /video/files là cố ý: chữ ký media
    (api.security.sign_media) và bộ lọc URL nội bộ ở lessons._sign_media đều nhận
    diện theo prefix này, nên ảnh đi qua đúng đường bảo mật đã có mà không phải
    thêm route/nginx/ký mới. Đổi giá lại: tên "video/files" giờ hơi sai nghĩa.
    """
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(data)
    return f"{_URL_PREFIX}/{name}"


# Content-type theo đuôi file — /video/files phục vụ cả mp4 lẫn ảnh sinh bởi AI.
MEDIA_TYPES = {
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
}


def media_type_for(name: str) -> str:
    return MEDIA_TYPES.get(Path(name).suffix.lower(), "application/octet-stream")


def resolve_url(url: str) -> Path | None:
    """URL -> đường dẫn file thật (chống path traversal). None nếu không hợp lệ."""
    if not url.startswith(f"{_URL_PREFIX}/"):
        return None
    name = url.removeprefix(f"{_URL_PREFIX}/")
    if "/" in name or ".." in name:
        return None
    path = _dir() / name
    return path if path.is_file() else None
