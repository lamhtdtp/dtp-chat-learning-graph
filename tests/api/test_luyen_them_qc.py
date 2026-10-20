"""US-25 — test bổ sung của QC lượt B (soát lỗ hổng sau khi DEV xong).

Phủ những chỗ test lượt A chưa chạm tới:
* Lượt luyện thêm và đề cuối kỳ NẰM CHUNG bảng `de_cuoi_ky`: mỗi đường của bên này
  không được đụng tới dòng của bên kia (nộp / mở lại / xoá một đề / xoá tất cả).
* Hoàn hạn mức khi rút không thành (`giam_quota`): đúng khoá, không âm, fail-open.
* Dữ liệu trả về khi nộp: lượt không xét đạt không mang `dat_yeu_cau` giả, DS "đúng k/n ý".
"""
import json
import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import DeCuoiKy, QuizAttempt
from app.integrations.testbank.client import TestbankLoi
from app.llm import cache as llm_cache
from tests.api.test_luyen_them import (  # noqa: F401  (fixture autouse + helper dùng chung)
    MSG_KHONG_THAY, _admin, _bai, _datnhom, _han_muc, _hs, _kho, _llm, _lam, _nop, _nop_tho,
    _rut, _rut_tho, _tra_loi, tb,
)


@pytest.fixture
def giam(mocker):
    """Theo dõi việc hoàn hạn mức (`giam_quota` thật gọi Redis — không có ở máy test)."""
    return mocker.patch("app.llm.cache.giam_quota", mocker.AsyncMock())


async def _de_cuoi_ky(session, uid) -> str:
    de_id = "ck-" + uuid.uuid4().hex[:12]
    session.add(DeCuoiKy(id=de_id, user_id=uid, tham_so_json=json.dumps({"exam": "hk1"}),
                         cau_json="[]", thong_bao=""))
    await session.commit()
    return de_id


# ═══ Chung bảng: cuối kỳ không đụng tới lượt luyện thêm ═════════════════════
async def test_de_cuoi_ky_khong_mo_nop_xoa_duoc_luot_luyen_them(client, session, tb):
    """Lượt luyện thêm dùng chung bảng với đề cuối kỳ. Nếu `/exam/cuoi-ky/*` nhận id của nó,
    học sinh nộp được lượt luyện thêm qua đường chấm của đề cuối kỳ (bỏ qua luật >= 3 câu,
    ghi attempt `nguon="cuoi_ky"` không gắn bài), xoá lịch sử luyện thêm hoặc xem đề."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    kho = _kho(bai, ["TN1"] * 4)
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, hs, bai)
    de_id = d["de_id"]

    r = await client.get(f"/exam/cuoi-ky/{de_id}", headers=hs)
    assert r.status_code == 404 and r.json()["detail"] == "Không tìm thấy đề này."
    r = await client.post("/exam/cuoi-ky/submit", headers=hs,
                          json={"de_id": de_id, "tra_loi": _tra_loi(kho, 4)})
    assert r.status_code == 404 and r.json()["detail"] == "Không tìm thấy đề này."
    r = await client.delete(f"/exam/cuoi-ky/{de_id}", headers=hs)
    assert r.status_code == 404
    assert (await client.delete("/exam/cuoi-ky?exam=hk1", headers=hs)).json()["da_xoa"] == 0

    # Không có gì bị ghi / mất: lượt vẫn còn nguyên, chưa nộp, nộp bình thường được sau đó.
    assert await session.scalar(select(func.count()).select_from(QuizAttempt).where(
        QuizAttempt.user_id == uid)) == 0
    de = await session.get(DeCuoiKy, de_id)
    assert de is not None and de.ket_qua_json is None and de.loai == "luyen_them"
    kq = await _nop(client, hs, de_id, _tra_loi(kho, 4))
    assert kq["diem"] == 4 and kq["xet_dat"] is True


async def test_nop_luyen_them_bang_id_de_cuoi_ky_thi_404_giong_khong_ton_tai(client, session, tb):
    """Chiều ngược lại: `/lessons/luyen-them/submit` không chấm đề cuối kỳ và không lộ
    rằng id đó có thật (cùng thông báo với id không tồn tại)."""
    hs, uid = await _hs(client, session)
    ck = await _de_cuoi_ky(session, uid)
    la = await _nop_tho(client, hs, ck, {})
    khong_co = await _nop_tho(client, hs, "khong-co-" + uuid.uuid4().hex[:6], {})
    assert la.status_code == khong_co.status_code == 404
    assert la.json() == khong_co.json() == {"detail": MSG_KHONG_THAY}
    assert await _datnhom(session, uid, nguon="cuoi_ky") == []
    assert (await session.get(DeCuoiKy, ck)).ket_qua_json is None


async def test_xoa_tat_ca_de_cuoi_ky_khong_xoa_luot_chua_nop(client, session, tb):
    """`DELETE /exam/cuoi-ky` chỉ xoá đề cuối kỳ: lượt luyện thêm đã rút (chưa nộp) còn nguyên."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    d = await _rut(client, hs, bai)
    ck = await _de_cuoi_ky(session, uid)
    assert (await client.delete("/exam/cuoi-ky", headers=hs)).json()["da_xoa"] == 1
    assert await session.get(DeCuoiKy, ck) is None
    assert await session.get(DeCuoiKy, d["de_id"]) is not None


