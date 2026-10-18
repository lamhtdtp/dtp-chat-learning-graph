"""Khoá so khớp nguyên văn YCCĐ phải GIỐNG HỆT quy tắc của DTP Testbank.

Testbank tra câu hỏi theo `ar.yccd_key` — một cột Postgres sinh tự động bằng
biểu thức SQL. Bản Python bên mình lệch một chút là gắn câu hỏi vào yêu cầu cần
đạt khác, và không có gì báo cho ai biết. Nên test này đối chiếu thẳng hai bên
trên cùng một bộ mẫu, giống `test_ar_key.py` của họ.
"""
import unicodedata

import pytest
from sqlalchemy import text

from app.lessons.ycd_key import chuan_hoa

#: Nguyên văn biểu thức sinh cột `ar.yccd_key` trong
#: services/content/src/content_service/ar_key.py của testbank.
BIEU_THUC_SQL = "lower(btrim(regexp_replace(normalize(:t, NFC), '\\s+', ' ', 'g')))"

MAU = [
    "Vận dụng được dấu hiệu chia hết cho 2, 5, 3, 9 để xét tính chia hết của một tổng, một hiệu",
    "Xác định được ƯCLN, BCNN của hai số tự nhiên",
    "  VẬN  DỤNG   được  ",
    "a b",                                    # NBSP
    "a b",                                    # thin space
    "a　b",                                    # ideographic space
    unicodedata.normalize("NFD", "Vận dụng"),      # chữ ở dạng tổ hợp dấu
    "dòng\nxuống\tdòng",
    "",
]


@pytest.mark.parametrize("nguyen_van", MAU)
async def test_khop_bieu_thuc_sql_cua_testbank(db_session, nguyen_van):
    sql = (await db_session.execute(text(f"select {BIEU_THUC_SQL}"), {"t": nguyen_van})).scalar()
    assert chuan_hoa(nguyen_van) == sql


def test_nfd_va_nfc_cho_cung_khoa():
    """Nguyên văn chép từ Word hay ở dạng NFD; cùng chữ thì phải cùng khoá."""
    assert chuan_hoa(unicodedata.normalize("NFD", "Vận dụng")) == chuan_hoa("Vận dụng")


def test_gop_khoang_trang_va_thuong_hoa():
    assert chuan_hoa("  VẬN  DỤNG   được ") == "vận dụng được"


def test_khong_bo_dau_cau():
    """Hai YCCĐ chỉ khác một dấu phẩy là HAI yêu cầu khác nhau. So khớp lỏng tay
    ở đây là gắn câu hỏi vào chỗ sai mà không ai biết."""
    assert chuan_hoa("a, b") != chuan_hoa("a b")


def test_khong_bo_dau_tieng_viet():
    assert chuan_hoa("vận dụng") != chuan_hoa("van dung")
