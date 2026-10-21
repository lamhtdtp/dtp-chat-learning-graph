"""US-27 (27b) — khối "Đề xuất" sau khi có kết quả + Test thêm: Kịch bản 12–30, 33–34
(KB 31–32 là giao diện; phần kiểm được ở đây: cờ `noi_bo` và kiểm tĩnh mã nguồn web). Viết TRƯỚC
khi DEV code (RED). Toàn `[tdd-core]`, không gọi LLM.

Nguồn: User-Stories/EPIC-04-On-Tap/US-27-kho-hoc-lieu-va-de-xuat.md + hợp đồng
docs/contracts/US-27-kho-hoc-lieu-va-de-xuat.md (§3–§6) ở repo tài liệu. Hạ tầng giả dùng chung:
`tests/api/de_xuat_khung.py` (đọc docstring đầu file đó để biết các GIẢ ĐỊNH).

GIẢ ĐỊNH THÊM (hợp đồng chưa đặt tên — DEV làm theo hoặc báo QC đổi test):
* KB 33: hàm đọc kho học liệu là `app.lessons.de_xuat.doc_kho_hoc_lieu` và nơi gọi nó truy cập qua
  module (`de_xuat.doc_kho_hoc_lieu(...)`, để `mocker.patch` có tác dụng). Nó lỗi thì khối Đề xuất
  suy giảm đúng hợp đồng §4 chứ không văng 500.
* KB 18: `phan` của mục bài học là id phần trong `app.lessons.bo_cuc.IDS` (câu quiz gắn `phan: "vi_du"`)
  hoặc "kien_thuc". Hợp đồng ví dụ `"vi_du_2"` — id này KHÔNG có trong bố cục hiện tại; test chỉ đòi
  `phan` bắt đầu bằng "vi_du" (xem báo cáo: cần chốt với BA/DEV).
* Cache bản đồ ar_id↔YCCĐ (≤ 10 phút, hợp đồng §4) phải xoá được cho test: `app.lessons.de_xuat.xoa_cache()`
  (fixture `_xoa_cache_ban_do_ar` gọi nếu có). Không có thì test dễ flaky khi nhiều kho giả trong một tiến trình.
* Hạn mức Test thêm là `settings.de_cuoi_ky_daily_limit` (hợp đồng §5), qua `app.llm.cache.incr_quota`.

KHÔNG viết được / chỉ kiểm một phần (lý do ở báo cáo): KB 19 phần "nút Xem lại bài không hiện" (hợp
đồng chưa nói API báo cờ nào — kiểm bằng Playwright); KB 17 "Xem thêm N" và KB 31–32 (giao diện);
KB 30 phần "nút Thử lại"; chữ `tinh_de_xuat` thuần (chưa có chữ ký công khai) — test qua API.
"""
import asyncio
import json
import logging
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("de_giao_cu_bat")  # US-26 đã ngừng: bật lại để dựng dữ liệu cũ
from sqlalchemy import func, select

from app.api import cuoi_ky
from app.db.models import DeCuoiKy
from app.integrations.testbank.client import TestbankChuaCauHinh, TestbankLoi
from app.llm import cache as llm_cache
from app.main import app
from tests.api.de_xuat_khung import (
    LOAI_BAI, LOAI_CO_QID, Cau, KhoDemGia, TbGia, cau_phu, chen_lich_su, dung_the_gioi,
    dat_quiz, ghi_chu_cua, lam_bai, lay_de_xuat, ma_cua, nap_kho, them_hl, tk,
)

GOC = Path(__file__).resolve().parents[2]
MSG_KHONG_HOC_LIEU = "Chưa có học liệu cho phần em làm sai — thử Test thêm để luyện tiếp"
MSG_KHO_CHET = "Chưa tải được video và tài liệu gợi ý, em mở lại sau nhé"
MSG_KHONG_CAU = "Chưa có câu luyện thêm cho phần này"
MSG_TEST_THEM_LOI = "Chưa tạo được bài mới, em thử lại sau ít phút"
KHOA_DE_XUAT = {"loi_khen", "thong_bao", "doc_them", "video", "test_them"}
KHOA_MUC = {"ma", "loai", "nhan", "url", "noi_bo", "muc_dich", "ghi_chu"}


# ── Hạ tầng ─────────────────────────────────────────────────────────────────
@pytest.fixture
def tb():
    gia = TbGia()
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    yield gia
    app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


@pytest.fixture(autouse=True)
def _khong_goi_model(mocker):
    return mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value="{}"))


@pytest.fixture(autouse=True)
def kho_dem(mocker):
    kho = KhoDemGia()
    for ten in ("incr_quota", "giam_quota", "get", "set"):
        mocker.patch.object(llm_cache, ten, getattr(kho, ten))
    return kho


@pytest.fixture(autouse=True)
def _xoa_cache_ban_do_ar():
    """Hợp đồng §4 cho phép cache bản đồ `ar_id ↔ YCCĐ` trong bộ nhớ ≤ 10 phút. Mỗi test dựng
    kho riêng (ar_id kèm uuid) nên cache sống qua test là nguồn flaky: DEV đặt một hàm
    `app.lessons.de_xuat.xoa_cache()` (hoặc khoá cache theo nội dung kho) — nếu có thì ở đây gọi."""
    try:
        from app.lessons import de_xuat
    except ImportError:
        yield
        return
    xoa = getattr(de_xuat, "xoa_cache", None)
    if callable(xoa):
        xoa()
    yield
    if callable(xoa):
        xoa()


async def canh(client, session, ycd_moi_bai=(2,), xuat_ban=None):
    the = await dung_the_gioi(session, ycd_moi_bai, xuat_ban)
    return the, await tk(client, "chuyen_gia"), await tk(client)


def _ma(the, tien_to: str, hau: str) -> str:
    return f"{tien_to}-{the.uid.upper()}-{hau}"


# Bài làm chuẩn 4 câu: X = YCCĐ 0 (sai câu 1), Y = YCCĐ 1 (đúng hết). Mỗi YCCĐ ≤ 2 câu và tổng ≤ 4
# để hợp với mọi loại bài (Luyện thêm rút tối đa 4 câu, Test thêm rút 2 câu / YCCĐ).
def _bai_chuan() -> list[Cau]:
    return [Cau(0, dung=False), Cau(0), Cau(1), Cau(1)]


def _khong_lo_hoc_lieu(raw: str, *tu_khoa: str) -> None:
    for k in ("de_xuat", "option_key", *tu_khoa):
        assert k not in raw, f"lộ '{k}' trước khi nộp"


# ═══ KB 12 — sai một YCCĐ có học liệu ═══════════════════════════════════════
@pytest.mark.parametrize("loai", LOAI_BAI)
async def test_sai_mot_ycd_chi_thay_hoc_lieu_on_lai_dung_ycd_kb12(client, session, tb, loai):
    the, gv, hs = await canh(client, session)
    khac, _gv2, _hs2 = await canh(client, session, (1,))
    sgk = (await them_hl(client, gv, the, 0, loai="SGK", ma=_ma(the, "SGK", "003")))["ma"]
    vd = (await them_hl(client, gv, the, 0, loai="VIDEO", ma=_ma(the, "VD", "001")))["ma"]
    cung_co = (await them_hl(client, gv, the, 0, loai="VIDEO", muc_dich="cung_co",
                             ma=_ma(the, "VD", "009")))["ma"]
    cua_bai_khac = (await them_hl(client, gv, khac, 0, loai="SGK", ma=_ma(khac, "SGK", "555")))["ma"]

    dx = (await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())).de_xuat
    assert ma_cua(dx["doc_them"]) == [sgk]
    assert ma_cua(dx["video"]) == [vd]
    tat_ca = ma_cua(dx["doc_them"]) + ma_cua(dx["video"])
    assert cung_co not in tat_ca                 # Củng cố không dùng cho YCCĐ còn sai
    assert cua_bai_khac not in tat_ca            # YCCĐ Y (không có học liệu) và YCCĐ của bài khác: không lọt