async def test_lich_su_cuoi_ky_chi_co_de_cuoi_ky_khi_hai_loai_cung_ton_tai(client, session, tb):
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    d = await _rut(client, hs, bai)
    ck = await _de_cuoi_ky(session, uid)
    ids = [x["de_id"] for x in (await client.get("/exam/cuoi-ky", headers=hs)).json()["de"]]
    assert ids == [ck] and d["de_id"] not in ids


# ═══ Hạn mức: hoàn lại khi rút không thành ═════════════════════════════════
async def test_rut_thanh_cong_khong_hoan_han_muc(client, session, tb, giam):
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    await _rut(client, await _hs(client), bai)
    assert giam.call_count == 0


@pytest.mark.parametrize("o", ["lay", "goi"])
async def test_kho_loi_thi_hoan_dung_khoa_da_dem(client, session, tb, _han_muc, giam, o):
    """KB24: kho lỗi không trừ hạn mức — hoàn đúng khoá đã tăng (không phải khoá khác)."""
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    tb.loi, tb.loi_o = TestbankLoi("mạng", tam_thoi=True), o
    r = await _rut_tho(client, await _hs(client), bai.tid)
    assert r.status_code == 503
    khoa_tang = _han_muc.call_args.args[0] if _han_muc.call_args.args else _han_muc.call_args.kwargs["key"]
    assert [c.args[0] for c in giam.call_args_list] == [khoa_tang]
    assert khoa_tang.startswith("ltquota:")


async def test_kho_trong_thi_hoan_han_muc(client, session, tb, giam):
    """KB5: kho chưa có câu -> không tạo lượt -> không trừ hạn mức."""
    bai = await _bai(session)
    tb.kho = {}
    r = await _rut(client, await _hs(client), bai)
    assert r["de_id"] is None
    assert giam.call_count == 1


async def test_vuot_han_muc_hoan_lai_luot_vua_dem(client, session, tb, _han_muc, giam):
    """Quá hạn mức: bộ đếm đã tăng lên N+1 -> phải trả về N, kẻo bấm thêm vẫn tăng mãi."""
    async def da_vuot(key, ttl):
        return 21

    _han_muc.side_effect = da_vuot
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    assert (await _rut_tho(client, await _hs(client), bai.tid)).status_code == 429
    assert giam.call_count == 1


async def test_bai_chua_co_ycd_khong_dem_han_muc(client, session, tb, _han_muc, giam):
    """KB6: không có gì để hỏi kho thì cũng không tiêu hạn mức."""
    bai = await _bai(session, n_ycd=0)
    r = await _rut(client, await _hs(client), bai)
    assert r["de_id"] is None
    assert _han_muc.call_count == 0 and giam.call_count == 0


async def test_admin_va_han_muc_khong_gioi_han_khong_dem_va_khong_hoan(client, session, tb, _han_muc, giam):
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    await _rut(client, await _admin(client, session), bai)
    assert _han_muc.call_count == 0 and giam.call_count == 0


