"""Client gọi DTP Testbank: token, làm mới, lỗi mạng — mock ở RANH GIỚI HTTP
(httpx.MockTransport), không cần testbank chạy."""
import json
import time

import httpx
import jwt
import pytest

from app.integrations.testbank.client import (
    CauHinh, KhoTokenBoNho, TestbankChuaCauHinh, TestbankClient, TestbankLoi,
)
from app.integrations.testbank.exam import rut_de
from app.integrations.testbank.noi_dung import lay_cau

CH = CauHinh(identity_url="http://id", content_url="http://ct", exam_url="http://ex",
             email="learning@dtpsoft.vn", password="x" * 16)


def _jwt(typ: str, song: int) -> str:
    return jwt.encode({"typ": typ, "exp": int(time.time()) + song, "jti": str(time.time_ns())},
                      "k" * 32, algorithm="HS256")


class KhoGia:
    """Testbank giả: đếm số lần đăng nhập / làm mới, cho phép cài lỗi."""

    def __init__(self, access_song: int = 900):
        self.login = self.refresh = 0
        self.access_song = access_song
        self.goi: list[tuple[str, dict, str | None]] = []
        self.tra_ve: dict[str, list[httpx.Response]] = {}
        self.refresh_hong = False

    def cap(self) -> dict:
        return {"access_token": _jwt("access", self.access_song),
                "refresh_token": _jwt("refresh", 30 * 86400),
                "token_type": "bearer", "expires_in": self.access_song}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content or b"{}")
        if req.url.path == "/auth/login":
            self.login += 1
            return httpx.Response(200, json=self.cap())
        if req.url.path == "/auth/refresh":
            self.refresh += 1
            if self.refresh_hong:
                return httpx.Response(401, json={"detail": "Token không hợp lệ hoặc đã hết hạn"})
            return httpx.Response(200, json=self.cap())
        self.goi.append((f"{req.url.host}{req.url.path}", body, req.headers.get("authorization")))
        hang = self.tra_ve.get(req.url.path)
        if hang:
            return hang.pop(0)
        return httpx.Response(200, json={"ok": True})


def _client(tb: KhoGia, kho=None) -> TestbankClient:
    return TestbankClient(CH, httpx.AsyncClient(transport=httpx.MockTransport(tb)),
                          kho or KhoTokenBoNho())


async def test_dang_nhap_mot_lan_roi_dung_lai_token():
    tb = KhoGia()
    c = _client(tb)
    await c.goi("exam", "/exams:preview", {})
    await c.goi("content", "/questions:resolve", {})
    assert tb.login == 1
    assert all(auth and auth.startswith("Bearer ") for _, _, auth in tb.goi)


async def test_moi_dich_mot_goc_rieng():
    tb = KhoGia()
    c = _client(tb)
    await c.goi("exam", "/exams:preview", {})
    await c.goi("content", "/questions:resolve", {})
    assert [g[0] for g in tb.goi] == ["ex/exams:preview", "ct/questions:resolve"]


async def test_access_sap_het_han_thi_lam_moi_khong_dang_nhap_lai():
    """Còn dưới 1 phút là làm mới — đợi 401 rồi mới làm thì mất một vòng gọi."""
    tb = KhoGia(access_song=30)
    c = _client(tb)
    await c.goi("exam", "/x", {})
    await c.goi("exam", "/x", {})
    assert (tb.login, tb.refresh) == (1, 1)


async def test_refresh_hong_thi_dang_nhap_lai_bang_mat_khau():
    tb = KhoGia(access_song=30)
    tb.refresh_hong = True
    c = _client(tb)
    await c.goi("exam", "/x", {})
    await c.goi("exam", "/x", {})
    assert (tb.login, tb.refresh) == (2, 1)


async def test_nhan_401_thi_bo_token_dang_nhap_lai_va_thu_lai_mot_lan():
    tb = KhoGia()
    tb.tra_ve["/x"] = [httpx.Response(401, json={"detail": "Token không hợp lệ hoặc đã hết hạn"}),
                       httpx.Response(200, json={"ok": 1})]
    c = _client(tb)
    assert await c.goi("exam", "/x", {}) == {"ok": 1}
    assert tb.login == 2


async def test_401_lan_hai_thi_bao_loi_khong_lap_vo_han():
    tb = KhoGia()
    tb.tra_ve["/x"] = [httpx.Response(401, json={"detail": "a"}),
                       httpx.Response(401, json={"detail": "a"})]
    with pytest.raises(TestbankLoi):
        await _client(tb).goi("exam", "/x", {})
    assert tb.login == 2


@pytest.mark.parametrize("ma", [502, 503, 500])
async def test_loi_5xx_la_tam_thoi(ma):
    tb = KhoGia()
    tb.tra_ve["/x"] = [httpx.Response(ma, json={"detail": "Chưa kết nối được kho câu hỏi"})]
    with pytest.raises(TestbankLoi) as e:
        await _client(tb).goi("exam", "/x", {})
    assert e.value.tam_thoi and e.value.ma == ma


