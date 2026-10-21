"""US-27 — các sửa sau lượt QC B: dữ liệu nhập CMS, seed CLI, mô tả Test thêm, cache /pool, hoàn hạn mức."""
import logging
import uuid

import pytest

from app.api import cuoi_ky
from app.db.models import VideoJob
from app.integrations.testbank.client import TestbankChuaCauHinh, TestbankLoi
from app.lessons import de_xuat
from app.main import app
from tests.api.de_xuat_khung import KhoDemGia, TbGia, cau_tb, Cau, dung_the_gioi, them_hl, tk
from tests.api.test_de_xuat import _khong_goi_model, _xoa_cache_ban_do_ar, kho_dem, tb  # noqa: F401
from tests.api.test_hoc_lieu_cms import _body


# ── 1. đường video nội bộ ───────────────────────────────────────────────────
@pytest.mark.parametrize("url", ["/video/files/..", "/video/files/...", "/video/files/../x.mp4",
                                 "/video/files/a/b.mp4", f"/video/files/khong-co-{uuid.uuid4().hex}.mp4"])
async def test_video_noi_bo_sai_hoac_khong_ton_tai_bi_tu_choi(client, session, tb, url):
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, url=url))
    assert r.status_code == 422 and r.json()["detail"] == "Video nội bộ không tồn tại", (url, r.text)


async def test_video_noi_bo_co_that_duoc_nhan_va_sua_nhan_khong_kiem_lai(client, session, tb):
    the = await dung_the_gioi(session)
    tag = uuid.uuid4().hex[:8]
    job = VideoJob(concept_key=f"us27-{tag}", sgk_version="v1", status="DONE",
                   video_url=f"/video/files/{tag}.mp4", title="t")
    session.add(job)
    await session.commit()
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, url=f"/video/files/{tag}.mp4"))
    assert r.status_code == 201, r.text
    job.status = "FAILED"                       # video bị gỡ sau đó
    await session.commit()
    r2 = await client.patch(f"/cms/hoc-lieu/{r.json()['id']}", headers=gv.h, json={"nhan": "đổi nhãn"})
    assert r2.status_code == 200, r2.text


# ── 2-3. kiểu dữ liệu sai ────────────────────────────────────────────────────
@pytest.mark.parametrize("truong,gia_tri,ten", [("qid", 5, "Mã câu"), ("option_key", 3, "Phương án"),
                                                ("nhan", ["x"], "Nhãn"), ("url", 7, "Đường dẫn"),
                                                ("ycd", {"a": 1}, "Yêu cầu cần đạt"), ("ma", 12, "Mã")])
async def test_kieu_sai_thi_422_chuoi_tieng_viet(client, session, tb, truong, gia_tri, ten):
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    b = _body(the)
    b[truong] = gia_tri
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=b)
    assert r.status_code == 422 and r.json()["detail"] == f"{ten} phải là chuỗi", r.text


@pytest.mark.parametrize("body", [[1], "abc", 5])
async def test_body_khong_phai_object_thi_422_chuoi(client, session, tb, body):
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=body)
    assert r.status_code == 422 and r.json()["detail"] == "Dữ liệu gửi lên không hợp lệ"
    r = await client.patch("/cms/hoc-lieu/1", headers=gv.h, json=body)
    assert r.status_code == 422 and r.json()["detail"] == "Dữ liệu gửi lên không hợp lệ"


# ── 4. seed CLI thiếu TESTBANK_* ─────────────────────────────────────────────
async def test_kiem_do_phu_thieu_cau_hinh_testbank_noi_tieng_viet_khong_traceback(mocker):
    from app import seed_hoc_lieu

    mocker.patch("app.integrations.testbank.client.tao_client", side_effect=TestbankChuaCauHinh(["TESTBANK_EMAIL"]))
    with pytest.raises(SystemExit) as e:
        await seed_hoc_lieu._ycd_cua_ar(["AR-1"])
    assert isinstance(e.value.code, str) and "TESTBANK" in e.value.code and "\n" not in e.value.code


# ── 5. mô tả Test thêm ──────────────────────────────────────────────────────
def test_noi_ten_ycd_bo_dau_cham_cuoi():
    assert de_xuat._noi_ten(["Nhận biết A.", "Nhận biết B", "C. "]) == "Nhận biết A, Nhận biết B, C"


# ── 7, 9. cache /pool + cảnh báo bị cắt ──────────────────────────────────────
async def test_pool_duoc_cache_60_giay_va_xoa_cache_xoa_ca_hai(tb, session):
    the = await dung_the_gioi(session)
    tb.dat([cau_tb(the, 1, Cau(0))])
    await de_xuat.doc_pool(tb, {de_xuat.chuan_hoa(the.ycds[0])})
    await de_xuat.doc_pool(tb, {de_xuat.chuan_hoa(the.ycds[0])})
    assert len(tb.lay_list) == 1
    # YCCĐ đang cần chưa có trong cache -> gọi lại ngay, không chờ hết hạn
    await de_xuat.doc_pool(tb, {"yccd-moi-chua-co"})
    assert len(tb.lay_list) == 2
    de_xuat.xoa_cache()
    await de_xuat.doc_pool(tb)
    assert len(tb.lay_list) == 3


async def test_pool_bi_cat_ghi_warning(tb, caplog):
    async def lay(dich, duong, params):
        return {"items": [], "total": 0, "truncated": True}

    tb.lay = lay
    caplog.set_level(logging.WARNING)
    await de_xuat.doc_pool(tb)
    assert any("bị cắt" in r.getMessage() for r in caplog.records)


# ── 8. hoàn hạn mức khi không tạo được đề ───────────────────────────────────
async def test_test_them_loi_testbank_hoan_han_muc(client, session, tb, kho_dem):
    hs = await tk(client)
    tb.loi = TestbankLoi("mạng", tam_thoi=True)
    r = await client.post("/exam/cuoi-ky/test-them", headers=hs.h, json={"ar_ids": ["AR-1"], "bo_qid": []})
    assert r.status_code == 503
    assert [v for k, v in kho_dem.d.items() if k.startswith("dequota:")] == [0]


async def test_generate_loi_testbank_hoan_han_muc(client, session, tb, kho_dem):
    hs = await tk(client)
    tb.loi = TestbankLoi("mạng", tam_thoi=True)
    r = await client.post("/exam/cuoi-ky/generate", headers=hs.h, json={})
    assert r.status_code == 503
    assert [v for k, v in kho_dem.d.items() if k.startswith("dequota:")] == [0]


async def test_generate_thanh_cong_van_tinh_mot_luot(client, session, tb, kho_dem):
    the = await dung_the_gioi(session)
    tb.dat([cau_tb(the, 1, Cau(0))])
    hs = await tk(client)
    r = await client.post("/exam/cuoi-ky/generate", headers=hs.h, json={})
    assert r.status_code == 200 and r.json()["de_id"]
    assert [v for k, v in kho_dem.d.items() if k.startswith("dequota:")] == [1]


# ── 6. dependency tuỳ chọn ──────────────────────────────────────────────────
async def test_dependency_tuy_chon_khong_tra_cuu_overrides_bang_tay():
    import inspect

    assert "request.app.dependency_overrides" not in inspect.getsource(cuoi_ky)
    assert app.dependency_overrides.get(cuoi_ky.lay_testbank) is None
