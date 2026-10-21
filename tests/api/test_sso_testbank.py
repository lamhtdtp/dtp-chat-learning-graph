"""US-28 — cấp phiếu đăng nhập một lần sang Testbank (phía learning).

Testbank không có mặt: learning chỉ ký phiếu, nên kiểm bằng cách giải phiếu với khoá công khai
learning công bố ở JWKS — đúng việc Testbank sẽ làm.
"""
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.config import settings
from app.db.models import NhatKySsoTestbank
from tests.api.conftest import tao_tai_khoan

GOC = "http://testbank-gv.test"


@pytest.fixture(scope="module")
def pem() -> str:
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()


@pytest.fixture
def sso_bat(monkeypatch, pem):
    monkeypatch.setattr(settings, "testbank_web_teacher_url", GOC)
    monkeypatch.setattr(settings, "sso_testbank_bat", True)
    monkeypatch.setattr(settings, "sso_testbank_private_key", pem)
    monkeypatch.setattr(settings, "sso_testbank_kid", "k1")


def _phieu(url: str) -> str:
    assert url.startswith(f"{GOC}/sso#phieu="), url
    return url.split("#phieu=", 1)[1]


async def _giai(client, phieu: str) -> dict:
    """Làm đúng việc của Testbank: lấy khoá công khai từ JWKS rồi kiểm chữ ký + nơi nhận."""
    j = (await client.get("/auth/.well-known/jwks.json")).json()["keys"][0]
    return jwt.decode(phieu, j["pem"], algorithms=["RS256"], audience="testbank-identity",
                      issuer="gia-su-dtp", options={"verify_iat": False})


