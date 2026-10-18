"""Chọn YCCĐ cho "bài làm mới" sau đề cuối kỳ — đầu vào `ar_ids` của testbank."""
from app.lessons.ycd_thong_ke import ThongKeYcd, chon_ar_on_lai


def _ls(ar: str | None, dung: int, tong: int) -> ThongKeYcd:
    return ThongKeYcd(ycd_key=f"k-{ar}", ycd_text="", ar_id=ar, dung=dung, tong=tong)


def test_lan_dau_lich_su_mong_van_lay_duoc_tu_bai_vua_lam():
    """Đề 12 câu thường phủ 12 YCCĐ, mỗi YCCĐ 1 câu: lịch sử chưa đủ 2 câu ở
    đâu cả nên `con_yeu` rỗng. Không rơi về bài vừa làm thì nút "làm bài mới"
    chẳng có gì để làm sau lần đầu."""
    out = chon_ar_on_lai([_ls("AR-1", 0, 1)], [("AR-1", 0, 1), ("AR-2", 1, 1)])
    assert out == ["AR-1"]


def test_lich_su_yeu_dung_truoc_roi_moi_toi_bai_vua_lam():
    ls = [_ls("AR-9", 1, 4), _ls("AR-1", 0, 1)]
    out = chon_ar_on_lai(ls, [("AR-1", 0, 1)])
    assert out == ["AR-9", "AR-1"]


def test_khu_trung_va_bo_cau_tu_sinh_khong_co_ar():
    ls = [_ls("AR-1", 0, 3), _ls(None, 0, 5)]
    assert chon_ar_on_lai(ls, [("AR-1", 0, 1)]) == ["AR-1"]


def test_bai_vua_lam_sai_nhieu_hon_xep_truoc():
    out = chon_ar_on_lai([], [("AR-2", 1, 2), ("AR-1", 0, 2), ("AR-3", 2, 2)])
    assert out == ["AR-1", "AR-2"]


def test_gioi_han_so_ycd():
    lan_nay = [(f"AR-{i}", 0, 1) for i in range(9)]
    assert len(chon_ar_on_lai([], lan_nay, toi_da=5)) == 5


def test_lam_dung_het_thi_rong():
    assert chon_ar_on_lai([], [("AR-1", 1, 1)]) == []
