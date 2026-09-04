import json
import uuid

import pytest

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
    # Nhãn đổi theo REQ §1.1: phần này giờ tên "Kiến thức trọng tâm".
    assert r.json()["nguon_bai"] == "Kiến thức trọng tâm"


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


def test_neo_nhan_du_7_phan():
    """§3.3 — thiếu một phần là học sinh bấm "Hỏi về đoạn này" ở đó thì trả lời sai đoạn."""
    from app.api.tutor import _NEO_RE

    for x in ("khoi_dong", "hoat_dong", "khai_niem", "kien_thuc", "minh_hoa",
              "luyen_tap", "bai_tap", "vi_du:1", "quiz:12"):
        assert _NEO_RE.match(x), x
    for x in ("bịa", "vi_du:0", "quiz:100", "khoi_dong ", "", "kien_thuc:1"):
        assert not _NEO_RE.match(x), x


def test_doan_bai_4_phan_moi_kem_kien_thuc_lam_nen():
    from app.api.tutor import _doan_bai

    class C:
        khai_niem = "<p>Lý thuyết nền</p>"
        khoi_dong = "<p>Câu hỏi mở đầu</p>"
        hoat_dong = ""
        luyen_tap = "<p>Bài luyện</p>"
        bai_tap = ""
        vi_du_json = "[]"; minh_hoa_json = "[]"; quiz_json = "[]"

    txt, nhan = _doan_bai(C(), "khoi_dong")
    assert nhan == "Khởi động"
    assert "Câu hỏi mở đầu" in txt and "Lý thuyết nền" in txt

    txt, nhan = _doan_bai(C(), "luyen_tap")
    assert nhan == "Luyện tập – Vận dụng" and "Bài luyện" in txt

    # Phần CHƯA SOẠN -> rơi về cả bài, không đưa mô hình đoạn rỗng
    txt, nhan = _doan_bai(C(), "hoat_dong")
    assert nhan == "Toàn bài"

    # kien_thuc và khai_niem trỏ cùng chỗ
    for a in ("kien_thuc", "khai_niem"):
        t, n = _doan_bai(C(), a)
        assert n == "Kiến thức trọng tâm" and "Lý thuyết nền" in t


# ─────────── Hình minh hoạ đính theo câu trả lời ───────────

async def _topic(session) -> int:
    """Đơn vị kiến thức TRỐNG (chưa có nội dung) — test tự thêm nội dung riêng."""
    subj = Subject(name=f"MonAnh-{uuid.uuid4().hex[:6]}")
    grade = Grade(name=f"KhoiAnh-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, grade])
    await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id,
                        mach_noi_dung="Tính đối xứng", don_vi_kien_thuc="Hình có trục đối xứng",
                        order_index=0)
    session.add(t)
    await session.flush()
    return t.id


def _ct(topic_id: int, **kw):
    return TopicContent(topic_id=topic_id, khai_niem="<p>Nội dung</p>",
                        trang_thai="published", **kw)


async def test_kem_hinh_cua_vi_du_khi_hoi_ngay_o_vi_du_do(client, session, mocker):
    """Neo `vi_du:1` là tín hiệu chắc chắn — không cần đoán bằng từ khoá."""
    import json as _j

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Ba hình này đều có trục đối xứng."}))
    h = await _auth(client)
    tid = await _topic(session)
    session.add(_ct(tid, vi_du_json=_j.dumps([
        {"de": "Trong các hình sau, hình nào có trục đối xứng?", "giai": "…",
         "anh": "/video/files/vd1.png"},
        {"de": "Tính 2+3", "giai": "5"}])))
    await session.commit()

    b = (await client.post("/tutor/ask", headers=h, json={
        "question": "Giải thích giúp mình", "topic_id": tid, "anchor": "vi_du:1"})).json()
    assert len(b["anh"]) == 1
    assert b["anh"][0]["url"].startswith("/video/files/vd1.png?exp=")   # đã ký
    assert b["anh"][0]["tu"] == "Ví dụ 1"
    assert "trục đối xứng" in b["anh"][0]["caption"]


