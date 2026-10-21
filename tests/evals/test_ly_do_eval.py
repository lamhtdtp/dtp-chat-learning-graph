"""Phần THUẦN của eval lý do từng phương án (US-30 KB 17): dataset đủ cỡ và đúng hình, hàm kiểm tự động,
hàm tổng hợp. Không gọi model — chạy eval thật bằng `python -m evals.run_ly_do_eval`."""
import json

from app.exam import ly_do as ly_do_svc
from app.exam import ly_do_to_de
from evals import run_ly_do_eval as ev


def _cau(r):
    return ly_do_to_de.cau_kieu_kho({**r, "qid": r["id"], "phien_ban": "V01", "khoi_du_kien": ""})


def test_dataset_du_co_va_dung_hinh():
    rows = ev._doc()
    kho = [r for r in rows if r["nhom"] == "kho"]
    sua = [r for r in rows if r["nhom"] == "da_sua"]
    assert len(kho) >= 30 and len(sua) >= 10
    assert {r["dang"] for r in kho} == {"TN1", "TNN", "DS"}
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        c = _cau(r)
        assert ly_do_svc.can_sinh(c), r["id"]                   # không hình, có đáp án, >= 2 phương án
        dung = ly_do_svc.dung_sai(c)
        assert any(dung.values()), r["id"]                       # có ít nhất một phương án đúng
        assert r["bai_giai"].strip()


def test_cau_da_sua_that_su_khac_kho():
    for r in (x for x in ev._doc() if x["nhom"] == "da_sua"):
        k = r["kho"]
        khac = (r["de_bai"] != k["de_bai"] or r["dap_an"] != k["dap_an"] or r["phuong_an"] != k["phuong_an"])
        assert khac, r["id"]


def test_dap_an_ds_khop_so_y_va_tnn_khop_phuong_an():
    for r in ev._doc():
        keys = {p["khoa"] for p in r["phuong_an"]}
        if r["dang"] == "DS":
            assert len(r["dap_an"].split(",")) == len(keys) and set(r["dap_an"].split(",")) <= {"Đ", "S"}, r["id"]
        else:
            assert set(r["dap_an"].split(",")) <= keys, r["id"]


def test_mau_thuan_nhan_bat_dung_ca():
    c = _cau({"id": "x", "dang": "TN1", "de_bai": "ƯCLN(12, 18)?", "bai_giai": "6",
              "phuong_an": [{"khoa": "A", "noi_dung": "2"}, {"khoa": "B", "noi_dung": "6"}], "dap_an": "B"})
    assert ev.mau_thuan_nhan(c, {"A": "Em nhầm với ước chung nhỏ. Phương án này sai.", "B": "Đúng vì 6 là ƯCLN."}) == []
    assert ev.mau_thuan_nhan(c, {"A": "Đây là đáp án đúng vì 2 là ước chung.", "B": "Phương án này sai vì 6 lớn."}) == ["A", "B"]
    # phủ định đứng trước thì không tính là khẳng định
    assert ev.mau_thuan_nhan(c, {"A": "Đây không phải là đáp án đúng, em nhầm."}) == []


def test_theo_kho_va_tong_hop():
    r = next(x for x in ev._doc() if x["id"] == "sua-02")
    assert ev.theo_kho({"A": "17 là số nguyên tố nên chọn", "B": "19 là nguyên tố"}, r["kho_dau_hieu"]) == ["A"]
    rows = [r]
    sach = {"id": "sua-02", "ly_do": {k: f"Lý do {k}" for k in "ABCD"}, "thieu": [],
            "giam_khao": {k: {"dung_toan": True, "mau_thuan": False, "ngoai_chuong_trinh": False, "theo_kho": False}
                          for k in "ABCD"}}
    kq = ev.tong_hop(rows, [sach])
    assert all(kq["dat"].values()) and kq["so_ly_do"] == 4
    ban = json.loads(json.dumps(sach))
    ban["ly_do"]["A"] = "17 là số nguyên tố"
    ban["giam_khao"]["B"]["ngoai_chuong_trinh"] = True
    kq = ev.tong_hop(rows, [ban])
    assert not kq["dat"]["da_sua_khong_theo_kho"] and not kq["dat"]["ngoai_chuong_trinh"]
    loi = ev.tong_hop(rows, [{"id": "sua-02", "loi": "model không trả lời"}])
    assert loi["so_ly_do"] == 0 and not any(loi["dat"].values())
