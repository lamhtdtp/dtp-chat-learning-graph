"""Khối `environment:` của service api trong docker-compose.app.yml là DANH SÁCH
TRẮNG — không có `env_file:`, image không chứa .env. Setting có trong config.py
mà không khai ở đó thì điền .env trên server cũng vô ích: container không thấy,
app im lặng chạy bằng giá trị mặc định.

Đã trả giá ba lần: CHAT_DAILY_LIMIT, TRO_LY_BAO_TRI, rồi TESTBANK_* (đề cuối kỳ
báo "chưa được kết nối với kho câu hỏi" dù .env server đã điền đủ).
"""
from pathlib import Path

import yaml

from app.config import Settings

GOC = Path(__file__).resolve().parents[2]

#: Setting PHẢI tới được container api trên server. Thêm setting mới mà người
#: vận hành cần đổi bằng .env -> thêm tên vào đây (test sẽ ép thêm vào compose).
BAT_BUOC = [
    "chat_daily_limit", "chat_max_chars", "tro_ly_bao_tri", "tro_ly_bao_tri_nhan",
    "testbank_identity_url", "testbank_content_url", "testbank_exam_url",
    "testbank_email", "testbank_password", "de_cuoi_ky_daily_limit",
]


def _env_api() -> set[str]:
    conf = yaml.safe_load((GOC / "docker-compose.app.yml").read_text())
    env = conf["services"]["api"]["environment"]
    return set(env) if isinstance(env, dict) else {e.split("=")[0] for e in env}


def test_setting_bat_buoc_co_trong_settings():
    """Gõ sai tên ở BAT_BUOC thì test dưới xanh vô nghĩa."""
    thieu = [f for f in BAT_BUOC if f not in Settings.model_fields]
    assert not thieu, f"Không có trong app/config.py: {thieu}"


def test_compose_api_chuyen_du_bien_vao_container():
    thieu = sorted(f.upper() for f in BAT_BUOC if f.upper() not in _env_api())
    assert not thieu, (
        f"docker-compose.app.yml (service api, environment:) thiếu: {thieu} — "
        "điền .env trên server cũng không tới được container.")


def test_compose_khong_con_bien_cua_tinh_nang_da_go():
    """ITEST_* là của i-Test đã gỡ: để lại là người đọc tưởng tính năng còn chạy."""
    con = sorted(k for k in _env_api() if k.startswith("ITEST_"))
    assert not con, f"Còn biến i-Test trong compose: {con}"
