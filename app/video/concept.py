"""Chuẩn hoá câu hỏi -> concept_key để cache/dùng lại video giữa các học sinh.

Nhiều câu hỏi khác chữ nhưng CÙNG khái niệm ("số nguyên tố là gì", "thế nào là
số nguyên tố") phải ra CÙNG concept_key -> chung 1 video (04-Video-Generation
§4). Dùng bảng khái niệm chuẩn + từ khoá kích hoạt, tất định và test được.

concept_key GỒM sgk_version: đổi sách -> key khác -> cache miss -> làm mới video
(US-19 Scenario 2). Câu không khớp khái niệm nào -> None: gating không sinh
video cho câu vụn/không rõ khái niệm (US-19 §gating).
"""

import re
import unicodedata

# slug khái niệm -> các từ khoá (đã bỏ dấu) nhận diện. Thứ tự: khái niệm cụ thể
# hơn đứng trước để khớp trước cái tổng quát.
_CONCEPTS: list[tuple[str, tuple[str, ...]]] = [
    ("uoc_chung_lon_nhat", ("uoc chung lon nhat", "ucln")),
    ("boi_chung_nho_nhat", ("boi chung nho nhat", "bcnn")),
    ("so_nguyen_to", ("so nguyen to", "hop so")),
    ("dau_hieu_chia_het", ("dau hieu chia het", "chia het")),
    ("luy_thua", ("luy thua",)),
    ("uoc_va_boi", ("uoc va boi", "uoc so", "boi so")),
    ("tap_hop", ("tap hop", "phan tu")),
    ("so_nguyen_am", ("so nguyen am", "so am", "so nguyen")),
    ("phan_so", ("phan so",)),
    ("so_thap_phan", ("so thap phan",)),
    ("ti_so_phan_tram", ("ti so", "phan tram")),
    ("tam_giac_deu", ("tam giac deu", "luc giac deu")),
    ("chu_vi_dien_tich", ("chu vi", "dien tich")),
    ("doan_thang_trung_diem", ("trung diem", "doan thang")),
    ("goc", ("goc",)),
]


# slug -> câu hỏi chuẩn để sinh câu trả lời grounded "đại diện" cho khái niệm
# (video theo khái niệm, không theo câu chữ của 1 học sinh — hỗ trợ pre-generate
# US-19 Scenario 3: sinh video mà không cần ai hỏi).
CONCEPT_QUERY: dict[str, str] = {
    "uoc_chung_lon_nhat": "Ước chung lớn nhất là gì?",
    "boi_chung_nho_nhat": "Bội chung nhỏ nhất là gì?",
    "so_nguyen_to": "Số nguyên tố là gì?",
    "dau_hieu_chia_het": "Dấu hiệu chia hết là gì?",
    "luy_thua": "Lũy thừa với số mũ tự nhiên là gì?",
    "uoc_va_boi": "Ước và bội là gì?",
    "tap_hop": "Tập hợp là gì và cách viết tập hợp?",
    "so_nguyen_am": "Số nguyên âm là gì?",
    "phan_so": "Phân số là gì?",
    "so_thap_phan": "Số thập phân là gì?",
    "ti_so_phan_tram": "Tỉ số và tỉ số phần trăm là gì?",
    "tam_giac_deu": "Tam giác đều có đặc điểm gì?",
    "chu_vi_dien_tich": "Cách tính chu vi và diện tích hình chữ nhật?",
    "doan_thang_trung_diem": "Trung điểm của đoạn thẳng là gì?",
    "goc": "Góc là gì?",
}


def _bo_dau(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường để so khớp từ khoá ổn định."""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    no_mark = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", no_mark.lower()).strip()


def detect_concept(text: str) -> str | None:
    """slug khái niệm đầu tiên khớp, hoặc None nếu không nhận ra khái niệm nào."""
    norm = _bo_dau(text)
    for slug, keywords in _CONCEPTS:
        if any(kw in norm for kw in keywords):
            return slug
    return None


def concept_key(text: str, sgk_version: str) -> str | None:
    """`{slug}::{sgk_version}` nếu nhận diện được khái niệm, ngược lại None."""
    slug = detect_concept(text)
    return f"{slug}::{sgk_version}" if slug else None


_KNOWN_SLUGS = {slug for slug, _ in _CONCEPTS}


def is_known_concept_key(concept_key: str, sgk_version: str) -> bool:
    """Kiểm concept_key client gửi lên có hợp lệ không (đúng định dạng, slug
    thuộc danh sách khái niệm, đúng phiên bản SGK) — chống tạo job tuỳ tiện."""
    slug, sep, ver = concept_key.partition("::")
    return sep == "::" and ver == sgk_version and slug in _KNOWN_SLUGS