@pytest.mark.parametrize("loai", ["cuoi_ky", "quiz"])
async def test_ycd_chi_co_hoc_lieu_cung_co_thi_nhom_an_kb12_q8(client, session, tb, loai):
    """Q8: YCCĐ còn sai mà chỉ có học liệu Củng cố thì KHÔNG dùng thay — nhóm đó ẩn."""
    the, gv, hs = await canh(client, session)
    await them_hl(client, gv, the, 0, loai="VIDEO", muc_dich="cung_co")
    await them_hl(client, gv, the, 0, loai="SGK", muc_dich="cung_co")
    dx = (await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())).de_xuat
    assert dx["video"] is None
    assert dx["doc_them"] is None or dx["doc_them"]["hoc_lieu"] == []


# ═══ KB 13–15 — theo phương án / theo câu (chỉ câu testbank có qid) ══════════
def _bai_phuong_an(chon: str) -> list[Cau]:
    """Câu 3 (qid …-Q3) thuộc YCCĐ X (=0), đáp án đúng C; học sinh chọn `chon`."""
    return [Cau(1), Cau(2), Cau(0, dung=False, chon=chon)]


async def _dung_kb13(client, session, tb):
    the, gv, hs = await canh(client, session, (3,))
    nap_kho(tb, the, _bai_phuong_an("B"))
    q3 = the.qid(3)
    pa_b = (await them_hl(client, gv, the, 0, qid=q3, option_key="B", ma=_ma(the, "VD", "021")))["ma"]
    cau = (await them_hl(client, gv, the, 0, qid=q3, ma=_ma(the, "VD", "020")))["ma"]
    ycd = (await them_hl(client, gv, the, 0, ma=_ma(the, "VD", "001")))["ma"]
    return the, hs, pa_b, cau, ycd


@pytest.mark.parametrize("loai", LOAI_CO_QID)
async def test_sai_dung_phuong_an_da_gan_thi_dung_dau_kb13(client, session, tb, loai):
    the, hs, pa_b, cau, ycd = await _dung_kb13(client, session, tb)
    ket = await lam_bai(loai, client, session, tb, the, hs, _bai_phuong_an("B"))
    video = ket.de_xuat["video"]
    assert ma_cua(video) == [pa_b, cau, ycd]
    assert ghi_chu_cua(video, pa_b) == f"Vì em chọn B ở câu {ket.stt[the.qid(3)]}"


@pytest.mark.parametrize("loai", LOAI_CO_QID)
async def test_sai_phuong_an_khac_khong_hien_hoc_lieu_cua_phuong_an_da_gan_kb14(client, session, tb, loai):
    the, hs, pa_b, cau, ycd = await _dung_kb13(client, session, tb)
    ket = await lam_bai(loai, client, session, tb, the, hs, _bai_phuong_an("A"))
    assert ma_cua(ket.de_xuat["video"]) == [cau, ycd]
    assert pa_b not in ma_cua(ket.de_xuat["video"]) + ma_cua(ket.de_xuat["doc_them"])


async def test_bo_trong_cau_khong_thanh_phuong_an_nao_kb14(client, session, tb):
    """Bỏ trống không phải "chọn B": không được kích hoạt học liệu của phương án nào, và không văng lỗi."""
    the, hs, pa_b, cau, ycd = await _dung_kb13(client, session, tb)
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, _bai_phuong_an(""))
    assert ma_cua(ket.de_xuat["video"]) == [cau, ycd]


@pytest.mark.parametrize("loai", LOAI_CO_QID)
async def test_hoc_lieu_theo_cau_chi_hien_khi_sai_dung_cau_do_kb15(client, session, tb, loai):
    the, gv, hs = await canh(client, session, (1,))
    specs = [Cau(0), Cau(0, dung=False)]                  # đúng câu 1 (Q1), sai câu 2 (Q2)
    nap_kho(tb, the, specs)
    theo_cau = (await them_hl(client, gv, the, 0, qid=the.qid(1), ma=_ma(the, "VD", "020")))["ma"]
    theo_ycd = (await them_hl(client, gv, the, 0, ma=_ma(the, "VD", "001")))["ma"]
    video = (await lam_bai(loai, client, session, tb, the, hs, specs)).de_xuat["video"]
    assert theo_cau not in ma_cua(video)
    assert ma_cua(video) == [theo_ycd]


async def test_cau_tn_nhieu_lua_chon_khop_phuong_an_da_chon_sai_kb13(client, session, tb):
    """Giả định 3 của US: câu nhiều lựa chọn thì "phương án" là từng lựa chọn em chọn SAI. Chọn thừa B
    (đáp án đúng A,C) -> học liệu gắn B hiện; chọn đúng A,C -> không hiện."""
    the, gv, hs = await canh(client, session, (1,))
    specs = [Cau(0, dung=False, chon="A,B", dang="TNN"), Cau(0)]
    nap_kho(tb, the, specs)
    pa_b = (await them_hl(client, gv, the, 0, qid=the.qid(1), option_key="B"))["ma"]
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)
    assert ma_cua(ket.de_xuat["video"])[0] == pa_b
    assert ghi_chu_cua(ket.de_xuat["video"], pa_b) == f"Vì em chọn B ở câu {ket.stt[the.qid(1)]}"
    hs2 = await tk(client)
    dung = await lam_bai("cuoi_ky", client, session, tb, the, hs2, [Cau(0, dang="TNN"), Cau(0)])
    assert dung.de_xuat["video"] is None                 # không còn sai -> không có Ôn lại nào


async def test_cau_dung_sai_khop_phuong_an_la_y_tra_loi_sai_kb13(client, session, tb):
    """Giả định 3: câu đúng/sai từng ý -> "phương án" là ý em trả lời sai. Đáp án Đ,S,Đ,S, em chọn
    S,S,Đ,S -> chỉ ý A sai: học liệu gắn ý A hiện, học liệu gắn ý B thì không."""
    the, gv, hs = await canh(client, session, (1,))
    specs = [Cau(0, dung=False, chon="S,S,Đ,S", dang="DS"), Cau(0)]
    nap_kho(tb, the, specs)
    y_a = (await them_hl(client, gv, the, 0, qid=the.qid(1), option_key="A", ma=_ma(the, "VD", "01A")))["ma"]
    y_b = (await them_hl(client, gv, the, 0, qid=the.qid(1), option_key="B", ma=_ma(the, "VD", "01B")))["ma"]
    video = (await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)).de_xuat["video"]
    assert y_a in ma_cua(video) and y_b not in ma_cua(video)


# ═══ KB 16 — trùng chỉ hiện một lần ═════════════════════════════════════════
@pytest.mark.parametrize("loai", ["quiz", "on_tap", "cuoi_ky", "de_giao"])
async def test_hoc_lieu_trung_chi_mot_lan_kem_ghi_chu_cau_kb16(client, session, tb, loai):
    the, gv, hs = await canh(client, session)
    hl = (await them_hl(client, gv, the, 0))["ma"]
    sai = {2, 5, 8}
    specs = [Cau(0, dung=False) if i in sai else Cau(1) for i in range(1, 9)]
    ket = await lam_bai(loai, client, session, tb, the, hs, specs)
    video = ket.de_xuat["video"]
    assert ma_cua(video).count(hl) == 1 and len(ma_cua(video)) == 1
    stt = sorted(ket.stt[the.qid(i)] for i in sai)
    assert ghi_chu_cua(video, hl) == "Liên quan câu " + ", ".join(str(n) for n in stt)
    assert stt == [2, 5, 8]


