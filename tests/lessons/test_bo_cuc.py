"""Bố cục 7 phần — quy tắc §1.3 là thứ dễ sai và sai thì học sinh thấy ngay."""
import json

from app.lessons import bo_cuc as bc


def test_rong_thi_dung_thu_tu_chuan_khong_an_gi():
    ds = bc.hien("")
    assert [p["id"] for p in ds] == list(bc.IDS)
    assert [p["so"] for p in ds] == [1, 2, 3, 4, 5, 6, 7]


def test_phan_an_khong_hien_va_KHONG_chiem_so():
    """Ẩn phần 2 -> phần 3 thành số 2. Để lỗ số là lỗi hay gặp nhất."""
    j = json.dumps([{"id": "khoi_dong"}, {"id": "hoat_dong", "an": True},
                    {"id": "kien_thuc"}, {"id": "minh_hoa"}])
    ds = bc.hien(j)
    ids = [p["id"] for p in ds]
    assert "hoat_dong" not in ids
    assert ids[:3] == ["khoi_dong", "kien_thuc", "minh_hoa"]
    assert [p["so"] for p in ds] == list(range(1, len(ds) + 1))


def test_doi_thu_tu_duoc_ton_trong():
    j = json.dumps([{"id": "bai_tap"}, {"id": "kien_thuc"}])
    ds = bc.hien(j)
    assert [p["id"] for p in ds][:2] == ["bai_tap", "kien_thuc"]


def test_phan_thieu_duoc_bo_SUNG_vao_cuoi():
    """Thêm phần mới vào PHAN về sau không được làm nó biến mất khỏi bố cục cũ."""
    ds = bc.doc(json.dumps([{"id": "kien_thuc"}]))
    assert len(ds) == len(bc.IDS) and ds[0]["id"] == "kien_thuc"
    assert set(p["id"] for p in ds) == set(bc.IDS)


def test_du_lieu_rac_khong_lam_sap():
    for xau in ("", None, "khong-phai-json", "{}", '[1,2,3]', '[{"id":"bịa"}]'):
        assert [p["id"] for p in bc.hien(xau)] == list(bc.IDS)


def test_ghi_luoc_id_la_va_khu_trung():
    s = bc.ghi([{"id": "bai_tap"}, {"id": "bịa"}, {"id": "bai_tap", "an": True}])
    assert json.loads(s) == [{"id": "bai_tap", "an": False}]


def test_da_soan_dem_ca_cot_json():
    class C:
        khoi_dong = "<p>x</p>"; hoat_dong = ""; khai_niem = "<p>y</p>"
        luyen_tap = "   "; bai_tap = ""
        minh_hoa_json = '[{"type":"image"}]'; vi_du_json = "[]"
    assert bc.da_soan(C()) == 3   # khoi_dong + khai_niem + minh_hoa


class _C:
    """TopicContent tối thiểu cho hien_thuc_te."""
    khoi_dong = "<p>kd</p>"; hoat_dong = ""; khai_niem = "<p>kt</p>"
    luyen_tap = "<p>lt</p>"; bai_tap = ""
    minh_hoa_json = "[]"; vi_du_json = '[{"de":"d","giai":"g"}]'


def test_phan_bat_nhung_RONG_khong_chiem_so():
    """Đã gặp thật: bài chưa có minh hoạ -> đề mục nhảy 1, 2, *4*."""
    ds = bc.hien_thuc_te(_C(), "")
    ids = [p["id"] for p in ds]
    assert ids == ["khoi_dong", "kien_thuc", "vi_du", "luyen_tap"]
    assert [p["so"] for p in ds] == [1, 2, 3, 4]     # liền mạch, không lỗ


def test_hien_thuc_te_van_ton_trong_an():
    j = json.dumps([{"id": "khoi_dong", "an": True}, {"id": "kien_thuc"}])
    ds = bc.hien_thuc_te(_C(), j)
    assert [p["id"] for p in ds][0] == "kien_thuc" and ds[0]["so"] == 1


def test_co_noi_dung_doc_dung_cot_json():
    c = _C()
    assert bc.co_noi_dung(c, "vi_du") is True
    assert bc.co_noi_dung(c, "minh_hoa") is False
    assert bc.co_noi_dung(c, "bai_tap") is False
    c.minh_hoa_json = "khong-phai-json"
    assert bc.co_noi_dung(c, "minh_hoa") is False
