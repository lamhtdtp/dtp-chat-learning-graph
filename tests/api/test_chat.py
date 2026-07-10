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


async def test_chat_offer_video_khong_tu_sinh(client, mocker):
    # On-demand: câu khái niệm đủ điều kiện -> OFFERED (hiện nút), KHÔNG tự tạo job.
    h = await _auth(client)
    _fake_graph(mocker, answer="Số nguyên tố là số tự nhiên lớn hơn 1...", intent="hoi_dap")
    mocker.patch("app.api.chat.video_cache.get_done_video", mocker.AsyncMock(return_value=None))
    create = mocker.patch("app.api.chat.video_cache.get_or_create_job")

    r = await client.post("/chat", json={"message": "Số nguyên tố là gì?"}, headers=h)

    v = r.json()["video"]
    assert v["status"] == "OFFERED"
    assert v["concept_key"] == "so_nguyen_to::cung_kham_pha_2024"
    create.assert_not_called()  # chưa bấm -> chưa tạo job


async def test_chat_cache_hit_hien_video_ngay(client, mocker):
    # Đã có video cho khái niệm -> trả DONE + URL ngay, không cần bấm (US-19).
    h = await _auth(client)
    _fake_graph(mocker, answer="Số nguyên tố là số tự nhiên lớn hơn 1...", intent="hoi_dap")
    mocker.patch("app.api.chat.video_cache.get_done_video", mocker.AsyncMock(
        return_value=SimpleNamespace(id=9, status="DONE", video_url="/video/files/x.mp4")))

    r = await client.post("/chat", json={"message": "Số nguyên tố là gì?"}, headers=h)

    v = r.json()["video"]
    assert v["status"] == "DONE" and v["video_url"] == "/video/files/x.mp4"


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


async def test_chat_hoc_sinh_duoc_moi_luyen_tap_itest(client, mocker):
    """Học sinh + intent hỏi đáp + có cấu hình i-Test -> mời luyện tập (offer topic)."""
    import app.api.chat as chat_api

    h = await _auth(client)  # role hoc_sinh
    _fake_graph(mocker, answer="Số nguyên tố là...", intent="hoi_dap")
    mocker.patch.object(chat_api.settings, "itest_database_url", "mysql+pymysql://x")

    body = (await client.post("/chat", json={"message": "Số nguyên tố là gì?"}, headers=h)).json()

    assert body["itest"] == {"topic": "Số nguyên tố là gì?"}  # offer mang chủ đề


async def test_chat_intent_ngoai_pham_vi_khong_moi_itest(client, mocker):
    """intent 'sinh_de' không thuộc _ITEST_INTENTS -> không mời (itest=None)."""
    import app.api.chat as chat_api

    h = await _auth(client)
    _fake_graph(mocker, answer="đề...", intent="sinh_de")
    mocker.patch.object(chat_api.settings, "itest_database_url", "mysql+pymysql://x")

    body = (await client.post("/chat", json={"message": "tạo đề"}, headers=h)).json()
    assert body["itest"] is None


async def test_chat_chua_cau_hinh_itest_thi_khong_moi(client, mocker):
    """Chưa cấu hình ITEST_DATABASE_URL -> không mời luyện tập."""
    import app.api.chat as chat_api

    h = await _auth(client)
    _fake_graph(mocker, answer="Số nguyên tố là...", intent="hoi_dap")
    mocker.patch.object(chat_api.settings, "itest_database_url", "")

    body = (await client.post("/chat", json={"message": "Số nguyên tố?"}, headers=h)).json()
    assert body["itest"] is None


async def test_chat_tra_ve_chip_goi_y(client, mocker):
    """Câu trả lời kèm ĐÚNG 1 chip 'tạo đề ngắn luyện tập'."""
    h = await _auth(client)
    _fake_graph(mocker, answer="Tập hợp là...", intent="hoi_dap")
    body = (await client.post("/chat", json={"message": "Số nguyên âm là gì?"}, headers=h)).json()
    assert len(body["suggestions"]) == 1
    assert body["suggestions"][0]["label"] == "Tạo một đề ngắn luyện tập"
    # query NHÚNG chủ đề vừa hỏi -> bài tập bám sát nội dung
    assert "Số nguyên âm là gì?" in body["suggestions"][0]["query"]
    assert "ôn tập" in body["suggestions"][0]["query"].lower()  # -> nhánh on_tap


async def test_chat_giai_bai_khong_video_khong_chip(client, mocker):
    """Giải bài tập (giai_bai) -> KHÔNG video minh hoạ và KHÔNG chip 'tạo đề ngắn'."""
    h = await _auth(client)
    _fake_graph(mocker, answer="Bước 1: ...", intent="giai_bai")
    body = (await client.post("/chat", json={"message": "Tính 2 + 3 x 5"}, headers=h)).json()
    assert body["video"] is None
    assert body["suggestions"] == []