async def test_khong_kem_hinh_khi_cau_hoi_khong_lien_quan_hinh(client, session, mocker):
    """Bài có ảnh nhưng hỏi chuyện khác -> không đính, tránh nhiễu."""
    import json as _j

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Luỹ thừa là phép nhân lặp."}))
    h = await _auth(client)
    tid = await _topic(session)
    session.add(_ct(tid, minh_hoa_json=_j.dumps([
        {"type": "image", "url": "/video/files/a.png", "caption": "Sơ đồ ước chung"},
        {"type": "image", "url": "/video/files/b.png", "caption": "Cây thừa số nguyên tố"}])))
    await session.commit()

    b = (await client.post("/tutor/ask", headers=h, json={
        "question": "Luỹ thừa là gì?", "topic_id": tid})).json()
    assert b["anh"] == []


async def test_chon_hinh_khop_caption_khi_hoi_chung_ca_bai(client, session, mocker):
    import json as _j

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node", mocker.AsyncMock(
        return_value={"answer": "Cây thừa số nguyên tố giúp phân tích 24 và 18."}))
    h = await _auth(client)
    tid = await _topic(session)
    session.add(_ct(tid, minh_hoa_json=_j.dumps([
        {"type": "image", "url": "/video/files/a.png", "caption": "Sơ đồ ước chung của 24 và 18"},
        {"type": "image", "url": "/video/files/b.png", "caption": "Cây thừa số nguyên tố của 24"}])))
    await session.commit()

    b = (await client.post("/tutor/ask", headers=h, json={
        "question": "Vẽ cây thừa số nguyên tố thế nào?", "topic_id": tid})).json()
    assert b["anh"], "câu hỏi nói về hình mà bài có ảnh -> phải đính"
    assert "thừa số nguyên tố" in b["anh"][0]["caption"]


async def test_khong_kem_video_va_khong_kem_khi_tra_loi_ngoai_sgk(client, session, mocker):
    """Video đã có thẻ phát riêng trong bài; và câu từ chối thì không đính hình."""
    import json as _j
    from app.graph.grounding import KHONG_TIM_THAY

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    h = await _auth(client)
    tid = await _topic(session)
    session.add(_ct(tid, minh_hoa_json=_j.dumps([
        {"type": "video", "url": "/video/files/v.mp4", "caption": "Video hình học"}])))
    await session.commit()

    # chỉ có video -> không đính gì
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Hình này có trục đối xứng."}))
    b = (await client.post("/tutor/ask", headers=h, json={
        "question": "Hình nào có trục đối xứng?", "topic_id": tid})).json()
    assert b["anh"] == []

    # trả lời "ngoài SGK" -> không đính hình vào câu từ chối
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": KHONG_TIM_THAY}))
    b2 = (await client.post("/tutor/ask", headers=h, json={
        "question": "Hình nào có trục đối xứng?", "topic_id": tid})).json()
    assert b2["khong_tim_thay"] is True and b2["anh"] == []


async def test_bai_chua_xuat_ban_thi_hoc_sinh_khong_thay_hinh(client, session, mocker):
    """Hình đi theo ĐÚNG luật quyền của nội dung: nháp thì học sinh không thấy."""
    import json as _j

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Hình vẽ cho thấy trục đối xứng."}))
    h = await _auth(client)
    tid = await _topic(session)
    from app.db.models import TopicContent
    session.add(TopicContent(topic_id=tid, khai_niem="<p>x</p>", trang_thai="draft",
                             minh_hoa_json=_j.dumps([
                                 {"type": "image", "url": "/video/files/a.png",
                                  "caption": "Hình trục đối xứng"}])))
    await session.commit()

    b = (await client.post("/tutor/ask", headers=h, json={
        "question": "Hình nào có trục đối xứng?", "topic_id": tid})).json()
    assert b["anh"] == []


async def test_khong_dinh_hinh_chi_vi_CAU_TRA_LOI_nhac_ten_bai(client, session, mocker):
    """Bài hình học thì câu trả lời nào cũng nhắc "…về hình có trục đối xứng".

    Lọc theo câu trả lời là mở cửa cho MỌI câu, kể cả "bài này có mấy phần?" —
    đã gặp thật. Ý muốn của học sinh nằm ở CÂU HỎI.
    """
    import json as _j

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node", mocker.AsyncMock(return_value={
        "answer": "Chào em! Bài học về hình có trục đối xứng này gồm 5 phần nhé."}))
    h = await _auth(client)
    tid = await _topic(session)
    session.add(_ct(tid, minh_hoa_json=_j.dumps([
        {"type": "image", "url": "/video/files/a.png", "caption": "Ba hình phẳng"}])))
    await session.commit()

    b = (await client.post("/tutor/ask", headers=h, json={
        "question": "Bài này có mấy phần?", "topic_id": tid})).json()
    assert b["anh"] == []


