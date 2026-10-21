"""US-28 — phiếu đăng nhập một lần sang Testbank (hàm thuần): claim, hạn, chữ ký, JWKS."""
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.sso import testbank as sso

KID = "learning-test"


@pytest.fixture(scope="module")
def pem() -> str:
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()


@pytest.fixture
def khoa(pem) -> sso.KhoaKy:
    return sso.KhoaKy.tu_gia_tri(pem, KID)


def _khoa_cong_khai(khoa) -> str:
    return sso.jwks(khoa)["keys"][0]["pem"]


def test_phieu_co_dung_claim_theo_hop_dong(khoa):
    phieu, than = sso.tao_phieu(khoa, user_id=1024, email="  Hoa@Truong.edu.vn ", ten="Trần Thị Hoa",
                                vai="giao_vien", now=1_792_564_800, jti="6f1c2a8e-3d0b-4a57-9a8e-2b7e5f1d9c40")
    assert than == {
        "iss": "gia-su-dtp", "aud": "testbank-identity", "typ": "sso-ticket",
        "sub": "1024", "email": "hoa@truong.edu.vn", "name": "Trần Thị Hoa", "role": "giao_vien",
        "iat": 1_792_564_800, "exp": 1_792_564_860, "jti": "6f1c2a8e-3d0b-4a57-9a8e-2b7e5f1d9c40"}
    assert jwt.get_unverified_header(phieu) == {"alg": "RS256", "typ": "JWT", "kid": KID}


def test_phieu_chi_chua_dung_cac_truong_can_khong_mat_khau_hay_token(khoa):
    """KB 8: email, họ tên, vai, nơi nhận, thời điểm cấp / hết hạn, mã phiếu — không hơn."""
    _, than = sso.tao_phieu(khoa, user_id=1, email="a@b.vn", ten="A", vai="admin")
    assert set(than) == {"iss", "aud", "typ", "sub", "email", "name", "role", "iat", "exp", "jti"}


def test_chu_ky_kiem_duoc_bang_khoa_cong_khai_va_het_han_sau_60_giay(khoa):
    phieu, than = sso.tao_phieu(khoa, user_id=7, email="a@b.vn", ten="A", vai="chuyen_gia", now=1000)
    cong_khai = _khoa_cong_khai(khoa)
    out = jwt.decode(phieu, cong_khai, algorithms=["RS256"], audience="testbank-identity",
                     issuer="gia-su-dtp", options={"verify_exp": False, "verify_iat": False})
    assert out["jti"] == than["jti"] and out["exp"] - out["iat"] == 60
    # Quá 60 giây (so với iat): hết hạn. Dùng `leeway` 0 và now giả bằng exp.
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(phieu, cong_khai, algorithms=["RS256"], audience="testbank-identity",
                   options={"verify_iat": False})   # exp = 1060, đã qua từ lâu


def test_sua_email_sau_khi_ky_thi_chu_ky_hong(khoa):
    phieu, _ = sso.tao_phieu(khoa, user_id=7, email="a@b.vn", ten="A", vai="giao_vien")
    h, p, s = phieu.split(".")
    import base64, json
    than = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    than["email"] = "khac@b.vn"
    p2 = base64.urlsafe_b64encode(json.dumps(than).encode()).rstrip(b"=").decode()
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(f"{h}.{p2}.{s}", _khoa_cong_khai(khoa), algorithms=["RS256"],
                   audience="testbank-identity", options={"verify_exp": False, "verify_iat": False})


def test_khoa_khac_khong_kiem_duoc(khoa):
    phieu, _ = sso.tao_phieu(khoa, user_id=7, email="a@b.vn", ten="A", vai="giao_vien")
    khac = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(phieu, khac, algorithms=["RS256"], audience="testbank-identity",
                   options={"verify_exp": False, "verify_iat": False})


def test_hoc_sinh_khong_bao_gio_duoc_cap_phieu(khoa):
    with pytest.raises(ValueError):
        sso.tao_phieu(khoa, user_id=7, email="a@b.vn", ten="A", vai="hoc_sinh")


def test_moi_phieu_mot_jti_rieng(khoa):
    a = sso.tao_phieu(khoa, user_id=7, email="a@b.vn", ten="A", vai="admin")[1]["jti"]
    b = sso.tao_phieu(khoa, user_id=7, email="a@b.vn", ten="A", vai="admin")[1]["jti"]
    assert a != b


def test_jwks_la_jwk_chuan_co_kid_va_pem(khoa):
    k = sso.jwks(khoa)["keys"][0]
    assert (k["kty"], k["use"], k["alg"], k["kid"]) == ("RSA", "sig", "RS256", KID)
    assert k["e"] == "AQAB" and len(k["n"]) > 300
    assert k["pem"].startswith("-----BEGIN PUBLIC KEY-----")
    assert "PRIVATE" not in str(k)


@pytest.mark.parametrize("pem_, kid", [("", KID), ("x", ""), ("khong-phai-pem", KID)])
def test_thieu_hoac_hong_khoa_thi_bao_chua_cau_hinh(pem_, kid):
    with pytest.raises(sso.SsoChuaCauHinh):
        sso.KhoaKy.tu_gia_tri(pem_, kid)


def test_khoa_viet_xuong_dong_bang_backslash_n_van_doc_duoc(pem):
    mot_dong = pem.strip().replace("\n", "\\n")
    assert sso.KhoaKy.tu_gia_tri(mot_dong, KID).private_pem == pem.strip()


def test_url_co_phieu_o_sau_dau_thang_khong_phai_query():
    assert sso.url_mo_testbank("https://tb.vn/", "abc.def") == "https://tb.vn/sso#phieu=abc.def"
    assert sso.url_mo_testbank("https://tb.vn/", None) == "https://tb.vn"
