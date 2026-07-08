"""Hash mật khẩu (bcrypt) + JWT. Không bao giờ lưu mật khẩu plaintext; secret
đọc từ env (settings.jwt_secret), không hardcode (xem full-system-spec mục 9).
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

_ALGORITHM = "HS256"
_TOKEN_TTL = timedelta(days=7)


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
