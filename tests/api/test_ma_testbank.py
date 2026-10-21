"""US-29 — học sinh làm bài theo MÃ DO GIÁO VIÊN PHÁT TRÊN TESTBANK, ngay trong learning (mức 0).

Testbank giả ở ranh giới HTTP (`tests/api/delivery_gia.py`, `httpx.MockTransport`): client thật,
đường dẫn thật, header khoá bài làm thật, mã lỗi thật. Tên test ghi kịch bản US-29 (KB n).
"""
import json
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.api import ma_testbank
from app.config import settings
from app.db.models import DeCuoiKy, QuizAttempt, StudentStats
from app.integrations.testbank.delivery import DeliveryClient
from app.main import app
from tests.api.conftest import tao_tai_khoan
from tests.api.delivery_gia import DeliveryGia

MA = "K7M3PX"


@pytest.fixture
def tb(monkeypatch):
    gia = DeliveryGia()
    gia.phat(MA)
    http = httpx.AsyncClient(transport=gia.transport())
    app.dependency_overrides[ma_testbank.lay_delivery] = lambda: DeliveryClient("http://tb.test/api/delivery", http)
    monkeypatch.setattr(settings, "testbank_delivery_url", "http://tb.test/api/delivery")
    yield gia
    app.dependency_overrides.pop(ma_testbank.lay_delivery, None)


@pytest.fixture(autouse=True)
def bo_dem(monkeypatch):
    """Bộ đếm dò mã bằng dict thay Redis (Redis local thường không chạy)."""
    dem: dict[str, int] = {}

    async def incr(key, ttl):
        dem[key] = dem.get(key, 0) + 1
        return dem[key]

    async def get(key):
        return str(dem[key]) if key in dem else None

    monkeypatch.setattr(ma_testbank.llm_cache, "incr_quota", incr)
    monkeypatch.setattr(ma_testbank.llm_cache, "get", get)
    return dem


async def _hs(client, ten="Nguyễn Văn An"):
    email, h = await tao_tai_khoan(client, "hoc_sinh", ten=ten)
    return h


async def _vao(client, h, ma=MA):
    return await client.post("/exam/ma/vao", headers=h, json={"ma": ma})


async def _vao_ok(client, h, ma=MA) -> dict:
    r = await _vao(client, h, ma)
    assert r.status_code == 200, r.text
    return r.json()


def _cau(stt: int, chon: str, seq: int = 1) -> dict:
    return {"stt": stt, "chon": chon, "seq": seq}


# ── A. Lối vào, vai ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("vai", ["giao_vien", "chuyen_gia", "admin"])
async def test_kb4_vai_khac_hoc_sinh_bi_tu_choi_khong_dung_den_testbank(client, tb, vai):
    _, h = await tao_tai_khoan(client, vai)
    r = await _vao(client, h)
    assert r.status_code == 403 and r.json()["detail"] == "Chỉ tài khoản học sinh làm bài theo mã"
    assert tb.goi == []


async def test_kb4_chua_dang_nhap_bi_tu_choi(client, tb):
    r = await client.post("/exam/ma/vao", json={"ma": MA})
    assert r.status_code == 401 and tb.goi == []


async def test_cau_hinh_ba_che_do(client, tb, monkeypatch):
    h = await _hs(client)
    assert (await client.get("/exam/ma/cau-hinh", headers=h)).json() == {"che_do": "tich_hop", "url_du_phong": None}
    monkeypatch.setattr(settings, "testbank_delivery_url", "")
    monkeypatch.setattr(settings, "testbank_web_student_url", "http://hs.test")
    assert (await client.get("/exam/ma/cau-hinh", headers=h)).json() == {
        "che_do": "du_phong", "url_du_phong": "http://hs.test"}
    monkeypatch.setattr(settings, "testbank_web_student_url", "")
    assert (await client.get("/exam/ma/cau-hinh", headers=h)).json()["che_do"] == "tat"


