import uuid

from sqlalchemy import select

from app.db.models import User


async def _reg(client, role: str = "hoc_sinh"):
    email = f"adm-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": role})
    return email, {"Authorization": f"Bearer {r.json()['token']}"}


async def _make_admin(client, session):
    email, h = await _reg(client)
    u = await session.scalar(select(User).where(User.email == email))
    u.role = "admin"
    await session.commit()
    return h, u


async def test_admin_yeu_cau_quyen(client):
    _, h = await _reg(client)  # học sinh thường
    assert (await client.get("/admin/users", headers=h)).status_code == 403


async def test_admin_liet_ke_user_kem_tien_do(client, session):
    h, _ = await _make_admin(client, session)
    email2, _ = await _reg(client)
    rows = (await client.get("/admin/users", headers=h)).json()
    assert email2 in [r["email"] for r in rows]
    assert {"id", "email", "role", "is_active", "hoan_thanh", "dang_hoc"} <= set(rows[0])


async def test_admin_khoa_user_chan_moi_truy_cap(client, session):
    h, _ = await _make_admin(client, session)
    email, hu = await _reg(client)
    u = await session.scalar(select(User).where(User.email == email))
    r = await client.post(f"/admin/users/{u.id}/active", json={"active": False}, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is False
    # user bị khoá -> get_current_user chặn 403 ở mọi endpoint đã xác thực
    assert (await client.get("/curriculum", headers=hu)).status_code == 403


async def test_admin_doi_vai_tro_va_han_muc(client, session):
    h, _ = await _make_admin(client, session)
    email, _ = await _reg(client)
    u = await session.scalar(select(User).where(User.email == email))
    r = await client.post(f"/admin/users/{u.id}/settings",
                          json={"role": "giao_vien", "daily_limit": 50}, headers=h)
    body = r.json()
    assert body["role"] == "giao_vien" and body["daily_limit_override"] == 50
