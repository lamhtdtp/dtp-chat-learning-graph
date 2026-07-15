import uuid
from types import SimpleNamespace

from sqlalchemy import select

from app.db.models import User
from app.main import app


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


async def test_admin_liet_ke_user_kem_thong_ke(client, session):
    h, _ = await _make_admin(client, session)
    email2, _ = await _reg(client)
    rows = (await client.get("/admin/users", headers=h)).json()
    assert email2 in [r["email"] for r in rows]
    assert {"id", "email", "role", "is_active", "sessions", "questions", "today"} <= set(rows[0])


async def test_admin_khoa_user_chan_moi_truy_cap(client, session):
    h, _ = await _make_admin(client, session)
    email, hu = await _reg(client)
    u = await session.scalar(select(User).where(User.email == email))
    r = await client.post(f"/admin/users/{u.id}/active", json={"active": False}, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is False
    # user bị khoá -> get_current_user chặn 403 ở mọi endpoint
    assert (await client.get("/sessions", headers=hu)).status_code == 403


async def test_admin_doi_vai_tro_va_han_muc(client, session):
    h, _ = await _make_admin(client, session)
    email, _ = await _reg(client)
    u = await session.scalar(select(User).where(User.email == email))
    r = await client.post(f"/admin/users/{u.id}/settings",
                          json={"role": "giao_vien", "daily_limit": 50}, headers=h)
    body = r.json()
    assert body["role"] == "giao_vien" and body["daily_limit_override"] == 50


async def test_admin_tracking_cau_hoi_cua_user(client, session, mocker):
    h, _ = await _make_admin(client, session)
    email, hu = await _reg(client)
    uid = (await session.scalar(select(User).where(User.email == email))).id  # giữ id (chat sẽ commit -> expire ORM)
    # user thường gửi 1 câu hỏi (mock graph + bỏ qua giới hạn)
    app.state.graph = SimpleNamespace(ainvoke=mocker.AsyncMock(
        return_value={"answer": "Đáp", "intent": "hoi_dap", "retrieved": []}))
    mocker.patch("app.api.chat.llm_cache.incr_quota", side_effect=lambda key, ttl: 1)
    await client.post("/chat", json={"message": "Số nguyên tố là gì?"}, headers=hu)

    msgs = (await client.get(f"/admin/users/{uid}/messages", headers=h)).json()
    assert any(m["content"] == "Số nguyên tố là gì?" for m in msgs)


async def test_admin_bieu_do_luot_hoi_theo_ngay(client, session, mocker):
    from datetime import datetime, timezone
    h, _ = await _make_admin(client, session)
    _, hu = await _reg(client)
    app.state.graph = SimpleNamespace(ainvoke=mocker.AsyncMock(
        return_value={"answer": "A", "intent": "hoi_dap", "retrieved": []}))
    mocker.patch("app.api.chat.llm_cache.incr_quota", side_effect=lambda key, ttl: 1)
    await client.post("/chat", json={"message": "Câu hỏi hôm nay"}, headers=hu)

    today = datetime.now(timezone.utc).date().isoformat()
    stats = (await client.get("/admin/stats/daily?days=7", headers=h)).json()
    assert any(s["date"] == today and s["count"] >= 1 for s in stats)
    # yêu cầu quyền admin
    _, hs = await _reg(client)
    assert (await client.get("/admin/stats/daily", headers=hs)).status_code == 403
