"""Test endpoint /exam/generate: phân quyền + luồng sinh đề (mock graph, không
gọi LLM thật)."""

import uuid

import app.exam.service as service


async def _auth(client, role: str) -> dict:
    email = f"exam-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "T", "role": role})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_thieu_token_bi_401(client):
    r = await client.post("/exam/generate", json={"hoc_ky": "hk1", "tong_so_cau": 10})
    assert r.status_code == 401


async def test_hoc_sinh_bi_cam_sinh_de(client):
    h = await _auth(client, "hoc_sinh")
    r = await client.post("/exam/generate", json={"hoc_ky": "hk1", "tong_so_cau": 10}, headers=h)
    assert r.status_code == 403


async def test_giao_vien_sinh_de_tra_ve_cau_hoi(client, mocker):
    from app.exam.check import CauHoi

    h = await _auth(client, "giao_vien")
    # Mock graph để không gọi LLM: trả về đề đã "sinh".
    mocker.patch.object(service._EXAM_GRAPH, "ainvoke", mocker.AsyncMock(return_value={
        "de_thi": [CauHoi(muc_do="de", noi_dung="1+1=?", dap_an="2", loi_giai="cộng")],
        "canh_bao": None,
        "so_lan_lap": 1,
    }))

    r = await client.post("/exam/generate", json={"hoc_ky": "hk1", "tong_so_cau": 10}, headers=h)

    assert r.status_code == 200
    body = r.json()
    assert body["hoc_ky"] == "hk1"
    assert sum(body["chi_tieu"].values()) == 10          # largest-remainder khớp tổng
    assert body["cau_hoi"][0]["noi_dung"] == "1+1=?"
    assert body["mach_noi_dung"]                          # có mạch nội dung từ ma trận


async def test_hoc_ky_khong_hop_le_bi_422(client):
    h = await _auth(client, "giao_vien")
    r = await client.post("/exam/generate", json={"hoc_ky": "hk3", "tong_so_cau": 10}, headers=h)
    assert r.status_code == 422


async def test_practice_hoc_sinh_sinh_de_ngan_theo_ma_tran(client, mocker):
    """Học sinh bấm 'Tạo một đề ngắn luyện tập' -> /exam/practice sinh đề bám ma
    trận (KHÔNG cần quyền giáo viên)."""
    from app.exam.check import CauHoi

    h = await _auth(client, "hoc_sinh")
    mocker.patch.object(service._EXAM_GRAPH, "ainvoke", mocker.AsyncMock(return_value={
        "de_thi": [CauHoi(muc_do="de", noi_dung="1+1=?", dap_an="2", loi_giai="cộng")],
        "canh_bao": None, "so_lan_lap": 1,
    }))

    r = await client.post("/exam/practice", json={}, headers=h)  # default hk1, 5 câu

    assert r.status_code == 200
    body = r.json()
    assert sum(body["chi_tieu"].values()) == 5           # đề ngắn 5 câu, khớp ma trận
    assert body["cau_hoi"][0]["noi_dung"] == "1+1=?"


async def test_practice_thieu_token_401(client):
    r = await client.post("/exam/practice", json={})
    assert r.status_code == 401


async def test_generate_mon_khong_hop_le_400(client, mocker):
    h = await _auth(client, "giao_vien")
    r = await client.post("/exam/generate", json={"hoc_ky": "hk1", "tong_so_cau": 10, "mon": "Vật lý"}, headers=h)
    assert r.status_code == 400


async def test_generate_mon_mac_dinh_toan_trong_response(client, mocker):
    from app.exam.check import CauHoi
    h = await _auth(client, "giao_vien")
    mocker.patch.object(service._EXAM_GRAPH, "ainvoke", mocker.AsyncMock(return_value={
        "de_thi": [CauHoi(muc_do="de", noi_dung="1+1=?", dap_an="2", loi_giai="c")],
        "canh_bao": None, "so_lan_lap": 1,
    }))
    body = (await client.post("/exam/generate", json={"hoc_ky": "hk1", "tong_so_cau": 10}, headers=h)).json()
    assert body["mon"] == "Toán"
