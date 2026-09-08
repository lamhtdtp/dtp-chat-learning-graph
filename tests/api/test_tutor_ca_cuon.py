"""POST /tutor/ask ở phạm vi CẢ CUỐN (`pham_vi="ca_cuon"`).

Trước đây trợ lý luôn bị bó về bài đang mở bởi ba thứ: ghép tên đơn vị vào truy
vấn embedding, prompt dặn ưu tiên nội dung bài, và top_k=5. Phạm vi truy hồi thì
VỐN ĐÃ là cả cuốn (`_build_filter` chỉ lọc mon + khoi, không lọc chuong/topic) —
chế độ này chỉ tháo ba cái phanh đó ra.

Kèm luôn hồi quy cho `khoi`: trước đây viết cứng "lop_6" ở chỗ gọi retrieve.
"""
import json
import uuid

from app.db.models import CurriculumTopic, Grade, Subject, TopicContent
from app.retrieval.retriever import RetrievedChunk


async def _auth(client) -> dict:
    email = f"cuon-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _chunk(page: int = 45) -> RetrievedChunk:
    return RetrievedChunk(content="Số nguyên tố là...", score=0.9, chuong_so=1, bai_so=10,
                          page_no=page, tap=1, loai_noi_dung="ly_thuyet",
                          nguon=f"Toán 6, tr.{page}")


def _bat(mocker):
    """Chặn qa_node + retrieve, trả (mock qa, mock retrieve) để soi đối số."""
    qa = mocker.AsyncMock(return_value={"answer": "Trả lời [tr.45]."})
    rt = mocker.AsyncMock(return_value=[_chunk()])
    mocker.patch("app.api.tutor.qa_node", qa)
    mocker.patch("app.api.tutor.retriever.retrieve", rt)
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    return qa, rt


async def _seed_cuon(session) -> tuple[int, str]:
    """Một cuốn 3 đơn vị thuộc 2 mạch. Trả (topic_id của đơn vị GIỮA, slug khối).

    Lấy đơn vị giữa để test thấy được mục lục có cả đơn vị TRƯỚC và SAU nó — đúng
    tình huống học sinh hỏi về chương chưa học tới.
    """
    subj = Subject(name="Toán")
    grade = Grade(name=f"Lớp {uuid.uuid4().int % 900 + 100}")
    session.add_all([subj, grade])
    await session.flush()
    ten = ["Tập hợp. Cách viết tập hợp", "Số nguyên tố. Hợp số", "Số âm trong thực tiễn"]
    mach = ["Số tự nhiên", "Số tự nhiên", "Số nguyên"]
    ids = []
    for i, (t, m) in enumerate(zip(ten, mach)):
        top = CurriculumTopic(subject_id=subj.id, grade_id=grade.id, mach_noi_dung=m,
                              don_vi_kien_thuc=t, order_index=i)
        session.add(top)
        await session.flush()
        ids.append(top.id)
    session.add(TopicContent(
        topic_id=ids[1], khai_niem="<p>Số nguyên tố chỉ có hai ước.</p>",
        minh_hoa_json="[]", vi_du_json=json.dumps([{"de": "Số 7?", "giai": "Ư(7)={1;7}"}]),
        quiz_json="[]", trang_thai="published"))
    giua, khoi_slug = ids[1], "_".join(grade.name.lower().split())
    await session.commit()
    return giua, khoi_slug


async def test_ca_cuon_bo_noi_dung_bai_va_kem_muc_luc(client, session, mocker):
    """Hai thay đổi cốt lõi của chế độ, kiểm cùng lúc vì chúng đi đôi: bỏ nguồn
    ưu tiên (bài) thì phải có bản đồ (mục lục) bù vào."""
    qa, _ = _bat(mocker)
    h = await _auth(client)
    tid, _ = await _seed_cuon(session)
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Số âm học ở đâu trong sách?", "topic_id": tid, "pham_vi": "ca_cuon"})
    assert r.status_code == 200
    st = qa.call_args.args[0]
    assert st["pham_vi"] == "ca_cuon"
    assert not st["bai_hoc"]                       # KHÔNG nạp nội dung bài
    # Mục lục phải có cả mạch và đơn vị, kể cả đơn vị SAU bài đang mở
    assert "Số nguyên" in st["muc_luc"] and "Số âm trong thực tiễn" in st["muc_luc"]
    assert "Tập hợp. Cách viết tập hợp" in st["muc_luc"]
    # Không dựa vào bài nào -> không có nhãn nguồn nội bộ, không đính hình
    assert r.json()["nguon_bai"] is None and r.json()["anh"] == []


