from app.ingestion.page_structure import (
    detect_bai,
    detect_chuong,
    gan_chuong_bai_theo_trang,
)


def test_detect_chuong_cac_dinh_dang():
    assert detect_chuong("# Chương 1: Số tự nhiên") == (1, "Số tự nhiên")
    assert detect_chuong("Chương 2  Số nguyên") == (2, "Số nguyên")
    assert detect_chuong("## CHƯƠNG 3: PHÂN SỐ") == (3, "PHÂN SỐ")


def test_detect_bai_cac_dinh_dang():
    assert detect_bai("# Bài 1: TẬP HỢP. PHẦN TỬ CỦA TẬP HỢP") == (1, "TẬP HỢP. PHẦN TỬ CỦA TẬP HỢP")
    assert detect_bai("Bài 12  Phép nhân") == (12, "Phép nhân")


def test_khong_nham_muc_con_hoat_dong_vi_du_la_bai():
    # các dòng này KHÔNG phải heading Chương/Bài dù có số
    assert detect_bai("## 1. TẬP HỢP. PHẦN TỬ CỦA TẬP HỢP") is None
    assert detect_bai("### HOẠT ĐỘNG 1") is None
    assert detect_bai("**VÍ DỤ 2**") is None
    assert detect_bai("**LUYỆN TẬP 1**") is None
    assert detect_chuong("## 1. TẬP HỢP") is None


def test_detect_lay_heading_dau_tien_trong_trang():
    # trang có heading nằm giữa nhiều dòng
    md = "Một dòng lý thuyết.\n\n# Bài 3: PHÉP CỘNG\n\nNội dung..."
    assert detect_bai(md) == (3, "PHÉP CỘNG")


def test_gan_chuong_bai_forward_fill_theo_trang():
    pages = [
        (5, "# Chương 1: Số tự nhiên\nMở đầu chương."),
        (6, "# Bài 1: TẬP HỢP\nNội dung bài 1."),
        (7, "Nội dung tiếp theo, không có heading."),  # kế thừa chương 1, bài 1
        (8, "Vẫn giữa bài 1."),
        (20, "# Bài 5: LUỸ THỪA\nNội dung."),           # bài mới, vẫn chương 1
        (63, "# Chương 2: Số nguyên\nMở đầu."),          # chương mới
        (64, "# Bài 9: SỐ NGUYÊN ÂM"),
    ]
    recs = gan_chuong_bai_theo_trang(pages)

    by_page = {r.page_no: r for r in recs}
    assert by_page[7].chuong_so == 1 and by_page[7].bai_so == 1
    assert by_page[8].chuong_so == 1 and by_page[8].bai_so == 1
    assert by_page[20].bai_so == 5 and by_page[20].chuong_so == 1
    assert by_page[64].chuong_so == 2 and by_page[64].bai_so == 9
    assert by_page[64].chuong_ten == "Số nguyên"


def test_chuong_moi_xoa_bai_cu_khong_ke_thua_nham():
    # Bug thật gặp khi pilot: trang mở Chương 2 (chưa có bài) bị forward-fill
    # nhầm bài cuối của Chương 1. Sang chương mới phải xoá bài cũ.
    pages = [
        (6, "# Chương 1: Số tự nhiên\n# Bài 1: TẬP HỢP"),
        (7, "Giữa bài 1."),
        (63, "# Chương 2: Số nguyên\nMở đầu chương, chưa có bài."),  # opener: bài phải None
        (64, "# Bài 1: SỐ NGUYÊN ÂM"),  # bài đánh số lại từ 1 theo chương
    ]
    recs = gan_chuong_bai_theo_trang(pages)
    by_page = {r.page_no: r for r in recs}

    assert by_page[63].chuong_so == 2
    assert by_page[63].bai_so is None and by_page[63].bai_ten is None
    assert by_page[64].chuong_so == 2 and by_page[64].bai_so == 1
    assert by_page[64].bai_ten == "SỐ NGUYÊN ÂM"


def test_footer_chan_trang_cung_chuong_khong_reset_bai():
    # Trang nội dung có footer "Chương 1 - Số tự nhiên" (khớp regex nhưng tên
    # hơi khác opener) — cùng SỐ chương thì không được coi là chương mới, giữ
    # nguyên bài đang học và giữ tên chương gốc từ opener.
    pages = [
        (5, "# Chương 1: Số tự nhiên"),
        (6, "# Bài 1: TẬP HỢP"),
        (8, "Nội dung giữa bài.\n\nChương 1 - Số tự nhiên"),  # dòng cuối là footer
    ]
    recs = gan_chuong_bai_theo_trang(pages)
    by_page = {r.page_no: r for r in recs}

    assert by_page[8].chuong_so == 1
    assert by_page[8].chuong_ten == "Số tự nhiên"  # giữ tên opener, không phải "- Số tự nhiên"
    assert by_page[8].bai_so == 1  # KHÔNG bị reset


def test_trang_dau_sach_chua_co_heading_thi_chuong_bai_rong():
    pages = [
        (1, "Bìa sách Toán 6"),
        (2, "Mục lục"),
        (5, "# Chương 1: Số tự nhiên"),
    ]
    recs = gan_chuong_bai_theo_trang(pages)
    by_page = {r.page_no: r for r in recs}
    assert by_page[1].chuong_so is None and by_page[1].bai_so is None
    assert by_page[2].chuong_so is None
    assert by_page[5].chuong_so == 1