# ═══ KB 17 — nhóm, thứ tự ổn định, giới hạn ═════════════════════════════════
async def _dung_kb17(client, session, tb):
    """3 YCCĐ X,Y,Z ở 3 bài (thứ tự ma trận X<Y<Z), mỗi YCCĐ 2 câu, học sinh sai hết.

    Chọn tên mã SAO CHO thứ tự mã ngược với thứ tự đúng ở mỗi tầng — chỉ khi đúng luật
    (phương án → câu → YCCĐ; rồi YCCĐ ma trận → câu → mã) mới ra đúng thứ tự dưới đây."""
    the, gv, hs = await canh(client, session, (1, 1, 1))
    specs = [Cau(0, False, "B"), Cau(0, False, "A"), Cau(1, False, "D"), Cau(1, False, "B"),
             Cau(2, False, "A"), Cau(2, False, "B")]
    nap_kho(tb, the, specs)
    q = the.qid

    async def them(loai, tien_to, hau, k, **kv):
        return (await them_hl(client, gv, the, k, loai=loai, ma=_ma(the, tien_to, hau), **kv))["ma"]

    video = {
        "pa_x": await them("VIDEO", "VD", "P2", 0, qid=q(1), option_key="B"),
        "pa_y": await them("VIDEO", "VD", "P1", 1, qid=q(4), option_key="B"),
        "cau_y": await them("VIDEO", "VD", "C9", 1, qid=q(3)),
        "cau_z": await them("VIDEO", "VD", "C1", 2, qid=q(5)),
        "ycd_x2": await them("VIDEO", "VD", "E2", 0),
        "ycd_x3": await them("VIDEO", "VD", "E3", 0),
    }
    doc = {
        "pa_x": await them("SGK", "SGK", "P2", 0, qid=q(2), option_key="A"),
        "pa_z": await them("SBT", "SBT", "P1", 2, qid=q(6), option_key="B"),
        "cau_x": await them("BTTC", "BTTC", "C9", 0, qid=q(1)),
        "cau_y": await them("SGK", "SGK", "C1", 1, qid=q(3)),
        "ycd_x": await them("SGK", "SGK", "E5", 0),
        "ycd_y": await them("SBT", "SBT", "E4", 1),
        "ycd_z": await them("BTTC", "BTTC", "E1", 2),
    }
    return the, hs, specs, video, doc


async def test_thu_tu_va_phan_nhom_on_dinh_kb17(client, session, tb):
    the, hs, specs, v, d = await _dung_kb17(client, session, tb)
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)
    dx = ket.de_xuat
    assert ma_cua(dx["video"]) == [v["pa_x"], v["pa_y"], v["cau_y"], v["cau_z"], v["ycd_x2"], v["ycd_x3"]]
    assert ma_cua(dx["doc_them"]) == [d["pa_x"], d["pa_z"], d["cau_x"], d["cau_y"],
                                      d["ycd_x"], d["ycd_y"], d["ycd_z"]]
    assert dx["video"]["toi_da"] == 3
    assert dx["doc_them"]["toi_da_hoc_lieu"] == 5 and dx["doc_them"]["toi_da_bai_hoc"] == 5
    assert all(m["loai"] == "VIDEO" for m in dx["video"]["hoc_lieu"])
    assert all(m["loai"] in ("SGK", "SBT", "BTTC") for m in dx["doc_them"]["hoc_lieu"])
    # Danh sách trả ĐỦ (giao diện tự cắt 3 / 5 và hiện "Xem thêm N").
    assert len(dx["video"]["hoc_lieu"]) == 6 and len(dx["doc_them"]["hoc_lieu"]) == 7


async def test_mo_lai_nhieu_lan_cho_cung_danh_sach_kb17(client, session, tb):
    the, hs, specs, _v, _d = await _dung_kb17(client, session, tb)
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)
    lan = [lay_de_xuat(await ket.mo_lai()) for _ in range(3)]
    for dx in lan:
        assert dx["video"] == ket.de_xuat["video"] and dx["doc_them"] == ket.de_xuat["doc_them"]


async def test_loai_hoc_lieu_dung_nhom_kb17(client, session, tb):
    """SGK/SBT/BTTC không lọt vào "Video", VIDEO không lọt vào "Đọc thêm", dù gắn cùng YCCĐ."""
    the, gv, hs = await canh(client, session)
    ma = {t: (await them_hl(client, gv, the, 0, loai=t))["ma"] for t in ("VIDEO", "SGK", "SBT", "BTTC")}
    dx = (await lam_bai("cuoi_ky", client, session, tb, the, hs, _bai_chuan())).de_xuat
    assert ma_cua(dx["video"]) == [ma["VIDEO"]]
    assert sorted(ma_cua(dx["doc_them"])) == sorted([ma["SGK"], ma["SBT"], ma["BTTC"]])


# ═══ KB 18 — bài học cần đọc lại ════════════════════════════════════════════
@pytest.mark.parametrize("loai", ["quiz", "on_tap"])
async def test_doc_them_co_bai_hoc_dung_truoc_hoc_lieu_sach_kb18(client, session, tb, loai):
    """Sai câu 3 và 8 cùng một bài: một mục bài học, ghi chú "Sai câu 3, 8"; câu 3 gắn phần
    "Ví dụ", câu 8 không gắn -> bấm vào đưa tới phần của câu sai đầu tiên."""
    the, gv, hs = await canh(client, session, (1,))
    sgk = (await them_hl(client, gv, the, 0, loai="SGK"))["ma"]
    specs = [Cau(0, dung=i not in (3, 8), phan="vi_du" if i == 3 else None) for i in range(1, 9)]
    dx = (await lam_bai(loai, client, session, tb, the, hs, specs)).de_xuat
    bh = dx["doc_them"]["bai_hoc"]
    assert len(bh) == 1
    assert (bh[0]["topic_id"], bh[0]["ten"], bh[0]["ghi_chu"]) == (
        the.bai[0].tid, the.bai[0].ten, "Sai câu 3, 8")
    assert bh[0]["phan"].startswith("vi_du")
    assert ma_cua(dx["doc_them"]) == [sgk]               # học liệu sách nằm ở danh sách riêng, sau bài học


@pytest.mark.parametrize("loai", ["quiz", "on_tap"])
async def test_khong_cau_sai_nao_gan_phan_thi_ve_kien_thuc_trong_tam_kb18(client, session, tb, loai):
    the, gv, hs = await canh(client, session, (1,))
    specs = [Cau(0, dung=i not in (3, 8)) for i in range(1, 9)]
    bh = (await lam_bai(loai, client, session, tb, the, hs, specs)).de_xuat["doc_them"]["bai_hoc"]
    assert [b["phan"] for b in bh] == ["kien_thuc"]


async def test_cau_testbank_luon_ve_kien_thuc_trong_tam_kb18(client, session, tb):
    """Câu testbank không biết phần nội dung của bài (chỉ có YCCĐ) -> luôn "Kiến thức trọng tâm"."""
    the, gv, hs = await canh(client, session, (1,))
    specs = [Cau(0, dung=i not in (3, 8)) for i in range(1, 9)]
    bh = (await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)).de_xuat["doc_them"]["bai_hoc"]
    assert [(b["phan"], b["ghi_chu"]) for b in bh] == [("kien_thuc", "Sai câu 3, 8")]