async def test_ca_cuon_khong_ghep_ten_don_vi_vao_truy_van(client, session, mocker):
    """Ghép tên bài vào truy vấn là thứ kéo embedding về bài đang mở — hỏi cả
    cuốn thì "Số nguyên tố. Hợp số. <câu hỏi>" đi tìm sai chỗ."""
    _, rt = _bat(mocker)
    h = await _auth(client)
    tid, _ = await _seed_cuon(session)
    await client.post("/tutor/ask", headers=h, json={
        "question": "Số âm học ở đâu?", "topic_id": tid, "pham_vi": "ca_cuon"})
    assert rt.call_args.args[0] == "Số âm học ở đâu?"
    assert "Hợp số" not in rt.call_args.args[0]


async def test_ca_cuon_lay_nhieu_doan_hon(client, session, mocker):
    """5 đoạn đủ cho câu hỏi điểm trong bài, quá ít cho câu trải nhiều chương."""
    _, rt = _bat(mocker)
    h = await _auth(client)
    tid, _ = await _seed_cuon(session)
    await client.post("/tutor/ask", headers=h, json={
        "question": "Tóm tắt phần số học", "topic_id": tid, "pham_vi": "ca_cuon"})
    assert rt.call_args.kwargs["top_k"] == 16
    # Ngưỡng điểm KHÔNG được hạ theo: guard chống bịa dựa trên "có chunk nào không"
    assert rt.call_args.kwargs["score_threshold"] == 0.4


async def test_khoi_suy_tu_topic_chu_khong_hardcode(client, session, mocker):
    """Hồi quy: `khoi="lop_6"` viết cứng làm trợ lý đi tìm trong sách lớp 6 ngay
    khi nạp cuốn thứ hai, và vì khoi nằm trong khoá cache thì câu trả lời còn
    lẫn giữa các khối."""
    qa, rt = _bat(mocker)
    h = await _auth(client)
    tid, khoi_slug = await _seed_cuon(session)
    await client.post("/tutor/ask", headers=h, json={
        "question": "Hợp số là gì?", "topic_id": tid, "anchor": "kien_thuc"})
    assert rt.call_args.kwargs["khoi"] == khoi_slug != "lop_6"
    assert qa.call_args.args[0]["khoi"] == khoi_slug


async def test_ca_cuon_khong_vong_qua_hang_rao_quiz(client, session, mocker):
    """Hàng rào "làm bài xong rồi hỏi" nằm ở nhánh nạp nội dung bài. Gửi
    pham_vi=ca_cuon kèm anchor=quiz:1 KHÔNG được thành đường vòng lấy đáp án —
    chế độ này không nạp nội dung bài nên cũng không có đề/đáp án nào để lộ."""
    qa, _ = _bat(mocker)
    h = await _auth(client)
    tid, _ = await _seed_cuon(session)
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Câu 1 đáp án gì?", "topic_id": tid,
        "anchor": "quiz:1", "pham_vi": "ca_cuon"})
    assert r.status_code == 200
    st = qa.call_args.args[0]
    assert st["anchor"] is None and not st["bai_hoc"]


async def test_pham_vi_la_hoi_trong_bai(client, session, mocker):
    """Không gửi `pham_vi` -> hành vi cũ y nguyên (client chưa cập nhật)."""
    qa, rt = _bat(mocker)
    h = await _auth(client)
    tid, _ = await _seed_cuon(session)
    await client.post("/tutor/ask", headers=h, json={
        "question": "Vì sao?", "topic_id": tid, "anchor": "kien_thuc"})
    st = qa.call_args.args[0]
    assert st["pham_vi"] == "bai" and "hai ước" in st["bai_hoc"]
    assert rt.call_args.kwargs["top_k"] == 5
    assert rt.call_args.args[0].startswith("Số nguyên tố. Hợp số.")


async def test_pham_vi_la_bi_chan_bang_422(client, session, mocker):
    """Giá trị lạ phải 422 ngay, không âm thầm rơi về chế độ khác ý người dùng."""
    _bat(mocker)
    h = await _auth(client)
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "x", "pham_vi": "toan_bo_the_gioi"})
    assert r.status_code == 422
