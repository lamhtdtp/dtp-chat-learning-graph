import uuid


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
