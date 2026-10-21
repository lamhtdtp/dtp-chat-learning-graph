"""US-30 — bài theo mã Testbank mức 1: kết quả theo YCCĐ + Đề xuất ngay sau nộp (giai đoạn 1), đáp án +
lời giải + lý do từng phương án khi thầy cô đóng bài (giai đoạn 2). Kịch bản 1-16, 18-25 (`[tdd-core]`);
Kịch bản 17 là `[llm-eval]` — ở đây chỉ test HỢP ĐỒNG (prompt dựng từ nội dung tờ đề), chất lượng đo ở
`evals/run_ly_do_eval.py`.

Testbank giả ở ranh giới HTTP (`tests/api/delivery_gia.py`, `httpx.MockTransport`, có đường đối tác);
kho câu hỏi giả `TbGia` (cho khối Đề xuất / Test thêm / so nội dung kho); LLM giả ở
`app.exam.ly_do.gateway.complete`. Tên test ghi kịch bản.
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.api import cuoi_ky, ma_testbank
from app.config import settings
from app.db.models import DeCuoiKy, LyDoPhuongAn, LyDoToDe, QuizAttempt, QuizAttemptItem, StudentStats
from app.exam import ly_do_to_de
from app.integrations.testbank.client import TestbankLoi
from app.integrations.testbank.doi_tac import DoiTacClient
from app.llm import cache as llm_cache
from app.llm.gateway import LLMUnavailable
from app.main import app
from tests.api.de_xuat_khung import (
    Cau, KhoDemGia, TbGia, TheGioi, cau_phu, cau_tb, dung_the_gioi, lay_de_xuat, them_hl, tk,
)
from tests.api.delivery_gia import DeliveryGia, cau_mau

MA = "K7M3PX"
ANH_GIAI = "9b7c" + "0" * 26 + "a1"
MSG_CHO = "Đáp án và giải thích sẽ mở khi thầy cô đóng bài"
MSG_DONG = "Thầy cô đã đóng bài — em xem đáp án và giải thích bên dưới"
MSG_QUA_HAN = "Bài đã quá hạn mở đáp án, em hỏi lại thầy cô nhé"
MSG_CHUA_KIEM = "Chưa kiểm tra được thầy cô đã đóng bài chưa, em thử lại sau ít phút"
MSG_CHUAN_BI_KQ = "Đang chuẩn bị kết quả theo yêu cầu cần đạt, em mở lại bài sau ít phút"
MSG_CHUAN_BI_LY_DO = "Đang chuẩn bị giải thích từng phương án, em mở lại sau ít phút"
KHOA_BI_MAT = ("dap_an", "bai_giai", "giai_html", "ly_do", "answer_key", "khoa_bai_lam", "bai_lam_tb_id",
               "bai_lam_id", "dap_an_html")


# ── Hạ tầng giả ─────────────────────────────────────────────────────────────
class _Token:
    """Thay `TestbankClient` ở ranh giới token: chỉ cần `goi_tho` (cùng chữ ký, cùng đổi lỗi mạng)."""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def goi_tho(self, method, url, *, body=None, timeout=None):
        try:
            return await self.http.request(method, url, json=body, headers={"authorization": "Bearer tok-dich-vu"})
        except httpx.HTTPError as exc:
            raise TestbankLoi("Không kết nối được DTP Testbank") from exc


@dataclass
class Canh:
    client: httpx.AsyncClient
    session: object
    gia: DeliveryGia
    kho: TbGia
    the: TheGioi
    llm: object

    def phat(self, ma=MA, **kv):
        self.gia.phat(ma, cau=to_de(self.the, self.kho, **kv))

    async def hs(self, ten="Nguyễn Văn An"):
        return await tk(self.client, "hoc_sinh", ten)

    async def vao(self, h, ma=MA, ok=True):
        r = await self.client.post("/exam/ma/vao", headers=h.h, json={"ma": ma})
        if ok:
            assert r.status_code == 200, r.text
            return r.json()
        return r

    async def mo(self, h, de_id) -> dict:
        r = await self.client.get(f"/exam/ma/{de_id}", headers=h.h)
        assert r.status_code == 200, r.text
        return r.json()

    async def luu_nop(self, h, de_id, chon: dict[int, str] | None = None) -> dict:
        chon = DEFAULT_CHON if chon is None else chon
        r = await self.client.post(f"/exam/ma/{de_id}/nop", headers=h.h, json={
            "cau": [{"stt": s, "chon": v, "seq": 1} for s, v in chon.items()]})
        assert r.status_code == 200, r.text
        return r.json()

    async def lam_va_nop(self, h, ma=MA, chon=None) -> dict:
        d = await self.vao(h, ma)
        return await self.luu_nop(h, d["de_id"], chon)

    async def dong_bo_db(self, de_id) -> dict:
        r = (await self.session.execute(text(
            "SELECT muc, khoa_bai_lam, bai_lam_tb_id, chi_tiet_json IS NOT NULL AS co_ct, dap_an_mo, "
            "het_han_dap_an, attempt_id FROM de_cuoi_ky WHERE id = :i"), {"i": de_id})).mappings().one()
        return dict(r)

    def so_chi_tiet(self) -> int:
        return len(self.gia.goi_theo("GET", "/doi-tac/bai-lam/chi-tiet"))

    def xem_lai_het_han(self, ma=None):
        """Giả lập đã qua 60 giây kể từ lần hỏi Testbank gần nhất (mọi bài, hoặc bài của mã `ma`)."""
        return self.session.execute(text(
            "UPDATE de_cuoi_ky SET kiem_luc = clock_timestamp() - interval '61 seconds' "
            "WHERE (CAST(:m AS text) IS NULL OR ma_testbank = :m)"), {"m": ma})


#: Chọn mặc định: 6 đúng (1, 2, 4, 6, 7, 8), 2 sai (9, 10), 1 đúng một phần (3), 1 tự luận (5).
DEFAULT_CHON = {1: "B", 2: "A,B", 3: "Đ,Đ", 4: "3", 5: "Em làm như sau", 6: "C", 7: "C", 8: "C", 9: "A", 10: "A"}
#: Câu thuộc YCCĐ: 1,2 -> 0 · 3,4,5 -> 1 · 6,7 -> 2 · 8,9,10 -> 3
_YCD = {1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 3, 9: 3, 10: 3}


def to_de(the: TheGioi, kho: TbGia, *, sua: dict[int, dict] | None = None, ycd: dict[int, str] | None = None) -> list[dict]:
    """10 câu của tờ đề. Các câu TN1 từ 6 đến 10 lấy ĐÚNG nội dung kho (để so nội dung với kho); `sua`
    là chỗ thầy cô sửa riêng cho tờ đề (đáp án, một phương án…)."""
    cau = cau_mau()
    for i in range(6, 11):
        k = kho.kho[the.qid(i)]
        cau[i - 1] = {"dang": "TN1", "de_bai": k["stem"], "dap_an": k["answer_key"],
                      "phuong_an": [{"khoa": o["key"], "nhan": o["key"], "noi_dung": o["text"]} for o in k["options"]]}
    cau[2]["cham_mot_phan"] = True
    cau[8]["bai_giai"] = f"Xem hình [[anh:{ANH_GIAI}]]"
    cau[8]["anh_giai"] = {ANH_GIAI: "/api/content/media/9b/7c/giai.png"}
    for i, c in enumerate(cau, start=1):
        c.update({"qid": the.qid(i), "phien_ban": "V01", "ar_id": the.ar(_YCD[i]),
                  "yccd": (ycd or {}).get(i, the.ycds[_YCD[i]])})
        c.setdefault("bai_giai", f"Lời giải {the.qid(i)}")
    for i, kv in (sua or {}).items():
        cau[i - 1].update(kv)
    return cau


@pytest.fixture(autouse=True)
def _khong_dung_redis(mocker):
    kho = KhoDemGia()
    for ten in ("incr_quota", "giam_quota", "get", "set"):
        mocker.patch.object(llm_cache, ten, getattr(kho, ten))
    return kho


@pytest.fixture(autouse=True)
def _xoa_cache():
    from app.lessons import de_xuat
    de_xuat.xoa_cache()
    yield
    de_xuat.xoa_cache()


@pytest_asyncio.fixture
async def canh(client, session, monkeypatch, mocker):
    the = await dung_the_gioi(session, (2, 2))
    kho = TbGia()
    # Kho: câu của bài (qid Q1..Q10) + 3 câu phụ cho mỗi YCCĐ (để "Test thêm" có câu khác mà rút).
    kho.dat([cau_tb(the, i, Cau(_YCD[i])) for i in range(1, 11)])
    kho.them(*[cau_phu(the, k, j) for k in range(4) for j in range(3)])
    gia = DeliveryGia()
    http = httpx.AsyncClient(transport=gia.transport())
    goc = "http://tb.test/api/delivery"
    from app.integrations.testbank.delivery import DeliveryClient
    app.dependency_overrides[ma_testbank.lay_delivery] = lambda: DeliveryClient(goc, http)
    app.dependency_overrides[ma_testbank.lay_doi_tac] = lambda: DoiTacClient(goc, _Token(http))
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: kho
    monkeypatch.setattr(settings, "testbank_delivery_url", goc)
    monkeypatch.setattr(settings, "testbank_doi_tac_bat", True)
    monkeypatch.setattr(settings, "testbank_chi_tiet_sau_nop_bat", True)
    llm = mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value="{}"))

    khoa_phien = asyncio.Lock()

    @asynccontextmanager
    async def mo_session():
        # Việc nền dùng chính phiên của test (transaction được rollback ở cuối); tuần tự vì một phiên
        # không commit đồng thời được (thật thì mỗi việc một phiên riêng).
        async with khoa_phien:
            yield session

    monkeypatch.setattr(ly_do_to_de, "mo_session", mo_session)
    c = Canh(client, session, gia, kho, the, llm)
    c.phat()
    yield c
    for f in (ma_testbank.lay_delivery, ma_testbank.lay_doi_tac, cuoi_ky.lay_testbank):
        app.dependency_overrides.pop(f, None)


def _bi_mat_khong_lo(obj, *them):
    raw = json.dumps(obj, ensure_ascii=False)
    for k in (*KHOA_BI_MAT, *them):
        assert k not in raw, f"lộ '{k}'"


def llm_tra(keys="ABCD", tien_to="LÝ DO"):
    return json.dumps({k: f"{tien_to} {k}" for k in keys}, ensure_ascii=False)


# ═══ A. Chuyển từ mức 0 sang mức 1 ═════════════════════════════════════════
async def test_kb1_co_tat_giu_nguyen_us29(canh, monkeypatch):
    monkeypatch.setattr(settings, "testbank_doi_tac_bat", False)
    monkeypatch.setattr(settings, "testbank_chi_tiet_sau_nop_bat", False)
    h = await canh.hs()
    out = await canh.lam_va_nop(h)
    assert out["trang_thai"] == "DA_NOP" and out["giai_doan"] == 0 and out["ghi_chu"] == []
    assert set(out["ket_qua"]) == {"diem", "tong", "dat_yeu_cau", "so_cau_cho_cham", "so_cau_dung", "cau",
                                   "cach_nop", "nop_luc"}
    assert [g for g in canh.gia.goi if g[1].startswith("/doi-tac")] == []        # không đụng đường đối tác
    assert canh.gia.goi_theo("POST", "/vao-thi") and len(canh.gia.bai) == 1 and canh.gia.bai_dt == {}
    n = (await canh.session.execute(select(func.count()).select_from(QuizAttempt)
                                    .where(QuizAttempt.user_id == h.id))).scalar()
    assert n == 0                                         # không thống kê YCCĐ (US-29 KB 20)


async def test_kb2_co_bat_bai_moi_vao_bang_duong_doi_tac(canh):
    an = await canh.hs("Nguyễn Văn An")
    d = await canh.vao(an)
    (vao,) = canh.gia.goi_theo("POST", "/doi-tac/vao-thi")
    assert vao[3] == {"ma": MA, "hoc_sinh": {"ma": str(an.id), "ho_ten": "Nguyễn Văn An"}}     # tên thuần
    b = canh.gia.bai_cua(MA, str(an.id))
    assert b["nhan"] == f"Gia sư DTP · HS{an.id}"
    assert canh.gia.tokens[0] == "Bearer tok-dich-vu"
    db = await canh.dong_bo_db(d["de_id"])
    assert db["muc"] == 1 and db["khoa_bai_lam"] is None and db["bai_lam_tb_id"]
    assert canh.gia.bai == {} and canh.gia.goi_theo("POST", "/vao-thi") == []
    _bi_mat_khong_lo(d)


async def test_kb3_mat_phan_hoi_khi_vao_thi_khong_tao_bai_thu_hai(canh):
    an = await canh.hs()
    canh.gia.rot_phan_hoi = True
    r = await canh.vao(an, ok=False)
    assert r.status_code == 503 and r.json()["detail"] == "Chưa mở được đề, em thử lại sau ít phút nhé"
    (bai_id,) = canh.gia.bai_dt
    d = await canh.vao(an)                                  # nhập lại
    assert list(canh.gia.bai_dt) == [bai_id] and len(canh.gia.theo_hs) == 1
    assert (await canh.dong_bo_db(d["de_id"]))["bai_lam_tb_id"] == bai_id


async def test_kb4_bai_muc_0_dang_lam_do_khi_bat_co(canh, monkeypatch):
    monkeypatch.setattr(settings, "testbank_doi_tac_bat", False)
    an = await canh.hs()
    d = await canh.vao(an)
    await canh.client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=an.h,
                          json={"cau": [{"stt": 1, "chon": "B", "seq": 1}]})
    monkeypatch.setattr(settings, "testbank_doi_tac_bat", True)
    d2 = await canh.vao(an)                                  # nhập lại khi cờ đã bật
    assert d2["de_id"] == d["de_id"] and d2["tra_loi"] == {"c1": "B"}
    d3 = await canh.mo(an, d["de_id"])                        # mở từ lịch sử
    assert d3["de_id"] == d["de_id"]
    assert canh.gia.goi_theo("POST", "/doi-tac/vao-thi") == [] and len(canh.gia.bai) == 1 and canh.gia.bai_dt == {}
    n = await canh.luu_nop(an, d["de_id"], {1: "B"})
    assert n["giai_doan"] == 0 and "theo_ycd" not in n["ket_qua"]
    assert [g for g in canh.gia.goi if g[1].startswith("/doi-tac")] == []
    canh.gia.dong(MA)                                        # lượt đóng sau đó: vẫn là kết quả mức 0
    assert (await canh.mo(an, d["de_id"]))["giai_doan"] == 0
    assert [g for g in canh.gia.goi if g[1].startswith("/doi-tac")] == []


async def test_kb5_tat_co_khong_lam_gay_bai_muc_1(canh, monkeypatch):
    an, binh = await canh.hs(), await canh.hs("Bình")
    d = await canh.vao(an)
    monkeypatch.setattr(settings, "testbank_doi_tac_bat", False)
    assert (await canh.mo(an, d["de_id"]))["trang_thai"] == "DANG_LAM"
    r = await canh.client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=an.h,
                              json={"cau": [{"stt": 1, "chon": "B", "seq": 1}]})
    assert r.status_code == 200 and canh.gia.goi_theo("PUT", "/doi-tac/bai-lam/tra-loi")
    out = await canh.luu_nop(an, d["de_id"], {1: "B"})
    assert out["trang_thai"] == "DA_NOP" and out["giai_doan"] == 1
    assert canh.gia.bai == {}
    await canh.vao(binh)                                     # bài vào thi MỚI sau khi tắt cờ: mức 0
    assert len(canh.gia.bai) == 1 and len(canh.gia.bai_dt) == 1


@pytest.mark.parametrize("tra, thong_bao, tinh_sai, ma_tt", [
    ("404", "Mã không đúng hoặc bài đã đóng, em hỏi lại thầy cô nhé", True, 404),
    ("HOC_SINH", "Em nhập sai mã nhiều lần, thử lại sau 10 phút nhé", False, 429),
    ("DOI_TAC", "Hệ thống đang tạm khoá nhập mã, em thử lại sau 8 phút", False, 429),
    ("401", "Chưa mở được đề, em thử lại sau ít phút nhé", False, 502),
    ("403", "Chưa mở được đề, em thử lại sau ít phút nhé", False, 502),
    ("404_duong", "Chưa mở được đề, em thử lại sau ít phút nhé", False, 502),
    ("500", "Chưa mở được đề, em thử lại sau ít phút nhé", False, 503),
])
async def test_kb6_loi_vao_thi_bang_duong_doi_tac(canh, caplog, tra, thong_bao, tinh_sai, ma_tt):
    h = await canh.hs()
    canh.gia.chan_giay = 480
    if tra == "404":
        r = await canh.vao(h, "R4T8WN", ok=False)
    else:
        if tra in ("HOC_SINH", "DOI_TAC"):
            canh.gia.chan_dt = tra
        else:
            canh.gia.dt_loi = tra
        with caplog.at_level(logging.WARNING):
            r = await canh.vao(h, ok=False)
    assert r.status_code == ma_tt and r.json()["detail"] == thong_bao
    dem = await llm_cache.get(ma_testbank._khoa_do(h.id))
    assert (dem == 1) if tinh_sai else (dem in (None, 0))
    assert canh.gia.bai == {} and canh.gia.goi_theo("POST", "/vao-thi") == []     # KHÔNG rơi về mức 0
    if tra in ("DOI_TAC", "401", "403", "404_duong", "500"):
        assert "CANH_BAO" in caplog.text
    n = (await canh.session.execute(select(func.count()).select_from(DeCuoiKy)
                                    .where(DeCuoiKy.user_id == h.id))).scalar()
    assert n == 0


# ═══ B. Giai đoạn 1 ═══════════════════════════════════════════════════════
async def test_kb7_nop_khi_luot_con_mo(canh):
    an = await canh.hs()
    out = await canh.lam_va_nop(an)
    assert out["giai_doan"] == 1 and out["ghi_chu"] == [MSG_CHO] and out["co_chi_tiet"] is True
    kq = out["ket_qua"]
    assert kq["diem"] == 3.25 and kq["tong"] == 4.5          # 6 câu đúng x 0,5 + 1 câu đúng một phần x 0,25 and kq["so_cau_cho_cham"] == 1 and kq["khong_cham"] == 1
    nhan = {c["stt"]: c["nhan"] for c in kq["cau"]}
    assert nhan[1] == "Đúng" and nhan[3] == "Đúng một phần" and nhan[9] == "Sai" and nhan[5] == "Chưa chấm"
    assert {c["stt"]: c["chon"] for c in kq["cau"]}[2] == "A,B"
    # kết quả theo YCCĐ: đúng / tổng câu chấm tự động, xếp như đề tự sinh (theo mã YCCĐ)
    assert [(y["ar_id"], y["dung"], y["tong"]) for y in kq["theo_ycd"]] == [
        (canh.the.ar(0), 2, 2), (canh.the.ar(1), 1, 2), (canh.the.ar(2), 2, 2), (canh.the.ar(3), 1, 3)]
    dx = kq["de_xuat"]
    assert dx["test_them"] and set(dx["test_them"]["ar_ids"]) == {canh.the.ar(1), canh.the.ar(3)}
    assert dx["doc_them"]["bai_hoc"][0]["topic_id"] == canh.the.bai[0].tid
    sai = [c for c in kq["cau"] if c["stt"] in (3, 9, 10)]
    assert all(c["topic_id"] and c["bai_xuat_ban"] is True for c in sai)
    assert next(c for c in kq["cau"] if c["stt"] == 1)["dung"] is True
    # tuyệt đối không có đáp án / lời giải / lý do / hình lời giải
    _bi_mat_khong_lo(out, ANH_GIAI, "Lời giải")
    assert out["trang_thai"] == "DA_NOP"


async def test_kb8_gan_cau_theo_nguyen_van_ycd_tren_to_de(canh, caplog):
    y = canh.the.ycds
    canh.phat(ycd={3: "  " + y[1].upper().replace(" ", "  ") + " ", 7: y[2].rstrip(".") + ",."})
    an = await canh.hs()
    with caplog.at_level(logging.WARNING):
        out = await canh.lam_va_nop(an)
    cau = {c["stt"]: c for c in out["ket_qua"]["cau"]}
    assert cau[3]["topic_id"] == canh.the.bai[0].tid and cau[3]["bai_xuat_ban"] is True      # khác hoa thường / khoảng trắng
    assert cau[7]["topic_id"] is None and cau[7]["bai_xuat_ban"] is False
    assert canh.the.ar(2) in caplog.text and "không khớp" in caplog.text                      # lỗi tra cứu nêu mã YCCĐ
    # câu 6 (cùng YCCĐ, đúng nguyên văn) vẫn khớp; câu 7 không đóng góp bài học vào Đề xuất
    assert cau[6]["topic_id"] == canh.the.bai[1].tid
    ten = [b["topic_id"] for b in out["ket_qua"]["de_xuat"]["doc_them"]["bai_hoc"]]
    assert canh.the.bai[1].tid in ten                      # nhờ câu 8-10 (YCCĐ 3) sai; câu 7 không thêm gì


async def test_kb9_thong_ke_ycd_dung_mot_lan_xp_khong_cong_lai(canh):
    an = await canh.hs()
    out = await canh.lam_va_nop(an)
    s = canh.session

    async def dem():
        at = (await s.execute(select(QuizAttempt).where(QuizAttempt.user_id == an.id))).scalars().all()
        xp = (await s.execute(select(StudentStats.xp_total).where(StudentStats.user_id == an.id))).scalar()
        return at, xp
    at, xp = await dem()
    assert len(at) == 1 and (at[0].diem, at[0].tong, at[0].nguon) == (6, 9, "de_giao")
    items = (await s.execute(select(QuizAttemptItem).where(QuizAttemptItem.attempt_id == at[0].id))).scalars().all()
    assert len(items) == 9 and sum(1 for i in items if i.dung) == 6                  # Đúng một phần = chưa đúng
    assert all(i.dap_an == "" for i in items) and 5 not in [i.ycd_key for i in items]
    assert not any(i.ycd_text == canh.the.ycds[1] and i.chon == "Em làm như sau" for i in items)   # TL không tính
    assert xp == 6 * 5 + 10                                                    # như US-29 G3: 6 câu đúng + thưởng đạt (3,25/4,5 điểm)
    # mở lại nhiều lần, rồi lượt đóng -> đủ đáp án: không thêm lần nộp, không thêm XP
    await canh.mo(an, out["de_id"])
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    assert (await canh.mo(an, out["de_id"]))["giai_doan"] == 2
    at2, xp2 = await dem()
    assert len(at2) == 1 and xp2 == xp


async def test_kb9_luat_ycd_con_yeu_tinh_ca_lan_nop_nay(canh):
    from app.lessons import ycd_thong_ke
    an = await canh.hs()
    out = await canh.lam_va_nop(an)
    assert set(out["ket_qua"]["de_xuat"]["test_them"]["ar_ids"]) == {canh.the.ar(1), canh.the.ar(3)}
    tk_ycd = {r.ar_id: (r.dung, r.tong) for r in await ycd_thong_ke.theo_ycd(canh.session, an.id)}
    assert tk_ycd == {canh.the.ar(0): (2, 2), canh.the.ar(1): (1, 2), canh.the.ar(2): (2, 2), canh.the.ar(3): (1, 3)}
    assert [r.ycd_key for r in ycd_thong_ke.con_yeu(await ycd_thong_ke.theo_ycd(canh.session, an.id))]


async def test_kb10_test_them_chi_gom_cau_cua_ycd_yeu_lay_tu_kho(canh):
    an = await canh.hs()
    out = await canh.lam_va_nop(an)
    tt = out["ket_qua"]["de_xuat"]["test_them"]
    assert set(tt["bo_qid"]) == {canh.the.qid(i) for i in range(1, 11)}            # ưu tiên câu khác câu của bài
    r = await canh.client.post("/exam/cuoi-ky/test-them", headers=an.h,
                               json={"ar_ids": tt["ar_ids"], "bo_qid": tt["bo_qid"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["de_id"] and d["de_id"] != out["de_id"]
    qids = {c["qid"] for c in d["cau"]}
    assert qids and not (qids & set(tt["bo_qid"])) and all("-X" in q for q in qids)
    # là bài tự luyện của An, không liên quan lượt phát: mã Testbank không thêm bài nào
    assert len(canh.gia.bai_dt) == 1


async def test_kb11_hoc_lieu_theo_cau_va_phuong_an_khong_ap_dung(canh):
    gv = await tk(canh.client, "chuyen_gia")
    q = canh.the.qid(9)
    theo_cau = await them_hl(canh.client, gv, canh.the, 3, qid=q, option_key="A", nhan="HL theo cau A")
    theo_ycd = await them_hl(canh.client, gv, canh.the, 3, nhan="HL theo YCCD")
    an = await canh.hs()
    out = await canh.lam_va_nop(an)                          # câu 9: An chọn A và Sai
    dx = lay_de_xuat(out)
    ma = [m["ma"] for g in (dx["video"], dx["doc_them"]) if g for m in g["hoc_lieu"]]
    assert theo_ycd["ma"] in ma and theo_cau["ma"] not in ma
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    dx2 = lay_de_xuat(await canh.mo(an, out["de_id"]))
    ma2 = [m["ma"] for g in (dx2["video"], dx2["doc_them"]) if g for m in g["hoc_lieu"]]
    assert theo_ycd["ma"] in ma2 and theo_cau["ma"] not in ma2


@pytest.mark.parametrize("tinh_huong, kiem, them", [
    ("tat_co", None, []),
    ("500", "500", [MSG_CHUAN_BI_KQ]),
    ("404_duong", "404_duong", [MSG_CHUAN_BI_KQ]),
])
async def test_kb12_chua_lay_duoc_chi_tiet_luc_nop(canh, monkeypatch, caplog, tinh_huong, kiem, them):
    if tinh_huong == "tat_co":
        monkeypatch.setattr(settings, "testbank_chi_tiet_sau_nop_bat", False)
    else:
        canh.gia.chi_tiet_loi = kiem
    an = await canh.hs()
    with caplog.at_level(logging.WARNING):
        out = await canh.lam_va_nop(an)
    assert out["giai_doan"] == 0 and out["ghi_chu"] == them and out["co_chi_tiet"] is False
    assert [c["nhan"] for c in out["ket_qua"]["cau"]][:2] == ["Đúng", "Đúng"] and "theo_ycd" not in out["ket_qua"]
    assert MSG_CHO not in json.dumps(out, ensure_ascii=False)                  # không nói gì về đáp án sau này
    assert (await canh.session.execute(select(func.count()).select_from(QuizAttempt)
                                       .where(QuizAttempt.user_id == an.id))).scalar() == 0
    assert (await canh.session.execute(select(StudentStats.xp_total).where(StudentStats.user_id == an.id))).scalar() == 40
    assert ("CANH_BAO" in caplog.text) == (tinh_huong == "404_duong")
    if tinh_huong != "tat_co":
        canh.gia.chi_tiet_loi = None                                            # lần mở sau Testbank trả chi tiết
        out2 = await canh.mo(an, out["de_id"])
        assert out2["giai_doan"] == 1 and out2["ghi_chu"] == [MSG_CHO]
        await canh.mo(an, out["de_id"])
        n = (await canh.session.execute(select(func.count()).select_from(QuizAttempt)
                                        .where(QuizAttempt.user_id == an.id))).scalar()
        assert n == 1                                                           # thống kê đúng một lần
        xp = (await canh.session.execute(select(StudentStats.xp_total).where(StudentStats.user_id == an.id))).scalar()
        assert xp == 40


async def test_kb12_het_gio_khong_co_chi_tiet_va_luot_dong_thi_den_thang_giai_doan_2(canh):
    canh.gia.chi_tiet_loi = "500"
    an = await canh.hs()
    out = await canh.lam_va_nop(an)
    canh.gia.chi_tiet_loi = None
    canh.gia.dong(MA)
    out2 = await canh.mo(an, out["de_id"])
    assert out2["giai_doan"] == 2 and out2["ghi_chu"] == [MSG_DONG]


@pytest.mark.parametrize("cach", ["dong_luot", "het_gio"])
async def test_kb13_bai_duoc_testbank_tu_nop(canh, cach):
    if cach == "het_gio":
        canh.gia.phat(MA, cau=to_de(canh.the, canh.kho), phut=30)
    an = await canh.hs()
    d = await canh.vao(an)
    await canh.client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=an.h,
                          json={"cau": [{"stt": 1, "chon": "B", "seq": 1}]})
    if cach == "dong_luot":
        canh.gia.dong(MA)
    else:
        canh.gia.het_gio.add(next(iter(canh.gia.bai_dt)))
    r = await canh.client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=an.h,
                              json={"cau": [{"stt": 2, "chon": "A,B", "seq": 2}]})
    assert r.status_code == 200 and r.json()["da_nop"] is True
    bai = r.json()["bai"]
    assert canh.so_chi_tiet() == 1                         # lấy chi tiết ngay trong lần đó
    assert bai["thong_bao"] == ("Thầy cô đã đóng bài, bài của em đã được nộp với các câu đã lưu" if cach == "dong_luot"
                                else "Bài đã tự nộp khi hết giờ")
    if cach == "dong_luot":
        assert bai["giai_doan"] == 2                       # lượt đã đóng: bỏ qua giai đoạn 1
    else:
        assert bai["giai_doan"] == 1


# ═══ C. Giai đoạn 2 ═══════════════════════════════════════════════════════
async def test_kb14_mo_lai_sau_khi_thay_co_dong_luot(canh):
    canh.llm.return_value = llm_tra("ABCD")
    an = await canh.hs()
    out1 = await canh.lam_va_nop(an)
    assert canh.so_chi_tiet() == 1
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    out = await canh.mo(an, out1["de_id"])
    assert canh.so_chi_tiet() == 2                                        # hỏi Testbank đúng một lần
    assert out["giai_doan"] == 2 and out["ghi_chu"] == [MSG_DONG]
    cau = {c["stt"]: c for c in out["ket_qua"]["cau"]}
    assert cau[6]["dap_an"] == "C" and "Lời giải" in cau[6]["giai_html"]
    assert cau[2]["dap_an"] == "A,B" and cau[3]["dap_an"] == "Đ,S"
    # đúng / sai, điểm, YCCĐ không đổi so với giai đoạn 1
    for k in ("diem", "tong", "dat_yeu_cau"):
        assert out["ket_qua"][k] == out1["ket_qua"][k]
    assert out["ket_qua"]["theo_ycd"] == out1["ket_qua"]["theo_ycd"]
    assert [(c["stt"], c["nhan"], c["dung"]) for c in out["ket_qua"]["cau"]] == \
           [(c["stt"], c["nhan"], c["dung"]) for c in out1["ket_qua"]["cau"]]
    # chép bản đầy đủ: các lần mở sau không hỏi lại Testbank
    for _ in range(3):
        await canh.xem_lai_het_han()
        assert (await canh.mo(an, out1["de_id"]))["giai_doan"] == 2
    assert canh.so_chi_tiet() == 2
    db = await canh.dong_bo_db(out1["de_id"])
    assert db["dap_an_mo"] is True


async def test_kb14_hien_thi_dung_to_de_cua_thay_co_khi_khac_kho(canh):
    canh.phat(sua={6: {"dap_an": "A", "bai_giai": "Thầy cô giải khác"}})
    an = await canh.hs()
    out1 = await canh.lam_va_nop(an, chon={6: "A"})
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    cau = {c["stt"]: c for c in (await canh.mo(an, out1["de_id"]))["ket_qua"]["cau"]}
    assert cau[6]["dap_an"] == "A" and "Thầy cô giải khác" in cau[6]["giai_html"] and cau[6]["dung"] is True
    assert canh.kho.kho[canh.the.qid(6)]["answer_key"] == "C"             # kho vẫn nói C


async def test_kb15_chi_kiem_khi_mo_bai_va_toi_da_mot_lan_moi_60_giay(canh):
    an = await canh.hs()
    ds = []
    for ma in ("K7M3PA", "K7M3PB", "K7M3PC"):
        canh.phat(ma)
        ds.append(await canh.lam_va_nop(an, ma=ma))
    truoc = len(canh.gia.goi)
    r = await canh.client.get("/exam/cuoi-ky", headers=an.h)               # mở lịch sử
    assert r.status_code == 200 and len(r.json()["de"]) == 3
    assert len(canh.gia.goi) == truoc                                      # không gọi Testbank cho bài nào
    # mở một bài chờ đáp án (lượt chưa đóng) nhiều lần: nhiều nhất một lần hỏi trong 60 giây
    for _ in range(5):
        out = await canh.mo(an, ds[0]["de_id"])
        assert out["giai_doan"] == 1 and out["ghi_chu"] == [MSG_CHO]
    assert len(canh.gia.goi) == truoc
    await canh.xem_lai_het_han()
    await canh.mo(an, ds[0]["de_id"])
    await canh.mo(an, ds[0]["de_id"])
    assert len(canh.gia.goi) == truoc + 1                                  # đúng một lần sau khi hết 60 giây


def test_kb15_khong_co_tac_vu_nen_hoi_testbank_dinh_ky():
    """Chỉ ba nơi được gọi `chi_tiet` của dịch vụ phát đề và đều nằm trong request (không Celery beat,
    không vòng lặp nền): nơi định nghĩa, nơi gọi và router."""
    import pathlib
    goc = pathlib.Path(__file__).resolve().parents[2] / "app"
    co_goi = {f.relative_to(goc).as_posix() for f in goc.rglob("*.py") if ".chi_tiet(" in f.read_text()}
    assert co_goi == {"exam/bai_ma_chi_tiet.py"}
    assert not [f for f in goc.rglob("*.py")
                if "beat_schedule" in f.read_text() or "periodic_task" in f.read_text()]


async def test_kb16_ly_do_theo_noi_dung_to_de(canh, mocker):
    qid = canh.the.qid(6)
    # Lý do đã có của (Q, v1) theo nội dung KHO — từ đề tự sinh.
    for k in "ABCD":
        canh.session.add(LyDoPhuongAn(qid=qid, version="V01", option_key=k, noi_dung=f"LÝ DO KHO {k}", nguon="ai"))
    await canh.session.commit()
    # L2: thầy cô sửa đáp án và một phương án (cùng mã câu và phiên bản).
    pa = [{"khoa": o["key"], "nhan": o["key"], "noi_dung": o["text"]} for o in canh.kho.kho[qid]["options"]]
    pa[1] = {**pa[1], "noi_dung": "7 (đã sửa)"}
    canh.gia.phat("M2M2M2", cau=to_de(canh.the, canh.kho, sua={6: {"dap_an": "B", "phuong_an": pa}}))
    canh.phat(MA)
    canh.llm.return_value = llm_tra("ABCD", "LÝ DO TỜ ĐỀ")

    def goi_cau_6():
        return [c for c in canh.llm.await_args_list if f"Đề {qid} ?" in c.args[1][0]["content"]]
    an, binh = await canh.hs("An"), await canh.hs("Bình")
    a = await canh.lam_va_nop(an)
    b = await canh.lam_va_nop(binh, ma="M2M2M2", chon={6: "B"})
    canh.gia.dong(MA)
    canh.gia.dong("M2M2M2")
    await canh.xem_lai_het_han()
    cau_a = {c["stt"]: c for c in (await canh.mo(an, a["de_id"]))["ket_qua"]["cau"]}
    assert {k: v["noi_dung"] for k, v in cau_a[6]["ly_do"].items()} == {k: f"LÝ DO KHO {k}" for k in "ABCD"}
    assert goi_cau_6() == []                                            # An: dùng lý do đã có, không gọi LLM cho câu này
    cau_b = {c["stt"]: c for c in (await canh.mo(binh, b["de_id"]))["ket_qua"]["cau"]}
    assert cau_b[6]["ly_do"] == {} and cau_b[6]["ly_do_ghi_chu"] == MSG_CHUAN_BI_LY_DO   # không lấy lý do của kho
    assert len(goi_cau_6()) == 1                                        # việc nền đã sinh từ tờ đề L2
    prompt = goi_cau_6()[0].args[1][0]["content"]
    assert "7 (đã sửa)" in prompt and "B. 7 (đã sửa) — ĐÚNG" in prompt and "A. 2 — SAI" in prompt
    cau_b2 = {c["stt"]: c for c in (await canh.mo(binh, b["de_id"]))["ket_qua"]["cau"]}
    assert {k: v["noi_dung"] for k, v in cau_b2[6]["ly_do"].items()} == {k: f"LÝ DO TỜ ĐỀ {k}" for k in "ABCD"}
    assert cau_b2[6]["ly_do"]["B"]["dung"] is True and cau_b2[6]["ly_do"]["C"]["dung"] is False
    # 30 học sinh khác cùng lượt L2 sang giai đoạn 2: dùng lại, không thêm lời gọi LLM cho câu này
    canh.gia.luot["M2M2M2"]["mo"] = True
    xs = []
    for i in range(30):
        hs = await canh.hs(f"Khác{i}")
        xs.append((hs, await canh.lam_va_nop(hs, ma="M2M2M2", chon={6: "B"})))
    canh.gia.dong("M2M2M2")
    await canh.xem_lai_het_han()
    for hs, x in xs:
        cau = {c["stt"]: c for c in (await canh.mo(hs, x["de_id"]))["ket_qua"]["cau"]}
        assert {k: v["noi_dung"] for k, v in cau[6]["ly_do"].items()} == {k: f"LÝ DO TỜ ĐỀ {k}" for k in "ABCD"}
    assert len(goi_cau_6()) == 1


async def test_kb16_dau_van_noi_dung():
    c = {"format_code": "TN1", "stem": "ƯCLN  của 12 và 18?", "stimulus": "",
         "options": [{"key": "A", "text": "2"}, {"key": "B", "text": "6"}], "answer_key": "B",
         "explanation": "Vì 6."}
    h = ly_do_to_de.dau_van(c)
    assert ly_do_to_de.dau_van({**c, "stem": "ƯCLN của 12 và 18? "}) == h               # khoảng trắng thừa không tính
    assert ly_do_to_de.dau_van({**c, "answer_key": "A"}) != h
    assert ly_do_to_de.dau_van({**c, "options": [c["options"][0], {"key": "B", "text": "7"}]}) != h
    assert ly_do_to_de.dau_van({**c, "explanation": "Vì 7."}) != h


async def test_kb18_ly_do_khong_lam_cham_xem_dap_an_va_llm_chet_khong_bia(canh):
    canh.llm.side_effect = LLMUnavailable("hết quota")
    an = await canh.hs()
    out1 = await canh.lam_va_nop(an)
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    out = await canh.mo(an, out1["de_id"])
    cau = {c["stt"]: c for c in out["ket_qua"]["cau"]}
    assert cau[6]["dap_an"] == "C" and cau[6]["giai_html"]                    # đáp án + lời giải có ngay
    assert cau[6]["ly_do"] == {} and cau[6]["ly_do_ghi_chu"] == MSG_CHUAN_BI_LY_DO
    # LLM sống lại, mở lại thì thấy
    canh.llm.side_effect = None
    canh.llm.return_value = llm_tra("ABCD")
    await canh.mo(an, out1["de_id"])
    cau = {c["stt"]: c for c in (await canh.mo(an, out1["de_id"]))["ket_qua"]["cau"]}
    assert set(cau[6]["ly_do"]) == set("ABCD") and cau[6]["ly_do_ghi_chu"] == ""


async def test_kb18_model_tra_thieu_phuong_an_thi_de_thieu_khong_bia(canh):
    canh.llm.return_value = json.dumps({"A": "Lý do A", "C": "Lý do C"}, ensure_ascii=False)
    an = await canh.hs()
    out1 = await canh.lam_va_nop(an)
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    await canh.mo(an, out1["de_id"])
    n_goi = canh.llm.await_count
    cau = {c["stt"]: c for c in (await canh.mo(an, out1["de_id"]))["ket_qua"]["cau"]}
    assert set(cau[6]["ly_do"]) == {"A", "C"} and cau[6]["ly_do_ghi_chu"] == ""
    await canh.mo(an, out1["de_id"])
    assert canh.llm.await_count == n_goi                                      # thiếu thì chấp nhận thiếu, không gọi lại


async def test_kb19_cau_co_hinh_va_tu_luan_o_giai_doan_2(canh):
    canh.llm.return_value = llm_tra("ABCD")
    an = await canh.hs()
    out1 = await canh.lam_va_nop(an)
    assert ANH_GIAI not in json.dumps(out1) and "giai.png" not in json.dumps(out1)      # giai đoạn 1: không hình lời giải
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    await canh.mo(an, out1["de_id"])
    out = await canh.mo(an, out1["de_id"])
    cau = {c["stt"]: c for c in out["ket_qua"]["cau"]}
    assert cau[1]["dap_an"] == "B" and cau[1]["giai_html"] and cau[1]["ly_do"] == {}    # có hình trong đề bài: không lý do
    assert cau[1]["ly_do_ghi_chu"] == ""                                                  # và cũng không "đang chuẩn bị"
    assert 'giai.png' in cau[9]["giai_html"] and "<img" in cau[9]["giai_html"]           # hình chỉ trong lời giải
    assert cau[5]["dang"] == "TL" and cau[5]["ly_do"] == {} and cau[5]["chon"] == "Em làm như sau"
    assert cau[5]["giai_html"] and cau[5]["nhan"] == "Chưa chấm"
    assert cau[4]["dang"] == "DSN" and cau[4]["ly_do"] == {}


async def test_kb20_qua_han_xem_lai_tren_testbank(canh):
    an, binh = await canh.hs("An"), await canh.hs("Bình")
    a = await canh.lam_va_nop(an)
    b = await canh.lam_va_nop(binh)
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    assert (await canh.mo(an, a["de_id"]))["giai_doan"] == 2                 # An mở khi còn trong hạn: chép đủ
    canh.gia.het_han.add(MA)                                                 # quá 30 ngày: Testbank 410 mọi lần đọc
    truoc = len(canh.gia.goi)
    out = await canh.mo(an, a["de_id"])
    assert out["giai_doan"] == 2 and len(canh.gia.goi) == truoc              # An: từ bản chép, không gọi Testbank
    ob = await canh.mo(binh, b["de_id"])                                     # Bình chưa từng mở sau khi đóng
    assert ob["giai_doan"] == 1 and ob["ghi_chu"] == [MSG_QUA_HAN] and "dap_an" not in json.dumps(ob)
    sau = len(canh.gia.goi)
    ob2 = await canh.mo(binh, b["de_id"])
    assert ob2["ghi_chu"] == [MSG_QUA_HAN] and len(canh.gia.goi) == sau      # các lần sau không gọi lại
    assert ob2["ket_qua"]["theo_ycd"] == ob["ket_qua"]["theo_ycd"]


# ═══ D. Lịch sử ═══════════════════════════════════════════════════════════
async def test_kb21_nhan_trang_thai_trong_lich_su(canh, monkeypatch):
    an = await canh.hs()
    monkeypatch.setattr(settings, "testbank_doi_tac_bat", False)
    canh.phat("MUCZER")
    muc0 = await canh.lam_va_nop(an, ma="MUCZER")
    monkeypatch.setattr(settings, "testbank_doi_tac_bat", True)
    for ma in ("CHKDAP", "DUDAPA", "KHCTX2"):
        canh.phat(ma)
    cho = await canh.lam_va_nop(an, ma="CHKDAP")
    du = await canh.lam_va_nop(an, ma="DUDAPA")
    canh.gia.chi_tiet_loi = "500"
    khong_ct = await canh.lam_va_nop(an, ma="KHCTX2")
    canh.gia.chi_tiet_loi = None
    canh.gia.dong("DUDAPA")
    await canh.xem_lai_het_han("DUDAPA")
    await canh.mo(an, du["de_id"])
    truoc = len(canh.gia.goi)
    ds = (await canh.client.get("/exam/cuoi-ky", headers=an.h)).json()["de"]
    assert len(canh.gia.goi) == truoc
    nhan = {x["ma"]: x["nhan_trang_thai"] for x in ds}
    assert nhan == {"MUCZER": None, "CHKDAP": "Chờ thầy cô đóng bài", "DUDAPA": "Đã có đáp án", "KHCTX2": None}
    assert all(x["xoa_duoc"] is False for x in ds)
    r = await canh.client.delete(f"/exam/cuoi-ky/{cho['de_id']}", headers=an.h)
    assert r.status_code == 403


# ═══ E. Bảo mật ═══════════════════════════════════════════════════════════
async def test_kb22_khong_lo_dap_an_truoc_khi_dong_ke_ca_khi_learning_co_san(canh):
    qid = canh.the.qid(6)
    # Learning có sẵn đáp án + lý do của cùng mã câu: kho, LyDoPhuongAn, và lý do theo nội dung tờ đề.
    for k in "ABCD":
        canh.session.add(LyDoPhuongAn(qid=qid, version="V01", option_key=k, noi_dung=f"BI MAT KHO {k}", nguon="ai"))
    h = ly_do_to_de.dau_van(ly_do_to_de.cau_kieu_kho({
        "qid": qid, "phien_ban": "V01", "dang": "TN1", "de_bai": canh.kho.kho[qid]["stem"], "khoi_du_kien": "",
        "phuong_an": [{"khoa": o["key"], "noi_dung": o["text"]} for o in canh.kho.kho[qid]["options"]],
        "dap_an": "C", "bai_giai": f"Lời giải {qid}"}))
    for k in "ABCD":
        canh.session.add(LyDoToDe(noi_dung_hash=h, option_key=k, noi_dung=f"BI MAT TO DE {k}", nguon="ai"))
    canh.session.add(LyDoToDe(noi_dung_hash=h, option_key="", noi_dung="", nguon="ai"))
    await canh.session.commit()
    canh.gia.ro_dap_an = True                                              # Testbank lỡ để lọt đáp án khi lượt còn mở
    an = await canh.hs()
    d = await canh.vao(an)
    tat_ca = [d]
    nop = await canh.luu_nop(an, d["de_id"])
    tat_ca += [nop, await canh.mo(an, d["de_id"]), await canh.vao(an),
               (await canh.client.get("/exam/cuoi-ky", headers=an.h)).json()]
    raw = json.dumps(tat_ca, ensure_ascii=False)
    for cam in ("BI MAT", "dap_an", "giai_html", "ly_do", "Lời giải", "giai.png", ANH_GIAI, "answer_key"):
        assert cam not in raw, cam
    assert nop["giai_doan"] == 1 and nop["ghi_chu"] == [MSG_CHO]
    # bản chép cũng không giữ đáp án
    ct = (await canh.session.execute(text("SELECT chi_tiet_json FROM de_cuoi_ky WHERE id = :i"),
                                     {"i": d["de_id"]})).scalar()
    assert all(c["dap_an"] is None and c["bai_giai"] is None for c in json.loads(ct)["cau"])
    # chỉ khi cờ của CHÍNH bài này bật (lượt đã đóng) mới có đáp án
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    assert (await canh.mo(an, d["de_id"]))["giai_doan"] == 2


async def test_kb23_chi_chu_bai_xem_duoc_bi_mat_khong_xuong_trinh_duyet_va_log(canh, caplog):
    caplog.set_level(logging.DEBUG)
    canh.llm.return_value = llm_tra("ABCD")
    an, binh = await canh.hs("An"), await canh.hs("Bình")
    a = await canh.lam_va_nop(an)
    bai_id = next(iter(canh.gia.bai_dt))
    canh.gia.dong(MA)
    await canh.xem_lai_het_han()
    day_du = await canh.mo(an, a["de_id"])
    await canh.mo(an, a["de_id"])
    # người khác (học sinh khác, giáo viên, chuyên gia, admin) gọi thẳng
    r_binh = await canh.client.get(f"/exam/ma/{a['de_id']}", headers=binh.h)
    r_ko_co = await canh.client.get("/exam/ma/khong-co-bai-nay", headers=binh.h)
    assert r_binh.status_code == 404 and r_binh.json() == r_ko_co.json()
    for vai in ("giao_vien", "chuyen_gia", "admin"):
        x = await tk(canh.client, vai)
        r = await canh.client.get(f"/exam/ma/{a['de_id']}", headers=x.h)
        assert r.status_code in (403, 404) and r.json()["detail"] != "Bài" and "dap_an" not in r.text
    _bi_mat_khong_lo(a)
    # không token / mã bài làm / đáp án trong log
    for cam in (bai_id, "tok-dich-vu", "Bearer", "Lời giải", "LÝ DO", "dap_an"):
        assert cam not in caplog.text, cam
    raw = json.dumps(day_du, ensure_ascii=False)
    assert bai_id not in raw and "tok-dich-vu" not in raw
    assert canh.gia.tokens and all(t == "Bearer tok-dich-vu" for t in canh.gia.tokens)       # token CÓ gửi cho Testbank


# ═══ F. Lỗi hệ thống ══════════════════════════════════════════════════════
@pytest.mark.parametrize("loi", ["500", "mang"])
async def test_kb24_testbank_chet_khi_mo_bai_cho_dap_an(canh, loi):
    an = await canh.hs()
    a = await canh.lam_va_nop(an)
    canh.gia.chi_tiet_loi = loi
    await canh.xem_lai_het_han()
    out = await canh.mo(an, a["de_id"])
    assert out["giai_doan"] == 1 and out["ghi_chu"] == [MSG_CHO, MSG_CHUA_KIEM]
    for k in ("diem", "tong", "dat_yeu_cau"):
        assert out["ket_qua"][k] == a["ket_qua"][k]
    assert out["ket_qua"]["theo_ycd"] == a["ket_qua"]["theo_ycd"]
    from app.integrations.testbank.delivery import TIMEOUT
    assert TIMEOUT.read == 10.0                                              # quá 10 giây thì dùng bản chép


async def test_kb25_testbank_khong_con_bai_do(canh, caplog):
    an = await canh.hs()
    a = await canh.lam_va_nop(an)
    canh.gia.chi_tiet_loi = "404_bai"
    await canh.xem_lai_het_han()
    with caplog.at_level(logging.WARNING):
        out = await canh.mo(an, a["de_id"])
    assert out["giai_doan"] == 1 and out["ket_qua"]["diem"] == a["ket_qua"]["diem"]
    assert "CANH_BAO testbank_khong_con_bai_lam" in caplog.text
    db = await canh.dong_bo_db(a["de_id"])
    assert db["co_ct"] is True and db["attempt_id"]                          # không xoá bản chép


async def test_vao_lai_bai_da_bi_tu_nop_khi_mat_phan_hoi_dung_lai_cau_tu_chi_tiet(canh):
    """Mất phản hồi vào thi, lượt đóng trước khi em nhập lại: Testbank trả bài ĐÃ NỘP (không kèm câu).
    Learning dựng câu từ chi tiết sau nộp và thấy luôn giai đoạn 2."""
    an = await canh.hs()
    canh.gia.rot_phan_hoi = True
    assert (await canh.vao(an, ok=False)).status_code == 503
    canh.gia.dong(MA)
    d = await canh.vao(an)
    assert d["trang_thai"] == "DA_NOP" and d["giai_doan"] == 2 and len(d["cau"]) == 10
    assert d["cau"][0]["de_html"] and d["ket_qua"]["cau"][0]["dap_an"] == "B"


# ═══ Hợp đồng & hàm thuần ═════════════════════════════════════════════════
async def test_kb17_contract_prompt_dung_tu_noi_dung_to_de():
    """KB 17 `[llm-eval]`: chất lượng đo ở `evals/run_ly_do_eval.py`; ở đây chỉ khẳng định prompt dựng từ
    ĐÁP ÁN / LỜI GIẢI CỦA TỜ ĐỀ (không phải của kho) và nhãn đúng / sai theo tờ đề."""
    from app.exam import ly_do as ly_do_svc
    c = ly_do_to_de.cau_kieu_kho({
        "qid": "Q", "phien_ban": "V01", "dang": "TNN", "de_bai": "Chọn số nguyên tố",
        "khoi_du_kien": "", "phuong_an": [{"khoa": "A", "noi_dung": "2"}, {"khoa": "B", "noi_dung": "4"},
                                          {"khoa": "C", "noi_dung": "5"}],
        "dap_an": "A,C", "bai_giai": "Số nguyên tố chỉ có hai ước."})
    p = ly_do_svc.tao_prompt(c)
    assert "A. 2 — ĐÚNG" in p and "B. 4 — SAI" in p and "C. 5 — ĐÚNG" in p and "Số nguyên tố chỉ có hai ước." in p


def test_ho_ten_thuan():
    from app.integrations.testbank.delivery import ho_ten_thuan
    assert ho_ten_thuan("  Nguyễn   Văn An ") == "Nguyễn Văn An"
    assert ho_ten_thuan("A") == "Học sinh" and ho_ten_thuan("") == "Học sinh"
    assert len(ho_ten_thuan("x" * 300)) == 100


async def test_token_dich_vu_that_dang_nhap_lam_moi_va_thu_lai_khi_401():
    """Đường đối tác dùng `TestbankClient.goi_tho` thật: đăng nhập identity, Bearer, 401 thì đăng nhập lại
    đúng một lần; URL (có mã bài làm) không vào log."""
    from app.integrations.testbank.client import CauHinh, KhoTokenBoNho, TestbankClient
    cap = {"dang_nhap": 0, "bearer": []}

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/auth/login"):
            cap["dang_nhap"] += 1
            return httpx.Response(200, json={"access_token": f"a{cap['dang_nhap']}", "refresh_token": "r",
                                             "expires_in": 900})
        cap["bearer"].append(req.headers["authorization"])
        if req.headers["authorization"] == "Bearer a1":
            return httpx.Response(401, json={"detail": "het han"})
        return httpx.Response(200, json={"bai_lam_id": "x", "vao_lai": False, "bai_lam": {}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(xu_ly))
    tb = TestbankClient(CauHinh("http://id.t", "http://c.t", "http://e.t", "dv@x", "mk"), http, KhoTokenBoNho())
    dc = DoiTacClient("http://tb.t/api/delivery", tb)
    r = await dc.xem("BAI-LAM-ID-BI-MAT")
    assert r["bai_lam_id"] == "x" and cap["dang_nhap"] == 2 and cap["bearer"] == ["Bearer a1", "Bearer a2"]
