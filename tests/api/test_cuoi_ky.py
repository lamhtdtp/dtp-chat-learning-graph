"""Đề cuối kỳ rút từ DTP Testbank (nhánh B6 của docs/STEPS-demo-4-buoc.md).

Testbank được thay bằng bản giả cắm qua dependency override — mock ở RANH GIỚI
(`TestbankClient.goi`), phần rút đề / lấy nội dung / chấm / ghi lịch sử chạy thật.
"""
import json
import uuid

import pytest
from sqlalchemy import select

from app.api import cuoi_ky
from app.db.models import (
    Blueprint, BlueprintCell, CurriculumTopic, Grade, QuizAttempt, QuizAttemptItem, Subject, User,
)
from app.integrations.testbank.client import TestbankChuaCauHinh, TestbankLoi
from app.main import app

ANH = "3f2a" + "0" * 26 + "e9"
YCD_1 = "Nhận biết được khái niệm số nguyên tố, hợp số."
YCD_2 = "Xác định được ước chung, ước chung lớn nhất."


def _cau(qid, ar, dang, *, answer, options=None, stem="Câu hỏi?", yccd=YCD_1, **kv):
    return {"qid": qid, "display_code": f"{qid}/{dang}", "ar_id": ar, "yccd_text": yccd,
            "difficulty": "B", "format_code": dang, "competency_code": "GQV",
            "stem": stem, "options": options or [], "answer_key": answer,
            "explanation": f"Lời giải {qid}", "family_qid": qid, "version": "V01",
            "group_id": None, "stimulus": None, "stimulus_lead": None,
            "assets": {}, "asset_sizes": {}, **kv}


_PA = [{"key": k, "text": t} for k, t in zip("ABCD", ["2", "3", "6", "36"])]
KHO = [
    _cau("Q1", "AR26-TO06-CK1-001", "TN1", answer="C", options=_PA,
         stem=f"ƯCLN [[anh:{ANH}]] bằng?",
         assets={ANH: "/api/content/media/3f/2a/x.png"}),
    _cau("Q2", "AR26-TO06-CK1-002", "DSN", answer="3,5", yccd=YCD_2),
    _cau("Q3", "AR26-TO06-CK1-002", "DS", answer="Đ,S,Đ,S", yccd=YCD_2,
         options=[{"key": k, "text": f"Khẳng định {k}"} for k in "ABCD"]),
    _cau("Q4", "AR26-TO06-CK1-001", "TL", answer=""),
]


class TestbankGiaLap:
    """Thay `TestbankClient`: chỉ cần `goi()` — rut_de/lay_cau đi qua đó."""

    def __init__(self, kho=KHO, *, thieu=None, loi: Exception | None = None, bo_qid=()):
        self.kho = {c["qid"]: c for c in kho}
        self.thieu = thieu
        self.loi = loi
        self.bo_qid = set(bo_qid)
        self.goi_list: list[tuple[str, str, dict]] = []

    __test__ = False

    async def goi(self, dich, duong, body):
        self.goi_list.append((dich, duong, body))
        if self.loi:
            raise self.loi
        if duong == "/exams:preview":
            ds = [c for c in self.kho.values()
                  if not body.get("ar_ids") or c["ar_id"] in body["ar_ids"]]
            return {"quota": {"B": len(ds)}, "is_complete": not self.thieu,
                    "shortage": self.thieu or {}, "pool_size": len(ds),
                    "message": "Thiếu 2 câu mức V." if self.thieu else f"Đã rút {len(ds)} câu.",
                    "items": [{"ordinal": i, "qid": c["qid"], "ar_id": c["ar_id"],
                               "difficulty_code": "B", "format_code": c["format_code"]}
                              for i, c in enumerate(ds, start=1)]}
        if duong == "/questions:resolve":
            assert body["include_answers"] is True
            return [self.kho[q] for q in body["qids"] if q not in self.bo_qid]
        raise AssertionError(duong)


@pytest.fixture
def tb():
    gia = TestbankGiaLap()
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    yield gia
    app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


@pytest.fixture(autouse=True)
def _khong_goi_model(mocker):
    """Lý do từng phương án gọi LLM — mặc định trả rỗng, test nào cần thì đè."""
    return mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value="{}"))


