"""US-26 — Giáo viên giao đề cuối kỳ bằng mã (39 kịch bản).

Nguồn: User-Stories/EPIC-03-Sinh-De/US-26-giao-de-bang-ma.md và hợp đồng API
docs/contracts/US-26-giao-de-bang-ma.md (cùng repo tài liệu). Router mới: `app/api/de_giao.py`,
tiền tố `/de-giao`. Test viết TRƯỚC khi DEV code (RED).

GIẢ ĐỊNH CẦN DEV LÀM THEO (hợp đồng chưa nói rõ — ghi ở đây để khỏi đoán)
--------------------------------------------------------------------------
1. Testbank giả cắm qua `app.dependency_overrides[app.api.cuoi_ky.lay_testbank]` — `app/api/de_giao.py`
   DÙNG CHUNG dependency này (không tạo dependency riêng). Testbank giả chỉ có `goi()` (POST):
   `/exams:preview` + `/questions:resolve` (include_answers=True). Chưa cấu hình: test patch
   `app.api.cuoi_ky.tao_client` -> `TestbankChuaCauHinh`. Vì `lay_testbank` hiện chọn câu thông báo
   theo đường dẫn (`/lessons/` hay không) và câu mặc định là "Đề cuối kỳ chưa được kết nối...",
   DEV phải thêm nhánh cho `/de-giao/` để `detail` có "Kho đề" (hợp đồng mục 2, KB 6).
2. Bộ đếm hạn mức / chặn dò mã đi qua `llm_cache` (một module duy nhất `app.llm.cache`). Test thay
   BỐN hàm của module đó bằng bộ nhớ trong có đồng hồ giả (xem `KhoDemGia`):
   `incr_quota(key, ttl) -> int`, `giam_quota(key, ttl)`, `get(key) -> str|None`, `set(key, value, ttl=...)`.
   DEV chỉ được dùng đúng bốn hàm này (đừng gọi `llm_cache._redis()` trực tiếp, test sẽ không bắt được).
   Hết hạn (TTL) mô phỏng bằng `kho_dem.tien(giay)`: khoá nào quá TTL thì biến mất.
   Chặn dò mã: tính TTL 10 phút (600 giây), khoá hết hạn thì hết chặn.
3. Giờ Việt Nam của hạn mức ngày: test thay `app.api.de_giao.datetime` bằng lớp giả (xem `_dong_ho`) —
   DEV viết `from datetime import datetime` ở đầu `app/api/de_giao.py` và lấy ngày bằng
   `datetime.now(<múi giờ Asia/Ho_Chi_Minh hoặc UTC+7>)` rồi đưa ngày VN vào khoá đếm. Cách này cho test
   chạy đúng ở mọi giờ máy (tính theo UTC thì test "qua nửa đêm giờ VN" đỏ).
4. Hạn mức: `settings.de_giao_daily_limit` (mặc định 20). Test lấy số nhỏ bằng `mocker.patch.object`.
5. `thong_bao` của lần vượt hạn mức chứa "đề giao, ngày mai tạo tiếp được nhé" (số 20 ghi theo setting).
6. `tong` ở bảng kết quả là số câu chấm được; `ti_le_dung` chấp nhận cả phân số 0..1 lẫn phần trăm 0..100
   (hợp đồng chưa chốt thang) — xem `_ti`.
7. Id đề giao (`id`, `nhap_id`) là giá trị mờ: test chỉ ghép vào đường dẫn, không giả định kiểu. Test dùng
   "987654321" làm id không tồn tại.
8. `nguoi_tao` (cột "Người tạo" của admin) chứa TÊN giáo viên (chuỗi hoặc đối tượng có tên).

KB KHÔNG viết được ở đây (lý do ở báo cáo): giao diện (KB 2 màn hình, KB 3 nút, KB 11 ghi chú, KB 25 hộp xác
nhận, KB 31 chữ "Chưa có học sinh nào làm đề này", KB 38 màn hình không có lựa chọn vai), KB 20 chạy
song song thật (fixture `client` dùng chung một session), KB 23 chất lượng lý do (eval).
"""
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import copy
import pytest

pytestmark = pytest.mark.usefixtures("de_giao_cu_bat")  # US-26 đã ngừng: bật lại để dựng dữ liệu cũ
from sqlalchemy import func, select

from app.api import cuoi_ky
from app.config import settings
from app.db.models import QuizAttempt, QuizAttemptItem
from app.integrations.testbank.client import TestbankChuaCauHinh, TestbankLoi
from app.lessons import ycd_thong_ke as ycd_tk_svc
from app.llm import cache as llm_cache
from app.llm.gateway import LLMUnavailable
from app.main import app
from tests.api.conftest import tao_tai_khoan

BANG = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
MSG_KHONG_QUYEN = "Bạn không có quyền giao đề"
MSG_KHONG_THAY_DE = "Không tìm thấy đề giao này"
MSG_SAI_DINH_DANG = "Mã gồm 6 chữ và số, em kiểm tra lại nhé"
MSG_KHONG_THAY_MA = "Không tìm thấy mã này, em hỏi lại thầy cô nhé"
MSG_DA_DONG = "Mã này đã đóng, em không làm được nữa"
MSG_CHAN_DO = "Em nhập sai mã nhiều lần, thử lại sau 10 phút nhé"
MSG_NOP_SAU_DONG = "Thầy cô đã đóng mã trước khi em nộp, bài này không được tính"
MSG_KHONG_XOA = "Bài thầy cô giao không xoá được"
MSG_DA_CAP_MA = "Đề giao đã cấp mã không xoá được, chỉ đóng được"
MSG_SO_CAU = "Số câu phải từ 1 đến 40"
MSG_KHO_RONG = "Kho chưa có câu nào cho đề này"
MSG_HET_HAN_MUC_DUOI = "đề giao, ngày mai tạo tiếp được nhé"
ID_KHONG_CO = "987654321"

KHOA_CAU_CONG_KHAI = {"stt", "qid", "dang", "muc_do", "ar_id", "ycd", "topic_id", "don_vi", "de_html",
                      "phuong_an", "du_kien_html", "cau_dan", "tu_cham"}
CAM_TRUOC_KHI_NOP = ("answer_key", "explanation", "Lời giải", "ly_do", "dap_an", "giai_html", "dap_an_html",
                     "LYDO-")

_PA = [{"key": k, "text": t} for k, t in zip("ABCD", ["2", "3", "6", "36"])]
_PA_DS = [{"key": k, "text": f"Khẳng định {k}"} for k in "ABCD"]
#: dạng -> (đáp án đúng, phương án, cách trả lời SAI chắc chắn)
_MAU = {
    "TN1": ("C", _PA, "A"), "TNN": ("A,C", _PA, "A"), "DS": ("Đ,S,Đ,S", _PA_DS, "S,Đ,S,Đ"),
    "DSN": ("3,5", [], "99"), "TL": ("", [], "bài tự luận"),
}
#: lý do giả của model: mỗi phương án một câu có dấu hiệu riêng để dò xem có lọt ra trình duyệt không.
LY_DO_MODEL = json.dumps({k: f"LYDO-{k}: giải thích phương án {k}." for k in "ABCD"}, ensure_ascii=False)


def _cau(qid, ar, dang, *, yccd=None, stem=None, **kv):
    mau = _MAU[dang]
    return {"qid": qid, "display_code": f"{qid}/{dang}", "ar_id": ar,
            "yccd_text": yccd or f"Thực hiện được yêu cầu {ar}.",
            "difficulty": "B", "format_code": dang, "competency_code": "GQV",
            "stem": stem or f"Đề {qid} ?", "options": mau[1], "answer_key": mau[0],
            "explanation": f"Lời giải gốc {qid}", "family_qid": qid, "version": "V01",
            "group_id": None, "stimulus": None, "stimulus_lead": None,
            "assets": {}, "asset_sizes": {}, **kv}


def _kho(n: int = 12, tl: int = 1, tag: str | None = None) -> list[dict]:
    """n câu, `tl` câu cuối là tự luận (không chấm tự động). Hai câu liền nhau chung một YCCĐ.
    qid kèm tag ngẫu nhiên: DB dev dùng chung và bảng lý do cache theo (qid, version)."""
    import uuid
    tag = tag or uuid.uuid4().hex[:6]
    dang = ["TN1", "TNN", "DS", "DSN"]
    out = []
    for i in range(1, n + 1):
        d = "TL" if i > n - tl else dang[(i - 1) % 4]
        out.append(_cau(f"{tag}-Q{i}", f"AR26-TO06-CK1-{(i + 1) // 2:03d}", d,
                        difficulty=("B", "H", "V")[(i - 1) % 3]))
    return out


def _dung(c: dict) -> str:
    return c["answer_key"]


def _sai(c: dict) -> str:
    return _MAU[c["format_code"]][2]


def _tra_loi(kho: list[dict], so_dung: int, *, bo_trong_cau_sai: bool = False) -> dict[str, str]:
    """`so_dung` câu chấm được đầu tiên trả lời đúng, các câu chấm được còn lại sai (hoặc bỏ trống)."""
    out, n = {}, 0
    for c in kho:
        if c["format_code"] == "TL":
            out[c["qid"]] = "bài tự luận"
            continue
        if n < so_dung:
            out[c["qid"]] = _dung(c)
        elif not bo_trong_cau_sai:
            out[c["qid"]] = _sai(c)
        n += 1
    return out


# ── Hạ tầng giả ─────────────────────────────────────────────────────────────
class TbGia:
    """Thay `TestbankClient`: chỉ cần `goi()` — rut_de / lay_cau đi qua đó."""

    __test__ = False

    def __init__(self, kho: list[dict], *, thieu: dict | None = None, thong_bao: str = "",
                 loi: Exception | None = None, bo_qid=()):
        self.kho = {c["qid"]: c for c in kho}
        self.thieu, self.thong_bao, self.loi, self.bo_qid = thieu, thong_bao, loi, set(bo_qid)
        self.goi_list: list[tuple[str, str, dict]] = []

    def so_lan_goi(self) -> int:
        return len(self.goi_list)

    async def goi(self, dich, duong, body):
        self.goi_list.append((dich, duong, body))
        if self.loi:
            raise self.loi
        if duong == "/exams:preview":
            ds = list(self.kho.values())[: body["total"]]
            return {"quota": {"B": len(ds)}, "is_complete": not self.thieu,
                    "shortage": self.thieu or {}, "pool_size": len(ds),
                    "message": (self.thong_bao or "Thiếu câu.") if self.thieu else f"Đã rút {len(ds)} câu.",
                    "items": [{"ordinal": i, "qid": c["qid"], "ar_id": c["ar_id"],
                               "difficulty_code": c["difficulty"], "format_code": c["format_code"]}
                              for i, c in enumerate(ds, start=1)]}
        if duong == "/questions:resolve":
            assert body["include_answers"] is True
            return [copy.deepcopy(self.kho[q]) for q in body["qids"] if q in self.kho and q not in self.bo_qid]
        raise AssertionError(duong)


class KhoDemGia:
    """Thay Redis trong `app.llm.cache`: có TTL theo đồng hồ giả `bay_gio` (giây)."""

    def __init__(self):
        self.d: dict[str, tuple[str, float]] = {}
        self.bay_gio = 0.0

    def tien(self, giay: float) -> None:
        self.bay_gio += giay

    def _song(self, key):
        v = self.d.get(key)
        if v is not None and v[1] <= self.bay_gio:
            del self.d[key]
            return None
        return v

    async def incr_quota(self, key, ttl):
        v = self._song(key)
        n = (int(v[0]) if v else 0) + 1
        self.d[key] = (str(n), v[1] if v else self.bay_gio + ttl)
        return n

    async def giam_quota(self, key, ttl):
        v = self._song(key)
        if v:
            self.d[key] = (str(max(int(v[0]) - 1, 0)), v[1])

    async def get(self, key):
        v = self._song(key)
        return v[0] if v else None

    async def set(self, key, value, ttl=86400):
        self.d[key] = (str(value), self.bay_gio + ttl)


@pytest.fixture
def tb():
    gia = TbGia(_kho())
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    yield gia
    app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


@pytest.fixture(autouse=True)
def _model(mocker):
    """Lý do từng phương án gọi LLM — mặc định trả lý do giả, test nào cần thì đè."""
    return mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value=LY_DO_MODEL))


