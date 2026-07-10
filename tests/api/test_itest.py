"""Test endpoint /itest: phân quyền + suggest/assemble (mock chi_tieu để không
phụ thuộc ma trận đã nạp)."""

import uuid
from types import SimpleNamespace

import app.api.itest as itest_api


async def _auth(client, role: str) -> dict:
    email = f"itest-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "T", "role": role})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _mock_chi_tieu(mocker, chi_tieu):
    mocker.patch.object(
        itest_api.service, "tinh_chi_tieu",
        mocker.AsyncMock(return_value=(SimpleNamespace(id=1), chi_tieu, {})),
    )


async def test_suggest_thieu_token_401(client):
    r = await client.post("/itest/suggest", json={"hoc_ky": "hk1", "tong_so_cau": 10})
    assert r.status_code == 401


async def test_hoc_sinh_khong_duoc_sync(client):
    h = await _auth(client, "hoc_sinh")
    r = await client.post("/itest/sync", headers=h)
    assert r.status_code == 403


async def test_hoc_sinh_khong_duoc_xem_mappings(client):
    h = await _auth(client, "hoc_sinh")
    r = await client.get("/itest/mappings", headers=h)
    assert r.status_code == 403


async def test_suggest_tra_ve_o_ma_tran(client, mocker):
    h = await _auth(client, "hoc_sinh")
    _mock_chi_tieu(mocker, {"de": 2, "trung_binh": 1, "kho": 1})
    mocker.patch.object(itest_api, "build_suggest_cells", mocker.AsyncMock(return_value=[]))
    mocker.patch.object(itest_api, "suggest_for_cells", mocker.AsyncMock(return_value=[]))

    r = await client.post("/itest/suggest", json={"hoc_ky": "hk1", "tong_so_cau": 4}, headers=h)

    assert r.status_code == 200
    assert r.json()["chi_tieu"] == {"de": 2, "trung_binh": 1, "kho": 1}


async def test_assemble_giu_attribution_va_check_ma_tran(client, mocker):
    h = await _auth(client, "hoc_sinh")
    _mock_chi_tieu(mocker, {"de": 1, "trung_binh": 1})

    r = await client.post("/itest/assemble", json={
        "hoc_ky": "hk1", "tong_so_cau": 2,
        "itest_picks": [{"itest_id": "q9", "muc_do": "de", "noi_dung": "1+1?"}],
        "ai_cau": [{"muc_do": "de", "noi_dung": "2+2?"}],
    }, headers=h)

    assert r.status_code == 200
    body = r.json()
    nguon = {c["nguon"] for c in body["bo_luyen"]["cau_hoi"]}
    assert nguon == {"itest:q9", "ai"}                 # attribution giữ nguồn
    assert body["ma_tran"]["thieu"] == {"trung_binh": 1}  # cảnh báo ô thiếu
    assert body["ma_tran"]["khop"] is False
