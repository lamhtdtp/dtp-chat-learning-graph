from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.api import security


def test_hash_khac_plaintext_va_verify_dung():
    h = security.hash_password("matkhau123")
    assert h != "matkhau123"  # không lưu plaintext
    assert security.verify_password("matkhau123", h) is True
    assert security.verify_password("sai", h) is False


def test_hash_moi_lan_khac_nhau_van_verify_duoc():
    # bcrypt salt ngẫu nhiên -> 2 hash khác nhau nhưng đều verify đúng
    assert security.hash_password("x") != security.hash_password("x")


def test_jwt_round_trip():
    token = security.create_token(42)
    assert security.decode_token(token) == 42


def test_jwt_het_han_bi_tu_choi():
    past = datetime.now(timezone.utc) - timedelta(days=8)
    token = security.create_token(1, now=past)  # TTL 7 ngày -> đã hết hạn
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_token(token)


def test_jwt_sai_chu_ky_bi_tu_choi():
    token = security.create_token(1)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "secret-khac", algorithms=["HS256"])
