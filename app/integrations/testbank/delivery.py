"""Client dịch vụ PHÁT ĐỀ của DTP Testbank — đường học sinh `/hs/*`, mức 0 (US-29).

Mức 0 = dùng nguyên đường học sinh Testbank đã có: vào thi bằng mã + họ tên, nhận KHOÁ BÀI LÀM
(header `X-Khoa-Bai-Lam`) rồi dùng khoá đó cho mọi lời gọi sau. Không token, không tài khoản dịch
vụ. Máy chủ learning gọi THAY học sinh; khoá nằm ở DB của learning, không bao giờ xuống trình
duyệt (nên trình duyệt không gọi thẳng Testbank thay learning được).

Mức 1 (`/doi-tac/*`, token đối tác, T7) và chi tiết sau nộp (T5) ở `doi_tac.py` (US-30), sau hai cờ
cấu hình `TESTBANK_DOI_TAC_BAT` / `TESTBANK_CHI_TIET_SAU_NOP_BAT`.

Hợp đồng nguồn: docs/YEU-CAU-TESTBANK-GIAO-DE.md, đối chiếu `services/delivery/.../routers/hs.py`
và `schemas.py` của Testbank.

Phần dưới cùng là hàm THUẦN: đổi dạng dữ liệu Testbank <-> dạng giao diện learning đang dùng
(`chon` là chuỗi: "B", "A,C", "Đ,S,,", "3,5") để dùng lại component làm bài hiện có.
"""
import json
import logging
import time
from typing import Any

import httpx

from app.integrations.testbank.client import TestbankChuaCauHinh
from app.integrations.testbank.hien_thi import sang_html

log = logging.getLogger(__name__)

#: Testbank im quá 10 giây thì báo lỗi (US-29 KB 23), không để học sinh nhìn màn hình trống.
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
HEADER_KHOA = "X-Khoa-Bai-Lam"
#: Họ tên Testbank nhận 2-100 ký tự (`VaoThiIn.ten_hop_le`).
_TEN_TOI_DA = 100


class DeliveryChuaCauHinh(TestbankChuaCauHinh):
    def __init__(self) -> None:
        super().__init__(["TESTBANK_DELIVERY_URL"])


class DeliveryLoi(Exception):
    """Lời gọi dịch vụ phát đề không thành.

    `status=None`: không nối được / quá hạn. `ma`/`thong_diep` đọc từ `detail` của Testbank
    (có dạng chuỗi hoặc `{ma, thong_diep}`). `tam_thoi`: mạng + 5xx — thử lại sau là được."""

    def __init__(self, status: int | None, *, ma: str = "", thong_diep: str = "",
                 retry_after: int | None = None):
        super().__init__(f"delivery {status}: {ma or thong_diep}")
        self.status = status
        self.ma = ma
        self.thong_diep = thong_diep
        self.retry_after = retry_after
        #: Thân 422 của lưu câu trả lời khi vẫn là `LuuOut` (đường đối tác dựng ngoại lệ trước khi đọc thân).
        self.luu_out: dict | None = None

    @property
    def tam_thoi(self) -> bool:
        return self.status is None or self.status >= 500


def _doc_detail(r: httpx.Response) -> tuple[str, str]:
    try:
        d = r.json().get("detail")
    except Exception:  # noqa: BLE001
        return "", r.text[:200]
    if isinstance(d, dict):
        return str(d.get("ma") or ""), str(d.get("thong_diep") or "")
    return "", d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)[:200]


