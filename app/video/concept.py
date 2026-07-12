"""Chuẩn hoá câu hỏi -> concept_key để cache/dùng lại video giữa các học sinh.

Nhiều câu hỏi khác chữ nhưng CÙNG khái niệm ("số nguyên tố là gì", "thế nào là
số nguyên tố") phải ra CÙNG concept_key -> chung 1 video (04-Video-Generation
§4). Dùng bảng khái niệm chuẩn + từ khoá kích hoạt, tất định và test được.

concept_key GỒM sgk_version: đổi sách -> key khác -> cache miss -> làm mới video
(US-19 Scenario 2). Câu không khớp khái niệm nào -> None: gating không sinh
video cho câu vụn/không rõ khái niệm (US-19 §gating).
"""

import base64
import binascii
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

# ---- Video "chủ đề tự do" (free) ----------------------------------------
# Khi học sinh CHỦ ĐỘNG xin video ("...video...") về một chủ đề CÓ ngữ liệu
# nhưng không nằm trong bảng khái niệm cố định, ta vẫn sinh video. Câu hỏi + môn
# được MÃ HOÁ thẳng vào concept_key (prefix free: + base64) -> không cần cột DB
# hay đổi frontend; pipeline giải mã lại để ground đúng câu, đúng môn. Cùng câu
# + môn -> cùng key -> vẫn dùng lại (cache), tất định.
_FREE_PREFIX = "free:"
_MAX_FREE_QUERY = 160  # chặn key phình + chống lạm dụng

_VIDEO_REQUEST_KW = ("video", "clip", "doan phim")


def is_video_request(text: str) -> bool:
    """Câu có phải học sinh XIN một video minh hoạ không (vd 'cho em xem video…')."""
    norm = _bo_dau(text)
    return any(kw in norm for kw in _VIDEO_REQUEST_KW)


# Cụm "xin video" cần lược để lấy CHỦ ĐỀ sạch -> ground chuẩn + cùng chủ đề (dù
# khác cách xin) ra cùng free-key. Giữ dấu tiếng Việt để không đổi nghĩa chủ đề.
_REQUEST_PHRASES = re.compile(
    r"(?i)\b(cho|giúp)\s+(em|mình|tớ|con|thầy|cô)\b|"
    r"\b(xem|làm|tạo|vẽ|dựng|xin)\b|\b(một|1)\b|"
    r"\bvideo\b|\bclip\b|\bđoạn phim\b|\bminh\s*ho[aạ]\b|\bvề\b|\bgiúp\b"
)


def topic_from_request(text: str) -> str:
    """Bỏ cụm 'xin video' khỏi câu -> còn lại chủ đề. Nếu lược quá ngắn (<3 ký tự)
    thì giữ nguyên câu gốc để không mất ngữ nghĩa."""
    stripped = _REQUEST_PHRASES.sub(" ", text)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ?.!,:;-")
    return stripped if len(stripped) >= 3 else text.strip()


def free_concept_key(query: str, mon: str, sgk_version: str) -> str:
    """concept_key cho chủ đề tự do: free:<b64('{mon}|{query}')>::<sgk_version>."""
    payload = f"{mon}|{query.strip()[:_MAX_FREE_QUERY]}".encode()
    body = base64.urlsafe_b64encode(payload).decode()
    return f"{_FREE_PREFIX}{body}::{sgk_version}"


def decode_free_slug(slug: str) -> tuple[str, str] | None:
    """Giải mã phần slug (đã bỏ ::version) của free-key -> (mon, query). None nếu
    không phải free-key hợp lệ."""
    if not slug.startswith(_FREE_PREFIX):
        return None
    try:
        raw = base64.urlsafe_b64decode(slug[len(_FREE_PREFIX):]).decode()
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    mon, sep, query = raw.partition("|")
    if not sep or not query:
        return None
    return mon, query


def is_known_concept_key(concept_key: str, sgk_version: str) -> bool:
    """Kiểm concept_key client gửi lên có hợp lệ không (đúng định dạng + phiên bản
    SGK): slug thuộc bảng khái niệm, HOẶC là free-key giải mã được. Chống tạo job
    tuỳ tiện — nhưng free-key vẫn phải ground được ở pipeline mới ra video."""
    slug, sep, ver = concept_key.partition("::")
    if sep != "::" or ver != sgk_version:
        return False
    return slug in _KNOWN_SLUGS or decode_free_slug(slug) is not None
