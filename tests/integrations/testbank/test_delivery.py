"""US-29 — hàm thuần của client dịch vụ phát đề: họ tên gửi, đổi dạng câu trả lời hai chiều."""
import pytest

from app.integrations.testbank.delivery import (
    chon_sang_tra_loi, ho_ten_gui, tra_loi_sang_chon,
)

PA = [{"key": k} for k in "ABCD"]
DS = [{"key": "1"}, {"key": "2"}, {"key": "3"}]


def test_ho_ten_gui_kem_dinh_danh_khong_lo_email():
    assert ho_ten_gui("Nguyễn Văn An", 1024) == "Nguyễn Văn An · HS1024"
    assert ho_ten_gui("  An   Bình ", 7) == "An Bình · HS7"
    assert ho_ten_gui("", 7) == "Học sinh · HS7"


def test_ho_ten_dai_bi_cat_ten_chu_khong_cat_dinh_danh():
    ten = ho_ten_gui("A" * 300, 123456)
    assert len(ten) == 100 and ten.endswith(" · HS123456")


@pytest.mark.parametrize("dang, chon, tra_loi", [
    ("TN1", "C", "C"), ("TN1", "", None),
    ("TNN", "A,C", ["A", "C"]), ("TNN", "", None),
    ("DSN", "3,5", "3,5"), ("DSN", "  ", None),
    ("TL", "dòng 1\ndòng 2", "dòng 1\ndòng 2"),
])
def test_chon_va_tra_loi_hai_chieu(dang, chon, tra_loi):
    cau = {"dang": dang, "phuong_an": PA}
    assert chon_sang_tra_loi(cau, chon) == tra_loi
    if tra_loi is not None:
        assert tra_loi_sang_chon(cau, tra_loi) == chon


def test_ds_theo_thu_tu_y_giu_cho_y_bo_trong():
    cau = {"dang": "DS", "phuong_an": DS}
    assert chon_sang_tra_loi(cau, "Đ,,S") == {"1": "Đ", "3": "S"}
    assert chon_sang_tra_loi(cau, ",,") is None
    assert chon_sang_tra_loi(cau, "Đ,X,S") == {"1": "Đ", "3": "S"}      # giá trị lạ bị bỏ
    assert tra_loi_sang_chon(cau, {"1": "Đ", "3": "S"}) == "Đ,,S"