async def test_nhieu_bai_theo_thu_tu_ma_tran_moi_bai_mot_lan_kb18(client, session, tb):
    the, gv, hs = await canh(client, session, (1, 2))
    # YCCĐ 0 ở bài 1; YCCĐ 1,2 ở bài 2. Sai YCCĐ 2 trước rồi 0 trong đề: mục bài học vẫn theo ma trận.
    specs = [Cau(2, False), Cau(0, False), Cau(1, False), Cau(0)]
    bh = (await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)).de_xuat["doc_them"]["bai_hoc"]
    assert [b["topic_id"] for b in bh] == [the.bai[0].tid, the.bai[1].tid]
    assert [b["ghi_chu"] for b in bh] == ["Sai câu 2", "Sai câu 1, 3"]
    assert [b["ten"] for b in bh] == [the.bai[0].ten, the.bai[1].ten]


# ═══ KB 19 — không gợi ý bài chưa xuất bản ═══════════════════════════════════
@pytest.mark.parametrize("loai", LOAI_BAI)
async def test_khong_goi_y_bai_chua_xuat_ban_van_co_hoc_lieu_sach_kb19(client, session, tb, loai):
    the, gv, hs = await canh(client, session, (2,), xuat_ban=[False])
    sgk = (await them_hl(client, gv, the, 0, loai="SGK", ma=_ma(the, "SGK", "003")))["ma"]
    dx = (await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())).de_xuat
    assert dx["doc_them"]["bai_hoc"] == []
    assert ma_cua(dx["doc_them"]) == [sgk]
    assert the.bai[0].ten not in json.dumps(dx, ensure_ascii=False)


async def test_bai_xuat_ban_va_bai_nhap_lan_nhau_chi_giu_bai_xuat_ban_kb19(client, session, tb):
    the, gv, hs = await canh(client, session, (1, 1), xuat_ban=[False, True])
    specs = [Cau(0, False), Cau(1, False)]
    bh = (await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)).de_xuat["doc_them"]["bai_hoc"]
    assert [b["topic_id"] for b in bh] == [the.bai[1].tid]


# ═══ KB 20 — YCCĐ không khớp thì không đoán ═════════════════════════════════
async def test_cau_khong_khop_ycd_khong_dong_gop_va_ghi_loi_kb20(client, session, tb, caplog):
    """Quiz tự sinh có YCCĐ chỉ khác một dấu chấm so với danh mục: KHÔNG đoán "gần đúng" sang YCCĐ 0
    (dù YCCĐ 0 có học liệu và bài học) mà ghi một lỗi tra cứu được."""
    the, gv, hs = await canh(client, session, (1,))
    await them_hl(client, gv, the, 0, loai="SGK")
    await them_hl(client, gv, the, 0, loai="VIDEO")
    gan_dung = the.ycds[0].rstrip(".")
    caplog.set_level(logging.WARNING)
    dx = (await lam_bai("quiz", client, session, tb, the, hs,
                        [Cau(0, False, ycd_text=gan_dung)], kho_cho_quiz=False)).de_xuat
    assert dx["video"] is None
    assert dx["doc_them"] is None or (dx["doc_them"]["bai_hoc"] == [] and dx["doc_them"]["hoc_lieu"] == [])
    loi = [r for r in caplog.records if r.levelno >= logging.ERROR and the.uid in r.getMessage()]
    assert loi, "không có bản ghi ERROR nào nêu YCCĐ không khớp (người vận hành không tra được)"


async def test_cau_testbank_khong_khop_ycd_khong_lam_hien_hoc_lieu_kb20(client, session, tb, caplog):
    the, gv, hs = await canh(client, session, (1,))
    sgk = (await them_hl(client, gv, the, 0, loai="SGK"))["ma"]
    specs = [Cau(0), Cau(0, False, ycd_text=the.ycds[0].rstrip("."))]
    caplog.set_level(logging.WARNING)
    dx = (await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)).de_xuat
    assert dx["video"] is None
    assert sgk not in ma_cua(dx["doc_them"])
    assert (dx["doc_them"] or {}).get("bai_hoc", []) == []
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ═══ KB 21 — câu tự luận không bị coi là sai ═════════════════════════════════
@pytest.mark.parametrize("loai", ["cuoi_ky", "de_giao"])
async def test_cau_tu_luan_khong_lam_ycd_con_sai_kb21(client, session, tb, loai):
    the, gv, hs = await canh(client, session)
    await them_hl(client, gv, the, 1, loai="SGK")
    await them_hl(client, gv, the, 1, loai="VIDEO")
    specs = [Cau(0), Cau(1, dang="TL")]                  # YCCĐ Z (=1) chỉ có câu tự luận
    dx = (await lam_bai(loai, client, session, tb, the, hs, specs)).de_xuat
    assert dx["video"] is None and dx["doc_them"] is None
    assert dx["loi_khen"] == "Em làm đúng tất cả 1 câu. Giỏi lắm!"


async def test_cau_tu_luan_de_trong_cung_khong_bi_tinh_sai_kb21(client, session, tb):
    the, gv, hs = await canh(client, session)
    await them_hl(client, gv, the, 1, loai="VIDEO")
    specs = [Cau(0), Cau(1, dang="TL")]
    nap_kho(tb, the, specs)
    d = (await client.post("/exam/cuoi-ky/generate", headers=hs.h, json={})).json()
    r = await client.post("/exam/cuoi-ky/submit", headers=hs.h, json={
        "de_id": d["de_id"], "tra_loi": {the.qid(1): "C"}})          # câu tự luận bỏ trống
    assert r.status_code == 200, r.text
    assert r.json()["de_xuat"]["video"] is None


# ═══ KB 22 / 23 — nhóm rỗng ẩn, không khung rỗng ═════════════════════════════
@pytest.mark.parametrize("loai", LOAI_BAI)
async def test_khong_co_video_thi_an_nhom_video_con_doc_them_va_test_them_kb22(client, session, tb, loai):
    the, gv, hs = await canh(client, session)
    await them_hl(client, gv, the, 0, loai="SGK")
    dx = (await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())).de_xuat
    assert dx["video"] is None
    assert dx["doc_them"] is not None and dx["doc_them"]["bai_hoc"]
    assert dx["test_them"] is not None
    assert dx["thong_bao"] is None


@pytest.mark.parametrize("loai", LOAI_BAI)
async def test_sai_ma_khong_co_gi_de_doc_van_con_test_them_kb23(client, session, tb, loai):
    the, gv, hs = await canh(client, session, (2,), xuat_ban=[False])
    dx = (await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())).de_xuat
    assert dx["doc_them"] is None and dx["video"] is None
    assert dx["thong_bao"] == MSG_KHONG_HOC_LIEU
    assert dx["test_them"] is not None
    assert dx["loi_khen"] is None