# ── B. Nhập mã ──────────────────────────────────────────────────────────────
async def test_kb5_nhap_dung_ma_thay_de_thay_co_giao(client, tb, session):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    assert d["tieu_de"] == "Kiểm tra cuối kỳ 1 — 6A" and d["nhan"] == "Đề thầy cô giao · mã K7M3PX"
    assert d["trang_thai"] == "DANG_LAM" and len(d["cau"]) == 10
    assert [c["stt"] for c in d["cau"]] == list(range(1, 11))
    assert [c["dang"] for c in d["cau"][:5]] == ["TN1", "TNN", "DS", "DSN", "TL"]
    c1 = d["cau"][0]
    assert '<img class="tb-anh"' in c1["de_html"] and "[[anh:" not in c1["de_html"]
    assert [p["key"] for p in c1["phuong_an"]] == list("ABCD")
    # Khối dữ kiện chung chỉ ở câu đầu của nhóm.
    assert d["cau"][5]["du_kien_html"] == "Cho bảng số liệu chung" and d["cau"][6]["du_kien_html"] == ""
    assert d["cau"][4]["tu_cham"] is False and d["cau"][0]["tu_cham"] is True     # tự luận: thầy cô chấm
    # Trên Testbank: đúng MỘT bài, tên kèm định danh theo Q4 (không lộ email).
    (vao_thi,) = tb.goi_theo("POST", "/vao-thi")
    assert vao_thi[3]["ho_ten"].startswith("Nguyễn Văn An · HS") and "@" not in vao_thi[3]["ho_ten"]
    assert vao_thi[3]["ma"] == MA and len(tb.bai) == 1


async def test_kb6_ma_duoc_chuan_hoa(client, tb):
    h = await _hs(client)
    d = await _vao_ok(client, h, " k7m 3px ")
    assert d["ma"] == MA
    assert tb.goi_theo("POST", "/vao-thi")[0][3]["ma"] == MA


@pytest.mark.parametrize("ma", ["K7M3P", "K7M3PXX", "K7M3P0", "K7M3PO", "K7M3P1", "K7M-3P", "", "ſ7M3PX"])
async def test_kb6_sai_dinh_dang_khong_hoi_testbank_khong_tinh_lan_sai(client, tb, bo_dem, ma):
    h = await _hs(client)
    for _ in range(7):
        r = await _vao(client, h, ma)
        assert r.status_code == 422 and r.json()["detail"] == "Mã gồm 6 chữ và số, em kiểm tra lại nhé"
    assert tb.goi == [] and bo_dem == {}
    assert (await _vao(client, h)).status_code == 200          # vẫn nhập được mã đúng


async def test_kb7_ma_khong_ton_tai_hoac_da_dong(client, tb):
    h = await _hs(client, "Chi")
    r = await _vao(client, h, "R4T8WN")
    assert r.status_code == 404 and r.json()["detail"] == "Mã không đúng hoặc bài đã đóng, em hỏi lại thầy cô nhé"
    tb.dong(MA)
    r = await _vao(client, h, MA)
    assert r.status_code == 404 and r.json()["detail"] == "Mã không đúng hoặc bài đã đóng, em hỏi lại thầy cô nhé"
    assert tb.bai == {}


async def test_kb8_nam_ma_sai_thi_bi_chan_ke_ca_ma_dung_va_khong_goi_testbank(client, tb):
    chi, binh = await _hs(client, "Chi"), await _hs(client, "Bình")
    for i in range(5):
        assert (await _vao(client, chi, f"R4T8W{'NPQRS'[i]}")).status_code == 404
    so_goi = len(tb.goi)
    r = await _vao(client, chi, MA)                              # mã đúng cũng bị chặn
    assert r.status_code == 429 and r.json()["detail"] == "Em nhập sai mã nhiều lần, thử lại sau 10 phút nhé"
    assert len(tb.goi) == so_goi
    assert (await _vao(client, binh, MA)).status_code == 200     # học sinh khác vẫn nhập bình thường


async def test_kb8_bon_lan_sai_chua_bi_chan(client, tb):
    chi = await _hs(client, "Chi")
    for i in range(4):
        await _vao(client, chi, f"R4T8W{'NPQR'[i]}")
    assert (await _vao(client, chi, MA)).status_code == 200