@pytest.fixture(autouse=True)
def _han_muc(mocker):
    dem = {"n": 0}

    async def incr(key, ttl):
        dem["n"] += 1
        return dem["n"]

    return mocker.patch("app.api.cuoi_ky.llm_cache.incr_quota", side_effect=incr)


async def _hs(client):
    email = f"ck-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _rut(client, hs, **kv):
    r = await client.post("/exam/cuoi-ky/generate", headers=hs,
                          json={"subject": "TO", "grade": "06", "exam": "CK1", "total": 12, **kv})
    assert r.status_code == 200, r.text
    return r.json()


# ── Rút đề ──────────────────────────────────────────────────────────────────
async def test_rut_de_tra_de_bai_khong_kem_dap_an(client, tb):
    """Ràng buộc cứng: không có đáp án / lời giải / lý do nào xuống trình duyệt
    trước khi nộp. Lý do từng phương án cũng lộ đáp án ("vì sao đúng")."""
    hs = await _hs(client)
    d = await _rut(client, hs)
    assert d["de_id"] and len(d["cau"]) == 4
    raw = json.dumps(d, ensure_ascii=False)
    for cam in ("answer_key", "explanation", "Lời giải", "ly_do", "dap_an", "3,5", "Đ,S,Đ,S"):
        assert cam not in raw, cam


async def test_rut_de_doi_anh_thanh_url_mo_duoc(client, tb):
    hs = await _hs(client)
    c1 = (await _rut(client, hs))["cau"][0]
    assert "[[anh:" not in c1["de_html"] and '<img class="tb-anh"' in c1["de_html"]
    assert [p["key"] for p in c1["phuong_an"]] == list("ABCD")


async def test_bao_cau_tu_luan_khong_tu_cham(client, tb):
    hs = await _hs(client)
    cau = {c["qid"]: c for c in (await _rut(client, hs))["cau"]}
    assert cau["Q4"]["tu_cham"] is False and cau["Q1"]["tu_cham"] is True


async def test_thieu_cau_thi_bao_ro_khong_lang_le(client, tb):
    tb.thieu = {"V": 2}
    hs = await _hs(client)
    d = await _rut(client, hs)
    assert d["du_cau"] is False and "Thiếu 2 câu mức V." in d["thong_bao"]


async def test_kho_tra_thieu_qid_thi_bao(client, tb):
    """`questions:resolve` bỏ qua LẶNG LẼ câu không thuộc kho mình thấy."""
    tb.bo_qid = {"Q3"}
    hs = await _hs(client)
    d = await _rut(client, hs)
    assert len(d["cau"]) == 3 and d["du_cau"] is False
    assert "1 câu" in d["thong_bao"]


async def test_khop_yccd_ve_dung_bai_hoc(client, session, tb):
    """B5: khớp NGUYÊN VĂN đã chuẩn hoá (ycd_key) với ma trận của mình, để sau
    khi nộp còn chỉ học sinh về đúng bài."""
    subj = await session.scalar(select(Subject).filter_by(name="Toán"))
    grade = await session.scalar(select(Grade).filter_by(name="Lớp 6"))
    if subj is None:
        subj = Subject(name="Toán"); session.add(subj)
    if grade is None:
        grade = Grade(name="Lớp 6"); session.add(grade)
    await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id, mach_noi_dung="Số tự nhiên",
                        don_vi_kien_thuc=f"Số nguyên tố {uuid.uuid4().hex[:4]}", order_index=999)
    session.add(t); await session.flush()
    bp = Blueprint(subject_id=subj.id, grade_id=grade.id, semester=f"t-{uuid.uuid4().hex[:6]}")
    session.add(bp); await session.flush()
    # YCCĐ riêng cho test — DB dev dùng chung đã có ma trận Toán 6 thật.
    ycd = f"Nhận biết được điều thử {uuid.uuid4().hex[:6]}, hợp số."
    # Khác khoảng trắng + hoa thường so với testbank -> vẫn phải khớp.
    session.add(BlueprintCell(blueprint_id=bp.id, muc_do="de", nang_luc="", topic_id=t.id,
                              yeu_cau_can_dat="  NHẬN BIẾT  " + ycd[len("Nhận biết "):] + " ",
                              dang_thuc="TN", ti_le=1, nhom_ti_le=0))
    tid = t.id            # đọc TRƯỚC commit — sau commit là MissingGreenlet
    await session.commit()
    tb.kho["Q9"] = _cau("Q9", "AR26-TO06-CK1-009", "TN1", answer="A", options=_PA, yccd=ycd)
    # Dấu câu khác là YCCĐ khác — không khớp lỏng.
    tb.kho["Q8"] = _cau("Q8", "AR26-TO06-CK1-008", "TN1", answer="A", options=_PA,
                        yccd=ycd.rstrip("."))

    hs = await _hs(client)
    cau = {c["qid"]: c for c in (await _rut(client, hs))["cau"]}
    assert cau["Q9"]["topic_id"] == tid
    assert cau["Q8"]["topic_id"] is None