@pytest.fixture(autouse=True)
def kho_dem(mocker):
    kho = KhoDemGia()
    for ten in ("incr_quota", "giam_quota", "get", "set"):
        mocker.patch.object(llm_cache, ten, getattr(kho, ten))
    return kho


def _dat_gioi_han(mocker, n: int) -> None:
    try:
        mocker.patch.object(settings, "de_giao_daily_limit", n)
    except (AttributeError, ValueError):
        pytest.fail("settings.de_giao_daily_limit chưa có (app/config.py)")


def _dong_ho(mocker, iso_utc: str) -> None:
    """Đóng băng đồng hồ của `app.api.de_giao` ở một thời điểm UTC."""
    try:
        import app.api.de_giao  # noqa: F401
    except ImportError:
        pytest.fail("app/api/de_giao.py chưa có")
    moc = datetime.fromisoformat(iso_utc).replace(tzinfo=timezone.utc)

    class DongHoGia(datetime):
        @classmethod
        def now(cls, tz=None):
            return moc.astimezone(tz) if tz else moc.replace(tzinfo=None)

        @classmethod
        def utcnow(cls):
            return moc.replace(tzinfo=None)

    mocker.patch("app.api.de_giao.datetime", DongHoGia, create=True)


# ── Tài khoản + lời gọi ─────────────────────────────────────────────────────
async def _tk(client, role="hoc_sinh", ten="An") -> SimpleNamespace:
    email, h = await tao_tai_khoan(client, role, ten, "dg")
    me = (await client.get("/auth/me", headers=h)).json()
    return SimpleNamespace(h=h, id=me["id"], ten=ten, email=email)


async def _xem_truoc(client, gv, exam="CK1", **kv):
    return await client.post("/de-giao/xem-truoc", headers=gv.h, json={"exam": exam, **kv})


async def _xt(client, gv, exam="CK1", **kv) -> dict:
    r = await _xem_truoc(client, gv, exam, **kv)
    assert r.status_code == 200, r.text
    return r.json()


async def _cap(client, gv, nhap_id):
    return await client.post(f"/de-giao/{nhap_id}/cap-ma", headers=gv.h)


async def _giao(client, gv, exam="CK1", **kv) -> SimpleNamespace:
    """Xem trước + cấp mã. Trả `.ma`, `.id`, `.xem_truoc`."""
    p = await _xt(client, gv, exam, **kv)
    r = await _cap(client, gv, p["nhap_id"])
    assert r.status_code == 200, r.text
    d = r.json()
    return SimpleNamespace(ma=d["ma"], id=d["id"], xem_truoc=p, cap=d)


async def _vao(client, hs, ma):
    return await client.post("/de-giao/vao", headers=hs.h, json={"ma": ma})


async def _vao_ok(client, hs, ma) -> dict:
    r = await _vao(client, hs, ma)
    assert r.status_code == 200, r.text
    return r.json()


async def _nop(client, hs, de_id, tra_loi):
    return await client.post("/de-giao/nop", headers=hs.h, json={"de_id": de_id, "tra_loi": tra_loi})


async def _nop_ok(client, hs, de_id, tra_loi) -> dict:
    r = await _nop(client, hs, de_id, tra_loi)
    assert r.status_code == 200, r.text
    return r.json()


async def _lam(client, hs, ma, kho, so_dung) -> dict:
    """Vào bằng mã rồi nộp với `so_dung` câu đúng. Trả kết quả."""
    v = await _vao_ok(client, hs, ma)
    return await _nop_ok(client, hs, v["de_id"], _tra_loi(kho, so_dung))


async def _ket_qua(client, gv, did):
    return await client.get(f"/de-giao/{did}/ket-qua", headers=gv.h)


async def _dem_lan_nop(session, uid: int, nguon="de_giao") -> int:
    return await session.scalar(select(func.count()).select_from(QuizAttempt)
                                .where(QuizAttempt.user_id == uid, QuizAttempt.nguon == nguon))


async def _dem_item(session, uid: int, nguon="de_giao") -> int:
    return await session.scalar(select(func.count()).select_from(QuizAttemptItem)
                                .join(QuizAttempt, QuizAttempt.id == QuizAttemptItem.attempt_id)
                                .where(QuizAttempt.user_id == uid, QuizAttempt.nguon == nguon))


def _ti(x, phan_so: float) -> bool:
    return x == pytest.approx(phan_so, abs=0.01) or x == pytest.approx(phan_so * 100, abs=0.1)


def _khong_lo(obj) -> None:
    raw = json.dumps(obj, ensure_ascii=False)
    for cam in CAM_TRUOC_KHI_NOP:
        assert cam not in raw, f"lộ '{cam}' trước khi nộp"


