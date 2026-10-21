"""Phiếu đăng nhập một lần sang DTP Testbank (US-28, docs/YEU-CAU-TESTBANK-GIAO-DE.md T3).

Learning ký, Testbank kiểm bằng KHOÁ CÔNG KHAI — Testbank không giữ bí mật chung nào, nên
Testbank bị lộ cũng không giả được phiếu của learning. Phiếu sống 60 giây, dùng một lần
(việc "một lần" do Testbank bảo đảm: nó ghi `jti` đã dùng), nơi nhận cố định là Testbank.

Hàm thuần: nhận cấu hình và đồng hồ qua tham số để test không phải chờ 60 giây thật.
"""
import base64
import re
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "gia-su-dtp"
AUDIENCE = "testbank-identity"
LOAI = "sso-ticket"
#: Cho Testbank 60 giây: đủ để trình duyệt mở tab mới và gọi identity, ngắn tới mức phiếu
#: lọt vào lịch sử / nhật ký cũng đã vô dụng.
TUOI_THO_GIAY = 60
#: Chỉ vai này xin được phiếu. Học sinh KHÔNG BAO GIỜ (US-28 G4): học sinh làm bài trong learning.
VAI_DUOC_SSO = frozenset({"giao_vien", "chuyen_gia", "admin"})


class SsoChuaCauHinh(Exception):
    """Thiếu khoá ký / kid, hoặc khoá không đọc được. Tính năng báo "chưa kết nối", không 500."""


@dataclass(frozen=True)
class KhoaKy:
    kid: str
    private_pem: str

    @classmethod
    def tu_gia_tri(cls, private_key: str, kid: str) -> "KhoaKy":
        # Biến môi trường một dòng thường viết xuống dòng thành "\n" chữ — nhận cả hai kiểu.
        pem = (private_key or "").strip().replace("\\n", "\n")
        kid = (kid or "").strip()
        if not pem or not kid:
            raise SsoChuaCauHinh("Thiếu SSO_TESTBANK_PRIVATE_KEY hoặc SSO_TESTBANK_KID")
        try:
            khoa = serialization.load_pem_private_key(pem.encode(), password=None)
        except Exception as exc:  # noqa: BLE001 — mọi kiểu PEM hỏng đều là "chưa cấu hình được"
            raise SsoChuaCauHinh("SSO_TESTBANK_PRIVATE_KEY không phải khoá RSA PEM hợp lệ") from exc
        if not isinstance(khoa, rsa.RSAPrivateKey) or khoa.key_size < 2048:
            raise SsoChuaCauHinh("SSO_TESTBANK_PRIVATE_KEY phải là khoá RSA từ 2048 bit")
        return cls(kid=kid, private_pem=pem)

    @classmethod
    def tu_settings(cls) -> "KhoaKy":
        from app.config import settings

        return cls.tu_gia_tri(settings.sso_testbank_private_key, settings.sso_testbank_kid)


def chuan_hoa_email(email: str) -> str:
    return (email or "").strip().lower()


def tao_phieu(khoa: KhoaKy, *, user_id: int, email: str, ten: str, vai: str,
              now: float | None = None, jti: str | None = None) -> tuple[str, dict]:
    """Trả `(phiếu, thân)`. Thân chỉ có đúng các trường hợp đồng cần (KB 8): không mật khẩu,
    không token phiên learning, không dữ liệu của người khác."""
    if vai not in VAI_DUOC_SSO:
        raise ValueError(f"Vai {vai!r} không được cấp phiếu")
    iat = int(now if now is not None else time.time())
    than = {
        "iss": ISSUER, "aud": AUDIENCE, "typ": LOAI,
        "sub": str(user_id), "email": chuan_hoa_email(email), "name": ten, "role": vai,
        "iat": iat, "exp": iat + TUOI_THO_GIAY, "jti": jti or str(uuid.uuid4()),
    }
    phieu = jwt.encode(than, khoa.private_pem, algorithm="RS256",
                       headers={"kid": khoa.kid, "typ": "JWT"})
    return phieu, than


def _b64(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwks(khoa: KhoaKy) -> dict:
    """Khoá công khai dạng JWK chuẩn, kèm `pem` cho giống lối JWKS hiện có của Testbank."""
    rieng = serialization.load_pem_private_key(khoa.private_pem.encode(), password=None)
    cong_khai = rieng.public_key()
    so = cong_khai.public_numbers()
    pem = cong_khai.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return {"keys": [{"kty": "RSA", "kid": khoa.kid, "use": "sig", "alg": "RS256",
                      "n": _b64(so.n), "e": _b64(so.e), "pem": pem}]}


def url_mo_testbank(goc_web_teacher: str, phieu: str | None) -> str:
    """Có phiếu: `<gốc>/sso#phieu=…` — phiếu ở sau dấu `#` để KHÔNG lọt vào nhật ký nginx hay
    header Referer (KB 8). Không phiếu: chính trang giáo viên, Testbank tự chuyển tới đăng nhập."""
    goc = goc_web_teacher.strip().rstrip("/")
    return f"{goc}/sso#phieu={phieu}" if phieu else goc


#: Ký tự điều khiển, khoảng trắng, `\` : trình duyệt đọc `\` như `/` còn bộ phân tích URL của
#: Python thì không, nên `https://testbank.dtpsoft.vn\@evil.com/sso` hai bên hiểu hai nghĩa khác nhau.
_KY_TU_LA = re.compile(r"[\x00-\x20\x7f\\]")


def _goc_nguon(url: str) -> tuple[str, str, int] | None:
    """(scheme, host, cổng thật) hoặc None. Cổng ngầm định 80/443 được điền để `https://a` và
    `https://a:443` coi là một origin."""
    try:
        t = urlsplit(url)
        host = t.hostname
        cong = t.port or {"http": 80, "https": 443}.get(t.scheme)
    except ValueError:
        return None
    if t.scheme not in ("http", "https") or not host or cong is None:
        return None
    return t.scheme, host.lower(), cong


def quay_ve_hop_le(quay_ve: str, goc_web_teacher: str) -> bool:
    """`quay_ve` do Testbank gửi qua trình duyệt nên là dữ liệu của kẻ lạ: chỉ nhận khi ĐÚNG origin
    của web giáo viên đã cấu hình và đường dẫn đúng `/sso` (chống chuyển hướng mở). Không có
    userinfo, query hay fragment. Kết quả chỉ để cho phép / từ chối — URL trả về luôn dựng từ cấu
    hình, không bao giờ ghép từ chuỗi này."""
    if not quay_ve or _KY_TU_LA.search(quay_ve):
        return False
    try:
        t = urlsplit(quay_ve)
    except ValueError:
        return False
    if t.username is not None or t.password is not None or t.query or t.fragment or t.path != "/sso":
        return False
    a, b = _goc_nguon(quay_ve), _goc_nguon(goc_web_teacher.strip())
    return a is not None and a == b
