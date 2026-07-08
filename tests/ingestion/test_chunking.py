from app.ingestion.chunking import chunk_page
from app.ingestion.page_structure import PageStructure

PS = PageStructure(
    page_no=6, chuong_so=1, chuong_ten="Số tự nhiên", bai_so=1, bai_ten="TẬP HỢP"
)
BOOK = dict(mon="toan", khoi="lop_6", sach="cung_kham_pha_tap_1", tap=1)


def _kinds(chunks):
    return [c.metadata.loai_noi_dung for c in chunks]


def test_chunk_gan_du_metadata():
    md = "# Bài 1: TẬP HỢP\nLý thuyết về tập hợp, đủ dài để thành một chunk riêng biệt."
    chunks = chunk_page(md, PS, **BOOK)

    assert len(chunks) == 1
    m = chunks[0].metadata
    assert m.mon == "toan" and m.khoi == "lop_6" and m.sach == "cung_kham_pha_tap_1"
    assert m.tap == 1 and m.chuong_so == 1 and m.bai_so == 1
    assert m.page_no == 6
    assert "tr.6" in m.nguon and "Tập 1" in m.nguon


def test_phan_loai_loai_noi_dung_theo_marker():
    md = (
        "# 1. TẬP HỢP\n"
        "Đây là phần lý thuyết giải thích khái niệm tập hợp cho học sinh lớp 6.\n"
        "**VÍ DỤ 1**\n"
        "Gọi A là tập hợp các số tự nhiên nhỏ hơn 5. Ta viết A = {0;1;2;3;4}.\n"
        "**LUYỆN TẬP 1**\n"
        "Viết tập hợp các chữ số trong số 2025 để luyện tập cho học sinh.\n"
        "### HOẠT ĐỘNG 2\n"
        "Hãy kể tên các phần tử trong hình vẽ minh hoạ sau đây cho đủ dài.\n"
    )
    chunks = chunk_page(md, PS, **BOOK)

    assert _kinds(chunks) == ["ly_thuyet", "vi_du", "bai_tap", "bai_tap"]


def test_cat_theo_ranh_gioi_khong_gop_vi_du_vao_ly_thuyet():
    md = (
        "Phần lý thuyết mở đầu đủ dài để tạo thành một chunk hoàn chỉnh riêng.\n"
        "**VÍ DỤ 1**\n"
        "Nội dung ví dụ minh hoạ cụ thể, cũng đủ dài để tách thành chunk riêng.\n"
    )
    chunks = chunk_page(md, PS, **BOOK)

    assert len(chunks) == 2
    assert chunks[0].metadata.loai_noi_dung == "ly_thuyet"
    assert "VÍ DỤ" not in chunks[0].content  # không dính ví dụ vào lý thuyết
    assert chunks[1].metadata.loai_noi_dung == "vi_du"


def test_bo_footer_chan_trang():
    md = (
        "# Bài 1: TẬP HỢP\n"
        "Nội dung lý thuyết đủ dài để giữ lại thành một chunk hợp lệ nhé.\n"
        "\n---\n"
        "2 | Chương 1 - Số tự nhiên\n"
    )
    chunks = chunk_page(md, PS, **BOOK)

    joined = " ".join(c.content for c in chunks)
    assert "Chương 1 - Số tự nhiên" not in joined
    assert "2 |" not in joined


def test_gop_manh_qua_ngan_vao_chunk_truoc():
    # dòng chú thích hình lẻ loi quá ngắn -> gộp vào chunk trước, không thành chunk rác
    md = (
        "**VÍ DỤ 1**\n"
        "Một ví dụ minh hoạ đủ dài để tạo thành một chunk nội dung hợp lệ đây.\n"
        "*Hình 1.1*\n"
    )
    chunks = chunk_page(md, PS, **BOOK)

    assert len(chunks) == 1
    assert "Hình 1.1" in chunks[0].content


def test_trang_khong_co_noi_dung_thuc_tra_ve_rong():
    md = "\n---\n1 | Chương 1 - Số tự nhiên\n"
    assert chunk_page(md, PS, **BOOK) == []