# ═══ A. Giáo viên tạo đề giao và nhận mã ════════════════════════════════════
async def test_tao_de_giao_du_cau_xem_truoc_roi_cap_ma_kb1(client, tb):
    """KB 1: xem trước 12 câu (có đáp án, lời giải, mức độ, YCCĐ) KHÔNG cấp mã; "Cấp mã" mới có mã,
    và mã gắn đúng bản đã xem (cùng câu, cùng thứ tự)."""
    gv = await _tk(client, "giao_vien", "Hoa")
    r = await client.post("/de-giao/xem-truoc", headers=gv.h, json={"exam": "CK1"})   # total mặc định
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["so_cau"] == 12 and p["total"] == 12 and len(p["cau"]) == 12
    assert p["du_cau"] is True and p["co_the_cap_ma"] is True and p["nhap_id"]
    assert p["exam"] == "CK1"
    c0 = p["cau"][0]
    assert {"dap_an", "dap_an_html", "giai_html", "ly_do", "muc_do", "ycd", "de_html", "phuong_an"} <= set(c0)
    assert c0["dap_an"] == tb.kho[c0["qid"]]["answer_key"] and "Lời giải gốc" in c0["giai_html"]
    # Rút ở chế độ XEM TRƯỚC (không trừ hạn mức testbank), tỉ lệ 40/30/30.
    dich, duong, body = tb.goi_list[0]
    assert duong == "/exams:preview"
    assert (body["exam"], body["total"], body["subject"], body["grade"]) == ("CK1", 12, "TO", "06")
    assert body["ratio"] == {"B": 40, "H": 30, "V": 30}
    assert not body.get("ar_ids")
    # Chưa có mã nào được cấp.
    assert "ma" not in p
    assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"] == []

    r = await _cap(client, gv, p["nhap_id"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert re.fullmatch(f"[{BANG}]{{6}}", d["ma"]) and d["trang_thai"] == "mo"
    assert (d["so_cau"], d["total"]) == (12, 12)
    # Bản gắn với mã là bản đã xem: cùng câu, cùng thứ tự.
    xem_lai = (await client.get(f"/de-giao/{d['id']}", headers=gv.h)).json()
    assert [c["qid"] for c in xem_lai["cau"]] == [c["qid"] for c in p["cau"]]
    hs = await _tk(client)
    assert [c["qid"] for c in (await _vao_ok(client, hs, d["ma"]))["cau"]] == [c["qid"] for c in p["cau"]]


async def test_cap_ma_hai_lan_tra_ve_dung_ma_cu_kb1(client, tb):
    """Bấm "Cấp mã" hai lần (mạng chậm) không được thành hai mã cho một đề."""
    gv = await _tk(client, "giao_vien")
    p = await _xt(client, gv)
    a = (await _cap(client, gv, p["nhap_id"])).json()
    b = (await _cap(client, gv, p["nhap_id"])).json()
    assert a["ma"] == b["ma"] and a["id"] == b["id"]
    assert len((await client.get("/de-giao", headers=gv.h)).json()["de_giao"]) == 1


@pytest.mark.parametrize("vai", ["giao_vien", "chuyen_gia", "admin"])
async def test_ba_vai_cms_deu_tao_duoc_de_giao(client, tb, vai):
    """Mô tả US: vai giáo viên / chuyên gia / admin trên CMS."""
    gv = await _tk(client, vai)
    g = await _giao(client, gv)
    assert re.fullmatch(f"[{BANG}]{{6}}", g.ma)


@pytest.mark.parametrize("tong", [0, -3, 12.5, 41, 1000])
async def test_so_cau_ngoai_1_den_40_bi_tu_choi_kb2(client, tb, tong):
    """KB 2: số câu 0, âm, không nguyên, > 40 -> từ chối, KHÔNG rút đề, không cấp mã."""
    gv = await _tk(client, "giao_vien")
    r = await _xem_truoc(client, gv, total=tong)
    assert r.status_code == 422, r.text
    assert MSG_SO_CAU in json.dumps(r.json()["detail"], ensure_ascii=False)
    assert tb.so_lan_goi() == 0
    assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"] == []


@pytest.mark.parametrize("tong", [1, 40])
async def test_bien_so_cau_1_va_40_duoc_chap_nhan_kb2(client, tb, tong):
    gv = await _tk(client, "giao_vien")
    r = await _xem_truoc(client, gv, total=tong)
    assert r.status_code == 200, r.text
    assert tb.goi_list[0][2]["total"] == tong


@pytest.mark.parametrize("exam", ["GK1", "ck1", "CK3", "", "CK1+CK2"])
async def test_ky_chi_la_ck1_hoac_ck2_kb2(client, tb, exam):
    gv = await _tk(client, "giao_vien")
    r = await _xem_truoc(client, gv, exam=exam)
    assert r.status_code == 422, r.text
    assert tb.so_lan_goi() == 0


async def test_ky_cuoi_ky_2_chuyen_dung_sang_testbank_kb2(client, tb):
    gv = await _tk(client, "giao_vien")
    p = await _xt(client, gv, exam="CK2")
    assert p["exam"] == "CK2" and tb.goi_list[0][2]["exam"] == "CK2"


async def test_kho_thieu_cau_bao_truoc_roi_cap_ma_voi_9_cau_kb3(client):
    """KB 3: kho chỉ có 9/12 câu -> xem trước 9 câu + thông báo thiếu BẰNG LỜI CỦA KHO, không bù mức khác,
    chưa cấp mã; giáo viên "Vẫn cấp mã" thì danh sách ghi 9/12 câu."""
    gia = TbGia(_kho(9), thieu={"V": 3}, thong_bao="Thiếu 3 câu mức Vận dụng.")
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        async with _Ctx(client) as gv:
            r = await _xem_truoc(client, gv, exam="CK2")
            p = r.json()
            assert r.status_code == 200 and p["so_cau"] == 9 and p["total"] == 12 and len(p["cau"]) == 9
            assert p["du_cau"] is False and p["co_the_cap_ma"] is True
            assert "Thiếu 3 câu mức Vận dụng." in p["thong_bao"]
            # Không tự lấy câu mức khác để bù: đúng một lần rút, không rút lại.
            assert [x[1] for x in gia.goi_list].count("/exams:preview") == 1
            assert "ma" not in p
            assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"] == []

            d = (await _cap(client, gv, p["nhap_id"])).json()
            assert (d["so_cau"], d["total"]) == (9, 12)
            row = (await client.get("/de-giao", headers=gv.h)).json()["de_giao"][0]
            assert (row["so_cau"], row["total"]) == (9, 12) and row["ma"] == d["ma"]
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


class _Ctx:
    """Tạo giáo viên trong khối `async with` (để test tự cắm testbank giả riêng)."""

    def __init__(self, client, ten="Hoa"):
        self.client, self.ten = client, ten

    async def __aenter__(self):
        return await _tk(self.client, "giao_vien", self.ten)

    async def __aexit__(self, *a):
        return False


async def test_huy_ban_xem_truoc_thi_khong_co_ma_va_khong_co_de_giao_kb3(client, tb):
    gv = await _tk(client, "giao_vien")
    p = await _xt(client, gv)
    r = await client.delete(f"/de-giao/{p['nhap_id']}", headers=gv.h)
    assert r.status_code == 204
    assert (await _cap(client, gv, p["nhap_id"])).status_code == 404       # đã huỷ, không cấp được nữa
    assert (await client.get(f"/de-giao/{p['nhap_id']}", headers=gv.h)).status_code == 404
    assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"] == []


async def test_ban_nhap_khong_hien_trong_danh_sach_kb3(client, tb):
    gv = await _tk(client, "giao_vien")
    await _xt(client, gv)
    assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"] == []


async def test_khong_xoa_duoc_de_da_cap_ma_chi_dong_duoc_q10(client, tb):
    """Q10: không xoá đề giao ở bản demo, chỉ đóng (xoá sẽ phải quyết luôn số phận bài làm của học sinh)."""
    gv = await _tk(client, "giao_vien")
    g = await _giao(client, gv)
    r = await client.delete(f"/de-giao/{g.xem_truoc['nhap_id']}", headers=gv.h)
    assert r.status_code == 409 and r.json()["detail"] == MSG_DA_CAP_MA
    assert len((await client.get("/de-giao", headers=gv.h)).json()["de_giao"]) == 1


async def test_giao_vien_khac_khong_huy_hay_cap_ma_ban_nhap_cua_nguoi_ta_kb35(client, tb):
    hoa, minh = await _tk(client, "giao_vien", "Hoa"), await _tk(client, "giao_vien", "Minh")
    p = await _xt(client, minh)
    for r in (await _cap(client, hoa, p["nhap_id"]),
              await client.delete(f"/de-giao/{p['nhap_id']}", headers=hoa.h)):
        assert r.status_code == 404 and r.json()["detail"] == MSG_KHONG_THAY_DE
    assert (await _cap(client, minh, p["nhap_id"])).status_code == 200      # của Minh vẫn nguyên


async def test_kho_tra_thieu_noi_dung_cau_van_cap_ma_duoc_kb4(client):
    """KB 4: rút 12 nhưng kho chỉ trả nội dung 11 -> xem trước 11 câu + "Kho trả thiếu 1 câu so với đề đã rút"."""
    kho = _kho()
    gia = TbGia(kho, bo_qid={kho[2]["qid"]})
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        async with _Ctx(client) as gv:
            p = await _xt(client, gv)
            assert p["so_cau"] == 11 and len(p["cau"]) == 11 and p["du_cau"] is False
            assert "Kho trả thiếu 1 câu so với đề đã rút" in p["thong_bao"]
            assert kho[2]["qid"] not in [c["qid"] for c in p["cau"]]
            assert p["co_the_cap_ma"] is True and "ma" not in p
            d = (await _cap(client, gv, p["nhap_id"])).json()
            assert (d["so_cau"], d["total"]) == (11, 12)
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


async def test_kho_rong_khong_cap_duoc_ma_kb5(client, _model):
    """KB 5: kho không có câu nào -> thông báo, KHÔNG có nhap_id / nút cấp mã, không lưu gì, không gọi LLM."""
    gia = TbGia([], thieu={"B": 5, "H": 4, "V": 3}, thong_bao="Thiếu 12 câu.")
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        async with _Ctx(client) as gv:
            r = await _xem_truoc(client, gv)
            p = r.json()
            assert r.status_code == 200
            assert p["nhap_id"] is None and p["co_the_cap_ma"] is False and p["cau"] == []
            assert MSG_KHO_RONG in p["thong_bao"] and p["so_cau"] == 0
            assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"] == []
            assert _model.await_count == 0
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


@pytest.mark.parametrize("loi,ma", [
    (TestbankLoi("mạng", tam_thoi=True), 503),
    (TestbankLoi("máy chủ 500", tam_thoi=True, ma=500), 503),
    (TestbankLoi("403", tam_thoi=False, ma=403), 502),
])
async def test_testbank_chet_khi_tao_de_giao_bao_loi_tieng_viet_kb6(client, tb, loi, ma):
    """KB 6: testbank lỗi -> thông báo tiếng Việt (không lỗi kỹ thuật thô), không mã, không đề; mã cũ vẫn chạy."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    cu = await _giao(client, gv)               # mã đã cấp trước khi kho chết
    tb.loi = loi
    r = await _xem_truoc(client, gv)
    assert r.status_code == ma
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "Kho đề" in detail
    for tho in ("Traceback", "TESTBANK", "httpx", "Exception", "500"):
        assert tho not in detail
    assert [x["ma"] for x in (await client.get("/de-giao", headers=gv.h)).json()["de_giao"]] == [cu.ma]
    # Đề đã cấp mã vẫn làm bài + nộp bình thường (không gọi kho).
    n = tb.so_lan_goi()
    kho = list(tb.kho.values())
    v = await _vao_ok(client, hs, cu.ma)
    kq = await _nop_ok(client, hs, v["de_id"], _tra_loi(kho, 11))
    assert kq["diem"] == 11 and tb.so_lan_goi() == n


async def test_testbank_chua_cau_hinh_bao_tieng_viet_kb6(client, mocker):
    """KB 6: chưa cấu hình kết nối -> 503 với lời của kho đề dành cho giáo viên (không phải câu của học sinh)."""
    app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)
    mocker.patch("app.api.cuoi_ky.tao_client", side_effect=TestbankChuaCauHinh(["TESTBANK_EMAIL"]))
    gv = await _tk(client, "giao_vien")
    r = await _xem_truoc(client, gv)
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "Kho đề" in detail and "TESTBANK_EMAIL" not in detail
    assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"] == []


async def test_model_sinh_ly_do_chet_van_cap_ma_va_khong_bia_ly_do_kb7(client, tb, _model):
    """KB 7: LLM chết/hết hạn mức -> vẫn có mã, đủ câu; sau khi nộp chỉ có đáp án + lời giải gốc, KHÔNG có lý do bịa."""
    _model.side_effect = LLMUnavailable("hết hạn mức")
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    assert g.xem_truoc["so_cau"] == 12 and g.xem_truoc["du_cau"] is True
    assert all(not c["ly_do"] for c in g.xem_truoc["cau"])
    kq = await _lam(client, hs, g.ma, list(tb.kho.values()), 5)
    assert len(kq["cau"]) == 12
    for c in kq["cau"]:
        assert c["ly_do"] == {}
        assert c["dap_an"] == tb.kho[c["qid"]]["answer_key"] and "Lời giải gốc" in c["giai_html"]


# ═══ KB 8: duy nhất của mã (hàm thuần: tests/exam/test_ma_de.py) ════════════
async def test_ma_trung_thi_sinh_lai_khong_cap_hai_de_cung_ma_kb8(client, tb, mocker):
    """KB 8: unique trong DB; sinh trùng thì sinh lại. Ép `sinh_ma` trả A, A, B -> đề thứ hai nhận B."""
    seq = iter(["AAAAAA", "AAAAAA", "BBBBBB", "CCCCCC", "DDDDDD"])
    gia = lambda: next(seq)  # noqa: E731
    mocker.patch("app.exam.ma_de.sinh_ma", side_effect=gia)
    mocker.patch("app.api.de_giao.sinh_ma", side_effect=gia, create=True)
    hoa, minh = await _tk(client, "giao_vien", "Hoa"), await _tk(client, "giao_vien", "Minh")
    a = await _giao(client, hoa)
    b = await _giao(client, minh)
    assert a.ma == "AAAAAA" and b.ma == "BBBBBB"


async def test_ma_da_dong_khong_bao_gio_cap_lai_kb8(client, tb, mocker):
    """KB 8: mã đã từng cấp (kể cả đã đóng) không được cấp lại cho đề giao khác."""
    seq = iter(["AAAAAA", "AAAAAA", "BBBBBB"])
    gia = lambda: next(seq)  # noqa: E731
    mocker.patch("app.exam.ma_de.sinh_ma", side_effect=gia)
    mocker.patch("app.api.de_giao.sinh_ma", side_effect=gia, create=True)
    gv = await _tk(client, "giao_vien")
    a = await _giao(client, gv)
    assert (await client.post(f"/de-giao/{a.id}/dong", headers=gv.h)).status_code == 200
    b = await _giao(client, gv)
    assert a.ma == "AAAAAA" and b.ma == "BBBBBB"


async def test_nhieu_de_giao_lien_tiep_co_ma_khac_nhau_dung_dinh_dang_kb8(client, tb):
    gv = await _tk(client, "giao_vien", "Hoa")
    ds = [(await _giao(client, gv)).ma for _ in range(8)]
    assert len(set(ds)) == 8
    assert all(re.fullmatch(f"[{BANG}]{{6}}", m) for m in ds)


async def test_de_giao_dong_bang_tai_luc_cap_ma_kb9(client, tb):
    """KB 9: sau khi cấp mã, kho sửa nội dung / đáp án hoặc thêm câu -> học sinh vẫn thấy đúng đề lúc cấp mã,
    chấm theo đáp án lúc cấp mã, và làm bài / nộp bài KHÔNG gọi lại kho."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    q = kho[0]                                   # TN1, đáp án gốc C
    de_html_goc = next(c for c in g.xem_truoc["cau"] if c["qid"] == q["qid"])["de_html"]
    n = tb.so_lan_goi()
    # Kho sửa nội dung + đáp án một câu, thêm câu mới.
    tb.kho[q["qid"]]["stem"] = "ĐỀ ĐÃ BỊ SỬA"
    tb.kho[q["qid"]]["answer_key"] = "A"
    tb.kho["moi"] = _cau("moi", "AR26-TO06-CK1-777", "TN1")

    v = await _vao_ok(client, hs, g.ma)
    assert len(v["cau"]) == 12 and "moi" not in [c["qid"] for c in v["cau"]]
    c0 = next(c for c in v["cau"] if c["qid"] == q["qid"])
    assert c0["de_html"] == de_html_goc and "ĐỀ ĐÃ BỊ SỬA" not in c0["de_html"]
    kq = await _nop_ok(client, hs, v["de_id"], {q["qid"]: "C"})        # C đúng theo đáp án LÚC CẤP MÃ
    k0 = next(c for c in kq["cau"] if c["qid"] == q["qid"])
    assert k0["dung"] is True and k0["dap_an"] == "C"
    assert tb.so_lan_goi() == n, "mở đề / nộp bài theo mã không được gọi lại kho"


# ═══ KB 10: phân quyền giáo viên ════════════════════════════════════════════
_DUONG_GIAO_VIEN = [
    ("POST", "/de-giao/xem-truoc", {"exam": "CK1"}),
    ("POST", f"/de-giao/{ID_KHONG_CO}/cap-ma", None),
    ("DELETE", f"/de-giao/{ID_KHONG_CO}", None),
    ("GET", "/de-giao", None),
    ("GET", f"/de-giao/{ID_KHONG_CO}", None),
    ("GET", f"/de-giao/{ID_KHONG_CO}/ket-qua", None),
    ("GET", f"/de-giao/{ID_KHONG_CO}/bai/1", None),
    ("POST", f"/de-giao/{ID_KHONG_CO}/dong", None),
]


@pytest.mark.parametrize("method,path,body", _DUONG_GIAO_VIEN)
async def test_hoc_sinh_khong_dung_duoc_chuc_nang_giao_vien_kb10_kb36(client, tb, method, path, body):
    """KB 10 + 36: học sinh gọi thẳng máy chủ -> 403 "Bạn không có quyền giao đề", không rút đề, không cấp mã,
    và không thấy gì của lớp (kể cả bảng kết quả / bài của bạn)."""
    hs = await _tk(client)
    r = await client.request(method, path, headers=hs.h, json=body)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == MSG_KHONG_QUYEN
    assert tb.so_lan_goi() == 0


@pytest.mark.parametrize("method,path,body", _DUONG_GIAO_VIEN + [
    ("POST", "/de-giao/vao", {"ma": "K7M3PX"}),
    ("POST", "/de-giao/nop", {"de_id": "x", "tra_loi": {}}),
])
async def test_chua_dang_nhap_bi_tu_choi_kb10(client, tb, method, path, body):
    r = await client.request(method, path, json=body)
    assert r.status_code == 401, r.text
    assert tb.so_lan_goi() == 0


async def test_hoc_sinh_khong_xem_duoc_dap_an_cua_de_giao_dang_mo_kb10(client, tb):
    """Đáp án trong bản xem trước chỉ dành cho người tạo: học sinh có mã vẫn không đọc được `GET /de-giao/{id}`."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    await _vao_ok(client, hs, g.ma)
    r = await client.get(f"/de-giao/{g.id}", headers=hs.h)
    assert r.status_code == 403 and "dap_an" not in r.text and "Lời giải" not in r.text


# ═══ B. Học sinh làm bài theo mã ════════════════════════════════════════════
async def test_nhap_dung_ma_mo_duoc_de_kb11(client):
    """KB 11: thấy đề 12 câu (đề bài, phương án, dữ kiện chung), kỳ, ghi chú "Đề thầy cô giao",
    câu không chấm tự động được ghi rõ trước khi làm."""
    kho = _kho()
    kho[0]["group_id"], kho[1]["group_id"] = "G1", "G1"
    kho[0]["stimulus"], kho[0]["stimulus_lead"] = "Dữ kiện chung của nhóm G1", "Dựa vào dữ kiện trên:"
    gia = TbGia(kho)
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        gv, hs = await _tk(client, "giao_vien"), await _tk(client)
        g = await _giao(client, gv, exam="CK2")
        v = await _vao_ok(client, hs, g.ma)
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)
    assert v["ma"] == g.ma and v["exam"] == "CK2" and v["ghi_chu"] == "Đề thầy cô giao" and v["de_id"]
    assert len(v["cau"]) == 12 and [c["stt"] for c in v["cau"]] == list(range(1, 13))
    assert v["ket_qua"] is None
    assert [p["key"] for p in v["cau"][0]["phuong_an"]] == list("ABCD")
    assert "Dữ kiện chung của nhóm G1" in v["cau"][0]["du_kien_html"] and v["cau"][0]["cau_dan"]
    assert v["cau"][1]["du_kien_html"] == ""          # dữ kiện chung hiện MỘT lần trước câu đầu nhóm
    assert [c["tu_cham"] for c in v["cau"]].count(False) == 1 and v["cau"][-1]["tu_cham"] is False


async def test_hai_hoc_sinh_cung_ma_thay_cung_de_va_khong_goi_kho_kb12(client, tb):
    gv = await _tk(client, "giao_vien")
    g = await _giao(client, gv)
    an, binh = await _tk(client, ten="An"), await _tk(client, ten="Binh")
    n = tb.so_lan_goi()
    a, b = await _vao_ok(client, an, g.ma), await _vao_ok(client, binh, g.ma)
    assert [c["qid"] for c in a["cau"]] == [c["qid"] for c in b["cau"]]
    assert [c["phuong_an"] for c in a["cau"]] == [c["phuong_an"] for c in b["cau"]]
    assert [c["de_html"] for c in a["cau"]] == [c["de_html"] for c in b["cau"]]
    assert a["de_id"] != b["de_id"], "mỗi em một bài làm riêng"
    assert tb.so_lan_goi() == n, "mở đề theo mã không được gọi kho"


async def test_ten_hoc_sinh_kb12_khong_lo_cho_nhau(client, tb):
    """Hai em mở cùng mã: payload của em này không chứa tên / id của em kia."""
    gv = await _tk(client, "giao_vien")
    g = await _giao(client, gv)
    an, binh = await _tk(client, ten="AnTenRiengXyz"), await _tk(client, ten="BinhTenRiengXyz")
    await _vao_ok(client, an, g.ma)
    raw = json.dumps(await _vao_ok(client, binh, g.ma), ensure_ascii=False)
    assert "AnTenRiengXyz" not in raw and an.email not in raw


@pytest.mark.parametrize("go", [" k7m 3px ", "k7m3px", "K7M3PX", "\tk7m\t3PX\n"])
async def test_ma_khong_phan_biet_hoa_thuong_va_bo_khoang_trang_kb13(client, tb, mocker, go):
    mocker.patch("app.exam.ma_de.sinh_ma", return_value="K7M3PX")
    mocker.patch("app.api.de_giao.sinh_ma", return_value="K7M3PX", create=True)
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    assert g.ma == "K7M3PX"
    v = await _vao_ok(client, hs, go)
    assert v["ma"] == "K7M3PX"


@pytest.mark.parametrize("ma", ["K7M3P", "K7M3PXX", "K7M3P0", "K7M3PO", "K7M3P1", "K7M3PI", "K7M3PL",
                                "K7M-3P", "", "   ", "KẸM3PX"])
async def test_ma_sai_dinh_dang_bi_tu_choi_422_kb14(client, tb, ma):
    hs = await _tk(client)
    r = await _vao(client, hs, ma)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == MSG_SAI_DINH_DANG
    assert tb.so_lan_goi() == 0


async def test_ma_dung_dinh_dang_nhung_chua_cap_404_kb14(client, tb):
    hs = await _tk(client)
    r = await _vao(client, hs, "ZZZZZZ")
    assert r.status_code == 404 and r.json()["detail"] == MSG_KHONG_THAY_MA


async def test_ma_dang_nhap_nhung_sai_van_la_khong_tim_thay_khong_phai_nhap_nhang_kb14(client, tb, mocker):
    """Mã khác một ký tự vẫn "không tìm thấy" — không gợi ý mã gần giống."""
    mocker.patch("app.exam.ma_de.sinh_ma", return_value="K7M3PX")
    mocker.patch("app.api.de_giao.sinh_ma", return_value="K7M3PX", create=True)
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    await _giao(client, gv)
    r = await _vao(client, hs, "K7M3PY")
    assert r.status_code == 404 and r.json()["detail"] == MSG_KHONG_THAY_MA


async def test_ma_da_dong_hoc_sinh_chua_tung_lam_khong_vao_duoc_kb15(client, tb):
    gv, chi = await _tk(client, "giao_vien"), await _tk(client, ten="Chi")
    g = await _giao(client, gv)
    assert (await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)).status_code == 200
    r = await _vao(client, chi, g.ma)
    assert r.status_code == 410 and r.json()["detail"] == MSG_DA_DONG
    assert "cau" not in r.json()
    kq = (await _ket_qua(client, gv, g.id)).json()
    assert kq["hoc_sinh"] == [] and kq["tong"]["dang_lam"] == 0       # không để lại bài làm dở


async def test_chan_do_ma_sau_10_lan_sai_trong_10_phut_kb16(client, tb, mocker, kho_dem):
    """KB 16: 10 mã đúng định dạng nhưng không tồn tại -> lần tiếp theo (kể cả mã ĐÚNG) bị chặn 10 phút,
    em khác không bị ảnh hưởng, hết 10 phút thì vào lại được."""
    mocker.patch("app.exam.ma_de.sinh_ma", return_value="K7M3PX")
    mocker.patch("app.api.de_giao.sinh_ma", return_value="K7M3PX", create=True)
    gv = await _tk(client, "giao_vien")
    g = await _giao(client, gv)
    do, khac = await _tk(client, ten="Do"), await _tk(client, ten="Khac")
    sai = [f"ZZZZZ{c}" for c in "23456789AB"]                          # 10 mã hợp lệ, chưa từng cấp
    for m in sai:
        r = await _vao(client, do, m)
        assert r.status_code == 404, f"{m}: {r.text}"
    r = await _vao(client, do, g.ma)                                   # mã ĐÚNG vẫn bị chặn
    assert r.status_code == 429 and r.json()["detail"] == MSG_CHAN_DO
    assert (await _vao(client, do, "ZZZZZZ")).status_code == 429
    # Em khác không bị ảnh hưởng.
    assert (await _vao(client, khac, g.ma)).status_code == 200
    # Em bị chặn không để lại bài làm dở.
    kq = (await _ket_qua(client, gv, g.id)).json()
    assert [h["user_id"] for h in kq["hoc_sinh"]] == [khac.id]
    # Chưa hết 10 phút thì vẫn chặn; hết rồi thì vào được.
    kho_dem.tien(300)
    assert (await _vao(client, do, g.ma)).status_code == 429
    kho_dem.tien(301)
    assert (await _vao(client, do, g.ma)).status_code == 200


async def test_chin_lan_sai_chua_bi_chan_kb16(client, tb, mocker):
    """Biên: 9 lần sai thì mã đúng vẫn vào được (ngưỡng là 10)."""
    mocker.patch("app.exam.ma_de.sinh_ma", return_value="K7M3PX")
    mocker.patch("app.api.de_giao.sinh_ma", return_value="K7M3PX", create=True)
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    for c in "23456789A":
        assert (await _vao(client, hs, f"ZZZZZ{c}")).status_code == 404
    assert (await _vao(client, hs, g.ma)).status_code == 200


async def test_chi_dem_ma_dung_dinh_dang_nhung_khong_ton_tai_kb16(client, tb):
    """Chỉ mã đúng định dạng mà không tồn tại mới tính vào chặn dò: gõ sai định dạng 15 lần,
    hoặc vào mã đã đóng / mã đúng nhiều lần thì không bị chặn."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    for _ in range(15):
        assert (await _vao(client, hs, "K7M3")).status_code == 422
    for _ in range(12):
        assert (await _vao(client, hs, g.ma)).status_code == 200


async def test_dong_ma_roi_vao_lai_khong_tinh_la_do_ma_kb16(client, tb):
    gv, chi, hs = await _tk(client, "giao_vien"), await _tk(client, ten="Chi"), await _tk(client)
    g = await _giao(client, gv)
    await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)
    for _ in range(12):
        assert (await _vao(client, chi, g.ma)).status_code == 410      # đóng chứ không phải "không tồn tại"


async def test_dap_an_khong_lo_xuong_trinh_duyet_truoc_khi_nop_kb17(client, tb):
    """KB 17 (luật bảo mật): mở đề, mở lại đề, nhập lại mã, mở qua lịch sử — payload KHÔNG có đáp án, lời giải,
    lý do từng phương án, và không thông tin nào cho biết phương án nào đúng."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    v1 = await _vao_ok(client, hs, g.ma)
    v2 = await _vao_ok(client, hs, g.ma)                                # nhập lại mã
    v3 = await _vao_ok(client, hs, g.ma.lower())
    ls = (await client.get(f"/exam/cuoi-ky/{v1['de_id']}", headers=hs.h)).json()   # mở qua lịch sử
    lich_su = (await client.get("/exam/cuoi-ky", headers=hs.h)).json()
    for p in (v1, v2, v3, ls, lich_su):
        _khong_lo(p)
    for v in (v1, v2, v3):
        assert v["ket_qua"] is None
        for c in v["cau"]:
            assert set(c) <= KHOA_CAU_CONG_KHAI, set(c) - KHOA_CAU_CONG_KHAI
            for pa in c["phuong_an"]:
                assert set(pa) == {"key", "html"}
    assert v1["de_id"] == v2["de_id"] == v3["de_id"]


async def test_nop_bai_theo_ma_cham_va_hien_ket_qua_kb18(client, session, tb):
    """KB 18: 8/11 câu chấm được (câu bỏ trống tính sai), "1 câu không chấm tự động", Đạt (8/11 >= 70%),
    từng câu có lựa chọn / đúng sai / đáp án / lời giải / lý do, kết quả theo YCCĐ đúng thứ tự ma trận."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    v = await _vao_ok(client, hs, g.ma)
    kq = await _nop_ok(client, hs, v["de_id"], _tra_loi(kho, 8, bo_trong_cau_sai=True))
    assert (kq["diem"], kq["tong"], kq["khong_cham"]) == (8, 11, 1)
    assert kq["dat_yeu_cau"] is True and kq["ma"] == g.ma and kq["de_id"] == v["de_id"]
    assert len(kq["cau"]) == 12
    cham = [c for c in kq["cau"] if c["cham_duoc"]]
    assert len(cham) == 11 and sum(c["dung"] for c in cham) == 8
    bo = [c for c in cham if c["chon"] == ""]
    assert len(bo) == 3 and all(c["dung"] is False for c in bo)       # bỏ trống = sai
    for c in kq["cau"]:
        assert {"chon", "dung", "dap_an", "giai_html", "ly_do", "ar_id", "ycd"} <= set(c)
        assert c["dap_an"] == tb.kho[c["qid"]]["answer_key"]
        assert f"Lời giải gốc {c['qid']}" in c["giai_html"]
    c_tn = next(c for c in kq["cau"] if c["dang"] == "TN1")
    assert set(c_tn["ly_do"]) == set("ABCD")
    assert c_tn["ly_do"]["C"]["dung"] is True and c_tn["ly_do"]["A"]["dung"] is False
    # Theo YCCĐ: đúng thứ tự mã, cộng lại khớp tổng (câu tự luận không vào).
    ids = [y["ar_id"] for y in kq["theo_ycd"]]
    assert ids == sorted(ids)
    assert sum(y["tong"] for y in kq["theo_ycd"]) == 11 and sum(y["dung"] for y in kq["theo_ycd"]) == 8
    assert {"ycd", "dung", "tong"} <= set(kq["theo_ycd"][0])
    assert "goi_y" in kq                                               # khối Đề xuất (US-27) dùng dữ liệu này
    # Ghi lịch sử: một lần nộp + một dòng cho mỗi câu chấm được.
    assert await _dem_lan_nop(session, hs.id) == 1 and await _dem_item(session, hs.id) == 11
    at = await session.scalar(select(QuizAttempt).where(QuizAttempt.user_id == hs.id,
                                                       QuizAttempt.nguon == "de_giao"))
    assert at.topic_id is None and (at.diem, at.tong, at.dat) == (8, 11, True)


async def test_7_tren_11_chua_dat_va_ket_qua_chi_co_sau_khi_nop_kb18(client, tb):
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    kq = await _lam(client, hs, (await _giao(client, gv)).ma, list(tb.kho.values()), 7)
    assert (kq["diem"], kq["tong"], kq["dat_yeu_cau"]) == (7, 11, False)       # 63,6% < 70%


@pytest.mark.parametrize("so_dung,dat", [(7, True), (6, False)])
async def test_nguong_dat_70_phan_tram_dung_bien_kb18(client, so_dung, dat):
    """Ngưỡng đạt "đúng >= 70%": 7/10 là Đạt (đúng bằng ngưỡng), 6/10 chưa đạt."""
    kho = _kho(10, tl=0)
    gia = TbGia(kho)
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        gv, hs = await _tk(client, "giao_vien"), await _tk(client)
        g = await _giao(client, gv, total=10)
        kq = await _lam(client, hs, g.ma, kho, so_dung)
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)
    assert (kq["diem"], kq["tong"], kq["dat_yeu_cau"]) == (so_dung, 10, dat)