@pytest.mark.parametrize("vai", ["giao_vien", "chuyen_gia", "admin"])
async def test_vai_duoc_sso_xin_duoc_phieu_dung_chu_ky(client, sso_bat, vai):
    email, h = await tao_tai_khoan(client, vai, ten="Trần Thị Hoa", prefix="Hoa")
    r = await client.post("/auth/sso/testbank", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["che_do"] == "sso"
    than = await _giai(client, _phieu(r.json()["url"]))
    assert than["email"] == email.lower() and than["role"] == vai and than["name"] == "Trần Thị Hoa"
    assert than["exp"] - than["iat"] == 60 and than["typ"] == "sso-ticket"


async def test_hoc_sinh_bi_tu_choi_khong_phieu_nao(client, sso_bat):
    _, h = await tao_tai_khoan(client, "hoc_sinh")
    r = await client.post("/auth/sso/testbank", headers=h)
    assert r.status_code == 403 and r.json()["detail"] == "Chỉ thầy cô dùng được Testbank"
    assert "phieu" not in r.text


async def test_chua_dang_nhap_bi_tu_choi(client, sso_bat):
    assert (await client.post("/auth/sso/testbank")).status_code == 401


async def test_tai_khoan_learning_bi_khoa_khong_xin_duoc_phieu(client, session, sso_bat):
    from app.db.models import User
    email, h = await tao_tai_khoan(client, "giao_vien")
    u = await session.scalar(select(User).where(User.email == email))
    u.is_active = False
    await session.commit()
    assert (await client.post("/auth/sso/testbank", headers=h)).status_code == 403


async def test_thieu_khoa_ky_thi_bao_chua_ket_noi_khong_500_khong_phieu(client, monkeypatch, sso_bat):
    monkeypatch.setattr(settings, "sso_testbank_private_key", "")
    _, h = await tao_tai_khoan(client, "giao_vien")
    r = await client.post("/auth/sso/testbank", headers=h)
    assert r.status_code == 503
    assert r.json()["detail"] == "Chưa kết nối Testbank, thầy cô báo quản trị viên giúp nhé"
    assert (await client.get("/auth/.well-known/jwks.json")).status_code == 503


async def test_thieu_dia_chi_testbank_thi_bao_chua_ket_noi(client, monkeypatch, sso_bat):
    monkeypatch.setattr(settings, "testbank_web_teacher_url", "")
    _, h = await tao_tai_khoan(client, "giao_vien")
    r = await client.post("/auth/sso/testbank", headers=h)
    assert r.status_code == 503 and "Chưa kết nối Testbank" in r.json()["detail"]


async def test_chua_bat_sso_thi_mo_trang_dang_nhap_va_khong_cap_phieu(client, monkeypatch, sso_bat):
    """Phương án tối thiểu (US-28 mục 8): Testbank chưa xong T3 nên không phiếu nào được cấp."""
    monkeypatch.setattr(settings, "sso_testbank_bat", False)
    email, h = await tao_tai_khoan(client, "giao_vien")
    r = await client.post("/auth/sso/testbank", headers=h)
    assert r.status_code == 200
    assert r.json() == {"che_do": "dang_nhap", "url": GOC}


async def test_jwks_cong_khai_khong_can_dang_nhap_va_khong_lo_khoa_rieng(client, sso_bat, pem):
    r = await client.get("/auth/.well-known/jwks.json")
    assert r.status_code == 200
    k = r.json()["keys"][0]
    assert k["kid"] == "k1" and k["alg"] == "RS256" and k["use"] == "sig"
    assert "PRIVATE" not in r.text


async def test_nhat_ky_ghi_thoi_diem_ma_phieu_va_ket_qua_khong_ghi_nguyen_phieu(client, session, sso_bat, caplog):
    email, h = await tao_tai_khoan(client, "giao_vien", prefix="nk")
    with caplog.at_level("INFO", logger="app.api.sso_testbank"):
        r1 = await client.post("/auth/sso/testbank", headers=h)
        r2 = await client.post("/auth/sso/testbank", headers=h)
    phieu = _phieu(r1.json()["url"])
    than = await _giai(client, phieu)
    dong = (await session.scalars(select(NhatKySsoTestbank).where(
        NhatKySsoTestbank.email == email.lower()).order_by(NhatKySsoTestbank.id))).all()
    assert [d.ket_qua for d in dong] == ["da_cap", "da_cap"]
    assert dong[0].jti == than["jti"] and dong[0].jti != dong[1].jti and dong[0].created_at
    # Nhật ký (DB và log) tra được theo email + jti, nhưng KHÔNG chứa nguyên phiếu.
    assert phieu not in caplog.text and r2.status_code == 200
    assert than["jti"] in caplog.text and email.lower() in caplog.text


async def test_nhat_ky_ghi_ca_lan_bi_tu_choi(client, session, sso_bat):
    email, h = await tao_tai_khoan(client, "hoc_sinh", prefix="hs")
    await client.post("/auth/sso/testbank", headers=h)
    dong = (await session.scalars(select(NhatKySsoTestbank).where(
        NhatKySsoTestbank.email == email.lower()))).all()
    assert [(d.ket_qua, d.jti) for d in dong] == [("tu_choi_vai", None)]


# ── quay_ve (T8): chống chuyển hướng mở ──────────────────────────────────────────────────────

GOC_THAT = "https://testbank.dtpsoft.vn"


@pytest.mark.parametrize("quay_ve", [
    "https://testbank.dtpsoft.vn/sso",
    "https://TESTBANK.dtpsoft.vn/sso",
    "https://testbank.dtpsoft.vn:443/sso",
])
async def test_quay_ve_dung_origin_duoc_nhan_va_url_dung_tu_cau_hinh(client, monkeypatch, sso_bat, quay_ve):
    monkeypatch.setattr(settings, "testbank_web_teacher_url", GOC_THAT)
    _, h = await tao_tai_khoan(client, "giao_vien")
    r = await client.post("/auth/sso/testbank", json={"quay_ve": quay_ve}, headers=h)
    assert r.status_code == 200, r.text
    # URL dựng từ cấu hình, KHÔNG phải chuỗi người gửi (kể cả khi chỉ khác hoa/thường).
    assert r.json()["url"].startswith(f"{GOC_THAT}/sso#phieu=")
    assert "?" not in r.json()["url"].split("#")[0]


@pytest.mark.parametrize("quay_ve", [
    "https://testbank.dtpsoft.vn.evil.com/sso",         # đuôi tên miền
    "https://evil.com/sso",
    "//evil.com",
    "//testbank.dtpsoft.vn/sso",                        # thiếu scheme
    "javascript:alert(1)",
    "https://testbank.dtpsoft.vn@evil.com/sso",         # userinfo
    "https://evil.com@testbank.dtpsoft.vn/sso",
    "https://testbank.dtpsoft.vn\\@evil.com/sso",       # `\` trình duyệt đọc như `/`
    "http://testbank.dtpsoft.vn/sso",                   # http vs https
    "https://testbank.dtpsoft.vn:8443/sso",             # cổng khác
    "https://testbank.dtpsoft.vn/",                     # sai đường dẫn
    "https://testbank.dtpsoft.vn/sso/../x",
    "https://testbank.dtpsoft.vn/sso?next=https://evil.com",
    "https://testbank.dtpsoft.vn/sso#x",
    " https://testbank.dtpsoft.vn/sso",
    "https://testbank.dtpsoft.vn/sso\n",
    "https://[::1/sso",                                 # URL hỏng: không được thành 500
    "",
])
async def test_quay_ve_sai_bi_400_khong_phieu_va_ghi_nhat_ky(client, session, monkeypatch, sso_bat, quay_ve):
    monkeypatch.setattr(settings, "testbank_web_teacher_url", GOC_THAT)
    email, h = await tao_tai_khoan(client, "giao_vien", prefix="qv")
    r = await client.post("/auth/sso/testbank", json={"quay_ve": quay_ve}, headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "Địa chỉ quay về Testbank không hợp lệ"
    assert "phieu" not in r.text and "x-testbank-url" not in r.headers
    dong = (await session.scalars(select(NhatKySsoTestbank).where(
        NhatKySsoTestbank.email == email.lower()))).all()
    assert [(d.ket_qua, d.jti) for d in dong] == [("quay_ve_sai", None)]


async def test_quay_ve_cong_khac_chi_nhan_khi_cau_hinh_cung_cong(client, monkeypatch, sso_bat):
    monkeypatch.setattr(settings, "testbank_web_teacher_url", "http://localhost:5174")
    _, h = await tao_tai_khoan(client, "giao_vien")
    ok = await client.post("/auth/sso/testbank", json={"quay_ve": "http://localhost:5174/sso"}, headers=h)
    sai = await client.post("/auth/sso/testbank", json={"quay_ve": "http://localhost:5175/sso"}, headers=h)
    assert ok.status_code == 200 and sai.status_code == 400


async def test_hoc_sinh_co_quay_ve_van_bi_403_khong_phieu(client, sso_bat):
    _, h = await tao_tai_khoan(client, "hoc_sinh")
    r = await client.post("/auth/sso/testbank", json={"quay_ve": f"{GOC}/sso"}, headers=h)
    assert r.status_code == 403 and "phieu" not in r.text


async def test_sso_tat_co_quay_ve_hop_le_khong_phieu(client, monkeypatch, sso_bat):
    monkeypatch.setattr(settings, "sso_testbank_bat", False)
    _, h = await tao_tai_khoan(client, "giao_vien")
    r = await client.post("/auth/sso/testbank", json={"quay_ve": f"{GOC}/sso"}, headers=h)
    assert r.status_code == 200 and r.json() == {"che_do": "dang_nhap", "url": GOC}


async def test_thieu_khoa_ky_voi_quay_ve_hop_le_503_kem_dia_chi_ve_tu_cau_hinh(client, monkeypatch, sso_bat):
    monkeypatch.setattr(settings, "sso_testbank_private_key", "")
    _, h = await tao_tai_khoan(client, "giao_vien")
    ok = await client.post("/auth/sso/testbank", json={"quay_ve": f"{GOC}/sso"}, headers=h)
    khong = await client.post("/auth/sso/testbank", json={}, headers=h)
    assert ok.status_code == 503 and ok.headers["x-testbank-url"] == GOC
    assert khong.status_code == 503 and "x-testbank-url" not in khong.headers