class DeliveryClient:
    def __init__(self, goc: str, http: httpx.AsyncClient):
        self.goc = goc.strip().rstrip("/")
        self._http = http

    async def _goi(self, method: str, duong: str, *, khoa: str | None = None,
                   body: Any = None) -> httpx.Response:
        """Log mỗi lời gọi (kết quả, độ trễ) — KHÔNG log khoá bài làm (US-29 mục 4)."""
        url = f"{self.goc}/hs{duong}"
        headers = {HEADER_KHOA: khoa} if khoa else {}
        t0 = time.monotonic()
        try:
            r = await self._http.request(method, url, json=body, headers=headers, timeout=TIMEOUT)
        except httpx.HTTPError as exc:
            log.warning("delivery %s %s loi_mang %s sau %.0fms", method, duong,
                        type(exc).__name__, (time.monotonic() - t0) * 1000)
            raise DeliveryLoi(None, thong_diep="Không kết nối được dịch vụ phát đề") from exc
        log.info("delivery %s %s -> %s %.0fms", method, duong, r.status_code,
                 (time.monotonic() - t0) * 1000)
        return r

    @staticmethod
    def _kiem(r: httpx.Response) -> Any:
        if r.is_success:
            return r.json()
        ma, td = _doc_detail(r)
        ra = None
        luu_out = None
        if r.status_code == 422:
            try:
                d = r.json()
            except ValueError:
                d = None
            luu_out = d if isinstance(d, dict) and "da_luu" in d else None
        if r.status_code == 429:
            try:
                ra = max(1, int(r.headers.get("retry-after", "")))
            except ValueError:
                ra = 600
        e = DeliveryLoi(r.status_code, ma=ma, thong_diep=td, retry_after=ra)
        e.luu_out = luu_out
        raise e

    async def vao_thi(self, ma: str, ho_ten: str) -> tuple[str, dict]:
        """Trả `(khoá bài làm, BaiLamHs)`. Mỗi lần gọi Testbank tạo MỘT BÀI MỚI — bên gọi phải
        bảo đảm không gọi hai lần cho cùng (học sinh, mã)."""
        d = self._kiem(await self._goi("POST", "/vao-thi", body={"ma": ma, "ho_ten": ho_ten}))
        return d["khoa_bai_lam"], d["bai_lam"]

    async def xem(self, khoa: str) -> dict:
        return self._kiem(await self._goi("GET", "/bai-lam", khoa=khoa))

    async def luu(self, khoa: str, cau: list[dict]) -> dict:
        r = await self._goi("PUT", "/bai-lam/tra-loi", khoa=khoa, body={"cau": cau})
        # 422 của Testbank KHÔNG phải lỗi: có câu sai định dạng nhưng các câu hợp lệ khác ĐÃ
        # được lưu, thân vẫn là LuuOut (`loi` nói câu nào). Coi là lỗi thì mất luôn phần đã lưu.
        if r.status_code == 422:
            try:
                d = r.json()
            except ValueError:
                d = None
            if isinstance(d, dict) and "da_luu" in d:
                return d
        return self._kiem(r)

    async def nop(self, khoa: str, cau: list[dict]) -> dict:
        return self._kiem(await self._goi("POST", "/bai-lam/nop", khoa=khoa, body={"cau": cau}))


_http: httpx.AsyncClient | None = None


def tao_delivery_client() -> DeliveryClient:
    """Cấu hình đọc lại mỗi lần để sửa env không phải khởi động lại; `httpx.AsyncClient` dùng lại."""
    from app.config import settings

    global _http
    if not (settings.testbank_delivery_url or "").strip():
        raise DeliveryChuaCauHinh()
    if _http is None:
        _http = httpx.AsyncClient(timeout=TIMEOUT)
    return DeliveryClient(settings.testbank_delivery_url, _http)


# ── Hàm thuần ───────────────────────────────────────────────────────────────
def ho_ten_gui(ten: str, user_id: int) -> str:
    """"<Tên> · HS<mã số>" (US-29 Q4): giáo viên phân biệt được bạn trùng tên, không lộ email.
    Cắt TÊN (không cắt hậu tố) để vừa 100 ký tự."""
    hau_to = f" · HS{user_id}"
    ten = " ".join((ten or "").split()) or "Học sinh"
    return ten[: _TEN_TOI_DA - len(hau_to)].rstrip() + hau_to


def ho_ten_thuan(ten: str) -> str:
    """Họ tên gửi Testbank ở mức 1 (US-30 C4): thuần, KHÔNG hậu tố — nhãn phân biệt học sinh trùng tên
    ("Gia sư DTP · HS<mã>") do Testbank dựng từ mã học sinh. Testbank nhận 2-100 ký tự."""
    ten = " ".join((ten or "").split())[:_TEN_TOI_DA].rstrip()
    return ten if len(ten) >= 2 else "Học sinh"


def chon_sang_tra_loi(cau: dict, chon: str) -> Any:
    """Chuỗi `chon` của giao diện -> câu trả lời đúng hình dạng Testbank nhận.

    TN1 "C" -> "C"; TNN "A,C" -> ["A","C"]; DS "Đ,S,," -> {"1":"Đ","2":"S"} (theo thứ tự ý);
    DSN / TL -> chữ nguyên văn. Bỏ trống -> None."""
    dang = cau["dang"]
    if dang in ("DSN", "TL"):
        return chon if (chon or "").strip() else None
    chon = (chon or "").strip()
    if not chon:
        return None
    if dang == "TN1":
        return chon
    if dang == "TNN":
        return [k for k in chon.split(",") if k] or None
    if dang == "DS":
        khoa = [p["key"] for p in cau["phuong_an"]]
        y = {khoa[i]: v for i, v in enumerate(chon.split(",")) if i < len(khoa) and v in ("Đ", "S")}
        return y or None
    return chon