async def test_xp_bai_theo_ma_cong_nhu_de_cuoi_ky_g4(client, tb):
    """G4: XP cộng như đề cuối kỳ tự rút: mỗi câu đúng 5, đạt thêm 10."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    xp0 = (await client.get("/me/stats", headers=hs.h)).json()["xp_total"]
    await _lam(client, hs, g.ma, list(tb.kho.values()), 8)
    xp1 = (await client.get("/me/stats", headers=hs.h)).json()["xp_total"]
    assert xp1 - xp0 == 8 * 5 + 10


async def test_nop_de_cua_nguoi_khac_hoac_khong_co_404_kb36(client, tb):
    gv, an, binh = await _tk(client, "giao_vien"), await _tk(client, ten="An"), await _tk(client, ten="Binh")
    g = await _giao(client, gv)
    v_an = await _vao_ok(client, an, g.ma)
    r = await _nop(client, binh, v_an["de_id"], {})
    assert r.status_code == 404
    r = await _nop(client, binh, "khong-co-de-nay", {})
    assert r.status_code == 404
    # Bài của An không bị ghi gì.
    assert (await _vao_ok(client, an, g.ma))["ket_qua"] is None


async def test_nop_bai_roi_nop_lai_thay_lai_ket_qua_lan_dau_kb19(client, session, tb):
    """KB 19: nộp lại hoặc nhập lại mã rồi gửi bộ đáp án khác -> vẫn thấy kết quả lần đầu; không mở lại ở trạng thái
    chưa làm; bảng giáo viên một dòng; thống kê YCCĐ + XP chỉ ghi một lần."""
    gv, an = await _tk(client, "giao_vien"), await _tk(client, ten="An")
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    v = await _vao_ok(client, an, g.ma)
    kq1 = await _nop_ok(client, an, v["de_id"], _tra_loi(kho, 8))
    xp1 = (await client.get("/me/stats", headers=an.h)).json()["xp_total"]
    # Bấm nộp lại với bộ đáp án khác.
    kq2 = await _nop_ok(client, an, v["de_id"], _tra_loi(kho, 0))
    assert kq2 == kq1 and (kq2["diem"], kq2["tong"]) == (8, 11)
    # Nhập lại mã: thấy lại kết quả, KHÔNG mở lại bài trắng.
    v2 = await _vao_ok(client, an, g.ma)
    assert v2["de_id"] == v["de_id"] and v2["ket_qua"] == kq1
    kq3 = await _nop_ok(client, an, v2["de_id"], _tra_loi(kho, 3))
    assert kq3 == kq1
    kq = (await _ket_qua(client, gv, g.id)).json()
    assert len(kq["hoc_sinh"]) == 1 and kq["hoc_sinh"][0]["diem"] == 8
    assert kq["tong"]["da_nop"] == 1
    assert await _dem_lan_nop(session, an.id) == 1 and await _dem_item(session, an.id) == 11
    assert (await client.get("/me/stats", headers=an.h)).json()["xp_total"] == xp1


async def test_nop_nhieu_lan_lien_tiep_chi_ghi_nhan_mot_kb20(client, session, tb):
    """KB 20 (tuần tự — fixture `client` dùng chung MỘT session nên không chạy song song thật được;
    review code phải kiểm khoá hàng `SELECT ... FOR UPDATE` / unique (de_giao_id, user_id) khi nộp):
    ba lần gửi với ba bộ đáp án khác nhau -> một bài nộp, mọi lần trả cùng kết quả."""
    gv, an = await _tk(client, "giao_vien"), await _tk(client, ten="An")
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    v = await _vao_ok(client, an, g.ma)
    kqs = [await _nop_ok(client, an, v["de_id"], _tra_loi(kho, k)) for k in (2, 9, 11)]
    assert kqs[0] == kqs[1] == kqs[2] and kqs[0]["diem"] == 2
    assert await _dem_lan_nop(session, an.id) == 1
    assert (await _ket_qua(client, gv, g.id)).json()["tong"]["da_nop"] == 1


async def test_mo_lai_ma_chua_nop_thay_lai_dung_de_khong_giu_lua_chon_kb21(client, tb):
    """KB 21: bản demo không lưu nháp — mở lại thấy đúng đề (cùng câu, cùng thứ tự), không có lựa chọn cũ."""
    gv, an = await _tk(client, "giao_vien"), await _tk(client, ten="An")
    g = await _giao(client, gv)
    v1 = await _vao_ok(client, an, g.ma)
    v2 = await _vao_ok(client, an, g.ma)
    assert v2["de_id"] == v1["de_id"] and v2["ket_qua"] is None
    assert [c["qid"] for c in v2["cau"]] == [c["qid"] for c in v1["cau"]]
    raw = json.dumps(v2, ensure_ascii=False)
    for cam in ("tra_loi", "chon", "da_chon", "nhap"):
        assert f'"{cam}"' not in raw
    # Mở lại không làm tăng số em "đang làm" (vẫn một dòng).
    kq = (await _ket_qua(client, gv, g.id)).json()
    assert kq["tong"]["dang_lam"] == 1 and len(kq["hoc_sinh"]) == 1


async def test_ket_qua_theo_ma_co_khoi_de_xuat_va_test_them_la_de_rieng_kb22(client, session, tb, mocker):
    """KB 22: màn kết quả có `goi_y` (khối Đề xuất chung, luật chọn ở US-27 — không kiểm lại ở đây);
    "Test thêm" = đề tự rút MỚI của riêng An, tính vào hạn mức rút đề, không thuộc mã, xoá được,
    không đổi bài theo mã."""
    mocker.patch.object(cuoi_ky.settings, "de_cuoi_ky_daily_limit", 1)
    gv, an = await _tk(client, "giao_vien"), await _tk(client, ten="An")
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    kq = await _lam(client, an, g.ma, kho, 3)
    assert kq["goi_y"]["ar_ids"], "có YCCĐ còn yếu thì phải có gợi ý"
    # Mở đề theo mã KHÔNG tính hạn mức rút đề hằng ngày (G5): vừa vào + nộp xong vẫn rút được 1 đề.
    r = await client.post("/exam/cuoi-ky/generate", headers=an.h, json={
        "subject": "TO", "grade": "06", "exam": "CK1", "total": 12, "ar_ids": kq["goi_y"]["ar_ids"]})
    assert r.status_code == 200, r.text
    moi = r.json()
    assert moi["de_id"] and moi["de_id"] != kq["de_id"]
    # ...và Test thêm tính vào hạn mức (đặt giới hạn 1 -> lần hai bị chặn).
    r2 = await client.post("/exam/cuoi-ky/generate", headers=an.h, json={})
    assert r2.status_code == 429
    # Không thuộc mã: bảng giáo viên giữ nguyên.
    b = (await _ket_qua(client, gv, g.id)).json()
    assert b["tong"]["da_nop"] == 1 and len(b["hoc_sinh"]) == 1
    # Lịch sử: đề tự rút không mang nhãn thầy cô giao và xoá được.
    ds = {x["de_id"]: x for x in (await client.get("/exam/cuoi-ky", headers=an.h)).json()["de"]}
    assert ds[moi["de_id"]]["loai"] == "cuoi_ky" and ds[moi["de_id"]]["ma"] is None
    assert ds[moi["de_id"]]["xoa_duoc"] is True
    assert ds[kq["de_id"]]["loai"] == "de_giao"
    assert (await client.delete(f"/exam/cuoi-ky/{moi['de_id']}", headers=an.h)).status_code == 204
    # Bài theo mã giữ nguyên kết quả lần nộp đầu.
    assert (await _vao_ok(client, an, g.ma))["ket_qua"] == kq
    assert await _dem_lan_nop(session, an.id) == 1


async def test_mo_de_theo_ma_khong_tru_han_muc_rut_de_cua_hoc_sinh_g5(client, tb, mocker, kho_dem):
    mocker.patch.object(cuoi_ky.settings, "de_cuoi_ky_daily_limit", 1)
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    for _ in range(3):
        await _vao_ok(client, hs, g.ma)
    assert not any(k.startswith(f"dequota:{hs.id}:") for k in kho_dem.d)
    r = await client.post("/exam/cuoi-ky/generate", headers=hs.h, json={})
    assert r.status_code == 200


# ═══ KB 23 [llm-eval]: hợp đồng sinh lý do (chất lượng đo bằng eval, không ở đây) ════
async def test_ly_do_sinh_mot_lan_luc_tao_de_va_khong_tang_theo_so_hoc_sinh_kb23(client, tb, _model):
    """KB 23 (hợp đồng): lý do từng phương án sinh SẴN lúc tạo đề giao, dùng chung cho mọi học sinh;
    số học sinh làm bài không làm tăng số lần gọi LLM; lúc mở đề / nộp không gọi model."""
    gv = await _tk(client, "giao_vien")
    g = await _giao(client, gv)
    assert _model.await_count >= 1
    n = _model.await_count
    kho = list(tb.kho.values())
    for i in range(3):
        hs = await _tk(client, ten=f"Hs{i}")
        await _lam(client, hs, g.ma, kho, 5)
    assert _model.await_count == n


async def test_ly_do_bam_dap_an_cua_kho_khong_de_model_quyet_dung_sai_kb23(client, tb, _model):
    """KB 23: phương án đúng/sai do KHO quyết (`answer_key`), model chỉ viết lý do; prompt mang đáp án + lời
    giải gốc; mô hình trả lý do lộn xộn cũng không đổi nhãn đúng/sai."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    prompt = json.dumps(_model.await_args_list[0].args + tuple(_model.await_args_list[0].kwargs.values()),
                        ensure_ascii=False, default=str)
    assert "Lời giải gốc" in prompt and "ĐÚNG" in prompt and "SAI" in prompt
    kq = await _lam(client, hs, g.ma, list(tb.kho.values()), 11)
    for c in kq["cau"]:
        if c["dang"] in ("TN1", "TNN", "DS"):
            dung = {k: v["dung"] for k, v in c["ly_do"].items()}
            if c["dang"] == "TN1":
                assert dung == {"A": False, "B": False, "C": True, "D": False}
            elif c["dang"] == "TNN":
                assert dung == {"A": True, "B": False, "C": True, "D": False}
            else:
                assert dung == {"A": True, "B": False, "C": True, "D": False}


