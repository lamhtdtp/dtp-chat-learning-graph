import uuid
from types import SimpleNamespace

from app.main import app


async def _auth(client) -> dict:
    email = f"chat-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _fake_graph(mocker, answer="Tập hợp là...", intent="hoi_dap", retrieved=None):
    from app.retrieval.retriever import RetrievedChunk
    if retrieved is None:
        retrieved = [RetrievedChunk(content="Tập hợp gồm phần tử.", score=0.8, chuong_so=1,
                                    bai_so=1, page_no=6, tap=1, loai_noi_dung="ly_thuyet", nguon="tr.6")]
    app.state.graph = SimpleNamespace(ainvoke=mocker.AsyncMock(
        return_value={"answer": answer, "intent": intent, "retrieved": retrieved}))
    return app.state.graph


async def test_chat_thieu_token_bi_401(client):
    r = await client.post("/chat", json={"message": "Tập hợp là gì?"})
    assert r.status_code == 401


async def test_chat_tao_phien_moi_tra_session_id_va_citations(client, mocker):
    h = await _auth(client)
    fake = _fake_graph(mocker)

    r = await client.post("/chat", json={"message": "Tập hợp là gì?"}, headers=h)

    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Tập hợp là..."
    assert body["intent"] == "hoi_dap"
    assert body["citations"][0]["page_no"] == 6
    assert isinstance(body["session_id"], int)  # phiên mới -> id int
    # thread_id gồm user_id:session_id
    tid = fake.ainvoke.await_args.kwargs["config"]["configurable"]["thread_id"]
    assert tid.endswith(f":{body['session_id']}")


async def test_chat_tiep_tuc_phien_cu_giu_session_id(client, mocker):
    h = await _auth(client)
    _fake_graph(mocker)
    first = (await client.post("/chat", json={"message": "câu 1"}, headers=h)).json()
    sid = first["session_id"]

    second = (await client.post("/chat", json={"message": "câu 2", "session_id": sid}, headers=h)).json()
    assert second["session_id"] == sid  # cùng phiên


async def test_chat_luu_lich_su_va_liet_ke_duoc(client, mocker):
    h = await _auth(client)
    _fake_graph(mocker, answer="Trả lời A")
    sid = (await client.post("/chat", json={"message": "Câu hỏi X"}, headers=h)).json()["session_id"]

    # GET /sessions liệt kê phiên
    sessions = (await client.get("/sessions", headers=h)).json()
    assert any(s["id"] == sid for s in sessions)

    # GET /sessions/{id} trả đủ user + assistant message
    msgs = (await client.get(f"/sessions/{sid}", headers=h)).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "Câu hỏi X"
    assert msgs[1]["content"] == "Trả lời A"


async def test_chat_rate_limit_tra_503(client, mocker):
    from app.llm.gateway import LLMUnavailable
    h = await _auth(client)

    async def boom(*a, **k):
        raise LLMUnavailable("429")
    app.state.graph = SimpleNamespace(ainvoke=boom)

    r = await client.post("/chat", json={"message": "Tập hợp là gì?"}, headers=h)
    assert r.status_code == 503
    assert "thử lại sau" in r.json()["detail"]


async def test_chat_dinh_video_cho_cau_khai_niem(client, mocker):
    # Câu hỏi khái niệm + có grounding + chưa có cache -> tạo job & enqueue Celery.
    h = await _auth(client)
    _fake_graph(mocker, answer="Số nguyên tố là số tự nhiên lớn hơn 1...", intent="hoi_dap")
    mocker.patch("app.api.chat.video_cache.get_done_video", mocker.AsyncMock(return_value=None))
    mocker.patch("app.api.chat.video_cache.get_or_create_job", mocker.AsyncMock(
        return_value=(SimpleNamespace(id=7, status="QUEUED", video_url=None), True)))
    delay = mocker.patch("app.ingestion.celery_app.render_video_task.delay")

    r = await client.post("/chat", json={"message": "Số nguyên tố là gì?"}, headers=h)

    assert r.json()["video"] == {"job_id": 7, "status": "QUEUED", "video_url": None}
    delay.assert_called_once_with(job_id=7)


async def test_chat_cache_hit_khong_tao_job_moi(client, mocker):
    # Đã có video cho khái niệm -> trả URL từ cache, KHÔNG enqueue job mới (US-19).
    h = await _auth(client)
    _fake_graph(mocker, answer="Số nguyên tố là số tự nhiên lớn hơn 1...", intent="hoi_dap")
    mocker.patch("app.api.chat.video_cache.get_done_video", mocker.AsyncMock(
        return_value=SimpleNamespace(id=9, status="DONE", video_url="/video/files/x.mp4")))
    delay = mocker.patch("app.ingestion.celery_app.render_video_task.delay")

    r = await client.post("/chat", json={"message": "Số nguyên tố là gì?"}, headers=h)

    assert r.json()["video"] == {"job_id": 9, "status": "DONE", "video_url": "/video/files/x.mp4"}
    delay.assert_not_called()


async def test_chat_khong_dinh_video_khi_giai_bai(client, mocker):
    # intent giai_bai -> không đính video (gating).
    h = await _auth(client)
    _fake_graph(mocker, answer="Bước 1...", intent="giai_bai")
    mocker.patch("app.ingestion.celery_app.render_video_task.delay")

    r = await client.post("/chat", json={"message": "Tính 2+3x5"}, headers=h)
    assert r.json()["video"] is None


async def test_chat_khong_dinh_video_khi_khong_grounding(client, mocker):
    # Không có citations -> không video.
    h = await _auth(client)
    _fake_graph(mocker, answer="Mình không tìm thấy...", intent="hoi_dap", retrieved=[])
    mocker.patch("app.ingestion.celery_app.render_video_task.delay")

    r = await client.post("/chat", json={"message": "Số nguyên tố là gì?"}, headers=h)
    assert r.json()["video"] is None