# ═══ KB 24 — Củng cố ═════════════════════════════════════════════════════════
async def _dung_kb24(client, session, tb, lich_su_y):
    """Y = YCCĐ 0 (đúng hết bài này), X = YCCĐ 1 (sai 1 câu). Lịch sử cũ của Y theo `lich_su_y`."""
    the, gv, hs = await canh(client, session)
    await chen_lich_su(session, hs.id, [[(the.ycds[0], d) for d in lan] for lan in lich_su_y])
    bttc = (await them_hl(client, gv, the, 0, loai="BTTC", muc_dich="cung_co", ma=_ma(the, "BTTC", "004")))["ma"]
    sgk_y = (await them_hl(client, gv, the, 0, loai="SGK", muc_dich="on_lai", ma=_ma(the, "SGK", "010")))["ma"]
    sgk_x = (await them_hl(client, gv, the, 1, loai="SGK", muc_dich="on_lai", ma=_ma(the, "SGK", "090")))["ma"]
    specs = [Cau(0), Cau(0), Cau(1, dung=False), Cau(1)]
    dx = (await lam_bai("cuoi_ky", client, session, tb, the, hs, specs)).de_xuat
    return dx, bttc, sgk_y, sgk_x


async def test_ycd_dung_nhung_chua_vung_ra_hoc_lieu_cung_co_sau_on_lai_kb24(client, session, tb):
    """4 lần nộp trước: Y 5 câu đúng 2; bài này đúng 2/2 -> 4/7 < 80%."""
    cu = [[True, False], [False], [True], [False]]
    dx, bttc, sgk_y, sgk_x = await _dung_kb24(client, session, tb, cu)
    assert ma_cua(dx["doc_them"]) == [sgk_x, bttc]       # Củng cố xếp SAU mọi Ôn lại (dù Y đứng trước X trong ma trận)
    assert ghi_chu_cua(dx["doc_them"], bttc) == "Củng cố"
    assert sgk_y not in ma_cua(dx["doc_them"])           # Y không còn sai -> không Ôn lại


async def test_dung_nguong_80_phan_tram_khong_con_chua_vung_kb24(client, session, tb):
    """Biên: "dưới 80%" — đúng 80% (4/5) là vững. Trước: 3 câu đúng 2; bài này đúng 2/2."""
    dx, bttc, _sgk_y, _sgk_x = await _dung_kb24(client, session, tb, [[True, True, False]])
    assert bttc not in ma_cua(dx["doc_them"])


async def test_chi_tinh_5_lan_nop_gan_nhat_kb24(client, session, tb):
    """Lần nộp cũ nhất (0/5) nằm NGOÀI cửa sổ 5 lần gần nhất (4 lần cũ + bài này) nên không kéo
    tỉ lệ xuống: 4 lần cuối đều đúng -> vững."""
    cu = [[False] * 5, [True], [True], [True], [True]]
    dx, bttc, _sgk_y, _sgk_x = await _dung_kb24(client, session, tb, cu)
    assert bttc not in ma_cua(dx["doc_them"])


# ═══ KB 25 — làm đúng hết ═══════════════════════════════════════════════════
async def _lam_dung_het(client, session, tb, *, lich_su_y):
    the, gv, hs = await canh(client, session)
    if lich_su_y:
        await chen_lich_su(session, hs.id, [[(the.ycds[0], d) for d in lan] for lan in lich_su_y])
    bttc = (await them_hl(client, gv, the, 0, loai="BTTC", muc_dich="cung_co"))["ma"]
    sgk = (await them_hl(client, gv, the, 0, loai="SGK", muc_dich="on_lai"))["ma"]
    specs = [Cau(0), Cau(0)] + [Cau(1)] * 8
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, specs,
                        tinh_chinh=lambda t: t.them(*[cau_phu(the, 0, j) for j in (1, 2)]))
    return the, ket.de_xuat, bttc, sgk


async def test_lam_dung_het_nhung_con_ycd_chua_vung_kb25(client, session, tb):
    cu = [[False, False, False], [False, False, False]]           # lịch sử: Y 0/6, bài này 2/2 -> 2/8
    the, dx, bttc, sgk = await _lam_dung_het(client, session, tb, lich_su_y=cu)
    assert dx["loi_khen"] == "Em làm đúng tất cả 10 câu. Giỏi lắm!"
    assert dx["doc_them"]["bai_hoc"] == []                        # không có mục bài học
    assert ma_cua(dx["doc_them"]) == [bttc]                       # chỉ Củng cố, không Ôn lại
    assert dx["video"] is None
    assert dx["test_them"] is not None and the.ar(0) in dx["test_them"]["ar_ids"]   # yếu theo lịch sử


async def test_lam_dung_het_va_khong_con_ycd_yeu_chi_co_loi_khen_kb25(client, session, tb):
    the, dx, bttc, sgk = await _lam_dung_het(client, session, tb, lich_su_y=None)
    assert dx["loi_khen"] == "Em làm đúng tất cả 10 câu. Giỏi lắm!"
    assert dx["doc_them"] is None and dx["video"] is None and dx["test_them"] is None
    assert dx["thong_bao"] is None


@pytest.mark.parametrize("loai", LOAI_BAI)
async def test_co_cau_sai_thi_khong_co_loi_khen_kb25(client, session, tb, loai):
    the, gv, hs = await canh(client, session)
    dx = (await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())).de_xuat
    assert dx["loi_khen"] is None


# ═══ KB 26 — cùng một khối ở mọi loại bài ═══════════════════════════════════
async def _bai_co_du_nhom(client, session, tb, loai):
    the, gv, hs = await canh(client, session)
    sgk = (await them_hl(client, gv, the, 0, loai="SGK"))["ma"]
    vd = (await them_hl(client, gv, the, 0, loai="VIDEO"))["ma"]
    ket = await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())
    return ket, sgk, vd, the


@pytest.mark.parametrize("loai", LOAI_BAI)
async def test_khoi_de_xuat_co_o_moi_loai_bai_dung_hinh_dang_kb26(client, session, tb, loai):
    ket, sgk, vd, the = await _bai_co_du_nhom(client, session, tb, loai)
    dx = ket.de_xuat
    assert set(dx) == KHOA_DE_XUAT
    assert set(dx["doc_them"]) >= {"bai_hoc", "hoc_lieu", "toi_da_bai_hoc", "toi_da_hoc_lieu"}
    assert set(dx["video"]) >= {"hoc_lieu", "toi_da"}
    assert set(dx["test_them"]) >= {"ar_ids", "ycd", "so_cau", "mo_ta", "thieu", "bo_qid"}
    for nhom in (dx["doc_them"], dx["video"]):
        for m in nhom["hoc_lieu"]:
            assert set(m) >= KHOA_MUC
            assert isinstance(m["noi_bo"], bool) and m["muc_dich"] in ("on_lai", "cung_co")
    for b in dx["doc_them"]["bai_hoc"]:
        assert set(b) >= {"topic_id", "ten", "phan", "ghi_chu"}
    assert ma_cua(dx["doc_them"]) == [sgk] and ma_cua(dx["video"]) == [vd]
    assert dx["video"]["hoc_lieu"][0]["noi_bo"] is False          # link ngoài -> tab mới
    assert dx["test_them"]["so_cau"] >= 1 and dx["test_them"]["mo_ta"].startswith("Bài mới ")


async def test_moi_loai_bai_cho_cung_bo_khoa_kb26(client, session, tb):
    """Giao diện dùng MỘT component: mọi loại phải trả cùng tập khoá ở mọi tầng."""
    hinh = {}
    for loai in LOAI_BAI:
        ket, *_ = await _bai_co_du_nhom(client, session, tb, loai)
        dx = ket.de_xuat
        hinh[loai] = (sorted(dx), sorted(dx["doc_them"]), sorted(dx["video"]), sorted(dx["test_them"]),
                      [sorted(m) for m in dx["video"]["hoc_lieu"] + dx["doc_them"]["hoc_lieu"]])
    mau = hinh[LOAI_BAI[0]]
    assert all(h == mau for h in hinh.values()), hinh