async def test_kb9_testbank_chan_nhap_ma_thi_bao_chung_khong_tinh_sai_va_ghi_canh_bao(client, tb, bo_dem, caplog):
    h = await _hs(client)
    tb.chan_giay = 125
    with caplog.at_level("WARNING", logger="app.api.ma_testbank"):
        r = await _vao(client, h)
    assert r.status_code == 429
    assert r.json()["detail"] == "Hệ thống đang tạm khoá nhập mã, em thử lại sau 3 phút"   # 125s -> 3 phút (làm tròn lên)
    assert bo_dem == {}
    assert "CANH_BAO testbank_chan_nhap_ma" in caplog.text


async def test_kb10_nhap_lai_mo_dung_bai_cu_khong_tao_bai_thu_hai(client, tb):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    r = await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h,
                         json={"cau": [_cau(1, "B"), _cau(2, "A,B"), _cau(3, "Đ,S"), _cau(4, "3")]})
    assert r.status_code == 200 and r.json()["da_luu"] == [1, 2, 3, 4]
    d2 = await _vao_ok(client, h)                                # "thiết bị khác"
    assert d2["de_id"] == d["de_id"] and len(tb.bai) == 1 and len(tb.goi_theo("POST", "/vao-thi")) == 1
    assert d2["tra_loi"] == {"c1": "B", "c2": "A,B", "c3": "Đ,S", "c4": "3"}
    # Nộp rồi nhập lại: thấy kết quả bài đã nộp, không làm lại được.
    n = await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": []})
    assert n.status_code == 200 and n.json()["trang_thai"] == "DA_NOP"
    d3 = await _vao_ok(client, h)
    assert d3["trang_thai"] == "DA_NOP" and d3["ket_qua"]["diem"] == n.json()["ket_qua"]["diem"]
    assert len(tb.goi_theo("POST", "/vao-thi")) == 1


async def test_kb11_da_co_bai_thi_vao_lai_duoc_du_luot_phat_da_dong(client, tb):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "B")]})
    tb.dong(MA)
    so_goi = len(tb.goi)
    d2 = await _vao_ok(client, h)
    assert d2["trang_thai"] == "DA_NOP"
    assert (await client.get(f"/exam/ma/{d['de_id']}", headers=h)).json()["trang_thai"] == "DA_NOP"
    assert len(tb.goi) == so_goi            # kết quả là bản chép ở learning: không hỏi lại Testbank


async def test_kb11_bai_do_khi_luot_phat_dong_thi_duoc_nop_ho_va_thay_ket_qua(client, tb):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(1, "B")]})
    tb.dong(MA)
    d2 = await _vao_ok(client, h)
    assert d2["trang_thai"] == "DA_NOP" and d2["thong_bao"].startswith("Thầy cô đã đóng bài")


# ── C. Làm bài ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("stt, chon, nhan", [
    (1, "C", "C"),                       # TN1: chọn một phương án
    (2, "A,C", ["A", "C"]),              # TNN: chọn hai phương án
    (3, "Đ,S", {"1": "Đ", "2": "S"}),    # DS: Đúng/Sai từng ý
    (3, ",S", {"2": "S"}),               # DS: ý bỏ trống không gửi
    (4, "3,5", "3,5"),                   # DSN: gõ một số
    (5, "Em làm như sau,\nbước hai", "Em làm như sau,\nbước hai"),   # TL: đoạn chữ (có dấu phẩy)
])
async def test_kb13_nam_dang_cau_testbank_nhan_dung_cau_tra_loi(client, tb, stt, chon, nhan):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    r = await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(stt, chon, 3)]})
    assert r.status_code == 200 and r.json()["da_luu"] == [stt]
    gui = tb.goi_theo("PUT")[0][3]["cau"][0]
    assert gui == {"so_thu_tu": stt, "tra_loi": nhan, "seq": 3}
    # Nộp: Testbank nhận đúng câu trả lời đó.
    await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(stt, chon, 4)]})
    assert tb.goi_theo("POST", "/bai-lam/nop")[0][3]["cau"][0]["tra_loi"] == nhan


async def test_kb12_bo_chon_gui_none_va_luu_dan(client, tb):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(1, "A", 1)]})
    await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(1, "", 2)]})
    assert tb.goi_theo("PUT")[1][3]["cau"][0]["tra_loi"] is None
    assert (await _vao_ok(client, h))["tra_loi"] == {}


