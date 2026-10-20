"""Đổi chữ của testbank (HTML đơn giản + dấu ảnh `[[anh:…]]`) sang HTML an toàn
cho trình duyệt học sinh."""
from app.integrations.testbank.hien_thi import co_anh, sang_html, sang_van_ban, url_anh

ID = "3f2a" + "0" * 26 + "e9"
GOC = "https://testbank.dtpsoft.vn/api/content"


def test_url_tuong_doi_ghep_vao_goc_content():
    """Testbank trả `/api/content/media/…`: tiền tố `/api/content` là tiền tố
    của cổng chung, thay bằng gốc content-service thì đúng cả prod (cùng cổng)
    lẫn máy dev (content chạy riêng cổng 8001, không có tiền tố)."""
    assert url_anh("/api/content/media/3f/2a/x.png", GOC) == f"{GOC}/media/3f/2a/x.png"
    assert url_anh("/api/content/media/x.png", "http://127.0.0.1:8001") == \
        "http://127.0.0.1:8001/media/x.png"


def test_url_tuyet_doi_giu_nguyen():
    u = "https://hcm03.vstorage.vngcloud.vn/v1/prod/e5/85/e5.png"
    assert url_anh(u, GOC) == u


def test_dau_anh_thanh_the_img():
    h = sang_html(f"Cho tập hợp [[anh:{ID}]].", {ID: "/api/content/media/a.png"}, {}, goc=GOC)
    assert f'<img class="tb-anh" src="{GOC}/media/a.png"' in h
    assert "[[anh:" not in h


def test_be_rong_tu_dau_anh_doi_point_sang_px():
    h = sang_html(f"[[anh:{ID}|w=120]]", {ID: "/api/content/media/a.png"}, {}, goc=GOC)
    assert 'width:160px' in h         # 120pt * 4/3


def test_be_rong_lay_tu_asset_sizes_khi_dau_khong_ghi():
    h = sang_html(f"[[anh:{ID}]]", {ID: "/api/content/media/a.png"},
                  {ID: {"w": 30.0, "h": 12.0}}, goc=GOC)
    assert 'width:40px' in h
    assert 'width="40" height="16"' in h   # 12pt * 4/3 — giữ tỉ lệ 30:12


def test_anh_khong_co_trong_assets_khong_de_lai_dau_tho():
    h = sang_html(f"Xem [[anh:{ID}]]", {}, {}, goc=GOC)
    assert "[[anh:" not in h and "thiếu hình" in h


def test_giu_the_dinh_dang_cho_phep():
    h = sang_html("<p>Số <strong>12</strong> và <u>4</u></p>", {}, {}, goc=GOC)
    assert h == "<p>Số <strong>12</strong> và <u>4</u></p>"


def test_chan_the_va_thuoc_tinh_nguy_hiem():
    """Nội dung đi thẳng vào dangerouslySetInnerHTML. Kho có người nhập tay từ
    Word: thẻ lạ phải thành chữ, không được thành mã chạy."""
    h = sang_html('<img src=x onerror=alert(1)><script>x</script><p onclick="y">a</p>',
                  {}, {}, goc=GOC)
    # Thẻ lạ ở lại dạng CHỮ đã thoát — đọc được, không chạy được.
    assert "<script" not in h and "<img src=x" not in h and "<p onclick" not in h
    assert "&lt;script&gt;" in h and "&lt;p onclick=" in h


def test_xuong_dong_va_khoang_trang_lien_tiep_giu_bo_cuc():
    """Đề có dòng "Hình 1      Hình 2" canh dưới ảnh bằng khoảng trắng."""
    h = sang_html("a\nHình 1   Hình 2", {}, {}, goc=GOC)
    assert "a<br>" in h and "Hình 1 &nbsp;&nbsp;Hình 2" in h


def test_rong_hoac_none_ra_chuoi_rong():
    assert sang_html(None, {}, {}, goc=GOC) == ""


def test_van_ban_cho_prompt_thay_anh_bang_nhan_va_bo_the():
    assert sang_van_ban(f"<p>Tổng [[anh:{ID}]] bằng</p>") == "Tổng [hình] bằng"


def test_co_anh():
    assert co_anh(f"x [[anh:{ID}|w=3]]") and not co_anh("x")


# ── Bảng ─────────────────────────────────────────────────────────────────────
BANG = ("Hỏi có bao nhiêu ngày bị lỗ\n<table><tbody><tr><td>Ngày</td><td>19/6</td></tr>"
        "<tr><td>Tiền lời (nghìn đồng)</td><td></td></tr></tbody></table>")


def test_giu_bang_cua_de():
    """Đề có bảng số liệu (gặp thật ở đề cuối kỳ Toán 6) — trước đây bảng bị
    thoát thành chữ, học sinh thấy nguyên "<table><tbody>…" trên màn hình."""
    h = sang_html(BANG, {}, {}, goc=GOC)
    assert "&lt;table" not in h and "&lt;td" not in h
    assert "<table><tbody><tr><td>Ngày</td><td>19/6</td></tr>" in h


def test_xuong_dong_va_khoang_trang_giua_the_bang_bi_bo():
    """`<br>` / khoảng trắng nằm giữa các thẻ bảng là nút chữ trong <table> —
    trình duyệt đẩy chúng ra NGOÀI bảng, thành dòng trống phía trên bảng."""
    h = sang_html("<table>\n<tr>\n  <td>a</td>\n  <td>b</td>\n</tr>\n</table>", {}, {}, goc=GOC)
    assert h == "<table><tr><td>a</td><td>b</td></tr></table>"


def test_xuong_dong_trong_o_van_giu():
    h = sang_html("<table><tr><td>dòng 1\ndòng 2</td></tr></table>", {}, {}, goc=GOC)
    assert "<td>dòng 1<br>dòng 2</td>" in h


def test_o_gop_giu_colspan_rowspan_bo_thuoc_tinh_khac():
    h = sang_html('<table><tr><td colspan="2" rowspan="3" onclick="x()" style="a">a</td></tr></table>',
                  {}, {}, goc=GOC)
    assert '<td colspan="2" rowspan="3">a</td>' in h
    assert "onclick" not in h and "style" not in h


def test_anh_trong_o_bang_van_thanh_img():
    h = sang_html(f"<table><tr><td>[[anh:{ID}]]</td></tr></table>",
                  {ID: "/api/content/media/a.png"}, {}, goc=GOC)
    assert '<td><img class="tb-anh"' in h


def test_van_ban_cho_prompt_bo_the_bang():
    assert "<t" not in sang_van_ban(BANG)


def test_chieu_cao_giu_ti_le_khi_dau_anh_ghi_de_be_rong():
    """`|w=60` đổi chiều rộng 30 -> 60pt thì chiều cao gốc 12pt phải thành 24pt (80x32 px)."""
    h = sang_html(f"[[anh:{ID}|w=60]]", {ID: "/api/content/media/a.png"},
                  {ID: {"w": 30.0, "h": 12.0}}, goc=GOC)
    assert 'width="80" height="32"' in h and "width:80px" in h
