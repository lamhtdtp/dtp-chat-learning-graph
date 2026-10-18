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
