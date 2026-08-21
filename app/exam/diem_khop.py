"""Điểm khớp giữa tên trong ma trận .docx và danh mục chương trình (REQ §2.5).

`0.7 × tên đơn vị + 0.3 × tên mạch`, chuẩn hoá NFC. Tên đơn vị nặng hơn vì nó cụ
thể; mạch chỉ để phá nhập nhằng khi hai mạch có đơn vị tên giống nhau.

Dùng cho BƯỚC ĐỐI CHIẾU (preview) — không tự gán, không tự tạo đơn vị mới. Không
khớp thì người duyệt gán tay hoặc bỏ (§2.5).
"""
import re
import unicodedata
from difflib import SequenceMatcher

# Ngưỡng phân loại — khớp mockup §2.5.
CAO = 0.8      # khớp chắc chắn
VUA = 0.5      # cần xem lại (0.5–0.8); dưới nữa = chưa gán


def chuan(s: str) -> str:
    """NFC + hạ chữ + gộp khoảng trắng + bỏ dấu câu.

    NFC là bắt buộc: cùng chữ "ố" có thể là 1 hay 2 code point tuỳ nguồn (Word hay
    xuất ra NFD), so chuỗi thô sẽ cho 0 điểm cho hai tên NHÌN GIỐNG NHAU y hệt.
    """
    s = unicodedata.normalize("NFC", (s or "").strip().lower())
    s = re.sub(r"[.,;:!?()\[\]\"'/–—-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _giong(a: str, b: str) -> float:
    a, b = chuan(a), chuan(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def diem(dv_nguon: str, mach_nguon: str, dv_dich: str, mach_dich: str) -> float:
    """Điểm khớp 0..1 giữa một dòng ma trận và một đơn vị trong danh mục."""
    return round(0.7 * _giong(dv_nguon, dv_dich) + 0.3 * _giong(mach_nguon, mach_dich), 4)


def xep_loai(d: float) -> str:
    return "cao" if d >= CAO else ("vua" if d >= VUA else "thap")


def khop_tot_nhat(dv_nguon: str, mach_nguon: str, ung_vien: list) -> tuple[object | None, float]:
    """Ứng viên khớp nhất trong danh mục + điểm. `ung_vien` là list CurriculumTopic.

    Trả (None, 0.0) khi danh mục rỗng — KHÔNG tự tạo đơn vị mới.
    """
    tot, cao_nhat = None, 0.0
    for t in ung_vien:
        d = diem(dv_nguon, mach_nguon, t.don_vi_kien_thuc or "", t.mach_noi_dung or "")
        if d > cao_nhat:
            tot, cao_nhat = t, d
    return tot, cao_nhat


def tong_ti_le_theo_muc_do(cells: list) -> dict[str, float]:
    """Cộng tỉ lệ theo mức độ từ `BlueprintCell`, MỖI NHÓM ô gộp một lần (§2.5).

    Bản DB của `matrix_parser.tong_ti_le_theo_muc_do`. Cộng thẳng từng dòng sẽ
    nhân bản tỉ lệ dùng chung và ra tổng 140% thay vì 100%.
    """
    seen: set = set()
    out: dict[str, float] = {}
    for c in cells:
        if c.nhom_ti_le in seen:
            continue
        seen.add(c.nhom_ti_le)
        out[c.muc_do] = out.get(c.muc_do, 0.0) + (c.ti_le or 0.0)
    return out
