"""§2.5 — điểm khớp là thứ quyết định dòng ma trận gán vào đơn vị nào."""
from app.exam import diem_khop as dk


def test_trung_khop_hoan_toan():
    assert dk.diem("Số nguyên tố", "Số tự nhiên", "Số nguyên tố", "Số tự nhiên") == 1.0


def test_NFC_hai_chuoi_nhin_giong_nhau_phai_khop():
    """Word xuất NFD, danh mục lưu NFC — so thô cho 0 điểm cho hai tên y hệt."""
    import unicodedata as u

    a = "Số nguyên tố"
    b = u.normalize("NFD", a)
    assert a != b                      # khác code point
    assert dk.diem(b, "Số tự nhiên", a, "Số tự nhiên") == 1.0


def test_trong_so_0_7_va_0_3():
    """Tên đơn vị nặng gấp hơn 2 lần tên mạch.

    Chỉ khẳng định QUAN HỆ chứ không ghim con số tuyệt đối cho phía sai: khớp mờ
    cho điểm lẻ cả với chuỗi không liên quan ("xyz" vs "số nguyên tố" ≈ 0.13) nên
    ghim số sẽ vỡ khi đổi thuật toán so chuỗi.
    """
    dung_dv = dk.diem("Số nguyên tố", "XYZ", "Số nguyên tố", "Số tự nhiên")
    dung_mach = dk.diem("XYZ", "Số tự nhiên", "Số nguyên tố", "Số tự nhiên")
    assert dung_dv >= 0.7                    # đúng đơn vị -> ít nhất trọng số 0.7
    assert dung_mach < dk.VUA                # đúng mạch thôi thì KHÔNG đủ để gán
    assert dung_dv > dung_mach * 1.7   # thực đo 1.78


def test_bo_qua_dau_cau_va_hoa_thuong():
    assert dk.diem("SỐ NGUYÊN TỐ.", "Số tự nhiên", "Số nguyên tố", "Số tự nhiên") == 1.0


def test_xep_loai_theo_nguong():
    assert dk.xep_loai(0.95) == "cao" and dk.xep_loai(0.8) == "cao"
    assert dk.xep_loai(0.65) == "vua" and dk.xep_loai(0.5) == "vua"
    assert dk.xep_loai(0.49) == "thap"


def test_khop_tot_nhat_danh_muc_rong_KHONG_tao_moi():
    t, d = dk.khop_tot_nhat("Bất kỳ", "Bất kỳ", [])
    assert t is None and d == 0.0


def test_tong_ti_le_moi_nhom_o_gop_chi_cong_MOT_lan():
    """Cộng thẳng từng dòng ra 140% thay vì 100% — lỗi đã kiểm chứng trên dữ liệu thật."""
    class C:
        def __init__(self, md, tl, nhom): self.muc_do, self.ti_le, self.nhom_ti_le = md, tl, nhom

    cells = [C("nhan_biet", 40.0, 1), C("nhan_biet", 40.0, 1),   # cùng nhóm -> 1 lần
             C("thong_hieu", 30.0, 2), C("van_dung", 30.0, 3)]
    assert dk.tong_ti_le_theo_muc_do(cells) == {
        "nhan_biet": 40.0, "thong_hieu": 30.0, "van_dung": 30.0}
    assert sum(dk.tong_ti_le_theo_muc_do(cells).values()) == 100.0


async def test_load_matrix_dem_va_danh_dau_don_vi_tu_tao(db_session, tmp_path):
    """§2.5 quyết định (b): vẫn tự tạo đơn vị, nhưng ĐÁNH DẤU + đếm để cảnh báo."""
    from sqlalchemy import select

    from app.db.models import CurriculumTopic, Grade, Subject
    from app.exam.matrix_loader import load_matrix

    md = tmp_path / "mt.md"
    md.write_text(
        "| STT | Mức độ | Năng lực | Biểu hiện | Yêu cầu cần đạt | Mạch | Đơn vị | Dạng thức | Tỉ lệ | Số câu |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        "| 1 | Dễ | NL | BH | Y1 | Số tự nhiên | Đơn vị hoàn toàn mới | TN | 100 | 5 |\n",
        encoding="utf-8")

    mon, khoi = f"M-{__import__('uuid').uuid4().hex[:6]}", f"K-{__import__('uuid').uuid4().hex[:6]}"
    bp = await load_matrix(db_session, md, mon=mon, khoi=khoi, hoc_ky="hk1")

    moi = getattr(bp, "don_vi_moi", [])
    assert len(moi) == 1 and moi[0].don_vi_kien_thuc == "Đơn vị hoàn toàn mới"
    # Cờ phải được ghi để CMS cảnh báo được
    t = await db_session.scalar(select(CurriculumTopic).where(
        CurriculumTopic.don_vi_kien_thuc == "Đơn vị hoàn toàn mới"))
    assert t.tu_ma_tran is True
    # Đơn vị chuyên gia tự thêm thì KHÔNG bị gắn cờ
    subj = await db_session.scalar(select(Subject).filter_by(name=mon))
    gr = await db_session.scalar(select(Grade).filter_by(name=khoi))
    tay = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                          don_vi_kien_thuc="Thêm tay", order_index=99)
    db_session.add(tay); await db_session.flush()
    assert tay.tu_ma_tran is False