async def test_gui_ar_ids_cho_bai_lam_moi(client, tb):
    hs = await _hs(client)
    d = await _rut(client, hs, ar_ids=["AR26-TO06-CK1-002"])
    assert {c["qid"] for c in d["cau"]} == {"Q2", "Q3"}
    assert tb.goi_list[0][2]["ar_ids"] == ["AR26-TO06-CK1-002"]


# ── Lỗi testbank không thành 500 ─────────────────────────────────────────────
@pytest.mark.parametrize("loi,ma", [
    (TestbankLoi("mạng", tam_thoi=True), 503),
    (TestbankLoi("403", tam_thoi=False, ma=403), 502),
])
async def test_loi_testbank_thanh_thong_diep_tieng_viet(client, tb, loi, ma):
    tb.loi = loi
    hs = await _hs(client)
    r = await client.post("/exam/cuoi-ky/generate", headers=hs,
                          json={"subject": "TO", "grade": "06", "exam": "CK1", "total": 12})
    assert r.status_code == ma and "Kho đề" in r.json()["detail"]


async def test_chua_cau_hinh_thi_503_va_khong_tru_luot(client, _han_muc, mocker):
    mocker.patch("app.api.cuoi_ky.tao_client",
                 side_effect=TestbankChuaCauHinh(["TESTBANK_EMAIL"]))
    hs = await _hs(client)
    r = await client.post("/exam/cuoi-ky/generate", headers=hs, json={})
    assert r.status_code == 503 and "chưa được kết nối" in r.json()["detail"]
    assert _han_muc.call_count == 0


async def test_het_luot_thi_chan_truoc_khi_goi_testbank(client, tb, mocker):
    mocker.patch.object(cuoi_ky.settings, "de_cuoi_ky_daily_limit", 1)
    hs = await _hs(client)
    await _rut(client, hs)
    n = len(tb.goi_list)
    r = await client.post("/exam/cuoi-ky/generate", headers=hs, json={})
    assert r.status_code == 429 and len(tb.goi_list) == n


# ── Nộp bài ─────────────────────────────────────────────────────────────────
async def _nop(client, hs, de_id, tra_loi):
    r = await client.post("/exam/cuoi-ky/submit", headers=hs,
                          json={"de_id": de_id, "tra_loi": tra_loi})
    assert r.status_code == 200, r.text
    return r.json()


async def test_cham_moi_dang_va_khong_tinh_cau_tu_luan(client, tb):
    hs = await _hs(client)
    d = await _rut(client, hs)
    kq = await _nop(client, hs, d["de_id"],
                    {"Q1": "C", "Q2": "3.5", "Q3": "Đ,S,S,S", "Q4": "bài tự luận"})
    cau = {c["qid"]: c for c in kq["cau"]}
    assert cau["Q1"]["dung"] and cau["Q2"]["dung"] and not cau["Q3"]["dung"]
    assert (cau["Q3"]["so_y_dung"], cau["Q3"]["so_y"]) == (3, 4)
    assert cau["Q4"]["cham_duoc"] is False
    # Câu tự luận không vào tổng — không trừ điểm học sinh vì giới hạn của máy.
    assert (kq["diem"], kq["tong"]) == (2, 3)
    # Sau khi nộp mới có đáp án + lời giải.
    assert cau["Q1"]["dap_an"] == "C" and "Lời giải Q1" in cau["Q1"]["giai_html"]


