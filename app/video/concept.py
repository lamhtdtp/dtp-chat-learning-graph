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

# slug khái niệm -> các từ khoá (đã bỏ dấu) nhận diện, TÁCH THEO MÔN. Thứ tự:
# khái niệm cụ thể hơn đứng trước để khớp trước cái tổng quát. Nhận diện chỉ tìm
# trong danh sách của ĐÚNG môn (mon) -> câu Tiếng Anh không khớp nhầm slug Toán.
_CONCEPTS_BY_MON: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "toan": [
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
    ],
    "tieng_anh": [
        ("en_hien_tai_tiep_dien", ("hien tai tiep dien", "present continuous", "present progressive")),
        ("en_thi_hien_tai_don", ("hien tai don", "present simple")),
        ("en_dong_tu_to_be", ("dong tu to be", "to be", "am is are")),
        ("en_mao_tu", ("mao tu", "a an the", "article", "mao tu a an the")),
        ("en_so_sanh_hon", ("so sanh hon", "comparative")),
    ],
}


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
    # Tiếng Anh 6 — câu chuẩn để ground từ SGK Tiếng Anh (mon=tieng_anh).
    "en_hien_tai_tiep_dien": "Thì hiện tại tiếp diễn (present continuous) dùng khi nào?",
    "en_thi_hien_tai_don": "Thì hiện tại đơn (present simple) dùng khi nào?",
    "en_dong_tu_to_be": "Động từ 'to be' (am, is, are) dùng như thế nào?",
    "en_mao_tu": "Mạo từ a, an, the dùng như thế nào?",
    "en_so_sanh_hon": "Cấu trúc so sánh hơn (comparative) trong tiếng Anh là gì?",
}

# slug -> mon: pipeline biết ground câu trả lời từ kho SGK của MÔN nào (Toán hay
# Tiếng Anh). Suy ra từ _CONCEPTS_BY_MON để không phải khai báo lặp.
CONCEPT_MON: dict[str, str] = {
    slug: mon for mon, concepts in _CONCEPTS_BY_MON.items() for slug, _ in concepts
}


def _bo_dau(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường để so khớp từ khoá ổn định."""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    no_mark = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", no_mark.lower()).strip()


def detect_concept(text: str, mon: str = "toan") -> str | None:
    """slug khái niệm đầu tiên khớp TRONG MÔN `mon`, hoặc None. Tìm theo môn để
    câu Tiếng Anh không khớp nhầm khái niệm Toán và ngược lại."""
    norm = _bo_dau(text)
    for slug, keywords in _CONCEPTS_BY_MON.get(mon, []):
        if any(kw in norm for kw in keywords):
            return slug
    return None


def concept_key(text: str, sgk_version: str, mon: str = "toan") -> str | None:
    """`{slug}::{sgk_version}` nếu nhận diện được khái niệm trong môn `mon`, ngược
    lại None. slug là duy nhất toàn hệ nên key không cần chứa mon (cache giữ nguyên)."""
    slug = detect_concept(text, mon)
    return f"{slug}::{sgk_version}" if slug else None


_KNOWN_SLUGS = set(CONCEPT_MON)


def is_known_concept_key(concept_key: str, sgk_version: str) -> bool:
    """Kiểm concept_key client gửi lên có hợp lệ không (đúng định dạng, slug
    thuộc danh sách khái niệm, đúng phiên bản SGK) — chống tạo job tuỳ tiện."""
    slug, sep, ver = concept_key.partition("::")
    return sep == "::" and ver == sgk_version and slug in _KNOWN_SLUGS