async def test_cau_co_hinh_khong_duoc_sinh_ly_do_kb23(client, _model):
    """KB 23: câu có hình trong đề bài hoặc phương án -> KHÔNG sinh lý do (không gọi model, `ly_do` rỗng)."""
    anh = "3f2a" + "0" * 26 + "e9"
    kho = [_cau("hinh-1", "AR26-TO06-CK1-001", "TN1", stem=f"Cho hình [[anh:{anh}]] ?",
                assets={anh: "/api/content/media/3f/2a/x.png"}),
           _cau("hinh-2", "AR26-TO06-CK1-001", "TN1",
                options=[{"key": "A", "text": f"[[anh:{anh}]]"}, {"key": "B", "text": "3"}],
                assets={anh: "/api/content/media/3f/2a/x.png"})]
    gia = TbGia(kho)
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        async with _Ctx(client) as gv:
            p = await _xt(client, gv, total=2)
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)
    assert _model.await_count == 0
    assert all(c["ly_do"] == {} for c in p["cau"])


async def test_ly_do_dung_lai_cache_theo_cau_cua_de_cuoi_ky_kb23(client, tb, _model):
    """Chi phí LLM (mục 4): dùng lại cache theo câu đã có -> rút lại đúng bộ câu đó thì không gọi model nữa."""
    gv = await _tk(client, "giao_vien")
    await _xt(client, gv)
    n = _model.await_count
    assert n >= 1
    await _xt(client, gv)
    assert _model.await_count == n


