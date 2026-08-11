import json
import uuid

from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, QuizAttempt, Subject, TopicContent, User
from app.retrieval.retriever import RetrievedChunk


async def _dang_ky(client) -> tuple[dict, str]:
    """Trả (headers, email) — email để tra user_id khi test cần dựng dữ liệu."""
    email = f"tut-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, email


async def _auth(client) -> dict:
    h, _ = await _dang_ky(client)
    return h


async def _seed_bai(session, *, trang_thai: str = "published") -> int:
    """Một đơn vị kiến thức ĐÃ BIÊN SOẠN (tên duy nhất để test cô lập). Trả topic_id."""
    subj = Subject(name=f"MonTut-{uuid.uuid4().hex[:6]}")
    grade = Grade(name=f"KhoiTut-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, grade])
    await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id, mach_noi_dung="Số tự nhiên",
                        don_vi_kien_thuc="Số nguyên tố. Hợp số", order_index=0)
    session.add(t)
    await session.flush()
    session.add(TopicContent(
        topic_id=t.id,
        khai_niem="<p>Số nguyên tố chỉ có <b>hai</b> ước.</p>",
        minh_hoa_json=json.dumps([{"type": "video", "caption": "Sàng Eratosthenes"}]),
        vi_du_json=json.dumps([{"de": "Số 7?", "giai": "Ư(7)={1;7}"},
                               {"de": "Phân tích 60", "giai": "60 = 2² · 3 · 5"}]),
        quiz_json=json.dumps([{"q": "Số nào là hợp số?", "o": ["19", "21"], "a": 1,
                               "lv": "de", "giai": "21 = 3 · 7"}]),
        trang_thai=trang_thai))
    # topic_id PHẢI lấy trước commit — đọc thuộc tính ORM sau commit là MissingGreenlet.
    tid = t.id
    await session.commit()
    return tid


def _bat_qa(mocker):
    """Chặn qa_node, trả về chính mock để test soi state đã truyền vào."""
    m = mocker.AsyncMock(return_value={"answer": "Trả lời [tr.45]."})
    mocker.patch("app.api.tutor.qa_node", m)
    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[_chunk(45)]))
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    return m


def _chunk(page: int) -> RetrievedChunk:
    return RetrievedChunk(content="Số nguyên tố là...", score=0.9, chuong_so=1, bai_so=10,
                          page_no=page, tap=1, loai_noi_dung="ly_thuyet",
                          nguon=f"Toán 6, tr.{page}")


async def test_tutor_tra_loi_bam_sgk(client, mocker):
    mocker.patch("app.api.tutor.retriever.retrieve",
                 mocker.AsyncMock(return_value=[_chunk(45), _chunk(45), _chunk(36)]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Số nguyên tố có đúng hai ước [tr.45]."}))
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    h = await _auth(client)
    r = await client.post("/tutor/ask", json={"question": "Số nguyên tố là gì?"}, headers=h)
    body = r.json()
    assert r.status_code == 200 and body["khong_tim_thay"] is False
    assert "[tr.45]" in body["answer"]
    # citations khử trùng theo trang (45 xuất hiện 2 lần -> 1) + tr.36
    pages = [c["page_no"] for c in body["citations"]]
    assert pages == [45, 36] and body["remaining"] == 19  # limit 20 - used 1


async def test_tutor_limits_tra_dung_gioi_han_cau_hinh(client):
    """Client đọc giới hạn từ đây thay vì hardcode -> đổi env là frontend theo ngay."""
    from app.config import settings

    h = await _auth(client)
    r = await client.get("/tutor/limits", headers=h)
    assert r.status_code == 200 and r.json() == {"max_chars": settings.chat_max_chars}


async def test_tutor_limits_can_dang_nhap(client):
    assert (await client.get("/tutor/limits")).status_code in (401, 403)


async def test_tutor_cau_hoi_qua_dai_400(client, mocker):
    """Vượt ĐÚNG 1 ký tự là chặn. Tính theo settings, không hardcode con số —
    test cũ ghim 500 nên khi nâng chat_max_chars lên 500 là hết chặn mà vẫn xanh."""
    from app.config import settings

    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    h = await _auth(client)
    r = await client.post("/tutor/ask", json={"question": "x" * (settings.chat_max_chars + 1)}, headers=h)
    assert r.status_code == 400 and "quá dài" in r.json()["detail"]


async def test_tutor_cau_hoi_dung_bien_van_qua(client, mocker):
    """Đúng max_chars ký tự phải ĐƯỢC hỏi — chặn ở > chứ không phải >=."""
    from app.config import settings

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[_chunk(45)]))
    mocker.patch("app.api.tutor.qa_node", mocker.AsyncMock(return_value={"answer": "ok [tr.45]"}))
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    h = await _auth(client)
    r = await client.post("/tutor/ask", json={"question": "x" * settings.chat_max_chars}, headers=h)
    assert r.status_code == 200


