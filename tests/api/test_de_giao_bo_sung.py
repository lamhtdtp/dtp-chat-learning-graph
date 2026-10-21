"""US-26 — test BỔ SUNG của QC sau khi DEV xong (lượt B): những thứ US không nhắc nhưng người dùng làm được.

Dùng lại hạ tầng giả của `test_de_giao.py` (testbank giả, kho đếm giả, LLM giả).
"""
import pytest

from tests.api.test_de_giao import (  # noqa: F401  (fixture autouse phải import vào module này)
    MSG_DA_DONG, MSG_KHONG_THAY_DE, _giao, _lam, _model, _nop, _tk, _vao, _vao_ok,
    kho_dem, tb,
)

MSG_CHI_HS = "Chỉ tài khoản học sinh làm bài theo mã"


async def test_nop_bai_theo_ma_qua_duong_de_cuoi_ky_khong_lach_duoc_luat_dong_ma(client, session, tb):
    """Vì sao: `/exam/cuoi-ky/submit` không kiểm mã đã đóng. Nếu nhận id bài theo mã, học sinh
    nộp qua đường này là qua mặt KB 34 (điểm vẫn ghi sau khi thầy cô đóng)."""
    gv, chi = await _tk(client, "giao_vien"), await _tk(client, ten="Chi")
    g = await _giao(client, gv)
    v = await _vao_ok(client, chi, g.ma)
    await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)
    r = await client.post("/exam/cuoi-ky/submit", headers=chi.h, json={"de_id": v["de_id"], "tra_loi": {}})
    assert r.status_code == 404, r.text
    ds = (await client.get(f"/de-giao/{g.id}/ket-qua", headers=gv.h)).json()
    assert ds["tong"]["da_nop"] == 0


async def test_mo_lai_bai_theo_ma_chua_nop_khi_ma_da_dong_bi_410_con_bai_da_nop_van_mo_duoc(client, tb):
    """Vì sao: bài dở không nộp được nữa nên mở ra là vô nghĩa (410); bài đã nộp thì KB 33 giữ nguyên."""
    gv = await _tk(client, "giao_vien")
    an, chi = await _tk(client, ten="An"), await _tk(client, ten="Chi")
    g = await _giao(client, gv)
    kq_an = await _lam(client, an, g.ma, list(tb.kho.values()), 8)
    v_chi = await _vao_ok(client, chi, g.ma)
    await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)

    r = await client.get(f"/exam/cuoi-ky/{v_chi['de_id']}", headers=chi.h)
    assert r.status_code == 410 and r.json()["detail"] == MSG_DA_DONG
    mo = await client.get(f"/exam/cuoi-ky/{kq_an['de_id']}", headers=an.h)
    assert mo.status_code == 200 and mo.json()["ket_qua"] == kq_an
    # Quyết định sau QC26-02: bài dở mà mã đã đóng KHÔNG còn trong lịch sử (không có gì để xem / nộp / xoá).
    ls = (await client.get("/exam/cuoi-ky", headers=chi.h)).json()["de"]
    assert ls == []


@pytest.mark.parametrize("vai", ["giao_vien", "chuyen_gia", "admin"])
async def test_vai_cms_khong_dung_duoc_duong_hoc_sinh_vao_va_nop(client, tb, vai):
    """Vì sao: giáo viên mở đề qua `/vao` sẽ tạo bài làm và hiện trong bảng kết quả như một học sinh."""
    gv = await _tk(client, vai)
    g = await _giao(client, gv)
    r = await _vao(client, gv, g.ma)
    assert r.status_code == 403 and r.json()["detail"] == MSG_CHI_HS
    r = await _nop(client, gv, "x", {})
    assert r.status_code == 403 and r.json()["detail"] == MSG_CHI_HS
    b = (await client.get(f"/de-giao/{g.id}/ket-qua", headers=gv.h)).json()
    assert b["hoc_sinh"] == []


async def test_bang_ket_qua_xep_ten_a_z_bo_dau_khong_phan_biet_hoa_thuong(client, tb):
    """Vì sao: so mã Unicode thô đẩy "Ánh" / "Đức" xuống sau "Zung"."""
    gv = await _tk(client, "giao_vien")
    g = await _giao(client, gv)
    ten = ["Zung", "Ánh", "bình", "Đức", "An", "Dũng"]
    for t in ten:
        await _vao_ok(client, await _tk(client, ten=t), g.ma)
    b = (await client.get(f"/de-giao/{g.id}/ket-qua", headers=gv.h)).json()
    assert [h["ten"] for h in b["hoc_sinh"]] == ["An", "Ánh", "bình", "Đức", "Dũng", "Zung"]


async def test_giao_vien_khong_xem_bai_hoc_sinh_thuoc_de_giao_cua_nguoi_khac(client, tb):
    """Vì sao: `uid` của em ở mã của Minh không được dò ra qua mã của Hoa."""
    hoa, minh, an = await _tk(client, "giao_vien"), await _tk(client, "giao_vien"), await _tk(client, ten="An")
    g_hoa, g_minh = await _giao(client, hoa), await _giao(client, minh)
    await _vao_ok(client, an, g_minh.ma)
    r = await client.get(f"/de-giao/{g_hoa.id}/bai/{an.id}", headers=hoa.h)
    assert r.status_code == 404
    r = await client.get(f"/de-giao/{g_minh.id}/bai/{an.id}", headers=hoa.h)
    assert r.status_code == 404 and r.json()["detail"] == MSG_KHONG_THAY_DE


@pytest.mark.parametrize("duong", ["99999999999999999999", "-1", "0"])
async def test_id_de_giao_cuc_doan_khong_gay_500(client, tb, duong):
    gv = await _tk(client, "giao_vien")
    for p in (f"/de-giao/{duong}", f"/de-giao/{duong}/ket-qua", f"/de-giao/{duong}/bai/{duong}"):
        assert (await client.get(p, headers=gv.h)).status_code in (404, 422), p
    assert (await client.post(f"/de-giao/{duong}/dong", headers=gv.h)).status_code in (404, 422)
    assert (await client.post(f"/de-giao/{duong}/cap-ma", headers=gv.h)).status_code in (404, 422)
    assert (await client.delete(f"/de-giao/{duong}", headers=gv.h)).status_code in (404, 422)


@pytest.mark.parametrize("total", ["12", True, 1.5, None, [], {}, -3])
async def test_so_cau_sai_kieu_bi_422_va_khong_goi_kho(client, tb, total):
    gv = await _tk(client, "giao_vien")
    r = await client.post("/de-giao/xem-truoc", headers=gv.h, json={"exam": "CK1", "total": total})
    assert r.status_code == 422, r.text
    assert tb.so_lan_goi() == 0


@pytest.mark.parametrize("role", ["", "HOC_SINH", "admin", "chuyen_gia", "giao_vien", " hoc_sinh", 1])
async def test_dang_ky_voi_vai_la_bi_400_hoac_422_va_khong_tao_tai_khoan(client, role):
    import uuid
    email = f"qc-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={"email": email, "password": "matkhau123", "name": "X", "role": role})
    assert r.status_code in (400, 422), r.text
    r2 = await client.post("/auth/login", json={"email": email, "password": "matkhau123"})
    assert r2.status_code in (400, 401, 404), "tài khoản đã bị tạo dù đăng ký bị từ chối"