# ═══ C. Lịch sử làm bài của học sinh ═════════════════════════════════════════
async def _hs_co_ba_bai(client, tb):
    """An có 2 bài cuối kỳ tự rút (1 đã nộp) + 1 bài theo mã đã nộp."""
    gv, an = await _tk(client, "giao_vien"), await _tk(client, ten="An")
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    kq = await _lam(client, an, g.ma, kho, 8)
    r1 = (await client.post("/exam/cuoi-ky/generate", headers=an.h, json={})).json()
    r2 = (await client.post("/exam/cuoi-ky/generate", headers=an.h, json={})).json()
    await client.post("/exam/cuoi-ky/submit", headers=an.h, json={"de_id": r1["de_id"], "tra_loi": {}})
    return gv, an, g, kq, r1["de_id"], r2["de_id"]


async def test_bai_theo_ma_hien_trong_lich_su_va_khong_xoa_duoc_kb24(client, tb):
    gv, an, g, kq, d1, d2 = await _hs_co_ba_bai(client, tb)
    ds = (await client.get("/exam/cuoi-ky", headers=an.h)).json()["de"]
    assert len(ds) == 3
    theo_id = {x["de_id"]: x for x in ds}
    bai_ma = theo_id[kq["de_id"]]
    assert bai_ma["loai"] == "de_giao" and bai_ma["ma"] == g.ma and bai_ma["xoa_duoc"] is False
    assert bai_ma["da_nop"] is True and (bai_ma["diem"], bai_ma["tong"]) == (8, 11)
    for d in (d1, d2):
        assert theo_id[d]["loai"] == "cuoi_ky" and theo_id[d]["ma"] is None and theo_id[d]["xoa_duoc"] is True
    # Mở lại được kết quả bài theo mã.
    mo = (await client.get(f"/exam/cuoi-ky/{kq['de_id']}", headers=an.h)).json()
    assert mo["ket_qua"] == kq
    # Xoá riêng bài theo mã: bị từ chối, bài vẫn còn (lịch sử + bảng giáo viên).
    r = await client.delete(f"/exam/cuoi-ky/{kq['de_id']}", headers=an.h)
    assert r.status_code == 403 and r.json()["detail"] == MSG_KHONG_XOA
    assert len((await client.get("/exam/cuoi-ky", headers=an.h)).json()["de"]) == 3
    b = (await _ket_qua(client, gv, g.id)).json()
    assert b["hoc_sinh"][0]["diem"] == 8 and b["tong"]["da_nop"] == 1


async def test_xoa_tat_ca_lich_su_giu_bai_theo_ma_kb25(client, session, tb):
    gv, an, g, kq, d1, d2 = await _hs_co_ba_bai(client, tb)
    r = await client.delete("/exam/cuoi-ky", headers=an.h)
    assert r.status_code == 200 and r.json()["da_xoa"] == 2
    ds = (await client.get("/exam/cuoi-ky", headers=an.h)).json()["de"]
    assert [x["de_id"] for x in ds] == [kq["de_id"]]
    # Còn trong thống kê YCCĐ của An và trong bảng kết quả của giáo viên.
    assert await _dem_lan_nop(session, an.id) == 1 and await _dem_item(session, an.id) == 11
    thong_ke = await ycd_tk_svc.theo_ycd(session, an.id)
    assert sum(t.tong for t in thong_ke) == 11
    b = (await _ket_qua(client, gv, g.id)).json()
    assert b["tong"]["da_nop"] == 1 and b["hoc_sinh"][0]["diem"] == 8


async def test_xoa_tat_ca_khi_chi_co_bai_theo_ma_xoa_0_bai_kb25(client, tb):
    gv, an = await _tk(client, "giao_vien"), await _tk(client, ten="An")
    g = await _giao(client, gv)
    await _lam(client, an, g.ma, list(tb.kho.values()), 8)
    assert (await client.delete("/exam/cuoi-ky", headers=an.h)).json()["da_xoa"] == 0
    assert (await client.delete("/exam/cuoi-ky?exam=CK1", headers=an.h)).json()["da_xoa"] == 0
    assert len((await client.get("/exam/cuoi-ky", headers=an.h)).json()["de"]) == 1


async def test_hoc_sinh_khac_khong_mo_hay_xoa_bai_theo_ma_cua_ban_kb36(client, tb):
    gv, an, binh = await _tk(client, "giao_vien"), await _tk(client, ten="An"), await _tk(client, ten="Binh")
    g = await _giao(client, gv)
    kq_binh = await _lam(client, binh, g.ma, list(tb.kho.values()), 9)
    assert (await client.get(f"/exam/cuoi-ky/{kq_binh['de_id']}", headers=an.h)).status_code == 404
    assert (await client.delete(f"/exam/cuoi-ky/{kq_binh['de_id']}", headers=an.h)).status_code == 404
    assert (await client.get("/exam/cuoi-ky", headers=an.h)).json()["de"] == []


async def test_bai_theo_ma_vao_thong_ke_ycd_va_trang_cms_kb26(client, session, tb):
    """KB 26: lần nộp theo mã tính vào thống kê YCCĐ như đề cuối kỳ (để chọn YCCĐ yếu cho Test thêm),
    và trang kết quả học sinh trên CMS hiện nhãn "Đề giao · mã <MÃ>" — không lẫn vào số liệu Kiểm tra nhanh."""
    gv, an = await _tk(client, "giao_vien"), await _tk(client, ten="An")
    ad = await _tk(client, "admin", "Quan tri")
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    await _lam(client, an, g.ma, kho, 3)
    tk = await ycd_tk_svc.theo_ycd(session, an.id, gan_day=5)
    assert sum(t.tong for t in tk) == 11 and sum(t.dung for t in tk) == 3
    r = await client.get(f"/admin/users/{an.id}/result", headers=ad.h)
    assert r.status_code == 200, r.text
    b = r.json()
    lan = [x for x in b["lan"] if x["nguon"] == "de_giao"]
    assert len(lan) == 1 and lan[0]["ten"] == f"Đề giao · mã {g.ma}"
    assert (lan[0]["diem"], lan[0]["tong"]) == (3, 11)
    assert b["tong_lan_de_giao"] == 1
    assert b["tong_lan"] == 0 and b["so_lan_dat"] == 0
    assert b["tong_lan_cuoi_ky"] == 0
    # Giáo viên (vai tác giả) cũng mở được trang này như với đề cuối kỳ.
    assert (await client.get(f"/admin/users/{an.id}/result", headers=gv.h)).status_code == 200


# ═══ D. Giáo viên xem kết quả và đóng mã ════════════════════════════════════
async def test_danh_sach_de_giao_cua_toi_kb27(client, tb):
    """KB 27: Hoa 3 đề, Minh 2 đề -> Hoa thấy đúng 3 của mình, mới tạo trước, đủ cột; không thấy của Minh."""
    hoa, minh = await _tk(client, "giao_vien", "Hoa"), await _tk(client, "giao_vien", "Minh")
    a, b, c = [await _giao(client, hoa) for _ in range(3)]
    for _ in range(2):
        await _giao(client, minh)
    hs1, hs2 = await _tk(client), await _tk(client)
    await _lam(client, hs1, a.ma, list(tb.kho.values()), 8)
    await _vao_ok(client, hs2, a.ma)
    ds = (await client.get("/de-giao", headers=hoa.h)).json()["de_giao"]
    assert [x["ma"] for x in ds] == [c.ma, b.ma, a.ma]                 # mới tạo trước
    assert {"id", "ma", "exam", "so_cau", "total", "created_at", "trang_thai", "dong_luc",
            "so_da_nop", "so_dang_lam", "nguoi_tao"} <= set(ds[0])
    cu = ds[-1]
    assert cu["trang_thai"] == "mo" and cu["dong_luc"] is None and cu["exam"] == "CK1"
    assert (cu["so_cau"], cu["total"]) == (12, 12)
    assert (cu["so_da_nop"], cu["so_dang_lam"]) == (1, 1)
    assert (ds[0]["so_da_nop"], ds[0]["so_dang_lam"]) == (0, 0)
    ma_minh = {x["ma"] for x in (await client.get("/de-giao", headers=minh.h)).json()["de_giao"]}
    assert len(ma_minh) == 2 and not ma_minh & {a.ma, b.ma, c.ma}


async def test_bang_ket_qua_mot_ma_kb28(client, tb):
    """KB 28: 3 dòng xếp tên A->Z; An/Bình có điểm + Đạt/Chưa đạt theo 70% + thời điểm nộp; Chi "đang làm"
    không điểm; đầu bảng có tổng; em chưa nhập mã không xuất hiện."""
    gv = await _tk(client, "giao_vien")
    chi = await _tk(client, ten="Chi")
    binh = await _tk(client, ten="Binh")
    an = await _tk(client, ten="An")
    chua_vao = await _tk(client, ten="Dung")
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    await _lam(client, binh, g.ma, kho, 5)           # nộp trước (để chứng tỏ xếp theo tên, không theo giờ nộp)
    await _lam(client, an, g.ma, kho, 9)
    await _vao_ok(client, chi, g.ma)
    r = await _ket_qua(client, gv, g.id)
    assert r.status_code == 200, r.text
    b = r.json()
    assert [h["ten"] for h in b["hoc_sinh"]] == ["An", "Binh", "Chi"]
    assert b["tong"] == {"da_nop": 2, "dat": 1, "dang_lam": 1}
    h_an, h_binh, h_chi = b["hoc_sinh"]
    assert (h_an["trang_thai"], h_an["diem"], h_an["tong"], h_an["dat"]) == ("da_nop", 9, 11, True)
    assert (h_binh["trang_thai"], h_binh["diem"], h_binh["tong"], h_binh["dat"]) == ("da_nop", 5, 11, False)
    assert h_an["nop_luc"] and h_binh["nop_luc"] and h_an["user_id"] == an.id
    assert h_chi["trang_thai"] == "dang_lam"
    assert h_chi["diem"] is None and h_chi["tong"] is None and h_chi["dat"] is None and h_chi["nop_luc"] is None
    assert chua_vao.id not in [h["user_id"] for h in b["hoc_sinh"]]


async def test_ket_qua_theo_ycd_cua_ca_ma_kb29(client):
    """KB 29: mỗi YCCĐ một dòng theo thứ tự mã; "số em đúng hết các câu của YCCĐ / số em đã nộp"; tỉ lệ đúng
    tính trên TỔNG LƯỢT trả lời; câu không chấm tự động và em đang làm không tính."""
    ycd1, ycd2 = "Nhận biết được khái niệm A.", "Xác định được điều B."
    kho = [_cau("k29-1", "AR26-TO06-CK1-001", "TN1", yccd=ycd1),
           _cau("k29-2", "AR26-TO06-CK1-001", "TN1", yccd=ycd1),
           _cau("k29-3", "AR26-TO06-CK1-002", "TN1", yccd=ycd2),
           _cau("k29-4", "AR26-TO06-CK1-009", "TL", yccd="Viết được bài luận.")]
    gia = TbGia(kho)
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        gv = await _tk(client, "giao_vien")
        g = await _giao(client, gv, total=4)
        tat_ca = {"k29-1": "C", "k29-2": "C", "k29-3": "C"}
        s1, s2, s3, s4 = [await _tk(client, ten=f"Hs{i}") for i in range(4)]
        await _lam_tu_do(client, s1, g.ma, tat_ca)
        await _lam_tu_do(client, s2, g.ma, {**tat_ca, "k29-2": "A"})
        await _lam_tu_do(client, s3, g.ma, {"k29-1": "A", "k29-2": "A", "k29-3": "A"})
        await _vao_ok(client, s4, g.ma)                                  # đang làm: không tính
        b = (await _ket_qua(client, gv, g.id)).json()
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)
    ty = b["theo_ycd"]
    assert [y["ar_id"] for y in ty] == ["AR26-TO06-CK1-001", "AR26-TO06-CK1-002"]   # không có câu tự luận
    y1, y2 = ty
    assert y1["ycd"] == ycd1 and y2["ycd"] == ycd2                       # nguyên văn
    assert (y1["so_hs_dung_het"], y1["so_hs_da_nop"]) == (1, 3) and _ti(y1["ti_le_dung"], 3 / 6)
    assert (y2["so_hs_dung_het"], y2["so_hs_da_nop"]) == (2, 3) and _ti(y2["ti_le_dung"], 2 / 3)
    assert b["tong"]["da_nop"] == 3 and b["tong"]["dang_lam"] == 1


