import json
import uuid

from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, Subject, TopicContent, User


async def _auth(client) -> dict:
    email = f"les-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _seed_curriculum(session):
    """Tạo môn/khối/đơn vị RIÊNG (tên duy nhất) để test cô lập. Trả (mon, khoi, topic_ids)."""
    mon, khoi = f"MonTest-{uuid.uuid4().hex[:6]}", f"Khoi-{uuid.uuid4().hex[:6]}"
    subj = Subject(name=mon); grade = Grade(name=khoi)
    session.add_all([subj, grade]); await session.flush()
    topics = []
    units = [("Số tự nhiên", "Tập hợp số tự nhiên"),
             ("Số tự nhiên", "Tập hợp số tự nhiên"),   # trùng -> phải bị khử
             ("Số tự nhiên", "Số nguyên tố và hợp số"),
             ("Số nguyên", "Số nguyên âm")]
    for i, (m, d) in enumerate(units):
        t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id,
                            mach_noi_dung=m, don_vi_kien_thuc=d, order_index=i)
        session.add(t); topics.append(t)
    await session.flush()
    return mon, khoi, topics


async def test_curriculum_gom_mach_va_khu_trung(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    await session.commit()
    groups = (await client.get(f"/curriculum?mon={mon}&khoi={khoi}", headers=h)).json()
    assert [g["mach"] for g in groups] == ["Số tự nhiên", "Số nguyên"]
    st = next(g for g in groups if g["mach"] == "Số tự nhiên")
    assert len(st["dv"]) == 2            # 3 dòng nhưng 1 trùng -> 2 đơn vị
    assert st["dv"][0]["trang_thai"] == "chua" and st["dv"][0]["co_noi_dung"] is False


async def test_lesson_chua_bien_soan_va_co_noi_dung(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    tid = topics[2].id
    await session.commit()
    # chưa biên soạn
    r = (await client.get(f"/lessons/{tid}", headers=h)).json()
    assert r["trang_thai"] == "chua_bien_soan" and r["khai_niem"] == "" and r["minh_hoa"] == []
    # thêm nội dung -> trả về đủ 4 phần
    session.add(TopicContent(topic_id=tid, khai_niem="<p>ĐN</p>",
        minh_hoa_json=json.dumps([{"type": "video", "source": "ai"}]),
        vi_du_json=json.dumps([{"de": "VD", "giai": "GI"}]), trang_thai="published"))
    await session.commit()
    r2 = (await client.get(f"/lessons/{tid}", headers=h)).json()
    assert r2["khai_niem"] == "<p>ĐN</p>" and r2["vi_du"][0]["de"] == "VD"
    assert r2["minh_hoa"][0]["source"] == "ai" and r2["trang_thai"] == "published"


async def test_progress_upsert_va_me(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    tid = topics[2].id
    await session.commit()
    # đánh dấu Đạt
    r = await client.post("/progress", json={"topic_id": tid, "trang_thai": "dat"}, headers=h)
    assert r.status_code == 200 and r.json()["trang_thai"] == "dat"
    me = (await client.get(f"/progress/me?mon={mon}&khoi={khoi}", headers=h)).json()
    assert me["dat"] == 1 and me["tong"] == 3 and 0 < me["overall"] <= 100
    # đơn vị vừa đánh dấu hiện 'dat' trong nhóm
    flat = [d for g in me["mach"] for d in g["dv"]]
    assert any(d["topic_id"] == tid and d["trang_thai"] == "dat" for d in flat)


async def test_progress_hop_le(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    tid0 = topics[0].id  # lấy id TRƯỚC commit (sau commit ORM bị expire)
    await session.commit()
    assert (await client.post("/progress", json={"topic_id": tid0, "trang_thai": "bay"}, headers=h)).status_code == 400
    assert (await client.post("/progress", json={"topic_id": 999999, "trang_thai": "dat"}, headers=h)).status_code == 404
    assert (await client.get("/lessons/999999", headers=h)).status_code == 404