async def test_kb12_cau_sai_dinh_dang_cua_testbank_van_bao_cau_nao_luu_duoc(client, tb):
    """Testbank trả 422 nhưng thân vẫn là LuuOut: các câu hợp lệ ĐÃ lưu, không được coi là lỗi cả loạt."""
    h = await _hs(client)
    d = await _vao_ok(client, h)
    r = await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(1, "A"), _cau(99, "A")]})
    assert r.status_code == 200
    assert r.json()["da_luu"] == [1] and r.json()["loi"][0]["so_thu_tu"] == 99


async def test_kb14_gio_may_chu_va_han_nop_tra_ve_de_dem_nguoc(client, tb):
    tb.phat("P9Q2RS", "Đề 30 phút", phut=30)
    h = await _hs(client)
    d = await _vao_ok(client, h, "P9Q2RS")
    assert d["thoi_gian_phut"] == 30 and d["han_nop_luc"] and d["gio_may_chu"]
    # Không giới hạn thời gian: không có hạn.
    assert (await _vao_ok(client, await _hs(client)))["han_nop_luc"] is None


async def test_kb14_het_gio_thi_bai_duoc_nop_voi_cau_da_luu_kem_ghi_chu(client, tb):
    tb.phat("P9Q2RS", "Đề 30 phút", phut=30)
    h = await _hs(client)
    d = await _vao_ok(client, h, "P9Q2RS")
    await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(1, "B")]})
    tb.het_gio.add(next(iter(tb.bai)))
    r = await client.get(f"/exam/ma/{d['de_id']}", headers=h)
    assert r.status_code == 200 and r.json()["trang_thai"] == "DA_NOP"
    assert r.json()["thong_bao"] == "Bài đã tự nộp khi hết giờ"
    assert r.json()["ket_qua"]["cau"][0]["trang_thai"] == "DUNG"
    # Lựa chọn gửi SAU thời điểm đó không được tính: lưu báo đã nộp, kết quả giữ nguyên.
    r2 = await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(2, "A,B")]})
    assert r2.json()["da_nop"] is True and r2.json()["bai"]["ket_qua"]["cau"][1]["chon"] == ""


async def test_kb15_giao_vien_dong_luot_phat_khi_em_dang_lam(client, tb):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h,
                     json={"cau": [_cau(i, "B") for i in range(1, 7) if i != 2 and i != 3 and i != 5] + [_cau(6, "A")]})
    tb.dong(MA)
    r = await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(7, "A")]})
    bai = r.json()["bai"]
    assert r.status_code == 200 and r.json()["da_nop"] is True
    assert bai["thong_bao"] == "Thầy cô đã đóng bài, bài của em đã được nộp với các câu đã lưu"
    chon = {c["stt"]: c["chon"] for c in bai["ket_qua"]["cau"]}
    assert chon[1] == "B" and chon[6] == "A" and chon[7] == ""        # câu 7 gửi sau khi đóng: không tính
    # Bấm nộp sau khi đóng: cùng một kết quả.
    n = await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(7, "A")]})
    assert n.json()["ket_qua"] == bai["ket_qua"]


# ── Bảo mật ─────────────────────────────────────────────────────────────────
async def test_kb16_khong_dap_an_khong_khoa_bai_lam_xuong_trinh_duyet(client, tb, session):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    khoa = next(iter(tb.bai))
    cac_phan_hoi = [d,
                    (await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(1, "B")]})).json(),
                    (await client.get(f"/exam/ma/{d['de_id']}", headers=h)).json(),
                    (await _vao(client, h)).json(),
                    (await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "B")]})).json(),
                    (await client.get("/exam/cuoi-ky", headers=h)).json(),
                    (await client.get(f"/exam/ma/{d['de_id']}", headers=h)).json()]
    thô = json.dumps(cac_phan_hoi, ensure_ascii=False)
    assert khoa not in thô and "khoa_bai_lam" not in thô and "X-Khoa" not in thô
    for cam in ("dap_an_html", "giai_html", "ly_do", "answer_key", "bai_giai", "yccd", "ar_id\": \"A"):
        assert cam not in thô, cam
    # Khoá có ở DB learning (nơi duy nhất cần), và Testbank nhận nó ở HEADER, không ở thân.
    assert (await session.scalar(select(DeCuoiKy.khoa_bai_lam).where(DeCuoiKy.id == d["de_id"]))) == khoa
    assert all(g[2] == khoa for g in tb.goi if g[1] != "/vao-thi")
    assert all(khoa not in json.dumps(g[3] or {}) for g in tb.goi)


