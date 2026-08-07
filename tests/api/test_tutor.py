import uuid

from app.retrieval.retriever import RetrievedChunk


async def _auth(client) -> dict:
    email = f"tut-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


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


async def test_tutor_cau_hoi_qua_dai_400(client, mocker):
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    h = await _auth(client)
    r = await client.post("/tutor/ask", json={"question": "x" * 500}, headers=h)
    assert r.status_code == 400


async def test_tutor_khong_tim_thay_khong_tra_citation(client, mocker):
    mocker.patch("app.api.tutor.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.api.tutor.qa_node",
                 mocker.AsyncMock(return_value={"answer": "Mình không tìm thấy nội dung này trong SGK. Em thử hỏi lại nhé!"}))
    mocker.patch("app.api.tutor.llm_cache.incr_quota", mocker.AsyncMock(return_value=1))
    h = await _auth(client)
    r = await client.post("/tutor/ask", json={"question": "Thời tiết hôm nay?"}, headers=h)
    body = r.json()
    assert r.status_code == 200 and body["khong_tim_thay"] is True and body["citations"] == []
