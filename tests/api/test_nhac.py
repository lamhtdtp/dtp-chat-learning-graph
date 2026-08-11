"""Lời nhắc chủ động của trợ lý (lát 4, phương án D).

Điểm cần giữ: nội dung sinh MỘT LẦN lúc biên soạn rồi cache — đường phục vụ học
sinh KHÔNG được gọi LLM, nếu không mỗi lần cuộn qua khái niệm là một lượt.
"""
import json
import uuid

from app.db.models import CurriculumTopic, Grade, Subject, TopicContent
from app.lessons import nhac as nhac_svc


async def _auth(client, role: str = "hoc_sinh") -> dict:
    email = f"nhac-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": role})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _seed(session, *, nhac_json: str = "[]", khai_niem: str = "<p>Số nguyên tố có hai ước.</p>") -> int:
    subj = Subject(name=f"MonNhac-{uuid.uuid4().hex[:6]}")
    grade = Grade(name=f"KhoiNhac-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, grade])
    await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id, mach_noi_dung="Số tự nhiên",
                        don_vi_kien_thuc="Số nguyên tố. Hợp số", order_index=0)
    session.add(t)
    await session.flush()
    session.add(TopicContent(topic_id=t.id, khai_niem=khai_niem, nhac_json=nhac_json,
                             trang_thai="published"))
    tid = t.id                      # lấy TRƯỚC commit — sau commit là MissingGreenlet
    await session.commit()
    return tid


_MOT_NHAC = json.dumps([{"moc": "khai_niem", "hoi": "15 là số nguyên tố hay hợp số?",
                         "dap": ["Hợp số", "Số nguyên tố"], "dung": 0, "giai": "15 = 3 · 5."}])


async def test_lesson_tra_nhac_da_cache_va_khong_goi_llm(client, session, mocker):
    gw = mocker.patch("app.lessons.nhac.gateway.complete", mocker.AsyncMock())
    h = await _auth(client)
    tid = await _seed(session, nhac_json=_MOT_NHAC)
    r = (await client.get(f"/lessons/{tid}", headers=h)).json()
    assert r["nhac"][0]["hoi"].startswith("15 là số nguyên tố")
    assert r["nhac"][0]["dung"] == 0
    assert gw.await_count == 0      # đây mới là điều đáng giữ


async def test_nhac_json_hong_thi_im_lang_chu_khong_sap_bai_hoc(client, session):
    """Nhắc là tính năng phụ — JSON hỏng không được kéo sập trang bài học."""
    h = await _auth(client)
    tid = await _seed(session, nhac_json="{ hỏng }")
    r = await client.get(f"/lessons/{tid}", headers=h)
    assert r.status_code == 200 and r.json()["nhac"] == []


def test_parse_bo_muc_khong_biet_dap_an_nao_dung():
    """Thiếu `dung` thì học sinh bấm chọn mà không được biết đúng/sai -> vô nghĩa."""
    thieu = '{"nhac": [{"hoi": "?", "dap": ["a", "b"], "giai": "x"}]}'
    assert nhac_svc._parse(thieu) == []
    ngoai_bien = '{"nhac": [{"hoi": "?", "dap": ["a", "b"], "dung": 5}]}'
    assert nhac_svc._parse(ngoai_bien) == []


def test_parse_lay_dung_mot_muc_va_chuan_hoa_moc():
    raw = ('{"nhac": [{"moc": "bịa", "hoi": "Câu 1?", "dap": ["a", "b"], "dung": 1, "giai": "g"},'
           '{"moc": "khai_niem", "hoi": "Câu 2?", "dap": ["c", "d"], "dung": 0}]}')
    out = nhac_svc._parse(raw)
    # Mỗi mốc là một lần cắt ngang mạch đọc -> chốt 1 lời nhắc, mốc lạ về khai_niem
    assert len(out) == 1 and out[0]["moc"] == "khai_niem" and out[0]["hoi"] == "Câu 1?"


async def test_khong_co_khai_niem_thi_khong_goi_llm(session, mocker):
    """Chưa soạn khái niệm thì chẳng có gì để kiểm tra hiểu — đừng đốt token."""
    gw = mocker.patch("app.lessons.nhac.gateway.complete", mocker.AsyncMock())
    tid = await _seed(session, khai_niem="")
    assert await nhac_svc.generate_nhac(session, tid) == []
    assert gw.await_count == 0


async def test_cms_tach_hai_nguyen_nhan_that_bai(client, session, mocker):
    """Thiếu Khái niệm là việc chuyên gia phải làm; AI trả hỏng là việc thử lại.
    Gộp một câu thì chuyên gia đi sửa nhầm chỗ."""
    gv = await _auth(client, "giao_vien")

    tid_rong = await _seed(session, khai_niem="")
    r1 = await client.post(f"/cms/topics/{tid_rong}/nhac/generate", headers=gv)
    assert r1.status_code == 400 and "Khái niệm" in r1.json()["detail"]

    mocker.patch("app.lessons.nhac.gateway.complete", mocker.AsyncMock(return_value="{ rác }"))
    tid = await _seed(session)
    r2 = await client.post(f"/cms/topics/{tid}/nhac/generate", headers=gv)
    assert r2.status_code == 502


async def test_cms_sinh_nhac_can_quyen_tac_gia(client, session, mocker):
    mocker.patch("app.lessons.nhac.gateway.complete",
                 mocker.AsyncMock(return_value=f'{{"nhac": {_MOT_NHAC}}}'))
    tid = await _seed(session)
    hs = await _auth(client, "hoc_sinh")
    assert (await client.post(f"/cms/topics/{tid}/nhac/generate", headers=hs)).status_code == 403

    gv = await _auth(client, "giao_vien")
    r = await client.post(f"/cms/topics/{tid}/nhac/generate", headers=gv)
    assert r.status_code == 200 and r.json()["nhac"][0]["dung"] == 0
    # đã cache -> học sinh đọc bài là có ngay
    assert (await client.get(f"/lessons/{tid}", headers=hs)).json()["nhac"][0]["dap"] == ["Hợp số", "Số nguyên tố"]
