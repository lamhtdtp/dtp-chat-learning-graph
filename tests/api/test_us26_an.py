"""US-26 mục 7 (KB 40-42): đề giao bằng mã của learning đã NGỪNG — ngừng cấp mã mới, dữ liệu cũ đọc được.

KHÔNG dùng fixture `de_giao_cu_bat`: ở đây kiểm chính trạng thái mặc định (cờ tắt).
"""
import json
import uuid

import pytest

from app.api import cuoi_ky
from app.config import settings
from app.db.models import DeCuoiKy, DeGiao
from app.main import app
from tests.api.conftest import tao_tai_khoan


@pytest.fixture
def tb_cam(mocker):
    """Testbank + LLM mà KHÔNG được chạm tới: có ai gọi là test đỏ."""
    class Cam:
        def __getattr__(self, ten):
            raise AssertionError(f"không được gọi testbank ({ten})")
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: Cam()
    llm = mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(side_effect=AssertionError("gọi LLM")))
    yield llm
    app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


@pytest.mark.parametrize("vai", ["giao_vien", "admin"])
async def test_kb40_rut_de_giao_va_cap_ma_bi_tu_choi_khong_goi_kho_hay_llm(client, tb_cam, vai):
    assert settings.de_giao_learning_bat is False
    _, h = await tao_tai_khoan(client, vai)
    r = await client.post("/de-giao/xem-truoc", headers=h, json={"exam": "CK1"})
    assert r.status_code == 410 and r.json()["detail"] == "Đề giao mới tạo trên Testbank"
    r = await client.post("/de-giao/1/cap-ma", headers=h)
    assert r.status_code == 410 and r.json()["detail"] == "Đề giao mới tạo trên Testbank"
    tb_cam.assert_not_called()


async def test_kb40_hoc_sinh_goi_duong_giao_vien_van_la_403(client, tb_cam):
    _, h = await tao_tai_khoan(client, "hoc_sinh")
    assert (await client.post("/de-giao/xem-truoc", headers=h, json={"exam": "CK1"})).status_code == 403


async def test_kb41_hoc_sinh_khong_con_nhap_duoc_ma_learning_va_khong_nop_duoc(client, tb_cam):
    _, h = await tao_tai_khoan(client, "hoc_sinh")
    r = await client.post("/de-giao/vao", headers=h, json={"ma": "K7M3PX"})
    assert r.status_code == 410 and "Testbank" in r.json()["detail"]
    r = await client.post("/de-giao/nop", headers=h, json={"de_id": "x", "tra_loi": {}})
    assert r.status_code == 410


async def _dung_bai_cu(client, session, *, nop: bool):
    gv_email, _ = await tao_tai_khoan(client, "giao_vien")
    from sqlalchemy import select
    from app.db.models import User
    gv_id = (await session.scalar(select(User).where(User.email == gv_email))).id
    hs_email, h = await tao_tai_khoan(client, "hoc_sinh")
    hs_id = (await session.scalar(select(User).where(User.email == hs_email))).id
    ma = uuid.uuid4().hex[:6].upper()
    giao = DeGiao(nguoi_tao_id=gv_id, exam="CK1", total=1, so_cau=1, ma=ma, trang_thai="mo",
                  tham_so_json=json.dumps({"exam": "CK1"}), cau_json="[]")
    session.add(giao)
    await session.flush()
    kq = {"de_id": "", "diem": 1, "tong": 1, "dat_yeu_cau": True, "khong_cham": 0, "cau": [],
          "theo_ycd": [], "goi_y": {"ar_ids": [], "tai_lieu": [], "de_moi": {}}, "ma": ma}
    de = DeCuoiKy(id=uuid.uuid4().hex[:12], user_id=hs_id, loai="de_giao", de_giao_id=giao.id,
                  tham_so_json=json.dumps({"exam": "CK1"}), cau_json="[]",
                  ket_qua_json=json.dumps(kq) if nop else None)
    session.add(de)
    de_id = de.id          # đọc TRƯỚC commit (MissingGreenlet)
    await session.commit()
    return h, de_id, ma


async def test_kb41_kb42_bai_da_nop_van_xem_duoc_bai_do_co_nhan_ngung_va_khong_mo_duoc(client, session):
    h1, nop_id, ma1 = await _dung_bai_cu(client, session, nop=True)
    (x,) = (await client.get("/exam/cuoi-ky", headers=h1)).json()["de"]
    assert (x["loai"], x["ma"], x["da_nop"], x["da_ngung"]) == ("de_giao", ma1, True, False)
    assert (await client.get(f"/exam/cuoi-ky/{nop_id}", headers=h1)).status_code == 200

    h2, do_id, ma2 = await _dung_bai_cu(client, session, nop=False)
    (y,) = (await client.get("/exam/cuoi-ky", headers=h2)).json()["de"]
    assert (y["ma"], y["da_nop"], y["da_ngung"], y["xoa_duoc"]) == (ma2, False, True, False)
    r = await client.get(f"/exam/cuoi-ky/{do_id}", headers=h2)
    assert r.status_code == 410 and "đã ngừng" in r.json()["detail"]
