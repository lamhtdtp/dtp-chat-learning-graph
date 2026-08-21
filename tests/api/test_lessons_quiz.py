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


async def test_submit_tra_phan_va_ycd_de_chi_duong(client, session):
    """§3.4 — mỗi câu sai phải chỉ được về đúng phần + yêu cầu cần đạt."""
    import json as _j
    import uuid as _u
    from app.db.models import CurriculumTopic, Grade, Subject, TopicContent

    e = f"q-{_u.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={"email": e, "password": "matkhau123",
                                                 "name": "HS", "role": "hoc_sinh"})
    hs = {"Authorization": f"Bearer {r.json()['token']}"}
    subj = Subject(name=f"M-{_u.uuid4().hex[:6]}"); gr = Grade(name=f"K-{_u.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                        don_vi_kien_thuc="D", order_index=0)
    session.add(t); await session.flush()
    tid = t.id
    quiz = [
        {"q": "1+1?", "o": ["1", "2"], "a": 1, "lv": "de",
         "phan": "luyen_tap", "ycd": "Cộng được hai số tự nhiên"},
        {"q": "2+2?", "o": ["4", "5"], "a": 0, "lv": "de"},   # câu CŨ, thiếu 2 khoá
    ]
    session.add(TopicContent(topic_id=tid, trang_thai="published", quiz_json=_j.dumps(quiz)))
    await session.commit()

    b = (await client.post("/quiz/submit", headers=hs,
                           json={"topic_id": tid, "answers": [0, 0]})).json()
    kq = b["ket_qua"]
    assert kq[0]["dung"] is False
    assert kq[0]["phan"] == "luyen_tap" and kq[0]["ycd"] == "Cộng được hai số tự nhiên"
    # Câu cũ không có `phan` -> rơi về kien_thuc chứ không phải None/rỗng
    assert kq[1]["phan"] == "kien_thuc" and kq[1]["ycd"] == ""


def test_parse_quiz_bo_phan_bia():
    """Model bịa tên phần -> phải rơi về kien_thuc, không lưu id rác."""
    import json as _j
    from app.lessons.quiz import _parse_quiz

    raw = _j.dumps({"quiz": [
        {"q": "a", "o": ["x", "y"], "a": 0, "lv": "de", "phan": "bịa", "ycd": "Y"},
        {"q": "b", "o": ["x", "y"], "a": 1, "lv": "de", "phan": "bai_tap"},
    ]})
    ds = _parse_quiz(raw)
    assert ds[0]["phan"] == "kien_thuc" and ds[0]["ycd"] == "Y"
    assert ds[1]["phan"] == "bai_tap"