@pytest.mark.parametrize("loai", LOAI_BAI)
async def test_ket_qua_cu_van_con_du_dieu_diem_va_dap_an_kb26(client, session, tb, loai):
    """Hồi quy: thêm `de_xuat` không làm mất phần kết quả đã có (điểm, đáp án, trường `goi_y` cũ
    được giữ theo hợp đồng §8)."""
    ket, *_ = await _bai_co_du_nhom(client, session, tb, loai)
    assert "diem" in ket.kq and "tong" in ket.kq
    if loai in ("cuoi_ky", "de_giao", "test_them", "luyen_them"):
        assert all("dap_an" in c for c in ket.kq["cau"])
    if loai in ("cuoi_ky", "de_giao"):
        assert "goi_y" in ket.kq and "theo_ycd" in ket.kq


# ═══ KB 27 — cùng kết quả theo YCCĐ thì cùng đề xuất ═════════════════════════
async def test_on_tap_va_cuoi_ky_cung_ket_qua_thi_cung_doc_them_va_video_kb27(client, session, tb):
    the, gv, hs1 = await canh(client, session)
    hs2 = await tk(client)
    for tien, loai, mp in (("SGK", "SGK", "on_lai"), ("VD", "VIDEO", "on_lai"), ("BTTC", "BTTC", "cung_co")):
        for k in (0, 1):
            await them_hl(client, gv, the, k, loai=loai, muc_dich=mp, ma=_ma(the, tien, f"K{k}"))
    specs = [Cau(0, False), Cau(1), Cau(0, False), Cau(1)]
    a = await lam_bai("on_tap", client, session, tb, the, hs1, specs)
    b = await lam_bai("cuoi_ky", client, session, tb, the, hs2, specs)
    assert a.de_xuat["doc_them"] == b.de_xuat["doc_them"] and a.de_xuat["doc_them"] is not None
    assert a.de_xuat["video"] == b.de_xuat["video"] and a.de_xuat["video"] is not None


async def test_bon_loai_testbank_cung_phuong_an_sai_thi_cung_hoc_lieu_kb27(client, session, tb):
    the, gv, _hs = await canh(client, session, (3,))
    specs = _bai_phuong_an("B")
    nap_kho(tb, the, specs)
    await them_hl(client, gv, the, 0, qid=the.qid(3), option_key="B", ma=_ma(the, "VD", "021"))
    await them_hl(client, gv, the, 0, qid=the.qid(3), ma=_ma(the, "VD", "020"))
    await them_hl(client, gv, the, 0, ma=_ma(the, "VD", "001"))
    await them_hl(client, gv, the, 0, loai="SGK", ma=_ma(the, "SGK", "003"))
    ket = {}
    for loai in LOAI_CO_QID:
        ket[loai] = (await lam_bai(loai, client, session, tb, the, await tk(client), specs)).de_xuat
    ref = ket["cuoi_ky"]
    for loai, dx in ket.items():
        assert ma_cua(dx["video"]) == ma_cua(ref["video"]) == [_ma(the, "VD", n) for n in ("021", "020", "001")], loai
        assert ma_cua(dx["doc_them"]) == ma_cua(ref["doc_them"]), loai
    assert ket["de_giao"]["video"] == ref["video"] and ket["de_giao"]["doc_them"] == ref["doc_them"]


# ═══ KB 28 — Test thêm ══════════════════════════════════════════════════════
async def _dung_kb28(client, session, tb):
    the, gv, hs = await canh(client, session, (3,))
    specs = [Cau(0, False), Cau(1, False), Cau(2)]       # X, Y sai; Z đúng
    phu = [cau_phu(the, k, j) for k in range(3) for j in (1, 2, 3)]
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, specs, tinh_chinh=lambda t: t.them(*phu))
    return the, hs, ket, {c["qid"] for c in phu}


async def test_khoi_test_them_noi_ro_ycd_yeu_kb28(client, session, tb):
    the, hs, ket, _phu = await _dung_kb28(client, session, tb)
    tt = ket.de_xuat["test_them"]
    assert set(tt["ar_ids"]) == {the.ar(0), the.ar(1)} and len(tt["ar_ids"]) == 2     # Z đúng nên không có
    assert set(tt["ycd"]) == {the.ycds[0], the.ycds[1]}
    assert tt["so_cau"] == 4
    # Tên YCCĐ bỏ dấu chấm cuối trước khi nối — không thì ra "…tính., …" (QC27, chốt 21/10/2026).
    a, b = the.ycds[0].rstrip("."), the.ycds[1].rstrip(".")
    assert tt["mo_ta"] in (f"Bài mới 4 câu về: {a}, {b}", f"Bài mới 4 câu về: {b}, {a}")
    assert {the.qid(1), the.qid(2)} <= set(tt["bo_qid"])
    assert tt["thieu"] == []


async def test_bam_test_them_tao_bai_moi_chi_gom_ycd_yeu_khong_trung_bai_cu_kb28(client, session, tb):
    the, hs, ket, phu = await _dung_kb28(client, session, tb)
    tt = ket.de_xuat["test_them"]
    tb.goi_list.clear()
    r = await client.post("/exam/cuoi-ky/test-them", headers=hs.h,
                          json={"ar_ids": tt["ar_ids"], "bo_qid": tt["bo_qid"]})
    assert r.status_code == 200, r.text
    de = r.json()
    assert de["de_id"] and 4 <= len(de["cau"]) <= 12 and len(de["cau"]) == 4
    assert {c["ar_id"] for c in de["cau"]} == {the.ar(0), the.ar(1)}              # không có Z
    for ar in (the.ar(0), the.ar(1)):
        assert sum(1 for c in de["cau"] if c["ar_id"] == ar) == 2                 # 2 câu mỗi YCCĐ
    assert {c["qid"] for c in de["cau"]} <= phu                                   # không câu của bài vừa nộp
    # Hợp đồng §5: chọn câu trên /pool, KHÔNG dùng exams:preview (nó ép tỉ lệ mức độ).
    assert all(duong != "/exams:preview" for (_d, duong, _b) in tb.goi_list)
    # Đề chưa nộp: không đáp án, không học liệu.
    raw = json.dumps(de, ensure_ascii=False)
    for cam in ("answer_key", "explanation", "Lời giải", "ly_do", "dap_an", "de_xuat"):
        assert cam not in raw, cam


async def test_test_them_la_de_tu_rut_co_trong_lich_su_va_xoa_duoc_kb28(client, session, tb):
    the, hs, ket, _phu = await _dung_kb28(client, session, tb)
    tt = ket.de_xuat["test_them"]
    de = (await client.post("/exam/cuoi-ky/test-them", headers=hs.h,
                            json={"ar_ids": tt["ar_ids"], "bo_qid": tt["bo_qid"]})).json()
    ds = (await client.get("/exam/cuoi-ky", headers=hs.h)).json()["de"]
    assert de["de_id"] in [x["de_id"] for x in ds]
    assert (await client.delete(f"/exam/cuoi-ky/{de['de_id']}", headers=hs.h)).status_code == 204


async def test_test_them_tinh_vao_han_muc_de_cuoi_ky_kb28(client, session, tb, mocker):
    the, hs, ket, _phu = await _dung_kb28(client, session, tb)
    mocker.patch.object(cuoi_ky.settings, "de_cuoi_ky_daily_limit", 1)
    # `lam_bai` ở trên đã rút 1 đề (đề cuối kỳ gốc) -> hạn mức 1 đã dùng hết: Test thêm bị chặn.
    tt = ket.de_xuat["test_them"]
    n = len(tb.goi_list)
    r = await client.post("/exam/cuoi-ky/test-them", headers=hs.h,
                          json={"ar_ids": tt["ar_ids"], "bo_qid": tt["bo_qid"]})
    assert r.status_code == 429 and len(tb.goi_list) == n          # chặn TRƯỚC khi gọi testbank


