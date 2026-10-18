"""Nộp bài phải ghi chi tiết TỪNG CÂU, khoá theo yêu cầu cần đạt.

Đây là nền của bước ④ trong demo ("gợi ý tài liệu bổ sung + bài làm mới chọn
theo YCCĐ"): không có chi tiết này thì chỉ nói được "em vừa sai câu này", không
nói được "em sai yêu cầu cần đạt này ba lần rồi".
"""
import json
import uuid

from sqlalchemy import select

from app.db.models import (
    CurriculumTopic, Grade, QuizAttempt, QuizAttemptItem, Subject, TopicContent,
)
from app.lessons.ycd_key import chuan_hoa

YCD_A = "Vận dụng được dấu hiệu chia hết cho 2, 5, 3, 9"
YCD_B = "Xác định được ƯCLN, BCNN của hai số tự nhiên"

_QUIZ = json.dumps([
    {"q": "Số nào chia hết cho cả 2 và 5?", "o": ["125", "230", "342", "415"], "a": 1,
     "lv": "de", "giai": "Tận cùng là 0.", "phan": "kien_thuc", "ycd": YCD_A},
    {"q": "ƯCLN(12; 18) bằng?", "o": ["2", "3", "6", "36"], "a": 2,
     "lv": "trung_binh", "giai": "2·3 = 6.", "phan": "khai_niem", "ycd": YCD_B},
], ensure_ascii=False)


async def _auth(client) -> dict:
    email = f"qai-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _seed(session) -> int:
    subj = Subject(name=f"MonQI-{uuid.uuid4().hex[:6]}")
    grade = Grade(name=f"KhoiQI-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, grade])
    await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id, mach_noi_dung="Số tự nhiên",
                        don_vi_kien_thuc="Dấu hiệu chia hết", order_index=0)
    session.add(t)
    await session.flush()
    session.add(TopicContent(topic_id=t.id, quiz_json=_QUIZ, trang_thai="published"))
    await session.flush()
    return t.id


async def _items(session, topic_id: int) -> list[QuizAttemptItem]:
    return list(await session.scalars(
        select(QuizAttemptItem)
        .join(QuizAttempt, QuizAttempt.id == QuizAttemptItem.attempt_id)
        .where(QuizAttempt.topic_id == topic_id)
        .order_by(QuizAttemptItem.id)))


async def test_nop_bai_ghi_chi_tiet_tung_cau(client, session):
    hs = await _auth(client)
    tid = await _seed(session)
    await session.commit()

    r = await client.post("/quiz/submit", headers=hs,
                          json={"topic_id": tid, "answers": [1, 3]})   # câu 1 đúng, câu 2 sai
    assert r.status_code == 200 and r.json()["diem"] == 1

    items = await _items(session, tid)
    assert len(items) == 2
    assert [i.dung for i in items] == [True, False]
    # Khoá bền là nguyên văn YCCĐ đã chuẩn hoá, không phải chỉ số câu.
    assert [i.ycd_key for i in items] == [chuan_hoa(YCD_A), chuan_hoa(YCD_B)]
    assert [i.phan for i in items] == ["kien_thuc", "khai_niem"]


async def test_luu_nhan_chu_khong_luu_chi_so(client, session):
    """Chỉ số phương án chỉ có nghĩa trong đúng đề đã sinh ra nó — mà đề thì bị
    sinh lại. Lưu nhãn chữ."""
    hs = await _auth(client)
    tid = await _seed(session)
    await session.commit()

    await client.post("/quiz/submit", headers=hs,
                      json={"topic_id": tid, "answers": [1, 3]})

    items = await _items(session, tid)
    assert [(i.chon, i.dap_an) for i in items] == [("B", "B"), ("D", "C")]


async def test_bo_trong_khac_voi_chon_phuong_an_A(client, session):
    """-1 là "không trả lời". Nhầm nó thành "A" là đếm một câu bỏ trống thành
    một câu chọn sai phương án A."""
    hs = await _auth(client)
    tid = await _seed(session)
    await session.commit()

    await client.post("/quiz/submit", headers=hs,
                      json={"topic_id": tid, "answers": [-1, -1]})

    items = await _items(session, tid)
    assert [i.chon for i in items] == ["", ""]
    assert all(not i.dung for i in items)


async def test_so_dong_chi_tiet_khop_tong_cua_lan_nop(client, session):
    hs = await _auth(client)
    tid = await _seed(session)
    await session.commit()

    r = await client.post("/quiz/submit", headers=hs,
                          json={"topic_id": tid, "answers": [1, 2]})

    at = await session.scalar(select(QuizAttempt).where(QuizAttempt.topic_id == tid))
    assert len(await _items(session, tid)) == at.tong == r.json()["tong"]
