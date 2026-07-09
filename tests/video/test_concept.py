import pytest

from app.video.concept import concept_key, detect_concept


@pytest.mark.parametrize("text,slug", [
    ("Số nguyên tố là gì ạ?", "so_nguyen_to"),
    ("Thế nào là số nguyên tố?", "so_nguyen_to"),
    ("Giải thích ƯCLN giúp em", "uoc_chung_lon_nhat"),
    ("bội chung nhỏ nhất là gì", "boi_chung_nho_nhat"),
    ("Cách viết một tập hợp?", "tap_hop"),
    ("dấu hiệu chia hết cho 3", "dau_hieu_chia_het"),
])
def test_detect_concept_khop_khai_niem(text, slug):
    assert detect_concept(text) == slug


def test_cau_hoi_khac_chu_cung_khai_niem_ra_cung_key():
    # Điều kiện cốt lõi để dùng lại video giữa học sinh (US-19 Scenario 1).
    a = concept_key("Số nguyên tố là gì?", "v1")
    b = concept_key("Cho em hỏi thế nào là số nguyên tố", "v1")
    assert a == b == "so_nguyen_to::v1"


def test_key_gom_sgk_version():
    # Đổi phiên bản SGK -> key khác -> cache miss (US-19 Scenario 2).
    assert concept_key("số nguyên tố", "v1") != concept_key("số nguyên tố", "v2")


def test_cau_khong_ro_khai_niem_tra_none():
    # Gating: câu vụn không sinh video.
    assert detect_concept("Chào bạn nhé") is None
    assert concept_key("ok cảm ơn", "v1") is None
