"""Bóc [[Tên đơn vị]] trong câu trả lời -> lối mở sang bài đó (phạm vi cả cuốn).

Hàm thuần, không cần DB: dựng CurriculumTopic trong bộ nhớ là đủ. Đây là chỗ dễ
sai âm thầm nhất của tính năng — mô hình viết tên tự do, khớp lỏng tay thì bấm
vào ra SAI BÀI, mà học sinh không có cách nào biết.
"""
from app.api.tutor import _boc_muc
from app.db.models import CurriculumTopic


def _t(i: int, mach: str, dv: str) -> CurriculumTopic:
    t = CurriculumTopic(subject_id=1, grade_id=2, mach_noi_dung=mach,
                        don_vi_kien_thuc=dv, order_index=i)
    t.id = i
    return t


ROWS = [
    _t(1, "Số tự nhiên", "Tập hợp. Cách viết tập hợp"),
    _t(2, "Số tự nhiên", "Số nguyên tố. Hợp số"),
    _t(3, "Số nguyên", "Số âm trong thực tiễn"),
]


def test_khop_nguyen_van_thi_co_loi_mo_bai():
    van, muc = _boc_muc("Phần này học sau bài [[Số nguyên tố. Hợp số]] nhé.", ROWS)
    assert "[[" not in van and "]]" not in van
    assert van == "Phần này học sau bài Số nguyên tố. Hợp số nhé."
    assert [(m.topic_id, m.ten) for m in muc] == [(2, "Số nguyên tố. Hợp số")]


def test_lech_dau_cau_van_khop():
    """`diem_khop.chuan` bỏ dấu câu nên "Số nguyên tố, Hợp số" vẫn ra đúng bài —
    mô hình sao tên từ mục lục thường sai đúng mấy dấu này."""
    _, muc = _boc_muc("Xem bài [[Số nguyên tố, Hợp số]] trước.", ROWS)
    assert [m.topic_id for m in muc] == [2]


def test_ten_bia_thi_bo_ngoac_nhung_KHONG_tao_link():
    """Khớp lỏng còn tệ hơn không có link: bấm vào ra sai bài."""
    van, muc = _boc_muc("Xem bài [[Đạo hàm nâng cao]] nhé.", ROWS)
    assert van == "Xem bài Đạo hàm nâng cao nhé." and muc == []


def test_trung_lap_chi_mot_lan():
    _, muc = _boc_muc("[[Số nguyên tố. Hợp số]] và lại [[Số nguyên tố. Hợp số]].", ROWS)
    assert len(muc) == 1


def test_giu_thu_tu_xuat_hien_trong_cau_tra_loi():
    """Thứ tự trong câu trả lời chính là thứ tự sư phạm mô hình vừa giải thích
    ("học A rồi tới B") — xếp lại theo order_index là làm lệch ý đó."""
    _, muc = _boc_muc(
        "Học [[Số âm trong thực tiễn]] sau khi xong [[Tập hợp. Cách viết tập hợp]].", ROWS)
    assert [m.topic_id for m in muc] == [3, 1]


def test_khong_co_ngoac_thi_khong_doi_gi():
    """Mô hình không tuân thủ -> tính năng tự tắt, KHÔNG được làm hỏng câu trả lời."""
    goc = "Số nguyên tố chỉ có hai ước [tr.45]."
    van, muc = _boc_muc(goc, ROWS)
    assert van == goc and muc == []


def test_ngoac_mo_coi_van_phai_sach():
    """Mô hình quên đóng ngoặc -> không giải được tên, nhưng "[[" thì TUYỆT ĐỐI
    không được còn trên màn hình học sinh."""
    van, muc = _boc_muc("Xem bài [[Số nguyên tố. Hợp số và phần còn lại", ROWS)
    assert "[[" not in van and muc == []


def test_khong_co_danh_muc_thi_khong_no():
    """topic_id lạ / danh mục rỗng -> vẫn bóc ngoặc, chỉ là không có link."""
    van, muc = _boc_muc("Xem bài [[Số nguyên tố. Hợp số]].", [])
    assert van == "Xem bài Số nguyên tố. Hợp số." and muc == []


def test_tran_so_luong_loi_mo_bai():
    rows = [_t(i, "M", f"Bài số {i}") for i in range(1, 9)]
    ans = " ".join(f"[[Bài số {i}]]" for i in range(1, 9))
    _, muc = _boc_muc(ans, rows)
    assert len(muc) == 4      # _MAX_MUC
