"""Client gọi DTP Testbank — máy chủ sang máy chủ, bằng tài khoản dịch vụ vai
`DOI_TAC_ON_LUYEN` (docs/24-HUONG-DAN-API-CHO-LEARNING.md của testbank).

Ba service, ba gốc URL riêng (identity / content / exam). KHÔNG gộp một biến rồi
tự ghép tiền tố: ở prod ba service nằm sau một tên miền (`/api/identity`,
`/api/content`, `/api/exam`), ở máy dev mỗi service một cổng không tiền tố. Một
biến thì chỉ đúng được một trong hai.

Token: access sống 15 phút, refresh 30 ngày. Làm mới khi access còn dưới 1 phút
hoặc khi nhận 401; refresh hỏng thì mới đăng nhập lại bằng mật khẩu. Token để
trong Redis (app stateless, nhiều replica dùng chung một cặp token thay vì mỗi
replica một lần đăng nhập); Redis hỏng thì rơi về bộ nhớ process, không chặn.

Lỗi testbank KHÔNG được thành 500 của mình: mọi thứ ra khỏi đây là `TestbankLoi`,
tầng API map sang 503 (tạm thời) hoặc 502 (mình gọi sai / cấu hình sai).
"""
import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

log = logging.getLogger(__name__)

Dich = Literal["identity", "content", "exam"]

#: Rút đề có gọi model phía testbank nên đọc lâu; kết nối thì phải nhanh — kết
#: nối 5 giây không được là testbank chết, chờ thêm cũng vô ích.
TIMEOUT = httpx.Timeout(20.0, connect=5.0)
#: Còn ít hơn chừng này giây là làm mới luôn, khỏi đợi 401.
_LAM_MOI_TRUOC = 60


class TestbankLoi(Exception):
    """Gọi testbank không thành.

    `tam_thoi=True`: mạng, 5xx — thử lại sau là được (API trả 503).
    `tam_thoi=False`: 4xx, sai mật khẩu — mình gọi sai hoặc cấu hình sai, thử lại
    không khỏi (API trả 502 và log đủ để người vận hành sửa)."""

    __test__ = False   # tên bắt đầu bằng "Test" — đừng để pytest tưởng là lớp test

    def __init__(self, thong_diep: str, *, tam_thoi: bool = True, ma: int | None = None,
                 chi_tiet: str = ""):
        super().__init__(thong_diep)
        self.tam_thoi = tam_thoi
        self.ma = ma
        self.chi_tiet = chi_tiet


class TestbankChuaCauHinh(TestbankLoi):
    """Thiếu URL hoặc tài khoản trong env — tính năng tắt, không phải lỗi mạng."""

    def __init__(self, thieu: list[str]):
        super().__init__(f"Chưa cấu hình kết nối DTP Testbank (thiếu: {', '.join(thieu)})",
                         tam_thoi=False)


@dataclass(frozen=True)
class CauHinh:
    identity_url: str
    content_url: str
    exam_url: str
    email: str
    password: str

    @classmethod
    def tu_gia_tri(cls, **kv: str) -> "CauHinh":
        thieu = [f"TESTBANK_{k.upper()}" for k, v in kv.items() if not (v or "").strip()]
        if thieu:
            raise TestbankChuaCauHinh(thieu)
        return cls(**{k: v.strip().rstrip("/") if k.endswith("_url") else v
                      for k, v in kv.items()})

    @classmethod
    def tu_settings(cls) -> "CauHinh":
        from app.config import settings

        return cls.tu_gia_tri(
            identity_url=settings.testbank_identity_url,
            content_url=settings.testbank_content_url,
            exam_url=settings.testbank_exam_url,
            email=settings.testbank_email,
            password=settings.testbank_password,
        )

    def goc(self, dich: Dich) -> str:
        return {"identity": self.identity_url, "content": self.content_url,
                "exam": self.exam_url}[dich]


# ── Chỗ giữ token ───────────────────────────────────────────────────────────
class KhoToken(Protocol):
    async def doc(self) -> dict | None: ...
    async def ghi(self, t: dict, ttl: int) -> None: ...
    async def xoa(self) -> None: ...


class KhoTokenBoNho:
    """Giữ token trong process. Dùng cho test, và làm chỗ dự phòng khi Redis hỏng."""

    def __init__(self) -> None:
        self._t: dict | None = None

    async def doc(self) -> dict | None:
        return self._t

    async def ghi(self, t: dict, ttl: int) -> None:
        self._t = t

    async def xoa(self) -> None:
        self._t = None


class KhoTokenRedis:
    """Một cặp token cho mọi replica. Redis hỏng -> rơi về bộ nhớ process, không
    chặn việc rút đề (cùng lối fail-open với app/llm/cache.py)."""

    _KHOA = "testbank:token"
    #: Dùng chung mọi instance (mỗi request một instance): dự phòng phải sống qua
    #: các request, không thì Redis chết là request nào cũng đăng nhập lại.
    _du_phong = KhoTokenBoNho()
    #: Chỉ kêu to lần đầu Redis hỏng — mỗi lượt rút đề đọc/ghi token vài lần.
    _da_bao = False

    @classmethod
    def _bao(cls, viec: str, exc: Exception) -> None:
        if not cls._da_bao:
            cls._da_bao = True
            log.warning("Redis hỏng (%s), giữ token testbank trong process: %s", viec, exc)

    async def doc(self) -> dict | None:
        from app.llm import cache

        try:
            raw = await cache._redis().get(self._KHOA)
        except Exception as exc:  # noqa: BLE001 — mất kết nối, sai mật khẩu…
            self._bao("đọc", exc)
            return await self._du_phong.doc()
        type(self)._da_bao = False
        return json.loads(raw) if raw else None

    async def ghi(self, t: dict, ttl: int) -> None:
        from app.llm import cache

        await self._du_phong.ghi(t, ttl)
        try:
            await cache._redis().set(self._KHOA, json.dumps(t), ex=max(ttl, 1))
        except Exception as exc:  # noqa: BLE001
            self._bao("ghi", exc)

    async def xoa(self) -> None:
        from app.llm import cache

        await self._du_phong.xoa()
        try:
            await cache._redis().delete(self._KHOA)
        except Exception:  # noqa: BLE001
            pass