# ═══ giam_quota: không âm, fail-open ═══════════════════════════════════════
class _RedisGia:
    def __init__(self, gia_tri: int, loi: Exception | None = None):
        self.v, self.loi, self.set_goi = gia_tri, loi, []

    async def decr(self, key):
        if self.loi:
            raise self.loi
        self.v -= 1
        return self.v

    async def set(self, key, val, ex=None):
        self.v = val
        self.set_goi.append((key, val, ex))


async def test_giam_quota_ve_0_khong_am(mocker):
    """Bộ đếm đã hết hạn (khoá mất) mà vẫn bị giảm -> DECR ra -1: phải đưa về 0, vì -1 là
    tặng thêm một lượt cho ngày hôm đó."""
    r = _RedisGia(0)
    mocker.patch("app.llm.cache._redis", return_value=r)
    await llm_cache.giam_quota("ltquota:1:20261020", 3600)
    assert r.v == 0 and r.set_goi == [("ltquota:1:20261020", 0, 3600)]


async def test_giam_quota_binh_thuong_chi_tru_mot(mocker):
    r = _RedisGia(5)
    mocker.patch("app.llm.cache._redis", return_value=r)
    await llm_cache.giam_quota("k", 3600)
    assert r.v == 4 and r.set_goi == []


async def test_giam_quota_redis_loi_thi_nuot_khong_nem(mocker):
    mocker.patch("app.llm.cache._redis", return_value=_RedisGia(5, loi=ConnectionError("chết")))
    await llm_cache.giam_quota("k", 3600)          # không raise


async def test_hoan_han_muc_loi_khong_lam_hong_phan_hoi_loi_kho(client, session, tb, mocker):
    """Redis chết đúng lúc hoàn: học sinh vẫn nhận thông báo kho (503), không phải 500."""
    mocker.patch("app.llm.cache._redis", return_value=_RedisGia(5, loi=ConnectionError("chết")))
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    tb.loi, tb.loi_o = TestbankLoi("mạng", tam_thoi=True), "lay"
    r = await _rut_tho(client, await _hs(client), bai.tid)
    assert r.status_code == 503 and "Kho đề" in r.json()["detail"]


# ═══ Kết quả nộp ═══════════════════════════════════════════════════════════
async def test_luot_khong_xet_dat_khong_mang_co_dat_yeu_cau(client, session, tb):
    """KB17: lượt 2/2 (dưới 3 câu chấm được) không phải "đạt" cũng không phải "chưa đạt"."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    _, kq = await _lam(client, hs, tb, bai, ["TN1", "TN1"], 2)
    assert kq["xet_dat"] is False and kq["dat_yeu_cau"] is False and kq["trang_thai"] == "chua"
    assert "2 câu chấm tự động" in kq["ghi_chu"] and "cần ít nhất 3" in kq["ghi_chu"]
    a = (await _datnhom(session, uid))[0]
    assert (a.diem, a.tong, a.dat) == (2, 2, False)


# ═══ Hàng rào "chưa làm Bài kiểm tra nhanh thì chưa được hỏi đáp án" ═══════
async def test_nop_luyen_them_khong_mo_khoa_dap_an_bai_kiem_tra_nhanh_cua_tro_ly(client, session, mocker):
    """Hàng rào ở tutor chặn 'câu 1 đáp án gì?' khi học sinh chưa nộp Bài kiểm tra nhanh (kẻo hỏi
    đủ lượt là có trọn bộ đáp án). Lượt luyện thêm dùng bộ câu KHÁC của kho, nên không được tính."""
    from sqlalchemy import select as _select

    from app.db.models import User
    from tests.api.test_tutor import _bat_qa, _dang_ky, _seed_bai

    qa = _bat_qa(mocker)
    h, email = await _dang_ky(client)
    tid = await _seed_bai(session)
    uid = await session.scalar(_select(User.id).filter_by(email=email))
    session.add(QuizAttempt(user_id=uid, topic_id=tid, diem=0, tong=0, dat=False, nguon="luyen_them"))
    await session.commit()
    r = await client.post("/tutor/ask", headers=h, json={
        "question": "Câu 1 đáp án gì?", "topic_id": tid, "anchor": "quiz:1"})
    assert r.status_code == 403 and "làm bài kiểm tra nhanh" in r.json()["detail"].lower()
    assert qa.call_count == 0