async def test_tutor_khong_tim_thay_khong_tra_citation(client, mocker):
    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Mình không tìm thấy nội dung này trong SGK. Em thử hỏi lại nhé!"}))
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    h = await _auth(client)
    r = await client.post("/tutor/ask", json={"question": "Thời tiết hôm nay?"}, headers=h)
    body = r.json()
    assert r.status_code == 200 and body["khong_tim_thay"] is True and body["citations"] == []
    assert body["nguon_bai"] is None


# ── Lát 1: trợ lý đọc được nội dung bài đang mở ───────────────────────────────

async def test_neo_vi_du_chi_ghep_dung_vi_du_do(client, session, mocker):
    """Hỏi ở Ví dụ 2 thì ngữ cảnh phải có lời giải của VD2 và KHÔNG có VD1 —
    ghép cả bài là đội token mà câu trả lời lại loãng."""
    qa = _bat_qa(mocker)
    h = await _auth(client)
    tid = await _seed_bai(session)
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Sao ra 2² · 3 · 5?", "topic_id": tid, "anchor": "vi_du:2"})
    assert r.status_code == 200 and r.json()["nguon_bai"] == "Ví dụ 2"
    st = qa.call_args.args[0]
    assert "60 = 2² · 3 · 5" in st["bai_hoc"] and "Ư(7)" not in st["bai_hoc"]
    # HTML của chuyên gia phải được bóc thẻ trước khi vào prompt
    assert "hai ước" in st["bai_hoc"] and "<b>" not in st["bai_hoc"]


async def test_cache_ctx_tach_theo_topic_va_anchor(client, session, mocker):
    """Thiếu topic_id/anchor trong khoá cache thì cùng một câu hỏi ngắn ở hai bài
    khác nhau sẽ dùng chung câu trả lời đã cache — sai âm thầm."""
    qa = _bat_qa(mocker)
    h = await _auth(client)
    tid = await _seed_bai(session)
    await client.post("/tutor/ask", headers=h, json={
        "question": "Giải thích lại đi", "topic_id": tid, "anchor": "khai_niem"})
    st = qa.call_args.args[0]
    assert st["topic_id"] == tid and st["anchor"] == "khai_niem"


async def test_neo_rac_khong_lam_hong_cau_hoi(client, session, mocker):
    """Neo lệch/bịa -> rơi về cả bài chứ không 4xx: học sinh đang giữa chừng bài,
    chặn câu hỏi vì một cái neo sai là tệ hơn."""
    qa = _bat_qa(mocker)
    h = await _auth(client)
    tid = await _seed_bai(session)
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Hợp số là gì?", "topic_id": tid, "anchor": "../../etc/passwd"})
    assert r.status_code == 200 and r.json()["nguon_bai"] == "Toàn bài"
    assert qa.call_args.args[0]["anchor"] is None


async def test_toan_bai_khong_kem_dap_an_quiz(client, session, mocker):
    """Hỏi bâng quơ mà nhận về nguyên đề + đáp án thì bài kiểm tra thành vô nghĩa."""
    qa = _bat_qa(mocker)
    h = await _auth(client)
    tid = await _seed_bai(session)
    await client.post("/tutor/ask", headers=h,
                      json={"question": "Tóm tắt bài này", "topic_id": tid})
    bai = qa.call_args.args[0]["bai_hoc"]
    assert "Số nào là hợp số?" not in bai and "Đáp án đúng" not in bai


