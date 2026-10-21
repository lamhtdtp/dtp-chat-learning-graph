import uuid

import pytest


def _email() -> str:
    return f"hs-{uuid.uuid4().hex[:8]}@vd.vn"


async def test_register_tra_ve_token(client):
    r = await client.post("/auth/register", json={
        "email": _email(), "password": "matkhau123", "name": "An", "role": "hoc_sinh",
    })
    assert r.status_code == 200
    assert r.json()["token"]


async def test_register_email_trung_bi_409(client):
    email = _email()
    body = {"email": email, "password": "x", "name": "A", "role": "hoc_sinh"}
    assert (await client.post("/auth/register", json=body)).status_code == 200
    r2 = await client.post("/auth/register", json=body)
    assert r2.status_code == 409


async def test_login_dung_mat_khau(client):
    email = _email()
    await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "A", "role": "hoc_sinh"})

    r = await client.post("/auth/login", json={"email": email, "password": "matkhau123"})
    assert r.status_code == 200
    assert r.json()["token"]


async def test_login_sai_mat_khau_bi_401(client):
    email = _email()
    await client.post("/auth/register", json={
        "email": email, "password": "dung", "name": "A", "role": "hoc_sinh"})

    r = await client.post("/auth/login", json={"email": email, "password": "sai"})
    assert r.status_code == 401


async def test_login_email_khong_ton_tai_bi_401(client):
    r = await client.post("/auth/login", json={"email": _email(), "password": "x"})
    assert r.status_code == 401


# ── US-26 KB 38: tự đăng ký chỉ tạo được học sinh ───────────────────────────
MSG_CHI_HOC_SINH = "Chỉ đăng ký được tài khoản học sinh. Tài khoản giáo viên do quản trị viên cấp."


async def test_dang_ky_khong_ghi_vai_thi_tao_hoc_sinh(client):
    """KB 38: không ghi `role` -> học sinh (màn hình đăng ký không còn lựa chọn vai)."""
    r = await client.post("/auth/register", json={
        "email": _email(), "password": "matkhau123", "name": "An"})
    assert r.status_code == 200 and r.json()["role"] == "hoc_sinh"


async def test_dang_ky_ghi_ro_hoc_sinh_van_duoc(client):
    r = await client.post("/auth/register", json={
        "email": _email(), "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    assert r.status_code == 200 and r.json()["role"] == "hoc_sinh"


@pytest.mark.parametrize("vai", ["giao_vien", "chuyen_gia", "admin", "GIAO_VIEN", "hocsinh", "x"])
async def test_dang_ky_kem_vai_khac_hoc_sinh_bi_tu_choi_400(client, vai):
    """KB 38: gửi vai khác học sinh thì BỊ TỪ CHỐI (không lặng lẽ bỏ qua) để bên gọi biết rõ,
    và KHÔNG có tài khoản nào được tạo — kể cả tài khoản học sinh."""
    email = _email()
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "Z", "role": vai})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == MSG_CHI_HOC_SINH
    # Không tạo gì: đăng nhập bằng đúng thông tin đó phải thất bại.
    r2 = await client.post("/auth/login", json={"email": email, "password": "matkhau123"})
    assert r2.status_code == 401


async def test_dang_ky_vai_giao_vien_bi_chan_thi_khong_tao_de_giao_duoc(client):
    """KB 38 (dòng cuối): người đó không có tài khoản giáo viên nên không tạo được đề giao."""
    email = _email()
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "Z", "role": "giao_vien"})
    assert r.status_code == 400
    # Đăng ký lại như học sinh (cùng email còn trống vì lần trước không tạo gì) -> vẫn là học sinh.
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "Z"})
    assert r.status_code == 200 and r.json()["role"] == "hoc_sinh"
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r = await client.post("/de-giao/xem-truoc", headers=h, json={"exam": "CK1"})
    assert r.status_code == 403 and r.json()["detail"] == "Bạn không có quyền giao đề"