async def test_nop_ghi_lich_su_theo_yccd_khong_gan_bai(client, session, tb):
    hs = await _hs(client)
    d = await _rut(client, hs)
    await _nop(client, hs, d["de_id"], {"Q1": "B", "Q2": "3.5", "Q3": "Đ,S,Đ,S"})

    at = await session.scalar(select(QuizAttempt).where(QuizAttempt.nguon == "cuoi_ky")
                              .order_by(QuizAttempt.id.desc()))
    assert at.topic_id is None and (at.diem, at.tong) == (2, 3)
    items = (await session.scalars(select(QuizAttemptItem).filter_by(attempt_id=at.id)
                                   .order_by(QuizAttemptItem.id))).all()
    assert [(i.qid, i.ar_id, i.chon, i.dung) for i in items] == [
        ("Q1", "AR26-TO06-CK1-001", "B", False),
        ("Q2", "AR26-TO06-CK1-002", "3.5", True),
        ("Q3", "AR26-TO06-CK1-002", "Đ,S,Đ,S", True)]
    assert items[0].dap_an == "C" and items[0].ycd_text == YCD_1


async def test_ket_qua_cham_theo_yccd(client, tb):
    hs = await _hs(client)
    d = await _rut(client, hs)
    kq = await _nop(client, hs, d["de_id"], {"Q1": "B", "Q2": "3.5", "Q3": "Đ,S,S,S"})
    theo = {y["ar_id"]: y for y in kq["theo_ycd"]}
    assert (theo["AR26-TO06-CK1-001"]["dung"], theo["AR26-TO06-CK1-001"]["tong"]) == (0, 1)
    assert (theo["AR26-TO06-CK1-002"]["dung"], theo["AR26-TO06-CK1-002"]["tong"]) == (1, 2)
    # Giữ thứ tự ma trận (mã YCCĐ), không xếp theo điểm.
    assert [y["ar_id"] for y in kq["theo_ycd"]] == sorted(theo)
    # 002 sai 1/2 câu — đủ dữ liệu để kết luận yếu nên đứng trước; 001 mới sai
    # một câu lẻ, vẫn vào đề mới nhưng xếp sau.
    assert kq["goi_y"]["ar_ids"] == ["AR26-TO06-CK1-002", "AR26-TO06-CK1-001"]


async def test_ly_do_tung_phuong_an_sinh_san_luc_rut_de(client, tb, _khong_goi_model):
    _khong_goi_model.return_value = json.dumps(
        {"A": "2 chỉ là một ước chung.", "B": "3 cũng vậy.", "C": "Đúng vì…", "D": "36 là BCNN."})
    # Q1 có hình ở đề -> không sinh. Thêm một câu chữ thuần để kiểm.
    tb.kho["Q5"] = _cau("Q5", "AR26-TO06-CK1-001", "TN1", answer="C", options=_PA,
                        stem="ƯCLN(12; 18) bằng?")
    hs = await _hs(client)
    d = await _rut(client, hs)
    assert _khong_goi_model.await_count >= 1         # sinh lúc RÚT đề, không phải lúc nộp
    _khong_goi_model.reset_mock()
    kq = await _nop(client, hs, d["de_id"], {"Q5": "D"})
    assert _khong_goi_model.await_count == 0
    q5 = next(c for c in kq["cau"] if c["qid"] == "Q5")
    assert q5["ly_do"]["D"] == {"noi_dung": "36 là BCNN.", "nguon": "ai", "dung": False}
    assert q5["ly_do"]["C"]["dung"] is True


async def test_nop_hai_lan_tra_lai_ket_qua_cu_khong_ghi_them(client, session, tb):
    """Bấm "Nộp" hai lần (mạng chậm) không được thành hai lần làm bài."""
    hs = await _hs(client)
    d = await _rut(client, hs)
    a = await _nop(client, hs, d["de_id"], {"Q1": "C"})
    b = await _nop(client, hs, d["de_id"], {"Q1": "A"})
    assert a == b
    n = await session.scalar(select(QuizAttempt.id).where(QuizAttempt.nguon == "cuoi_ky")
                             .order_by(QuizAttempt.id.desc()))
    items = (await session.scalars(select(QuizAttemptItem).filter_by(attempt_id=n))).all()
    assert len(items) == 3