async def test_bai_cua_nguoi_khac_la_404_va_khong_goi_testbank(client, tb):
    an, binh = await _hs(client), await _hs(client, "Bình")
    d = await _vao_ok(client, an)
    so_goi = len(tb.goi)
    for r in (await client.get(f"/exam/ma/{d['de_id']}", headers=binh),
              await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=binh, json={"cau": []}),
              await client.post(f"/exam/ma/{d['de_id']}/nop", headers=binh, json={"cau": []})):
        assert r.status_code == 404
    assert len(tb.goi) == so_goi


async def test_giao_vien_khong_mo_luu_nop_duoc_bai_theo_ma(client, tb):
    an = await _hs(client)
    d = await _vao_ok(client, an)
    _, gv = await tao_tai_khoan(client, "giao_vien")
    assert (await client.get(f"/exam/ma/{d['de_id']}", headers=gv)).status_code == 403
    assert (await client.post(f"/exam/ma/{d['de_id']}/nop", headers=gv, json={"cau": []})).status_code == 403


# ── D. Nộp bài và kết quả ───────────────────────────────────────────────────
async def test_kb17_ket_qua_chi_diem_va_trang_thai_tung_cau(client, tb, session):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    tl = [_cau(1, "B"), _cau(2, "A,B"), _cau(3, "Đ,S"), _cau(4, "3"), _cau(5, "Bài làm tự luận"), _cau(6, "C")]
    r = await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": tl})
    assert r.status_code == 200
    kq = r.json()["ket_qua"]
    assert kq["diem"] == 2.0 and kq["tong"] == 4.5 and kq["so_cau_cho_cham"] == 1
    nhan = {c["stt"]: (c["trang_thai"], c["nhan"], c["chon"]) for c in kq["cau"]}
    assert nhan[1] == ("DUNG", "Đúng", "B") and nhan[6] == ("SAI", "Sai", "C")
    assert nhan[5] == ("CHO_GIAO_VIEN_CHAM", "Chưa chấm", "Bài làm tự luận")
    assert r.json()["co_chi_tiet"] is False
    for cam in ("de_xuat", "theo_ycd", "dap_an", "ly_do", "goi_y"):
        assert cam not in r.text, cam


async def test_kb19_nop_hai_lan_chi_mot_lan_nop_len_testbank_va_cung_ket_qua(client, tb):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    a = await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "B")]})
    b = await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "A")]})
    assert a.json()["ket_qua"] == b.json()["ket_qua"]
    assert len(tb.goi_theo("POST", "/bai-lam/nop")) == 1


async def test_kb20_khong_ghi_thong_ke_ycd_khi_khong_co_chi_tiet(client, tb, session):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    uid = await session.scalar(select(DeCuoiKy.user_id).where(DeCuoiKy.id == d["de_id"]))
    truoc = await session.scalar(select(func.count()).select_from(QuizAttempt).where(QuizAttempt.user_id == uid))
    await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "B")]})
    sau = await session.scalar(select(func.count()).select_from(QuizAttempt).where(QuizAttempt.user_id == uid))
    assert truoc == sau == 0


async def test_g3_xp_cong_mot_lan_theo_so_cau_dung(client, tb, session):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    uid = await session.scalar(select(DeCuoiKy.user_id).where(DeCuoiKy.id == d["de_id"]))
    await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "B"), _cau(4, "3")]})
    await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": []})
    await client.get(f"/exam/ma/{d['de_id']}", headers=h)
    xp = await session.scalar(select(StudentStats.xp_total).where(StudentStats.user_id == uid))
    assert xp == 2 * 5                       # 2 câu đúng x 5 XP; 2/9 < 70% nên không thưởng "đạt"


