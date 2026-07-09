import uuid
from types import SimpleNamespace

from app.main import app
from app.retrieval.retriever import RetrievedChunk


async def _auth(client) -> dict:
    email = f"sess-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _fake_graph(mocker):
    app.state.graph = SimpleNamespace(ainvoke=mocker.AsyncMock(return_value={
        "answer": "x", "intent": "hoi_dap",
        "retrieved": [RetrievedChunk(content="c", score=0.8, chuong_so=1, bai_so=1,
                                     page_no=6, tap=1, loai_noi_dung="ly_thuyet", nguon="tr.6")]}))


async def test_sessions_thieu_token_401(client):
    assert (await client.get("/sessions")).status_code == 401


async def test_xoa_phien(client, mocker):
    h = await _auth(client)
    _fake_graph(mocker)
    sid = (await client.post("/chat", json={"message": "hi"}, headers=h)).json()["session_id"]

    assert (await client.delete(f"/sessions/{sid}", headers=h)).status_code == 204
    # sau khi xoá: không còn trong danh sách, và GET messages -> 404
    assert all(s["id"] != sid for s in (await client.get("/sessions", headers=h)).json())
    assert (await client.get(f"/sessions/{sid}", headers=h)).status_code == 404


async def test_khong_xem_duoc_phien_cua_user_khac(client, mocker):
    h1 = await _auth(client)
    _fake_graph(mocker)
    sid = (await client.post("/chat", json={"message": "hi"}, headers=h1)).json()["session_id"]

    h2 = await _auth(client)  # user khác
    assert (await client.get(f"/sessions/{sid}", headers=h2)).status_code == 404
    assert all(s["id"] != sid for s in (await client.get("/sessions", headers=h2)).json())
