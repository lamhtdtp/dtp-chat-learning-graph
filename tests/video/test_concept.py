import pytest

from app.video.concept import (
    concept_key, decode_free_slug, detect_concept, free_concept_key,
    is_known_concept_key, is_video_request, topic_from_request,
)


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


def test_detect_concept_theo_mon():
    # Khái niệm Tiếng Anh chỉ khớp khi mon=tieng_anh; không lẫn sang Toán.
    assert detect_concept("thì hiện tại tiếp diễn dùng khi nào", "tieng_anh") == "en_hien_tai_tiep_dien"
    assert detect_concept("present simple", "tieng_anh") == "en_thi_hien_tai_don"
    assert detect_concept("present simple", "toan") is None  # sai môn -> không khớp


@pytest.mark.parametrize("text,expected", [
    ("cho em xem video về quang hợp", True),
    ("làm clip giải thích giúp em", True),
    ("số nguyên tố là gì", False),
])
def test_is_video_request(text, expected):
    assert is_video_request(text) is expected


@pytest.mark.parametrize("text,topic", [
    ("Cho em xem video về hình thang cân", "hình thang cân"),
    ("làm một clip giải thích phép nhân phân số", "giải thích phép nhân phân số"),
    ("video quang hợp", "quang hợp"),
])
def test_topic_from_request_bo_cum_xin_video(text, topic):
    assert topic_from_request(text) == topic


def test_topic_from_request_giu_nguyen_khi_qua_ngan():
    # Lược hết -> giữ câu gốc (không để chủ đề rỗng).
    assert topic_from_request("làm video") == "làm video"


def test_free_key_roundtrip_va_dedup():
    # Cùng câu + môn -> cùng free-key (dùng lại video); giải mã đúng câu + môn.
    k1 = free_concept_key("Quang hợp là gì?", "tieng_anh", "v1")
    k2 = free_concept_key("Quang hợp là gì?", "tieng_anh", "v1")
    assert k1 == k2 and k1.startswith("free:") and k1.endswith("::v1")
    slug = k1.split("::")[0]
    assert decode_free_slug(slug) == ("tieng_anh", "Quang hợp là gì?")


def test_is_known_concept_key_nhan_ca_free():
    # Free-key hợp lệ được /video/generate chấp nhận; key bịa thì không.
    good = free_concept_key("Chủ đề bất kỳ có trong sách", "toan", "cung_kham_pha_2024")
    assert is_known_concept_key(good, "cung_kham_pha_2024")
    assert not is_known_concept_key("bịa::cung_kham_pha_2024", "cung_kham_pha_2024")
    assert not is_known_concept_key(good, "phien_ban_khac")  # sai version