async def test_hoi_cau_quiz_khi_chua_nop_bai_bi_chan(client, session, mocker):
    """Chưa nộp mà hỏi 'câu 1 đáp án gì' -> hỏi đủ N lượt là có trọn bộ đáp án."""
    _bat_qa(mocker)
    h = await _auth(client)
    tid = await _seed_bai(session)
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Câu 1 sai ở đâu?", "topic_id": tid, "anchor": "quiz:1"})
    assert r.status_code == 403 and "làm bài kiểm tra nhanh" in r.json()["detail"].lower()


async def test_hoi_cau_quiz_sau_khi_nop_thi_duoc(client, session, mocker):
    qa = _bat_qa(mocker)
    h, email = await _dang_ky(client)
    tid = await _seed_bai(session)
    uid = await session.scalar(select(User.id).filter_by(email=email))
    session.add(QuizAttempt(user_id=uid, topic_id=tid, diem=1, tong=1, dat=True))
    await session.commit()
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Câu 1 sai ở đâu?", "topic_id": tid, "anchor": "quiz:1"})
    assert r.status_code == 200 and r.json()["nguon_bai"] == "Bài kiểm tra · Câu 1"
    assert "21 = 3 · 7" in qa.call_args.args[0]["bai_hoc"]


async def test_bai_chua_xuat_ban_khong_lo_cho_hoc_sinh(client, session, mocker):
    """Bản nháp chuyên gia chưa duyệt — cùng luật với GET /lessons."""
    qa = _bat_qa(mocker)
    h = await _auth(client)
    tid = await _seed_bai(session, trang_thai="draft")
    r = await client.post("/tutor/ask", headers=h,
                          json={"question": "Bài này nói gì?", "topic_id": tid})
    assert r.status_code == 200 and r.json()["nguon_bai"] is None
    assert qa.call_args.args[0]["bai_hoc"] == ""


async def test_qdrant_hong_van_tra_loi_duoc_bang_noi_dung_bai(client, session, mocker):
    """Truy hồi SGK hỏng từng là 500 vì chỉ có mỗi nguồn đó. Nay bài đã biên soạn
    là đủ để trả lời tử tế."""
    mocker.patch("app.api.tutor.qa_node", mocker.AsyncMock(return_value={"answer": "Hai ước."}))
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    mocker.patch("app.api.tutor.retriever.retrieve",
                 mocker.AsyncMock(side_effect=ConnectionError("All connection attempts failed")))
    h = await _auth(client)
    tid = await _seed_bai(session)
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Số nguyên tố là gì?", "topic_id": tid, "anchor": "khai_niem"})
    assert r.status_code == 200 and r.json()["citations"] == []
    assert r.json()["nguon_bai"] == "Khái niệm"


async def test_qdrant_hong_va_khong_co_bai_thi_503(client, mocker):
    """Không còn nguồn nào -> nói thẳng là đang quá tải, KHÔNG giả vờ 'chưa có
    trong SGK' (SGK vẫn ổn, chỉ là tìm kiếm chết)."""
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    mocker.patch("app.api.tutor.retriever.retrieve",
                 mocker.AsyncMock(side_effect=ConnectionError("down")))
    h = await _auth(client)
    r = await client.post("/tutor/ask", headers=h, json={"question": "Số nguyên tố là gì?"})
    assert r.status_code == 503


async def test_topic_id_khong_ton_tai_van_tra_loi_bang_sgk(client, mocker):
    """id cũ/hỏng không được làm chết câu hỏi — vẫn còn SGK để trả lời."""
    _bat_qa(mocker)
    h = await _auth(client)
    r = await client.post("/tutor/ask", headers=h,
                          json={"question": "Số nguyên tố là gì?", "topic_id": 99999999})
    assert r.status_code == 200 and r.json()["nguon_bai"] is None
