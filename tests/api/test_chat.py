from types import SimpleNamespace

import pytest

from app.api.deps import get_current_user
from app.main import app
from app.retrieval.retriever import RetrievedChunk


async def test_chat_thieu_token_bi_401(client):
    r = await client.post("/chat", json={"message": "Tập hợp là gì?"})
    assert r.status_code == 401


@pytest.fixture
def as_student():
    """Bỏ qua xác thực thật, coi như đã đăng nhập là học sinh."""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, role="hoc_sinh")
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def test_chat_tra_reply_va_citations(client, as_student, mocker):
    chunk = RetrievedChunk(content="Tập hợp gồm các phần tử.", score=0.8, chuong_so=1,
                           bai_so=1, page_no=6, loai_noi_dung="ly_thuyet", nguon="Toán 6, tr.6")
    fake_graph = SimpleNamespace(ainvoke=mocker.AsyncMock(return_value={
        "answer": "Tập hợp là một nhóm các phần tử.",
        "intent": "hoi_dap",
        "retrieved": [chunk],
    }))
    app.state.graph = fake_graph

    r = await client.post("/chat", json={"message": "Tập hợp là gì?", "session_id": "s1"})

    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Tập hợp là một nhóm các phần tử."
    assert body["intent"] == "hoi_dap"
    assert body["citations"][0]["page_no"] == 6
    assert body["session_id"] == "s1"
    # thread_id gồm user_id + session_id để tách phiên theo user
    assert fake_graph.ainvoke.await_args.kwargs["config"]["configurable"]["thread_id"] == "7:s1"


async def test_chat_truyen_role_vao_graph(client, as_student, mocker):
    fake_graph = SimpleNamespace(ainvoke=mocker.AsyncMock(return_value={
        "answer": "x", "intent": "hoi_dap", "retrieved": []}))
    app.state.graph = fake_graph

    await client.post("/chat", json={"message": "hi"})

    assert fake_graph.ainvoke.await_args.args[0]["role"] == "hoc_sinh"