def tra_loi_sang_chon(cau: dict, tra_loi: Any) -> str:
    """Ngược lại của `chon_sang_tra_loi` — dựng lại lựa chọn đã lưu để giao diện hiện."""
    if tra_loi is None:
        return ""
    dang = cau["dang"]
    if dang == "TNN":
        return ",".join(tra_loi) if isinstance(tra_loi, list) else str(tra_loi)
    if dang == "DS":
        if not isinstance(tra_loi, dict):
            return ""
        return ",".join(tra_loi.get(p["key"], "") for p in cau["phuong_an"])
    return tra_loi if isinstance(tra_loi, str) else str(tra_loi)


def qid_cau(stt: int) -> str:
    """Khoá câu phía giao diện. Testbank không đưa mã câu cho học sinh (và không được đưa)."""
    return f"c{stt}"


def cau_cong_khai(c: dict, goc: str) -> dict:
    """Một `CauHs` của Testbank -> dạng câu giao diện learning đang dùng (CauCuoiKy).

    Không có đáp án vì Testbank không gửi. Hình: `anh` / `anh_co` của câu đi qua `sang_html` để
    `[[anh:…]]` thành `<img>` (dùng chung bộ làm sạch HTML với đề tự rút)."""
    a, sz = c.get("anh") or {}, c.get("anh_co") or {}
    dang = c["dang"]
    return {
        "stt": c["so_thu_tu"], "qid": qid_cau(c["so_thu_tu"]), "dang": dang,
        "muc_do": "", "ar_id": "", "ycd": "", "topic_id": None, "don_vi": "",
        "de_html": sang_html(c.get("de_bai"), a, sz, goc=goc),
        "phuong_an": [{"key": p["khoa"], "nhan": p.get("nhan") or p["khoa"],
                       "html": sang_html(p.get("noi_dung"), a, sz, goc=goc)}
                      for p in c.get("phuong_an") or []],
        "du_kien_html": sang_html(c.get("khoi_du_kien"), a, sz, goc=goc),
        "cau_dan": c.get("dan_khoi_du_kien") or "",
        # Tự luận: Testbank không chấm; giao diện nói rõ "Câu này thầy cô chấm" (KB 5).
        "tu_cham": dang != "TL",
        "diem_toi_da": c.get("diem_toi_da"),
    }


def ket_qua_gon(ket_qua: dict, cau: list[dict], da_chon: dict[str, str], *, cach_nop: str | None,
                nop_luc: str | None) -> dict:
    """`KetQuaHs` của Testbank -> bản chép lưu ở learning (và trả cho giao diện).

    `diem` / `tong` / `dat_yeu_cau` cùng tên với kết quả đề tự rút để lịch sử dùng chung. Điểm là
    điểm PHẦN CHẤM TỰ ĐỘNG của Testbank (có thể lẻ), không phải số câu."""
    theo_stt = {c["stt"]: c for c in cau}
    dong = []
    for k in ket_qua.get("cau") or []:
        c = theo_stt.get(k["so_thu_tu"])
        dong.append({
            "stt": k["so_thu_tu"], "trang_thai": k["trang_thai"], "nhan": k["nhan"],
            "diem": k.get("diem"), "diem_toi_da": k.get("diem_toi_da"),
            "chon": da_chon.get(qid_cau(k["so_thu_tu"]), ""),
            "dang": c["dang"] if c else "",
        })
    diem, tong = float(ket_qua.get("tong_diem") or 0), float(ket_qua.get("tong_diem_toi_da") or 0)
    return {
        "diem": diem, "tong": tong, "dat_yeu_cau": bool(tong) and diem / tong >= 0.7,
        "so_cau_cho_cham": int(ket_qua.get("so_cau_cho_cham") or 0),
        "so_cau_dung": sum(1 for d in dong if d["trang_thai"] == "DUNG"),
        "cau": dong, "cach_nop": cach_nop, "nop_luc": nop_luc,
    }