async def test_test_them_can_dang_nhap_va_khong_nhan_rac_kb28(client, session, tb):
    r = await client.post("/exam/cuoi-ky/test-them", json={"ar_ids": ["AR-1"], "bo_qid": []})
    assert r.status_code == 401
    hs = await tk(client)
    for body in ({"ar_ids": "AR-1"}, {"ar_ids": [1, 2]}, {"ar_ids": ["AR-1"], "bo_qid": "x"}):
        r = await client.post("/exam/cuoi-ky/test-them", headers=hs.h, json=body)
        assert 400 <= r.status_code < 500, (body, r.status_code, r.text)


# ═══ KB 29 — kho thiếu câu ═════════════════════════════════════════════════
async def test_kho_co_cau_cho_x_khong_co_cho_y_kb29(client, session, tb):
    """Câu của Bài kiểm tra nhanh do learning tự sinh nên Y không có câu nào trong kho đề."""
    the, gv, hs = await canh(client, session)
    tb.dat([cau_phu(the, 0, 1), cau_phu(the, 0, 2)])
    dx = (await lam_bai("quiz", client, session, tb, the, hs,
                        [Cau(0, False), Cau(0, False), Cau(1, False), Cau(1, False)],
                        kho_cho_quiz=False)).de_xuat
    tt = dx["test_them"]
    assert tt["ar_ids"] == [the.ar(0)] and tt["ycd"] == [the.ycds[0]]
    assert tt["thieu"] == [f"Chưa có câu luyện cho {the.ycds[1]}"]
    assert the.ycds[1] not in tt["mo_ta"]


async def test_kho_khong_co_cau_nao_an_nhom_test_them_kb29(client, session, tb):
    the, gv, hs = await canh(client, session)
    tb.dat([])
    dx = (await lam_bai("quiz", client, session, tb, the, hs, _bai_chuan(), kho_cho_quiz=False)).de_xuat
    assert dx["test_them"] is None
    assert dx["thong_bao"] == MSG_KHONG_CAU


# ═══ KB 30 — Testbank chết khi bấm Test thêm ═════════════════════════════════
@pytest.mark.parametrize("loi", [TestbankLoi("mạng", tam_thoi=True),
                                 TestbankLoi("403", tam_thoi=False, ma=403),
                                 TestbankLoi("503", tam_thoi=True, ma=503)],
                         ids=["mang", "tu_choi_4xx", "5xx"])
async def test_testbank_loi_khi_bam_test_them_khong_tao_bai_rong_kb30(client, session, tb, loi):
    the, gv, hs = await canh(client, session)
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, _bai_chuan())
    truoc = [x["de_id"] for x in (await client.get("/exam/cuoi-ky", headers=hs.h)).json()["de"]]
    tt = ket.de_xuat["test_them"]
    tb.loi = loi
    r = await client.post("/exam/cuoi-ky/test-them", headers=hs.h,
                          json={"ar_ids": tt["ar_ids"], "bo_qid": tt["bo_qid"]})
    assert r.status_code == 503 and r.json()["detail"] == MSG_TEST_THEM_LOI
    tb.loi = None
    sau = [x["de_id"] for x in (await client.get("/exam/cuoi-ky", headers=hs.h)).json()["de"]]
    assert sau == truoc                                  # không có bài làm rỗng nào được tạo
    assert (await session.scalar(select(func.count()).select_from(DeCuoiKy)
                                 .where(DeCuoiKy.user_id == hs.id))) == len(truoc)


async def test_ket_qua_va_khoi_de_xuat_giu_nguyen_khi_testbank_chet_kb30(client, session, tb):
    """Màn kết quả không đổi: mở lại kết quả lúc testbank chết vẫn ra đủ điểm + khối Đề xuất
    (Test thêm trả theo `ar_ids` đã biết — hợp đồng §4)."""
    the, gv, hs = await canh(client, session)
    await them_hl(client, gv, the, 0, loai="SGK")
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, _bai_chuan())
    tb.loi = TestbankLoi("mạng", tam_thoi=True)
    mo = await ket.mo_lai()
    assert mo["ket_qua"]["diem"] == ket.kq["diem"]
    dx = lay_de_xuat(mo)
    assert dx["doc_them"] == ket.de_xuat["doc_them"]
    assert dx["test_them"] is not None and dx["test_them"]["ar_ids"] == ket.de_xuat["test_them"]["ar_ids"]


async def test_testbank_khong_phan_hoi_qua_10_giay_thi_bao_loi_kb30(client, session, tb):
    """Testbank treo: trong tối đa 10 giây (+ dung sai) học sinh phải thấy thông báo, không phải
    chờ tới timeout 20 giây của client HTTP."""
    the, gv, hs = await canh(client, session)
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, _bai_chuan())
    tt = ket.de_xuat["test_them"]
    tb.treo_giay = 60
    t0 = time.monotonic()
    try:
        r = await asyncio.wait_for(
            client.post("/exam/cuoi-ky/test-them", headers=hs.h,
                        json={"ar_ids": tt["ar_ids"], "bo_qid": tt["bo_qid"]}), timeout=15)
    except asyncio.TimeoutError:
        pytest.fail("Test thêm không trả lời trong 15 giây khi testbank treo (KB30: tối đa 10 giây)")
    dt = time.monotonic() - t0
    assert dt <= 12, f"mất {dt:.1f}s"
    assert r.status_code == 503 and r.json()["detail"] == MSG_TEST_THEM_LOI


# ═══ KB 31 — cách mở học liệu (phần kiểm được ở API + mã nguồn web) ═══════════
def _web_src() -> Path:
    return GOC / "web" / "src"


def _de_xuat_view() -> Path | None:
    kq = sorted(_web_src().rglob("DeXuatView.tsx"))
    return kq[0] if kq else None


def test_component_de_xuat_view_ton_tai_va_dung_chung_kb26():
    """Hợp đồng §6: MỘT component `DeXuatView` cho cả bốn màn kết quả."""
    f = _de_xuat_view()
    assert f is not None, "chưa có web/src/**/DeXuatView.tsx"
    for man in ("QuizView", "OnTapView", "LuyenThemView", "CuoiKyView"):
        src = next(_web_src().rglob(f"{man}.tsx")).read_text()
        assert "DeXuatView" in src, f"{man}.tsx chưa dùng DeXuatView"


def test_khoi_goi_y_cu_da_go_kb26():
    """KB26: không còn khối "Nên đọc lại N phần" / "Đọc lại trước khi làm tiếp" riêng lẻ."""
    for f in _web_src().rglob("*.tsx"):
        src = f.read_text()
        assert "Nên đọc lại" not in src, f
        assert "Đọc lại trước khi làm tiếp" not in src, f


def test_link_ngoai_mo_tab_moi_khong_cho_trang_dich_dieu_khien_kb31():
    f = _de_xuat_view()
    assert f is not None, "chưa có DeXuatView.tsx"
    src = f.read_text()
    assert 'target="_blank"' in src
    assert 'rel="noopener noreferrer"' in src