# ── E. Lịch sử ──────────────────────────────────────────────────────────────
async def test_kb21_bai_theo_ma_trong_lich_su_khong_xoa_duoc(client, tb, session):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    r = await client.get("/exam/cuoi-ky", headers=h, params={"exam": "CK1"})   # kỳ nào cũng hiện
    (x,) = r.json()["de"]
    assert (x["loai"], x["ma"], x["tieu_de"], x["da_nop"], x["xoa_duoc"]) == (
        "testbank", MA, "Kiểm tra cuối kỳ 1 — 6A", False, False)
    assert (await client.get("/exam/cuoi-ky", headers=h, params={"exam": "CK2"})).json()["de"][0]["ma"] == MA
    await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "B")]})
    (x,) = (await client.get("/exam/cuoi-ky", headers=h)).json()["de"]
    assert x["da_nop"] is True and x["diem"] == 0.5 and x["tong"] == 4.5
    r = await client.delete(f"/exam/cuoi-ky/{d['de_id']}", headers=h)
    assert r.status_code == 403 and r.json()["detail"] == "Bài thầy cô giao không xoá được"
    # "Xoá tất cả" chỉ xoá đề tự sinh; bài theo mã còn nguyên ở learning và trên Testbank.
    assert (await client.delete("/exam/cuoi-ky", headers=h)).json() == {"da_xoa": 0}
    assert len((await client.get("/exam/cuoi-ky", headers=h)).json()["de"]) == 1
    assert len(tb.bai) == 1


async def test_kb22_nhap_ma_cu_cua_learning_thi_hoi_testbank_khong_mo_bai_cu(client, tb, session):
    """US-26 đã ngừng: mã cũ chỉ còn là một mã lạ với Testbank."""
    h = await _hs(client)
    r = await _vao(client, h, "Q2W3ER")        # mã US-26 cũ — Testbank không có
    assert r.status_code == 404 and tb.goi_theo("POST", "/vao-thi")[0][3]["ma"] == "Q2W3ER"


# ── F. Lỗi hệ thống ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("chet", [True, "500"])
async def test_kb23_testbank_chet_khi_nhap_ma(client, tb, bo_dem, chet):
    h = await _hs(client)
    tb.chet = chet
    r = await _vao(client, h)
    assert r.status_code == 503 and r.json()["detail"] == "Chưa mở được đề, em thử lại sau ít phút nhé"
    assert "Traceback" not in r.text and "httpx" not in r.text
    assert bo_dem == {}
    tb.chet = False
    assert (await _vao(client, h)).status_code == 200


async def test_kb23_chua_cau_hinh_phat_de_thi_bao_thu_lai_khong_500(client, monkeypatch):
    app.dependency_overrides.pop(ma_testbank.lay_delivery, None)
    monkeypatch.setattr(settings, "testbank_delivery_url", "")
    h = await _hs(client)
    r = await _vao(client, h)
    assert r.status_code == 503 and r.json()["detail"] == "Chưa mở được đề, em thử lại sau ít phút nhé"


async def test_kb24_testbank_chet_khi_luu_hoac_nop_khong_tao_ket_qua_nop_lai_duoc(client, tb, session):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    tb.chet = True
    msg = "Chưa gửi được bài, em đừng đóng app, bấm Nộp lại sau ít phút"
    r = await client.put(f"/exam/ma/{d['de_id']}/tra-loi", headers=h, json={"cau": [_cau(1, "B")]})
    assert r.status_code == 503 and r.json()["detail"] == msg
    r = await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "B")]})
    assert r.status_code == 503 and r.json()["detail"] == msg
    assert (await session.scalar(select(DeCuoiKy.ket_qua_json).where(DeCuoiKy.id == d["de_id"]))) is None
    tb.chet = False
    r = await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": [_cau(1, "B"), _cau(2, "A,B")]})
    assert r.status_code == 200 and r.json()["ket_qua"]["cau"][1]["chon"] == "A,B"


async def test_testbank_tra_4xx_la_la_thi_502_khong_phai_500(client, tb):
    h = await _hs(client)
    d = await _vao_ok(client, h)
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(403, json={"detail": "cấm"})))
    app.dependency_overrides[ma_testbank.lay_delivery] = lambda: DeliveryClient("http://tb.test", http)
    r = await client.post(f"/exam/ma/{d['de_id']}/nop", headers=h, json={"cau": []})
    assert r.status_code == 502 and "em" in r.json()["detail"]