def _het_han(token: str, mac_dinh: float) -> float:
    """Đọc `exp` trong thân JWT, không kiểm chữ ký — testbank đã kiểm ở phía họ,
    mình chỉ cần biết lúc nào phải làm mới (tài liệu tích hợp §3)."""
    try:
        than = token.split(".")[1]
        than += "=" * (-len(than) % 4)
        return float(json.loads(base64.urlsafe_b64decode(than))["exp"])
    except Exception:  # noqa: BLE001 — token lạ thì dựa vào expires_in
        return mac_dinh


def _chi_tiet(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail")
    except Exception:  # noqa: BLE001
        return r.text[:300]
    return d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)[:300]


class TestbankClient:
    __test__ = False

    def __init__(self, cau_hinh: CauHinh, http: httpx.AsyncClient, kho: KhoToken,
                 *, now=time.time):
        self.ch = cau_hinh
        self._http = http
        self._kho = kho
        self._now = now

    # ── HTTP trần ──
    async def _post(self, url: str, body: Any, token: str | None = None) -> httpx.Response:
        headers = {"authorization": f"Bearer {token}"} if token else {}
        try:
            return await self._http.post(url, json=body, headers=headers, timeout=TIMEOUT)
        except httpx.HTTPError as exc:
            log.warning("Không gọi được testbank %s: %s", url, exc)
            raise TestbankLoi("Không kết nối được DTP Testbank") from exc

    @staticmethod
    def _doc(r: httpx.Response, url: str) -> Any:
        if r.is_success:
            return r.json()
        ct = _chi_tiet(r)
        tam_thoi = r.status_code >= 500
        (log.warning if tam_thoi else log.error)(
            "Testbank trả %s cho %s: %s", r.status_code, url, ct)
        raise TestbankLoi(f"DTP Testbank trả lỗi {r.status_code}", tam_thoi=tam_thoi,
                          ma=r.status_code, chi_tiet=ct)

    # ── Token ──
    async def _luu_cap(self, cap: dict) -> str:
        bay_gio = self._now()
        access, refresh = cap["access_token"], cap["refresh_token"]
        t = {
            "access": access, "refresh": refresh,
            "access_exp": _het_han(access, bay_gio + float(cap.get("expires_in") or 900)),
            "refresh_exp": _het_han(refresh, bay_gio + 30 * 86400),
        }
        await self._kho.ghi(t, ttl=int(t["refresh_exp"] - bay_gio))
        return access

    async def _dang_nhap(self) -> str:
        url = f"{self.ch.identity_url}/auth/login"
        r = await self._post(url, {"email": self.ch.email, "password": self.ch.password})
        if r.status_code == 401:
            # Sai mật khẩu / tài khoản bị khoá: chờ bao lâu cũng không khỏi.
            log.error("Testbank từ chối tài khoản dịch vụ %s: %s", self.ch.email, _chi_tiet(r))
            raise TestbankLoi("Tài khoản dịch vụ testbank bị từ chối", tam_thoi=False,
                              ma=401, chi_tiet=_chi_tiet(r))
        return await self._luu_cap(self._doc(r, url))

    async def _lam_moi(self, refresh: str) -> str | None:
        url = f"{self.ch.identity_url}/auth/refresh"
        try:
            r = await self._post(url, {"refresh_token": refresh})
        except TestbankLoi:
            return None
        if not r.is_success:
            return None
        return await self._luu_cap(r.json())

    async def _token(self) -> str:
        t = await self._kho.doc()
        bay_gio = self._now()
        if t and t["access_exp"] - bay_gio > _LAM_MOI_TRUOC:
            return t["access"]
        if t and t["refresh_exp"] - bay_gio > _LAM_MOI_TRUOC:
            moi = await self._lam_moi(t["refresh"])
            if moi:
                return moi
        return await self._dang_nhap()

    # ── Gọi có xác thực ──
    async def goi(self, dich: Dich, duong: str, body: Any) -> Any:
        url = f"{self.ch.goc(dich)}{duong}"
        r = await self._post(url, body, await self._token())
        if r.status_code == 401:
            # Token bị từ chối dù chưa hết hạn theo đồng hồ của mình (testbank
            # đổi khoá, lệch giờ…). Bỏ token, đăng nhập lại, thử ĐÚNG MỘT lần.
            await self._kho.xoa()
            r = await self._post(url, body, await self._dang_nhap())
        return self._doc(r, url)


_http: httpx.AsyncClient | None = None


def tao_client() -> TestbankClient:
    """Client dùng thật. `httpx.AsyncClient` dùng lại giữa các request (giữ kết
    nối); cấu hình đọc lại mỗi lần để sửa env không phải khởi động lại."""
    global _http
    ch = CauHinh.tu_settings()
    if _http is None:
        _http = httpx.AsyncClient(timeout=TIMEOUT)
    return TestbankClient(ch, _http, KhoTokenRedis())