async def test_khong_nop_duoc_de_cua_ban_khac(client, tb):
    d = await _rut(client, await _hs(client))
    r = await client.post("/exam/cuoi-ky/submit", headers=await _hs(client),
                          json={"de_id": d["de_id"], "tra_loi": {}})
    assert r.status_code == 404


async def test_mo_lai_de_chua_nop_khong_lo_dap_an(client, tb):
    hs = await _hs(client)
    d = await _rut(client, hs)
    r = (await client.get(f"/exam/cuoi-ky/{d['de_id']}", headers=hs)).json()
    assert r["ket_qua"] is None and "answer_key" not in json.dumps(r)
    assert [c["qid"] for c in r["cau"]] == [c["qid"] for c in d["cau"]]


# ── Lịch sử đề đã làm (GET /exam/cuoi-ky) ───────────────────────────────────
async def test_liet_ke_de_cua_minh_moi_nhat_truoc(client, tb):
    hs = await _hs(client)
    d1 = await _rut(client, hs)
    await _nop(client, hs, d1["de_id"], {"Q1": "C", "Q2": "1"})
    d2 = await _rut(client, hs)                         # rút mà chưa nộp

    ds = (await client.get("/exam/cuoi-ky", headers=hs)).json()["de"]
    assert [x["de_id"] for x in ds] == [d2["de_id"], d1["de_id"]]
    moi, cu = ds
    assert moi["da_nop"] is False and moi["diem"] is None
    assert cu["da_nop"] is True and (cu["diem"], cu["tong"]) == (1, 3)
    assert cu["exam"] == "CK1" and cu["so_cau"] == 4 and cu["dat"] is False


async def test_liet_ke_khong_lo_de_cua_ban_khac(client, tb):
    await _rut(client, await _hs(client))
    ds = (await client.get("/exam/cuoi-ky", headers=await _hs(client))).json()["de"]
    assert ds == []


async def test_liet_ke_loc_theo_ky(client, tb):
    hs = await _hs(client)
    await _rut(client, hs)                               # CK1
    await _rut(client, hs, exam="CK2")
    ds = (await client.get("/exam/cuoi-ky?exam=CK2", headers=hs)).json()["de"]
    assert [x["exam"] for x in ds] == ["CK2"]


async def test_liet_ke_khong_lo_dap_an(client, tb):
    hs = await _hs(client)
    d = await _rut(client, hs)
    await _nop(client, hs, d["de_id"], {"Q1": "C"})
    raw = json.dumps((await client.get("/exam/cuoi-ky", headers=hs)).json(), ensure_ascii=False)
    assert "answer_key" not in raw and "Lời giải" not in raw


async def test_mo_lai_de_da_nop_tra_ket_qua_cu(client, tb):
    hs = await _hs(client)
    d = await _rut(client, hs)
    kq = await _nop(client, hs, d["de_id"], {"Q1": "C"})
    r = (await client.get(f"/exam/cuoi-ky/{d['de_id']}", headers=hs)).json()
    assert r["ket_qua"] == kq


async def test_gio_nop_cung_nguon_voi_gio_rut(client, tb):
    """nop_luc và luc phải cùng một đồng hồ (Postgres). Lệch nguồn là lịch sử
    hiện giờ nộp TRƯỚC giờ rút đề cả mấy tiếng (DB +07, Python UTC)."""
    from datetime import datetime

    hs = await _hs(client)
    d = await _rut(client, hs)
    await _nop(client, hs, d["de_id"], {"Q1": "C"})
    x = (await client.get("/exam/cuoi-ky", headers=hs)).json()["de"][0]
    rut, nop = datetime.fromisoformat(x["luc"]), datetime.fromisoformat(x["nop_luc"])
    assert 0 <= (nop - rut).total_seconds() < 60