async def _lam_tu_do(client, hs, ma, tra_loi) -> dict:
    v = await _vao_ok(client, hs, ma)
    return await _nop_ok(client, hs, v["de_id"], tra_loi)


async def test_xem_chi_tiet_bai_cua_tung_em_kb30(client, tb):
    gv = await _tk(client, "giao_vien")
    an, chi = await _tk(client, ten="An"), await _tk(client, ten="Chi")
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    await _lam(client, an, g.ma, kho, 8)
    await _vao_ok(client, chi, g.ma)
    r = await client.get(f"/de-giao/{g.id}/bai/{an.id}", headers=gv.h)
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["diem"], b["tong"]) == (8, 11) and len(b["cau"]) == 12
    for c in b["cau"]:
        assert {"chon", "dung", "dap_an", "giai_html"} <= set(c)
    assert b["theo_ycd"] and sum(y["dung"] for y in b["theo_ycd"]) == 8
    # Chi đang làm: chỉ "Em chưa nộp bài", không lộ lựa chọn nào.
    r = await client.get(f"/de-giao/{g.id}/bai/{chi.id}", headers=gv.h)
    assert r.status_code == 200
    assert r.json() == {"da_nop": False, "thong_bao": "Em chưa nộp bài"}


async def test_bang_ket_qua_khi_chua_ai_lam_kb31(client, tb):
    gv = await _tk(client, "giao_vien")
    g = await _giao(client, gv)
    r = await _ket_qua(client, gv, g.id)
    assert r.status_code == 200
    b = r.json()
    assert b["hoc_sinh"] == [] and b["theo_ycd"] == []
    assert (b["tong"]["da_nop"], b["tong"]["dang_lam"]) == (0, 0)


async def test_giao_vien_xem_lai_de_kem_dap_an_khong_tao_bai_lam_kb32(client, tb):
    """KB 32: người tạo xem đúng bộ câu học sinh sẽ làm (cùng thứ tự) kèm đáp án + lời giải; thao tác này không
    tạo bài làm và người tạo không xuất hiện trong bảng kết quả."""
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    r = await client.get(f"/de-giao/{g.id}", headers=gv.h)
    assert r.status_code == 200, r.text
    d = r.json()
    v = await _vao_ok(client, hs, g.ma)
    assert [c["qid"] for c in d["cau"]] == [c["qid"] for c in v["cau"]]
    for c in d["cau"]:
        assert c["dap_an"] == tb.kho[c["qid"]]["answer_key"] and "Lời giải gốc" in c["giai_html"]
    kq = (await _ket_qua(client, gv, g.id)).json()
    assert [h["user_id"] for h in kq["hoc_sinh"]] == [hs.id] and gv.id not in [h["user_id"] for h in kq["hoc_sinh"]]
    assert kq["tong"]["dang_lam"] == 1


async def test_dong_ma_kb33(client, tb):
    """KB 33: đóng -> "Đã đóng" kèm thời điểm; em chưa mở không vào được; em đã nộp vẫn xem kết quả, nhập lại mã
    thấy kết quả của mình; bảng giáo viên đầy đủ; không mở lại được; đóng lần nữa không đổi gì."""
    gv = await _tk(client, "giao_vien")
    an, chi = await _tk(client, ten="An"), await _tk(client, ten="Chi")
    g = await _giao(client, gv)
    kq_an = await _lam(client, an, g.ma, list(tb.kho.values()), 8)

    r = await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["trang_thai"] == "dong" and d["dong_luc"]
    row = (await client.get("/de-giao", headers=gv.h)).json()["de_giao"][0]
    assert row["trang_thai"] == "dong" and row["dong_luc"] == d["dong_luc"]

    r = await _vao(client, chi, g.ma)
    assert r.status_code == 410 and r.json()["detail"] == MSG_DA_DONG
    v = await _vao_ok(client, an, g.ma)                                # An nhập lại mã vẫn thấy kết quả
    assert v["ket_qua"] == kq_an
    ls = (await client.get("/exam/cuoi-ky", headers=an.h)).json()["de"]
    assert [x["de_id"] for x in ls] == [kq_an["de_id"]]
    assert (await client.get(f"/exam/cuoi-ky/{kq_an['de_id']}", headers=an.h)).json()["ket_qua"] == kq_an
    b = (await _ket_qua(client, gv, g.id)).json()
    assert b["tong"]["da_nop"] == 1 and b["hoc_sinh"][0]["diem"] == 8

    # Đóng lần nữa: không đổi gì (giữ thời điểm đóng cũ).
    r2 = await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)
    assert r2.status_code == 200 and r2.json() == d


@pytest.mark.parametrize("method,duong", [("POST", "mo"), ("POST", "mo-lai"), ("PUT", "mo"), ("PATCH", "")])
async def test_ma_da_dong_khong_co_duong_mo_lai_kb33(client, tb, method, duong):
    gv = await _tk(client, "giao_vien")
    g = await _giao(client, gv)
    await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)
    r = await client.request(method, f"/de-giao/{g.id}/{duong}".rstrip("/"), headers=gv.h,
                             json={"trang_thai": "mo"})
    assert r.status_code in (404, 405, 422), r.text
    assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"][0]["trang_thai"] == "dong"


async def test_bai_dang_lam_do_khi_dong_ma_bi_tu_choi_khi_nop_kb34(client, session, tb):
    """KB 34: Chi đang làm, giáo viên đóng, Chi nộp -> từ chối; không điểm, không ghi thống kê YCCĐ;
    bảng ghi "Chưa nộp (mã đã đóng)"; bài đã nộp trọn vẹn trước đó vẫn tính."""
    gv = await _tk(client, "giao_vien")
    an, chi = await _tk(client, ten="An"), await _tk(client, ten="Chi")
    kho = list(tb.kho.values())
    g = await _giao(client, gv)
    await _lam(client, an, g.ma, kho, 8)                              # nộp TRƯỚC khi đóng
    v_chi = await _vao_ok(client, chi, g.ma)
    await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)
    r = await _nop(client, chi, v_chi["de_id"], _tra_loi(kho, 11))
    assert r.status_code == 409 and r.json()["detail"] == MSG_NOP_SAU_DONG
    assert await _dem_lan_nop(session, chi.id) == 0 and await _dem_item(session, chi.id) == 0
    b = (await _ket_qua(client, gv, g.id)).json()
    dong_chi = next(h for h in b["hoc_sinh"] if h["user_id"] == chi.id)
    assert dong_chi["trang_thai"] == "chua_nop_ma_dong" and dong_chi["diem"] is None
    assert b["tong"]["da_nop"] == 1                                    # An vẫn tính bình thường
    # Chi nhập lại mã sau khi đóng: chưa nộp -> không vào được.
    r = await _vao(client, chi, g.ma)
    assert r.status_code == 410 and r.json()["detail"] == MSG_DA_DONG


async def test_nop_roi_moi_dong_thi_van_tinh_kb34(client, session, tb):
    gv, an = await _tk(client, "giao_vien"), await _tk(client, ten="An")
    g = await _giao(client, gv)
    kq = await _lam(client, an, g.ma, list(tb.kho.values()), 8)
    await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)
    kq2 = await _nop(client, an, kq["de_id"], {})                      # nộp lại sau đóng: vẫn là kết quả đã ghi
    assert kq2.status_code == 200 and kq2.json() == kq
    assert await _dem_lan_nop(session, an.id) == 1


_THAO_TAC_CUA_NGUOI_TAO = [
    ("GET", "{id}", None), ("GET", "{id}/ket-qua", None), ("GET", "{id}/bai/{uid}", None),
    ("POST", "{id}/dong", None),
]


@pytest.mark.parametrize("method,mau,body", _THAO_TAC_CUA_NGUOI_TAO)
async def test_giao_vien_khac_khong_xem_hay_dong_de_giao_cua_nguoi_ta_kb35(client, tb, method, mau, body):
    """KB 35: Hoa mở / xem kết quả / xem bài / đóng mã của Minh -> 404 "Không tìm thấy đề giao này",
    GIỐNG HỆT khi mã không tồn tại (không lộ sự tồn tại), và trạng thái mã không đổi."""
    hoa, minh, hs = await _tk(client, "giao_vien", "Hoa"), await _tk(client, "giao_vien", "Minh"), await _tk(client)
    g = await _giao(client, minh)
    await _lam(client, hs, g.ma, list(tb.kho.values()), 8)
    duong = "/de-giao/" + mau.format(id=g.id, uid=hs.id)
    r = await client.request(method, duong, headers=hoa.h, json=body)
    assert r.status_code == 404 and r.json()["detail"] == MSG_KHONG_THAY_DE
    # Cùng thông báo & mã như đề không tồn tại.
    r0 = await client.request(method, "/de-giao/" + mau.format(id=ID_KHONG_CO, uid=hs.id),
                              headers=hoa.h, json=body)
    assert (r0.status_code, r0.json()) == (r.status_code, r.json())
    row = (await client.get("/de-giao", headers=minh.h)).json()["de_giao"][0]
    assert row["trang_thai"] == "mo"
    assert (await client.get("/de-giao", headers=hoa.h)).json()["de_giao"] == []


async def test_admin_lam_duoc_nhu_nguoi_tao_va_thay_moi_de_giao_kb35(client, tb):
    hoa, minh = await _tk(client, "giao_vien", "HoaGv"), await _tk(client, "giao_vien", "MinhGv")
    ad, hs = await _tk(client, "admin", "QuanTri"), await _tk(client)
    a, b = await _giao(client, hoa), await _giao(client, minh)
    await _lam(client, hs, b.ma, list(tb.kho.values()), 8)
    kq = await _ket_qua(client, ad, b.id)
    assert kq.status_code == 200 and kq.json()["tong"]["da_nop"] == 1
    assert (await client.get(f"/de-giao/{b.id}/bai/{hs.id}", headers=ad.h)).status_code == 200
    assert (await client.get(f"/de-giao/{b.id}", headers=ad.h)).status_code == 200
    r = await client.post(f"/de-giao/{b.id}/dong", headers=ad.h)
    assert r.status_code == 200 and r.json()["trang_thai"] == "dong"
    ds = {x["id"]: x for x in (await client.get("/de-giao", headers=ad.h)).json()["de_giao"]}
    assert {a.id, b.id} <= set(ds)
    assert "HoaGv" in json.dumps(ds[a.id]["nguoi_tao"], ensure_ascii=False)
    assert "MinhGv" in json.dumps(ds[b.id]["nguoi_tao"], ensure_ascii=False)
    # Giáo viên thường không thấy cột của người khác.
    assert b.id not in {x["id"] for x in (await client.get("/de-giao", headers=hoa.h)).json()["de_giao"]}


