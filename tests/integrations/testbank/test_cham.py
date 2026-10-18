"""Chấm câu rút từ DTP Testbank — chạy ở máy chủ learning, đáp án không xuống
trình duyệt. Luật chấm chép theo docs/24-HUONG-DAN-API-CHO-LEARNING.md §7 của
testbank: lệch luật với họ là cùng một bài, hai bên chấm ra hai điểm."""
from app.integrations.testbank.cham import cham, tach_khoa


# ── tách khoá ──────────────────────────────────────────────────────────────
def test_tach_khoa_nhan_ca_phay_cham_phay_va_gach_cheo():
    assert tach_khoa("A,C") == tach_khoa("A;C") == tach_khoa("A/C") == ["A", "C"]


def test_tach_khoa_bo_khoang_trang_va_o_rong():
    assert tach_khoa(" a , c ,") == ["A", "C"]


# ── TN1 ────────────────────────────────────────────────────────────────────
def test_tn1_dung():
    kq = cham("TN1", "C", "C")
    assert kq.cham_duoc and kq.dung


def test_tn1_khong_phan_biet_hoa_thuong():
    assert cham("TN1", "C", "c").dung


def test_tn1_sai():
    assert not cham("TN1", "C", "B").dung


def test_bo_trong_la_sai_nhung_van_cham_duoc():
    """Bỏ trống không phải "không chấm được": câu vẫn tính vào tổng."""
    kq = cham("TN1", "C", "")
    assert kq.cham_duoc and not kq.dung


# ── TNN ────────────────────────────────────────────────────────────────────
def test_tnn_dung_du_moi_phuong_an_moi_co_diem():
    assert cham("TNN", "A,C", "C,A").dung


def test_tnn_thieu_mot_phuong_an_la_sai():
    assert not cham("TNN", "A,C", "A").dung


def test_tnn_thua_mot_phuong_an_la_sai():
    assert not cham("TNN", "A,C", "A,B,C").dung


# ── DS ─────────────────────────────────────────────────────────────────────
def test_ds_dung_ca_bon_y():
    kq = cham("DS", "Đ,S,Đ,S", "Đ,S,Đ,S")
    assert kq.dung and (kq.so_y_dung, kq.so_y) == (4, 4)


def test_ds_dem_so_y_dung_khi_sai_mot_y():
    kq = cham("DS", "Đ,S,Đ,S", "Đ,S,S,S")
    assert not kq.dung and (kq.so_y_dung, kq.so_y) == (3, 4)


def test_ds_coi_D_khong_dau_nhu_Đ():
    """Testbank báo trước: có thể gặp `D` không dấu thay cho `Đ`, ở cả hai phía."""
    assert cham("DS", "D,S,Đ,S", "Đ,S,d,s").dung


def test_ds_y_bo_trong_tinh_la_sai_khong_lech_vi_tri():
    """Bỏ trống ý B thì ý C vẫn phải so với ý C, không được dồn lên."""
    kq = cham("DS", "Đ,S,Đ,S", "Đ,,Đ,S")
    assert (kq.so_y_dung, kq.so_y) == (3, 4)


# ── DSN ────────────────────────────────────────────────────────────────────
def test_dsn_bo_khoang_trang_va_hoa_thuong():
    assert cham("DSN", "x = 21", "X=21").dung


def test_dsn_coi_phay_nhu_cham():
    assert cham("DSN", "3,5", "3.5").dung


def test_dsn_giu_dung_luat_testbank_khong_tu_noi_long():
    """"3.510.000" và "3510000" là một số với người đọc, nhưng luật testbank
    không bỏ dấu chấm phân cách nghìn. Chấm khác họ là cùng một bài hai điểm."""
    assert not cham("DSN", "3.510.000", "3510000").dung


def test_dsn_dap_an_la_anh_thi_khong_cham_tu_dong():
    kq = cham("DSN", "[[anh:" + "a" * 32 + "]]", "5")
    assert not kq.cham_duoc


def test_dsn_dap_an_nhieu_dong_thi_khong_cham_tu_dong():
    assert not cham("DSN", "x = 1\ny = 2", "x=1").cham_duoc


# ── TL / lạ ────────────────────────────────────────────────────────────────
def test_tu_luan_khong_cham_tu_dong():
    kq = cham("TL", "A", "A")
    assert not kq.cham_duoc and not kq.dung


def test_dang_la_khong_cham_va_khong_no():
    assert not cham("XYZ", "A", "A").cham_duoc


def test_dap_an_rong_thi_khong_cham_duoc():
    """Câu thiếu đáp án ở kho mà vẫn chấm thì mọi bài làm đều "sai"."""
    assert not cham("TN1", "", "A").cham_duoc
