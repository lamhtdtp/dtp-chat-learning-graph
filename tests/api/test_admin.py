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


async def test_ket_qua_hoc_sinh_luu_tung_lan(client, session, mocker):
    """Mỗi lần nộp quiz là một dòng — làm lại KHÔNG ghi đè, để thấy tiến bộ."""
    import json as _json
    from app.db.models import CurriculumTopic, Grade, Subject, TopicContent

    gv = (await _reg(client, "giao_vien"))[1]
    hs = (await _reg(client, "hoc_sinh"))[1]
    subj = Subject(name=f"M-{uuid.uuid4().hex[:6]}"); gr = Grade(name=f"K-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="Số tự nhiên",
                        don_vi_kien_thuc="Số nguyên tố", order_index=0)
    session.add(t); await session.flush()
    tid = t.id
    quiz = [{"q": "1+1?", "o": ["1", "2"], "a": 1, "lv": "de"},
            {"q": "2+2?", "o": ["4", "5"], "a": 0, "lv": "de"}]
    session.add(TopicContent(topic_id=tid, khai_niem="<p>x</p>", trang_thai="published",
                             quiz_json=_json.dumps(quiz)))
    await session.commit()

    me = (await client.get("/auth/me", headers=hs)).json()
    # Lần 1 sai hết -> 0/2, không đạt. Lần 2 đúng hết -> 2/2, đạt.
    r1 = await client.post("/quiz/submit", headers=hs, json={"topic_id": tid, "answers": [0, 1]})
    r2 = await client.post("/quiz/submit", headers=hs, json={"topic_id": tid, "answers": [1, 0]})
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    r = await client.get(f"/admin/users/{me['id']}/ket-qua", headers=gv)
    assert r.status_code == 200
    b = r.json()
    assert b["tong_lan"] == 2 and b["so_lan_dat"] == 1        # 2 lần, 1 lần đạt
    assert [x["diem"] for x in b["lan"]] == [2, 0]            # mới -> cũ
    g = b["theo_don_vi"][0]
    assert g["so_lan"] == 2 and g["tot_nhat"] == 100 and g["gan_nhat"] == 100 and g["dat"] is True


async def test_ket_qua_hoc_sinh_chan_hoc_sinh_khac_xem(client, session):
    """Học sinh KHÔNG được xem kết quả của người khác; giáo viên thì được."""
    hs = (await _reg(client, "hoc_sinh"))[1]
    me = (await client.get("/auth/me", headers=hs)).json()
    assert (await client.get(f"/admin/users/{me['id']}/ket-qua", headers=hs)).status_code == 403
    gv = (await _reg(client, "giao_vien"))[1]
    assert (await client.get(f"/admin/users/{me['id']}/ket-qua", headers=gv)).status_code == 200
