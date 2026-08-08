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

    r = await client.get(f"/admin/users/{me['id']}/result", headers=gv)
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
    assert (await client.get(f"/admin/users/{me['id']}/result", headers=hs)).status_code == 403
    gv = (await _reg(client, "giao_vien"))[1]
    assert (await client.get(f"/admin/users/{me['id']}/result", headers=gv)).status_code == 200


async def test_result_chi_cho_tai_khoan_hoc_sinh(client, session):
    """GV/QT không có kết quả học tập -> 400 rõ ràng, không trả bảng rỗng."""
    gv_email, gv = await _reg(client, "giao_vien")
    me_gv = (await client.get("/auth/me", headers=gv)).json()
    r = await client.get(f"/admin/users/{me_gv['id']}/result", headers=gv)
    assert r.status_code == 400 and "học sinh" in r.json()["detail"]


async def test_tao_tai_khoan_chuyen_gia_va_quan_tri(client, session):
    """Admin tạo được giáo viên + admin; /auth/register vẫn KHÔNG cho chọn admin."""
    adm, _ = await _make_admin(client, session)
    em = f"gv-{uuid.uuid4().hex[:6]}@vd.vn"
    r = await client.post("/admin/users", headers=adm, json={
        "email": em, "password": "matkhau123", "name": "Cô A", "role": "giao_vien"})
    assert r.status_code == 201 and r.json()["role"] == "giao_vien"
    # Tài khoản mới đăng nhập được ngay
    assert (await client.post("/auth/login", json={"email": em, "password": "matkhau123"})).status_code == 200
    # Trùng email -> 409
    r2 = await client.post("/admin/users", headers=adm, json={
        "email": em, "password": "matkhau123", "name": "X", "role": "admin"})
    assert r2.status_code == 409


async def test_tao_tai_khoan_chan_hoc_sinh_va_nguoi_khong_phai_admin(client, session):
    adm, _ = await _make_admin(client, session)
    # Không tạo học sinh ở đây — các em tự đăng ký.
    r = await client.post("/admin/users", headers=adm, json={
        "email": f"x-{uuid.uuid4().hex[:6]}@vd.vn", "password": "matkhau123",
        "name": "B", "role": "hoc_sinh"})
    assert r.status_code == 400
    # Giáo viên KHÔNG được tạo tài khoản (chống tự nhân bản quyền).
    _, gv = await _reg(client, "giao_vien")
    r2 = await client.post("/admin/users", headers=gv, json={
        "email": f"y-{uuid.uuid4().hex[:6]}@vd.vn", "password": "matkhau123",
        "name": "C", "role": "giao_vien"})
    assert r2.status_code == 403


async def test_tao_tai_khoan_mat_khau_ngan_bi_chan(client, session):
    adm, _ = await _make_admin(client, session)
    r = await client.post("/admin/users", headers=adm, json={
        "email": f"z-{uuid.uuid4().hex[:6]}@vd.vn", "password": "123", "name": "D", "role": "admin"})
    assert r.status_code == 422


async def test_overview_thong_ke_hoc_tap(client, session, mocker):
    """Tile + nhịp theo ngày (có bơm ngày trống) + đơn vị đuối nhất."""
    import json as _json
    from datetime import date
    from app.db.models import CurriculumTopic, Grade, Subject, TopicContent

    gv = (await _reg(client, "giao_vien"))[1]
    hs = (await _reg(client, "hoc_sinh"))[1]
    subj = Subject(name=f"M-{uuid.uuid4().hex[:6]}"); gr = Grade(name=f"K-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="Số tự nhiên",
                        don_vi_kien_thuc="Số nguyên tố", order_index=0)
    session.add(t); await session.flush()
    tid = t.id
    quiz = [{"q": "1+1?", "o": ["1", "2"], "a": 1, "lv": "de"}]
    session.add(TopicContent(topic_id=tid, khai_niem="<p>x</p>", trang_thai="published",
                             quiz_json=_json.dumps(quiz)))
    await session.commit()

    for _ in range(3):   # 3 lượt SAI -> đủ ngưỡng toi_thieu, 100% trượt
        await client.post("/quiz/submit", headers=hs, json={"topic_id": tid, "answers": [0]})

    b = (await client.get("/admin/overview?ngay=7", headers=gv)).json()
    assert b["tong"]["luot_lam"] >= 3 and b["tong"]["hoc_sinh"] >= 1
    # Đúng `ngay` điểm, ngày không có lượt vẫn có mặt với 0 — đường không nối tắt.
    assert len(b["hoat_dong"]) == 7
    assert b["hoat_dong"][-1]["ngay"] == str(date.today())
    assert all("so_lan" in x for x in b["hoat_dong"])
    kho = next(x for x in b["kho_nhat"] if x["topic_id"] == tid)
    assert kho["so_lan"] == 3 and kho["ty_le_truot"] == 100


async def test_overview_bo_don_vi_qua_it_luot(client, session):
    """1 lượt trượt lẻ KHÔNG được nhảy lên đầu bảng với '100% trượt'."""
    import json as _json
    from app.db.models import CurriculumTopic, Grade, Subject, TopicContent

    gv = (await _reg(client, "giao_vien"))[1]
    hs = (await _reg(client, "hoc_sinh"))[1]
    subj = Subject(name=f"M-{uuid.uuid4().hex[:6]}"); gr = Grade(name=f"K-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                        don_vi_kien_thuc="Chỉ một lượt", order_index=0)
    session.add(t); await session.flush()
    tid = t.id
    session.add(TopicContent(topic_id=tid, trang_thai="published",
                             quiz_json=_json.dumps([{"q": "?", "o": ["a", "b"], "a": 1, "lv": "de"}])))
    await session.commit()
    await client.post("/quiz/submit", headers=hs, json={"topic_id": tid, "answers": [0]})

    b = (await client.get("/admin/overview", headers=gv)).json()
    assert tid not in [x["topic_id"] for x in b["kho_nhat"]]