@pytest.mark.parametrize("ma", [403, 422])
async def test_loi_4xx_khong_phai_tam_thoi(ma):
    """403/422 là mình gọi sai hoặc cấu hình sai — thử lại không khỏi."""
    tb = KhoGia()
    tb.tra_ve["/x"] = [httpx.Response(ma, json={"detail": "Vai trò hiện tại không được rút đề"})]
    with pytest.raises(TestbankLoi) as e:
        await _client(tb).goi("exam", "/x", {})
    assert not e.value.tam_thoi and "không được rút đề" in e.value.chi_tiet


async def test_mat_ket_noi_la_loi_tam_thoi():
    def hong(req):
        raise httpx.ConnectError("refused", request=req)

    c = TestbankClient(CH, httpx.AsyncClient(transport=httpx.MockTransport(hong)), KhoTokenBoNho())
    with pytest.raises(TestbankLoi) as e:
        await c.goi("exam", "/x", {})
    assert e.value.tam_thoi


async def test_sai_mat_khau_khong_phai_tam_thoi():
    def sai(req):
        return httpx.Response(401, json={"detail": "Email hoặc mật khẩu không đúng"})

    c = TestbankClient(CH, httpx.AsyncClient(transport=httpx.MockTransport(sai)), KhoTokenBoNho())
    with pytest.raises(TestbankLoi) as e:
        await c.goi("exam", "/x", {})
    assert not e.value.tam_thoi


def test_chua_cau_hinh_thi_bao_ro():
    with pytest.raises(TestbankChuaCauHinh):
        CauHinh.tu_gia_tri(identity_url="", content_url="http://ct", exam_url="http://ex",
                           email="a@b.vn", password="x")


# ── rút đề ──────────────────────────────────────────────────────────────────
_DE = {"quota": {"B": 5, "H": 4, "V": 3}, "is_complete": False, "shortage": {"V": 2},
       "pool_size": 9, "covered_ars": ["AR26-TO06-CK1-001"], "message": "Thiếu 2 câu mức V.",
       "items": [{"ordinal": 1, "qid": "Q26-000101", "ar_id": "AR26-TO06-CK1-001",
                  "difficulty_code": "B", "format_code": "TN1", "competency_code": "GQV",
                  "domain_code": "STN"}]}


async def test_rut_de_gui_dung_ten_truong_va_doc_thieu_cau():
    tb = KhoGia()
    tb.tra_ve["/exams:preview"] = [httpx.Response(200, json=_DE)]
    de = await rut_de(_client(tb), subject="TO", grade="06", exam="CK1", total=12,
                      ar_ids=["AR26-TO06-CK1-001"], seed=7)
    _, body, _ = tb.goi[0]
    # Tên trường là `exam`, KHÔNG phải `exam_code` (đính chính của testbank).
    assert body["exam"] == "CK1" and "exam_code" not in body
    assert body["ratio"] == {"B": 40, "H": 30, "V": 30}
    assert body["ar_ids"] == ["AR26-TO06-CK1-001"] and body["seed"] == 7
    assert not de.is_complete and de.shortage == {"V": 2} and de.message == "Thiếu 2 câu mức V."
    assert de.items[0].qid == "Q26-000101" and de.items[0].muc_do == "B"


async def test_rut_de_khong_gui_ar_ids_khi_rong():
    """`ar_ids: []` có thể bị hiểu là "không YCCĐ nào" -> đề rỗng."""
    tb = KhoGia()
    tb.tra_ve["/exams:preview"] = [httpx.Response(200, json=_DE)]
    await rut_de(_client(tb), subject="TO", grade="06", exam="CK1", total=12, ar_ids=[], seed=1)
    assert tb.goi[0][1].get("ar_ids") is None


# ── lấy nội dung ────────────────────────────────────────────────────────────
async def test_lay_cau_chia_lo_200_va_giu_thu_tu():
    tb = KhoGia()
    qids = [f"Q26-{i:06d}" for i in range(250)]

    def tra(path_qids):
        return httpx.Response(200, json=[{"qid": q} for q in path_qids])

    # Trả theo đúng lô được gửi -> kiểm luôn thứ tự ghép.
    tb.tra_ve["/questions:resolve"] = [tra(qids[:200]), tra(qids[200:])]
    out = await lay_cau(_client(tb), qids)
    assert [len(b["qids"]) for _, b, _ in tb.goi] == [200, 50]
    assert all(b["include_answers"] is True for _, b, _ in tb.goi)
    assert [c["qid"] for c in out] == qids


async def test_lay_cau_rong_khong_goi_mang():
    tb = KhoGia()
    assert await lay_cau(_client(tb), []) == []
    assert tb.goi == [] and tb.login == 0
