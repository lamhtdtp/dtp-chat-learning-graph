"""US-26 KB 8 / KB 13 / KB 14 — hàm thuần của mã giao đề: `app/exam/ma_de.py`.

Hợp đồng (docs/contracts/US-26-giao-de-bang-ma.md mục 2):
- `sinh_ma() -> str`: 6 ký tự thuộc bảng `23456789ABCDEFGHJKMNPQRSTUVWXYZ` (31 ký tự, bỏ 0 O 1 I L),
  sinh bằng `secrets` (không đoán được từ thời điểm tạo / số thứ tự / người tạo).
- `chuan_hoa_ma(s) -> str | None`: bỏ MỌI khoảng trắng, đổi hoa; không đúng định dạng -> `None`.

Tính duy nhất KHÔNG thể chứng minh ở hàm thuần (không gian 31^6 ≈ 887 triệu, sinh ngẫu nhiên) —
nó do unique trong DB + sinh lại khi trùng, kiểm ở tests/api/test_de_giao.py
(`test_ma_trung_thi_sinh_lai_*`).
"""
import random
import re

import pytest

BANG = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _ma_de():
    from app.exam import ma_de
    return ma_de


def test_bang_ky_tu_co_31_ky_tu_khong_chua_ky_tu_de_nham():
    assert len(BANG) == 31 and len(set(BANG)) == 31
    for cam in "01OIL":
        assert cam not in BANG


def test_sinh_ma_dai_dung_6_ky_tu_thuoc_bang_ky_tu():
    """Vì sao: giáo viên đọc mã cho cả lớp — 0/O, 1/I/L đọc và chép nhầm."""
    sinh_ma = _ma_de().sinh_ma
    for _ in range(1000):
        ma = sinh_ma()
        assert isinstance(ma, str) and len(ma) == 6, ma
        assert re.fullmatch(f"[{BANG}]{{6}}", ma), ma


def test_sinh_1000_ma_khong_co_ky_tu_thuong_khoang_trang_hay_dau():
    sinh_ma = _ma_de().sinh_ma
    tat_ca = "".join(sinh_ma() for _ in range(1000))
    assert set(tat_ca) <= set(BANG)
    assert tat_ca == tat_ca.upper() and not any(c.isspace() for c in tat_ca)


def test_sinh_1000_ma_gan_nhu_khong_trung_nhau():
    """Hàm ngẫu nhiên nên KHÔNG khẳng định tuyệt đối 1000/1000 khác nhau (xác suất trùng ~0,05%):
    chỉ chặn kiểu cài sai (số đếm lặp, mã theo giờ, hằng số). Tính duy nhất tuyệt đối do DB giữ."""
    sinh_ma = _ma_de().sinh_ma
    ds = [sinh_ma() for _ in range(1000)]
    assert len(set(ds)) >= 995
    # Dùng đủ bảng ký tự, không dồn vào vài ký tự.
    assert len(set("".join(ds))) >= 29


def test_sinh_ma_khong_dung_module_random_khong_an_toan(mocker):
    """Yêu cầu phi chức năng: mã sinh từ nguồn ngẫu nhiên an toàn (`secrets`), không phải
    `random` (Mersenne Twister đoán được từ vài đầu ra)."""
    sinh_ma = _ma_de().sinh_ma
    for ten in ("choice", "choices", "randint", "randrange", "sample", "random", "shuffle", "getrandbits"):
        mocker.patch.object(random, ten, side_effect=AssertionError(f"random.{ten} không an toàn"))
    assert len(sinh_ma()) == 6


@pytest.mark.parametrize("vao,ra", [
    ("K7M3PX", "K7M3PX"),
    (" k7m 3px ", "K7M3PX"),          # KB 13: chữ thường + khoảng trắng
    ("k7m3px", "K7M3PX"),
    ("K7M3PX\n", "K7M3PX"),
    ("\tK7M\t3PX ", "K7M3PX"),
    ("  234 567  ", "234567"),
])
def test_chuan_hoa_ma_bo_khoang_trang_va_doi_hoa(vao, ra):
    assert _ma_de().chuan_hoa_ma(vao) == ra


@pytest.mark.parametrize("sai", [
    "",                # rỗng
    "   ",             # chỉ khoảng trắng
    "K7M3P",           # thiếu ký tự
    "K7M3PXX",         # thừa ký tự
    "K7M3P0",          # có 0
    "K7M3PO",          # có O
    "K7M3P1",          # có 1
    "K7M3PI",          # có I
    "K7M3PL",          # có L
    "k7m3pl",          # L chữ thường (đổi hoa rồi vẫn là L)
    "K7M-3P",          # dấu
    "K7M3P!",
    "K7M.3PX",
    "KẸM3PX",          # chữ có dấu tiếng Việt
])
def test_chuan_hoa_ma_sai_dinh_dang_tra_none(sai):
    """KB 14: sai định dạng là `None` — không đoán, không cắt bớt cho vừa."""
    assert _ma_de().chuan_hoa_ma(sai) is None


@pytest.mark.parametrize("la", ["ſ7M3PX", "ßAAAA", "K7M3PẍX", "K7M3P\u212a"])
def test_chuan_hoa_ma_ky_tu_ngoai_ascii_tra_none_bug_qc26_05(la):
    """`.upper()` biến ſ -> S, ß -> SS, K (Kelvin) -> K: mã lạ không được khớp mã thật."""
    assert _ma_de().chuan_hoa_ma(la) is None