async def test_phu_tu_khong_phu_thuoc_do_dai_cau_tra_loi():
    """Caption ngắn vs câu trả lời dài: đo bằng ĐỘ PHỦ TỪ, không phải SequenceMatcher.

    SequenceMatcher chia cho tổng độ dài hai chuỗi nên caption 90 ký tự so với
    câu trả lời 1500 ký tự cho tỉ lệ ≤ 0.11 dù trùng từng chữ — ngưỡng nào cũng
    không bao giờ đạt, tính năng im lặng.
    """
    from app.api.tutor import _NGUONG_ANH, _phu_tu

    cap = "Cây thừa số nguyên tố của 24 và 18"
    dai = ("Chào em! " + "Ta phân tích 24 và 18 thành thừa số nguyên tố. " * 40)
    assert _phu_tu(cap, dai) >= _NGUONG_ANH
    assert _phu_tu("Sơ đồ khí hậu Việt Nam", dai) < _NGUONG_ANH


async def test_hinh_khong_khop_caption_van_dinh_hinh_dau_khi_hoi_ro_ve_hinh(
        client, session, mocker):
    """Caption kiểu "Hình minh hoạ" không trùng chữ nào — im lặng thì tính năng chết."""
    import json as _j

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Ba hình đều khác nhau."}))
    h = await _auth(client)
    tid = await _topic(session)
    session.add(_ct(tid, minh_hoa_json=_j.dumps([
        {"type": "image", "url": "/video/files/a.png", "caption": "Hình minh hoạ"}])))
    await session.commit()

    b = (await client.post("/tutor/ask", headers=h, json={
        "question": "Cho mình xem hình vẽ với", "topic_id": tid})).json()
    assert len(b["anh"]) == 1 and b["anh"][0]["caption"] == "Hình minh hoạ"


# ─────────── Không được 500 vì cột JSON của nội dung bị rác ───────────

@pytest.mark.parametrize("rac", [
    "{}",                       # dict -> vòng for lặp qua KHOÁ (chuỗi) -> AttributeError
    "[1, 2, 3]",                # list số -> .get() trên int
    '["chuoi"]',                # list chuỗi
    "khong-phai-json",          # JSONDecodeError
    "null",
])
async def test_ask_khong_500_khi_cot_json_bi_rac(client, session, mocker, rac):
    """Nội dung do AI sinh + chuyên gia sửa tay trong CMS -> đầu vào không tin được.

    Trước đây `for m in json.loads(...)` trên một dict sẽ lặp qua khoá rồi
    `m.get(...)` nổ AttributeError -> 500 cho cả câu hỏi.
    """
    from app.db.models import TopicContent

    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Hình này có trục đối xứng."}))
    h = await _auth(client)
    tid = await _topic(session)
    session.add(TopicContent(topic_id=tid, khai_niem="<p>Nội dung</p>",
                             trang_thai="published",
                             minh_hoa_json=rac, vi_du_json=rac, quiz_json=rac))
    await session.commit()

    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Hình nào có trục đối xứng?", "topic_id": tid})
    assert r.status_code == 200, r.text
    assert r.json()["anh"] == []


async def test_ask_van_tra_loi_khi_chon_hinh_no_loi(client, session, mocker):
    """Đính hình chạy SAU khi đã tiêu lượt hỏi — lỗi ở đó không được xoá câu trả lời."""
    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Đáp án đây."}))
    mocker.patch("app.api.tutor._chon_anh", side_effect=RuntimeError("hỏng"))
    h = await _auth(client)
    tid = await _topic(session)
    session.add(_ct(tid))
    await session.commit()

    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Hình nào có trục đối xứng?", "topic_id": tid})
    assert r.status_code == 200
    assert r.json()["answer"] == "Đáp án đây." and r.json()["anh"] == []