def test_khung_phat_bao_loi_khi_video_noi_bo_hong_kb32():
    f = _de_xuat_view()
    assert f is not None, "chưa có DeXuatView.tsx"
    assert "Video tạm thời không phát được" in "".join(
        p.read_text() for p in _web_src().rglob("*.tsx"))


# ═══ KB 33 — kho học liệu không đọc được ═════════════════════════════════════
@pytest.mark.parametrize("loai", LOAI_BAI)
async def test_kho_hoc_lieu_loi_ket_qua_van_day_du_khoi_suy_giam_kb33(client, session, tb, loai, mocker):
    the, gv, hs = await canh(client, session)
    await them_hl(client, gv, the, 0, loai="SGK")
    await them_hl(client, gv, the, 0, loai="VIDEO")
    try:
        mocker.patch("app.lessons.de_xuat.doc_kho_hoc_lieu", side_effect=RuntimeError("kho học liệu chết"))
    except (AttributeError, ModuleNotFoundError) as e:
        pytest.fail(f"chưa có app.lessons.de_xuat.doc_kho_hoc_lieu (giả định ở docstring): {e}")
    ket = await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())
    assert ket.kq["diem"] == 3 and ket.kq["tong"] == 4               # điểm + kết quả vẫn đủ
    dx = ket.de_xuat
    assert dx["video"] is None                                       # không có nhóm Video rỗng
    assert dx["doc_them"]["hoc_lieu"] == [] and dx["doc_them"]["bai_hoc"]
    assert dx["test_them"] is not None
    assert dx["thong_bao"] == MSG_KHO_CHET


# ═══ KB 34 — không lộ học liệu trước khi nộp ═════════════════════════════════
async def test_khong_lo_hoc_lieu_o_moi_duong_truoc_khi_nop_kb34(client, session, tb):
    the, gv, hs = await canh(client, session, (3,))
    specs = _bai_phuong_an("B")
    nap_kho(tb, the, specs)
    nhan = f"NHAN-BI-MAT-{the.uid}"
    url = f"https://hoc-lieu-bi-mat.example/{the.uid}"
    ma = []
    for kv in ({"option_key": "B"}, {}):
        hl = await them_hl(client, gv, the, 0, qid=the.qid(3), nhan=nhan, url=url, **kv)
        ma.append(hl["ma"])
    ma.append((await them_hl(client, gv, the, 0, nhan=nhan, url=url))["ma"])
    cam = (nhan, url, *ma)

    nap_kho(tb, the, specs)
    tb.them(cau_phu(the, 0, 1), cau_phu(the, 0, 2))        # để Test thêm có câu mà rút
    # Bài kiểm tra nhanh / ôn tập: dữ liệu bài học + đề.
    await dat_quiz(session, the, specs)
    phan_hoi = {
        "bai_hoc": await client.get(f"/lessons/{the.bai[0].tid}", headers=hs.h),
        "on_tap_de": await client.get("/on-tap/de", headers=hs.h, params={
            "pham_vi": "mach", "gia_tri": the.mach}),
        "luyen_them": await client.post(f"/lessons/{the.bai[0].tid}/luyen-them", headers=hs.h, json={}),
        "rut_cuoi_ky": await client.post("/exam/cuoi-ky/generate", headers=hs.h, json={}),
        "test_them": await client.post("/exam/cuoi-ky/test-them", headers=hs.h,
                                       json={"ar_ids": [the.ar(0)], "bo_qid": []}),
    }
    de = phan_hoi["rut_cuoi_ky"].json()
    phan_hoi["mo_lai_chua_nop"] = await client.get(f"/exam/cuoi-ky/{de['de_id']}", headers=hs.h)
    phan_hoi["lich_su"] = await client.get("/exam/cuoi-ky", headers=hs.h)
    gv2 = await tk(client, "giao_vien")
    nhap = (await client.post("/de-giao/xem-truoc", headers=gv2.h, json={"exam": "CK1"})).json()
    ma_giao = (await client.post(f"/de-giao/{nhap['nhap_id']}/cap-ma", headers=gv2.h)).json()["ma"]
    phan_hoi["de_giao_vao"] = await client.post("/de-giao/vao", headers=hs.h, json={"ma": ma_giao})
    for ten, r in phan_hoi.items():
        assert r.status_code == 200, (ten, r.status_code, r.text[:200])
        _khong_lo_hoc_lieu(r.text, *cam)
    # Đối chứng: SAU khi nộp thì có (nếu không, các assert trên không chứng minh được gì).
    sau = await client.post("/exam/cuoi-ky/submit", headers=hs.h, json={
        "de_id": de["de_id"], "tra_loi": {the.qid(3): "B"}})
    assert sau.status_code == 200
    assert ma[0] in json.dumps(sau.json(), ensure_ascii=False)


async def test_hoc_sinh_khac_khong_xem_duoc_khoi_de_xuat_cua_nguoi_khac_kb34(client, session, tb):
    the, gv, hs = await canh(client, session)
    await them_hl(client, gv, the, 0)
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, _bai_chuan())
    ke_la = await tk(client)
    r = await client.get(f"/exam/cuoi-ky/{ket.de_id}", headers=ke_la.h)
    assert r.status_code == 404
    assert "de_xuat" not in r.text


# ═══ Hợp đồng §4 — tính lại mỗi lần trả về; suy giảm khi testbank chưa nối ═════
@pytest.mark.parametrize("loai,duong", [("cuoi_ky", "/exam/cuoi-ky/submit"),
                                        ("de_giao", "/de-giao/nop"),
                                        ("luyen_them", "/lessons/luyen-them/submit")])
async def test_nop_lai_tinh_lai_de_xuat_theo_kho_hien_tai_kb8(client, session, tb, loai, duong):
    """Bấm "Nộp" lần hai trả kết quả cũ (không ghi thêm) nhưng `de_xuat` vẫn phải theo kho HIỆN TẠI
    (Q11) — nếu DEV lưu `de_xuat` vào `ket_qua_json` thì học liệu thêm / xoá sau đó không thấy."""
    the, gv, hs = await canh(client, session)
    ket = await lam_bai(loai, client, session, tb, the, hs, _bai_chuan())
    assert ket.de_xuat["video"] is None
    moi = (await them_hl(client, gv, the, 0, loai="VIDEO"))["ma"]
    r = await client.post(duong, headers=hs.h, json={"de_id": ket.de_id, "tra_loi": {}})
    assert r.status_code == 200, r.text
    assert ma_cua(r.json()["de_xuat"]["video"]) == [moi]
    assert r.json()["diem"] == ket.kq["diem"]


@pytest.mark.parametrize("loai", ["quiz", "on_tap"])
async def test_testbank_chua_noi_khong_lam_hong_nop_bai_quiz_kb33(client, session, tb, mocker, loai):
    """Câu quiz / ôn tập tự sinh: nộp bài KHÔNG được phụ thuộc testbank. Chưa cấu hình / không với
    tới được thì kết quả vẫn 200 và vẫn có học liệu + bài học (phần cần testbank mới suy giảm)."""
    the, gv, hs = await canh(client, session)
    sgk = (await them_hl(client, gv, the, 0, loai="SGK"))["ma"]
    app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)
    mocker.patch("app.api.cuoi_ky.tao_client", side_effect=TestbankChuaCauHinh(["TESTBANK_EMAIL"]))
    ket = await lam_bai(loai, client, session, tb, the, hs, _bai_chuan(), kho_cho_quiz=False)
    assert ket.kq["diem"] == 3
    assert ma_cua(ket.de_xuat["doc_them"]) == [sgk]
    assert ket.de_xuat["doc_them"]["bai_hoc"]
