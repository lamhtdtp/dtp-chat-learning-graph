import io
import json
import uuid

from app.db.models import CurriculumTopic, Grade, Subject


async def _auth(client, role="giao_vien") -> dict:
    email = f"cms-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "GV", "role": role})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _seed(session):
    mon, khoi = f"MonC-{uuid.uuid4().hex[:6]}", f"KhoiC-{uuid.uuid4().hex[:6]}"
    subj = Subject(name=mon); grade = Grade(name=khoi)
    session.add_all([subj, grade]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id,
                        mach_noi_dung="Số tự nhiên", don_vi_kien_thuc="Số nguyên tố", order_index=0)
    session.add(t); await session.flush()
    return mon, khoi, t.id


async def test_cms_chi_tac_gia(client, session):
    hs = await _auth(client, "hoc_sinh")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    assert (await client.get(f"/cms/curriculum?mon={mon}&khoi={khoi}", headers=hs)).status_code == 403
    assert (await client.get(f"/cms/topics/{tid}", headers=hs)).status_code == 403


async def test_cms_save_va_completeness(client, session):
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    # trống -> 0/4
    t0 = (await client.get(f"/cms/topics/{tid}", headers=gv)).json()
    assert t0["completeness"]["done"] == 0 and t0["trang_thai"] == "draft"
    # lưu 2 phần -> 2/4, xuất bản
    r = await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>Số nguyên tố…</p>",
        "minh_hoa": [{"type": "video", "url": "", "caption": "", "source": "ai"}],
        "vi_du": [], "day": {"muc_tieu": "MT"}, "nguon": None, "trang_thai": "published"})
    assert r.status_code == 200 and r.json()["completeness"]["done"] == 2
    # HS thấy nội dung đã xuất bản qua /lessons
    hs = await _auth(client, "hoc_sinh")
    les = (await client.get(f"/lessons/{tid}", headers=hs)).json()
    assert les["trang_thai"] == "published" and les["khai_niem"] == "<p>Số nguyên tố…</p>"


async def test_cms_trang_thai_khong_hop_le_400(client, session):
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    r = await client.put(f"/cms/topics/{tid}", headers=gv, json={"trang_thai": "xong"})
    assert r.status_code == 400


async def test_cms_nhap_chua_xuat_ban_hs_khong_thay(client, session):
    gv = await _auth(client, "giao_vien")
    hs = await _auth(client, "hoc_sinh")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>nháp</p>", "minh_hoa": [], "vi_du": [], "trang_thai": "draft"})
    les = (await client.get(f"/lessons/{tid}", headers=hs)).json()
    assert les["trang_thai"] == "chua_bien_soan" and les["khai_niem"] == ""


async def test_cms_ai_ingest(client, session, mocker):
    mocker.patch("app.lessons.ingest.gateway.complete", mocker.AsyncMock(return_value=json.dumps({
        "khai_niem": "<p>AI nháp</p>",
        "vi_du": [{"de": "VD1", "giai": "GIẢI1"}],
    }, ensure_ascii=False)))
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    r = await client.post(f"/cms/topics/{tid}/ai-ingest", headers=gv, json={"nguon": "trích SGK"})
    body = r.json()
    assert body["khai_niem"] == "<p>AI nháp</p>" and body["vi_du"][0]["de"] == "VD1"
    # ingest KHÔNG tự lưu — topic vẫn trống
    assert (await client.get(f"/cms/topics/{tid}", headers=gv)).json()["completeness"]["done"] == 0


async def test_cms_upload_video(client, session):
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    files = {"file": ("clip.mp4", io.BytesIO(b"\x00\x01fakevideo"), "video/mp4")}
    r = await client.post(f"/cms/topics/{tid}/video?caption=Minh+hoa", headers=gv, files=files)
    assert r.status_code == 200
    mh = r.json()["minh_hoa"]
    assert mh[-1]["type"] == "video" and mh[-1]["source"] == "expert"
    assert mh[-1]["url"].startswith("/video/files/")
    # định dạng sai -> 400
    bad = {"file": ("x.txt", io.BytesIO(b"abc"), "text/plain")}
    assert (await client.post(f"/cms/topics/{tid}/video", headers=gv, files=bad)).status_code == 400
