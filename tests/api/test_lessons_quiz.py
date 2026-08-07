import json
import uuid

from app.db.models import CurriculumTopic, Grade, Subject


async def _auth(client, role="hoc_sinh") -> dict:
    email = f"quiz-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": role})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _seed(session):
    mon, khoi = f"MonQ-{uuid.uuid4().hex[:6]}", f"KhoiQ-{uuid.uuid4().hex[:6]}"
    subj = Subject(name=mon); grade = Grade(name=khoi)
    session.add_all([subj, grade]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id,
                        mach_noi_dung="Số tự nhiên", don_vi_kien_thuc="Số nguyên tố", order_index=0)
    session.add(t); await session.flush()
    return t.id


_QUIZ_JSON = json.dumps({"quiz": [
    {"q": "Số nào là số nguyên tố?", "o": ["9", "15", "13", "21"], "a": 2, "lv": "de", "giai": "13 chỉ có 2 ước."},
    {"q": "Số 1 là?", "o": ["Số nguyên tố", "Hợp số", "Không phải cả hai"], "a": 2, "lv": "de", "giai": "1 có 1 ước."},
]}, ensure_ascii=False)


async def test_generate_quiz_chi_tac_gia(client, session, mocker):
    mocker.patch("app.lessons.quiz.gateway.complete", mocker.AsyncMock(return_value=_QUIZ_JSON))
    hs = await _auth(client, "hoc_sinh")
    gv = await _auth(client, "giao_vien")
    tid = await _seed(session)
    await session.commit()
    # học sinh -> 403
    assert (await client.post(f"/lessons/{tid}/quiz/generate", headers=hs)).status_code == 403
    # giáo viên -> sinh + cache
    r = await client.post(f"/lessons/{tid}/quiz/generate", headers=gv)
    assert r.status_code == 200 and r.json()["so_cau"] == 2


async def test_hoc_sinh_khong_thay_dap_an(client, session, mocker):
    mocker.patch("app.lessons.quiz.gateway.complete", mocker.AsyncMock(return_value=_QUIZ_JSON))
    gv = await _auth(client, "giao_vien")
    hs = await _auth(client, "hoc_sinh")
    tid = await _seed(session)
    await session.commit()
    await client.post(f"/lessons/{tid}/quiz/generate", headers=gv)
    # xuất bản nội dung để HS thấy được (quiz giữ nguyên, PUT không đụng quiz)
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>ND</p>", "minh_hoa": [], "vi_du": [], "trang_thai": "published"})
    # HS: quiz có đề + phương án, KHÔNG có 'a'/'giai'
    hs_lesson = (await client.get(f"/lessons/{tid}", headers=hs)).json()
    assert hs_lesson["co_quiz"] is True and len(hs_lesson["quiz"]) == 2
    assert "a" not in hs_lesson["quiz"][0] and "giai" not in hs_lesson["quiz"][0]
    # GV: thấy đủ đáp án
    gv_lesson = (await client.get(f"/lessons/{tid}", headers=gv)).json()
    assert gv_lesson["quiz"][0]["a"] == 2


async def test_submit_cham_diem_va_tien_do(client, session, mocker):
    mocker.patch("app.lessons.quiz.gateway.complete", mocker.AsyncMock(return_value=_QUIZ_JSON))
    gv = await _auth(client, "giao_vien")
    hs = await _auth(client, "hoc_sinh")
    tid = await _seed(session)
    await session.commit()
    await client.post(f"/lessons/{tid}/quiz/generate", headers=gv)
    # đúng cả 2 -> đạt -> tiến độ 'dat'
    r = await client.post("/quiz/submit", json={"topic_id": tid, "answers": [2, 2]}, headers=hs)
    body = r.json()
    assert body["diem"] == 2 and body["tong"] == 2 and body["dat_yeu_cau"] is True
    assert body["trang_thai"] == "dat" and body["ket_qua"][0]["dung"] is True
    # làm lại sai -> KHÔNG hạ cấp khỏi 'dat'
    r2 = await client.post("/quiz/submit", json={"topic_id": tid, "answers": [0, 0]}, headers=hs)
    assert r2.json()["dat_yeu_cau"] is False and r2.json()["trang_thai"] == "dat"


async def test_submit_khi_chua_co_quiz_400(client, session):
    hs = await _auth(client, "hoc_sinh")
    tid = await _seed(session)
    await session.commit()
    r = await client.post("/quiz/submit", json={"topic_id": tid, "answers": [0]}, headers=hs)
    assert r.status_code == 400


async def test_gamification_xp_va_stats(client, session, mocker):
    mocker.patch("app.lessons.quiz.gateway.complete", mocker.AsyncMock(return_value=_QUIZ_JSON))
    gv = await _auth(client, "giao_vien")
    hs = await _auth(client, "hoc_sinh")
    tid = await _seed(session)
    await session.commit()
    await client.post(f"/lessons/{tid}/quiz/generate", headers=gv)
    # nộp đúng 2/2 -> XP = 2*5 + 10(pass) = 20, streak khởi tạo = 1
    r = (await client.post("/quiz/submit", json={"topic_id": tid, "answers": [2, 2]}, headers=hs)).json()
    assert r["xp"] == 20 and r["streak"] == 1 and r["xp_week"] == 20
    # /me/stats phản ánh XP tuần + streak
    st = (await client.get("/me/stats", headers=hs)).json()
    assert st["xp_week"] == 20 and st["streak"] == 1 and "current_mach" in st
