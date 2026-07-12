"""Hash mật khẩu (bcrypt) + JWT. Không bao giờ lưu mật khẩu plaintext; secret
đọc từ env (settings.jwt_secret), không hardcode (xem full-system-spec mục 9).
"""

import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

_ALGORITHM = "HS256"
_TOKEN_TTL = timedelta(days=7)

# Ký URL media (video/ảnh) — thẻ <img>/<video> không gửi được header Authorization,
# nên gắn chữ ký HMAC có hạn vào query string. Cùng secret với JWT.
_MEDIA_TTL = 12 * 3600  # 12 giờ


def _media_sig(path: str, exp: int) -> str:
    msg = f"{path}:{exp}".encode()
    return hmac.new(settings.jwt_secret.encode(), msg, hashlib.sha256).hexdigest()


def sign_media(path: str, *, ttl: int = _MEDIA_TTL, now: int | None = None) -> str:
    """Trả `path?exp=<ts>&sig=<hmac>` — chỉ ai có link ký hợp lệ + chưa hết hạn
    mới tải được file. `path` là đường dẫn không kèm query (vd /video/files/x.mp4)."""
    exp = (now if now is not None else int(time.time())) + ttl
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}exp={exp}&sig={_media_sig(path, exp)}"


def verify_media(path: str, exp: str | None, sig: str | None, *, now: int | None = None) -> bool:
    """Kiểm chữ ký + hạn cho `path` (không kèm query). Sai/hết hạn -> False."""
    if not exp or not sig:
        return False
    try:
        exp_i = int(exp)
    except ValueError:
        return False
    if exp_i < (now if now is not None else int(time.time())):
        return False
    return hmac.compare_digest(_media_sig(path, exp_i), sig)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(user_id: int, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + _TOKEN_TTL}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> int:
    """Trả về user_id. Ném jwt.PyJWTError (hết hạn/sai chữ ký/hỏng) để caller
    map sang 401."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    return int(payload["sub"])