async def test_hoc_sinh_khong_xem_ket_qua_cua_ban_kb36(client, tb):
    """KB 36: An (có mã, đã nộp) cố mở bảng kết quả / bài của Bình qua máy chủ -> bị từ chối, không lộ tên, điểm, lựa chọn."""
    gv = await _tk(client, "giao_vien")
    an, binh = await _tk(client, ten="An"), await _tk(client, ten="BinhBiMat")
    g = await _giao(client, gv)
    kho = list(tb.kho.values())
    await _lam(client, an, g.ma, kho, 5)
    await _lam(client, binh, g.ma, kho, 9)
    for duong in (f"/de-giao/{g.id}/ket-qua", f"/de-giao/{g.id}/bai/{binh.id}", f"/de-giao/{g.id}/bai/{an.id}",
                  f"/de-giao/{g.id}"):
        r = await client.get(duong, headers=an.h)
        assert r.status_code == 403, f"{duong}: {r.status_code}"
        assert "BinhBiMat" not in r.text and binh.email not in r.text
    r = await client.post(f"/de-giao/{g.id}/dong", headers=an.h)
    assert r.status_code == 403
    assert (await client.get("/de-giao", headers=gv.h)).json()["de_giao"][0]["trang_thai"] == "mo"


# ═══ E. Hạn mức 20 đề giao / ngày / giáo viên ════════════════════════════════
async def test_han_muc_mac_dinh_la_20_de_giao_moi_ngay():
    assert settings.de_giao_daily_limit == 20


async def test_het_han_muc_20_de_giao_trong_ngay_gio_viet_nam_kb37(client, tb, _model, mocker):
    """KB 37 (mặc định 20 thật): đề thứ 21 trong ngày VN -> 429 đúng chữ, không rút đề, không gọi kho,
    không gọi LLM, không cấp mã; mã cũ vẫn dùng; giáo viên khác không bị ảnh hưởng; sang ngày VN hôm sau tạo
    được; admin không giới hạn."""
    _dong_ho(mocker, "2026-10-20T16:59:00")                  # 23:59 giờ VN ngày 20/10 (UTC vẫn là 20/10)
    hoa, minh = await _tk(client, "giao_vien", "Hoa"), await _tk(client, "giao_vien", "Minh")
    hs = await _tk(client)
    dau = await _giao(client, hoa)                           # đề giao thứ 1
    for _ in range(19):
        await _xt(client, hoa)                               # 19 bản xem trước nữa (huỷ/để nháp đều tính)
    n_tb, n_llm = tb.so_lan_goi(), _model.await_count

    r = await _xem_truoc(client, hoa)
    assert r.status_code == 429, r.text
    assert r.json()["detail"] == "Hôm nay thầy cô đã tạo 20 đề giao, ngày mai tạo tiếp được nhé"
    assert tb.so_lan_goi() == n_tb and _model.await_count == n_llm
    assert len((await client.get("/de-giao", headers=hoa.h)).json()["de_giao"]) == 1
    # Mã đã cấp vẫn làm bài, xem kết quả, đóng bình thường.
    await _lam(client, hs, dau.ma, list(tb.kho.values()), 8)
    assert (await _ket_qua(client, hoa, dau.id)).json()["tong"]["da_nop"] == 1
    assert (await client.post(f"/de-giao/{dau.id}/dong", headers=hoa.h)).status_code == 200
    # Hạn mức tính riêng từng giáo viên.
    assert (await _xem_truoc(client, minh)).status_code == 200
    # Qua nửa đêm giờ VN (00:01 ngày 21/10 = 17:01 UTC ngày 20/10) -> tạo được lại.
    _dong_ho(mocker, "2026-10-20T17:01:00")
    assert (await _xem_truoc(client, hoa)).status_code == 200


async def test_han_muc_ngay_tinh_theo_gio_viet_nam_khong_phai_utc_kb37(client, tb, mocker):
    """Ranh giới ngày phải là 00:00 GIỜ VIỆT NAM: 17:01 UTC (đã sang ngày mới ở VN) mở lại hạn mức;
    tính theo UTC thì còn bị chặn tới 00:00 UTC (07:00 sáng VN)."""
    _dat_gioi_han(mocker, 2)
    _dong_ho(mocker, "2026-10-20T16:30:00")
    gv = await _tk(client, "giao_vien")
    assert (await _xem_truoc(client, gv)).status_code == 200
    assert (await _xem_truoc(client, gv)).status_code == 200
    assert (await _xem_truoc(client, gv)).status_code == 429
    _dong_ho(mocker, "2026-10-20T17:30:00")                   # 00:30 ngày 21/10 giờ VN
    assert (await _xem_truoc(client, gv)).status_code == 200
    _dong_ho(mocker, "2026-10-20T16:30:00")                   # (đồng hồ quay lại ngày 20: vẫn đã hết)
    assert (await _xem_truoc(client, gv)).status_code == 429


async def test_ban_xem_truoc_da_huy_van_tinh_vao_han_muc_kb37(client, tb, mocker):
    _dat_gioi_han(mocker, 2)
    gv = await _tk(client, "giao_vien")
    for _ in range(2):
        p = await _xt(client, gv)
        assert (await client.delete(f"/de-giao/{p['nhap_id']}", headers=gv.h)).status_code == 204
    r = await _xem_truoc(client, gv)
    assert r.status_code == 429 and MSG_HET_HAN_MUC_DUOI in r.json()["detail"]


async def test_lan_rut_that_bai_vi_kho_loi_khong_tinh_han_muc_kb37(client, tb, mocker):
    _dat_gioi_han(mocker, 2)
    gv = await _tk(client, "giao_vien")
    tb.loi = TestbankLoi("mạng", tam_thoi=True)
    for _ in range(5):
        assert (await _xem_truoc(client, gv)).status_code == 503
    tb.loi = None
    assert (await _xem_truoc(client, gv)).status_code == 200
    assert (await _xem_truoc(client, gv)).status_code == 200
    assert (await _xem_truoc(client, gv)).status_code == 429


async def test_kho_rong_khong_tinh_han_muc_kb37(client, mocker):
    """Hợp đồng: tính mỗi lần rút được >= 1 câu; kho rỗng không tính."""
    _dat_gioi_han(mocker, 1)
    gia = TbGia([], thieu={"B": 1}, thong_bao="Thiếu.")
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        async with _Ctx(client) as gv:
            for _ in range(3):
                assert (await _xem_truoc(client, gv)).json()["co_the_cap_ma"] is False
            gia.kho = {c["qid"]: c for c in _kho()}
            gia.thieu = None
            assert (await _xem_truoc(client, gv)).status_code == 200
            assert (await _xem_truoc(client, gv)).status_code == 429
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


async def test_tham_so_sai_khong_tinh_han_muc_kb37(client, tb, mocker):
    _dat_gioi_han(mocker, 1)
    gv = await _tk(client, "giao_vien")
    assert (await _xem_truoc(client, gv, total=0)).status_code == 422
    assert (await _xem_truoc(client, gv, exam="GK1")).status_code == 422
    assert (await _xem_truoc(client, gv)).status_code == 200


async def test_het_han_muc_khong_goi_kho_khong_goi_llm_va_han_muc_theo_tung_giao_vien_kb37(client, tb, _model, mocker):
    _dat_gioi_han(mocker, 1)
    hoa, minh = await _tk(client, "giao_vien", "Hoa"), await _tk(client, "giao_vien", "Minh")
    await _xt(client, hoa)
    n_tb, n_llm = tb.so_lan_goi(), _model.await_count
    r = await _xem_truoc(client, hoa)
    assert r.status_code == 429 and MSG_HET_HAN_MUC_DUOI in r.json()["detail"]
    assert tb.so_lan_goi() == n_tb and _model.await_count == n_llm
    assert (await _xem_truoc(client, minh)).status_code == 200


async def test_admin_khong_bi_gioi_han_han_muc_kb37(client, tb, mocker):
    _dat_gioi_han(mocker, 2)
    ad = await _tk(client, "admin", "QuanTri")
    for _ in range(5):
        assert (await _xem_truoc(client, ad)).status_code == 200


async def test_redis_loi_thi_cho_qua_khong_chan_giao_vien_kb37(client, tb, mocker):
    """Cùng luật với hạn mức đề cuối kỳ: bộ đếm lỗi -> fail-open, không chặn giáo viên vì hạ tầng phụ."""
    mocker.patch.object(llm_cache, "incr_quota", side_effect=ConnectionError("redis chết"))
    gv = await _tk(client, "giao_vien")
    assert (await _xem_truoc(client, gv)).status_code == 200


async def test_redis_loi_thi_khong_chan_do_ma_va_van_vao_duoc_kb16(client, tb, mocker):
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    for ten in ("incr_quota", "get", "set", "giam_quota"):
        mocker.patch.object(llm_cache, ten, side_effect=ConnectionError("redis chết"))
    assert (await _vao(client, hs, g.ma)).status_code == 200


# ═══ KB 39: tài khoản giáo viên do admin cấp và tài khoản cũ ═════════════════
async def test_giao_vien_do_admin_tao_tao_duoc_de_giao_kb39(client, tb):
    ad = await _tk(client, "admin", "QuanTri")
    email = f"gv-{__import__('uuid').uuid4().hex[:6]}@vd.vn"
    r = await client.post("/admin/users", headers=ad.h, json={
        "email": email, "password": "matkhau123", "name": "Co A", "role": "giao_vien"})
    assert r.status_code == 201, r.text
    login = await client.post("/auth/login", json={"email": email, "password": "matkhau123"})
    assert login.status_code == 200 and login.json()["role"] == "giao_vien"
    gv = SimpleNamespace(h={"Authorization": f"Bearer {login.json()['token']}"})
    p = await client.post("/de-giao/xem-truoc", headers=gv.h, json={"exam": "CK1"})
    assert p.status_code == 200 and p.json()["so_cau"] == 12
    c = await _cap(client, gv, p.json()["nhap_id"])
    assert c.status_code == 200 and re.fullmatch(f"[{BANG}]{{6}}", c.json()["ma"])


async def test_tai_khoan_giao_vien_co_san_van_dung_binh_thuong_kb39(client, tb):
    """KB 39: tài khoản giáo viên đã có (tạo trực tiếp trong DB, như tài khoản tự đăng ký trước US-26)
    vẫn là giáo viên, đăng nhập, tạo đề giao, xem kết quả, đóng mã của mình."""
    gv = await _tk(client, "giao_vien", "Cu")
    login = await client.post("/auth/login", json={"email": gv.email, "password": "matkhau123"})
    assert login.status_code == 200 and login.json()["role"] == "giao_vien"
    assert (await client.get("/auth/me", headers=gv.h)).json()["role"] == "giao_vien"
    g = await _giao(client, gv)
    assert (await _ket_qua(client, gv, g.id)).status_code == 200
    assert (await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)).json()["trang_thai"] == "dong"


# ═══ Sửa lỗi QC lượt B ═══════════════════════════════════════════════════════
async def test_bai_dang_do_ma_da_dong_khong_con_trong_lich_su_bug_qc26_02(client, tb):
    """Mã đóng khi em mở dở: không liệt kê (không nộp / xoá / xem được gì). Em đã nộp thì vẫn liệt kê."""
    gv, chi, an = await _tk(client, "giao_vien"), await _tk(client, ten="Chi"), await _tk(client, ten="An")
    g = await _giao(client, gv)
    await _vao_ok(client, chi, g.ma)
    await _lam(client, an, g.ma, list(tb.kho.values()), 8)
    assert len((await client.get("/exam/cuoi-ky", headers=chi.h)).json()["de"]) == 1     # mã còn mở: hiện
    await client.post(f"/de-giao/{g.id}/dong", headers=gv.h)
    assert (await client.get("/exam/cuoi-ky", headers=chi.h)).json()["de"] == []
    assert len((await client.get("/exam/cuoi-ky", headers=an.h)).json()["de"]) == 1


async def test_thong_bao_cho_hoc_sinh_khong_nhac_kho_bug_qc26_03(client):
    gia = TbGia(_kho(9), thieu={"V": 3}, thong_bao="Thiếu 3 câu mức Vận dụng, cần bổ sung câu vào kho.")
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    try:
        gv, hs = await _tk(client, "giao_vien"), await _tk(client)
        g = await _giao(client, gv, exam="CK2")
        assert "Thiếu 3 câu" in g.xem_truoc["thong_bao"]            # giáo viên vẫn thấy lời của kho
        v = await _vao_ok(client, hs, g.ma)
    finally:
        app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)
    assert v["thong_bao"] == "Đề này có 9 câu."


async def test_thong_bao_rong_cho_hoc_sinh_khi_du_cau_bug_qc26_03(client, tb):
    gv, hs = await _tk(client, "giao_vien"), await _tk(client)
    g = await _giao(client, gv)
    assert (await _vao_ok(client, hs, g.ma))["thong_bao"] == ""
