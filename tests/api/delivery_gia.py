"""Testbank GIẢ ở ranh giới HTTP cho US-29: dịch vụ phát đề, đường học sinh `/hs/*` mức 0.

Bắt chước hợp đồng THẬT (đối chiếu `dtp-testbank/services/delivery/.../routers/hs.py`,
`schemas.py`, `bai_lam.py`): mỗi lần `vao-thi` tạo MỘT BÀI MỚI, danh tính là header
`X-Khoa-Bai-Lam`, 404 cùng một thông điệp cho mã sai / đã đóng, 409 `DA_NOP` khi lưu vào bài đã
nộp, 422 từng câu vẫn trả `LuuOut`, nộp lại trả đúng kết quả lần đầu, đóng lượt phát thì nộp hộ.
Learning dùng `httpx.AsyncClient` thật nên toàn bộ phần HTTP (header, mã lỗi, JSON) chạy thật.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone

import httpx

ANH = "3f2a" + "0" * 26 + "e9"
GIO = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def cau_mau() -> list[dict]:
    """10 câu: đủ năm dạng + nhóm có dữ kiện chung + hình. `dap_an` chỉ để máy chấm GIẢ dùng."""
    pa = [{"khoa": k, "nhan": k, "noi_dung": t} for k, t in zip("ABCD", ["2", "3", "6", "36"])]
    ds = [{"khoa": str(i), "nhan": "abcd"[i - 1], "noi_dung": f"Ý {i}"} for i in (1, 2)]
    cau = [
        {"dang": "TN1", "de_bai": f"ƯCLN [[anh:{ANH}]] bằng?", "phuong_an": pa, "dap_an": "B",
         "anh": {ANH: "/api/content/media/3f/2a/x.png"}, "anh_co": {ANH: {"w": 30, "h": 12}}},
        {"dang": "TNN", "de_bai": "Chọn các số nguyên tố", "phuong_an": pa, "dap_an": ["A", "B"]},
        {"dang": "DS", "de_bai": "Đúng hay sai?", "phuong_an": ds, "dap_an": {"1": "Đ", "2": "S"}},
        {"dang": "DSN", "de_bai": "Tính 1 + 2", "phuong_an": [], "dap_an": "3"},
        {"dang": "TL", "de_bai": "Trình bày cách giải", "phuong_an": [], "dap_an": None},
    ]
    # Nhóm câu dùng chung một dữ kiện (khối dữ kiện chỉ ở câu ĐẦU của nhóm — như Testbank).
    for i in range(5):
        cau.append({"dang": "TN1", "de_bai": f"Câu nhóm {i + 1}", "phuong_an": pa, "dap_an": "A",
                    "khoi_du_kien": "Cho bảng số liệu chung" if i == 0 else "",
                    "dan_khoi_du_kien": "Dựa vào bảng:" if i == 0 else "", "nhom": 1})
    return cau


class DeliveryGia:
    def __init__(self):
        self.luot: dict[str, dict] = {}
        self.bai: dict[str, dict] = {}
        self.goi: list[tuple[str, str, str | None, dict | None]] = []
        self.chan_giay: int | None = None     # đặt -> mọi vao-thi trả 429
        self.chet: bool | str = False         # True: lỗi mạng; "500": trả 500
        self.het_gio: set[str] = set()        # khoá bài đã quá hạn nộp

    # ── dựng dữ liệu ──
    def phat(self, ma: str, tieu_de="Kiểm tra cuối kỳ 1 — 6A", cau=None, phut=None):
        self.luot[ma] = {"tieu_de": tieu_de, "cau": cau or cau_mau(), "mo": True, "phut": phut}

    def dong(self, ma: str):
        self.luot[ma]["mo"] = False

    def goi_theo(self, method: str, duong: str | None = None):
        return [g for g in self.goi if g[0] == method and (duong is None or g[1] == duong)]

    # ── HTTP ──
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._xu_ly)

    def _xu_ly(self, req: httpx.Request) -> httpx.Response:
        duong = req.url.path.split("/hs", 1)[1]    # gốc có thể kèm tiền tố (/api/delivery)
        khoa = req.headers.get("x-khoa-bai-lam")
        body = json.loads(req.content) if req.content else None
        self.goi.append((req.method, duong, khoa, body))
        if self.chet is True:
            raise httpx.ConnectError("không nối được", request=req)
        if self.chet == "500":
            return httpx.Response(500, json={"detail": "Internal Server Error"})
        if duong == "/vao-thi":
            return self._vao_thi(body)
        b = self.bai.get(khoa or "")
        if b is None:
            return httpx.Response(404 if khoa else 401, json={"detail": "Không tìm thấy bài làm"})
        l = self.luot[b["ma"]]
        # Hết giờ / đóng lượt phát: nộp hộ NGAY lúc có ai chạm vào bài (Testbank không có tiến trình nền).
        if b["nop"] is None and (not l["mo"] or khoa in self.het_gio):
            self._nop(b, "DONG_LUOT_PHAT" if not l["mo"] else "HET_GIO")
        if req.method == "GET":
            return httpx.Response(200, json=self._bai_hs(b))
        if duong == "/bai-lam/tra-loi":
            if b["nop"]:
                return httpx.Response(409, json={"detail": {"ma": "DA_NOP", "thong_diep": "Bài làm đã nộp"}})
            da_luu, loi = self._luu(b, body["cau"])
            return httpx.Response(422 if loi else 200, json={
                "da_luu": da_luu, "loi": loi, "luu_luc": GIO.isoformat()})
        if duong == "/bai-lam/nop":
            if b["nop"] is None:
                da_luu, loi = self._luu(b, body["cau"])
                if loi:
                    return httpx.Response(422, json={"detail": {
                        "ma": "CAU_TRA_LOI_KHONG_HOP_LE", "thong_diep": "Có câu không hợp lệ", "loi": loi}})
                self._nop(b, "TAY")
            return httpx.Response(200, json=self._bai_hs(b))
        return httpx.Response(404, json={"detail": "?"})

    def _vao_thi(self, body: dict) -> httpx.Response:
        if self.chan_giay is not None:
            return httpx.Response(429, json={"detail": "Bạn nhập sai mã quá nhiều lần."},
                                  headers={"Retry-After": str(self.chan_giay)})
        ten = body["ho_ten"].strip()
        if not 2 <= len(ten) <= 100:
            return httpx.Response(422, json={"detail": [{"msg": "Họ tên dài từ 2 đến 100 ký tự"}]})
        ma = body["ma"].strip().upper()
        l = self.luot.get(ma)
        if l is None or not l["mo"]:
            return httpx.Response(404, json={"detail": "Mã không đúng hoặc bài thi đã đóng"})
        khoa = secrets.token_urlsafe(24)
        self.bai[khoa] = {"ma": ma, "ho_ten": ten, "tra_loi": {}, "nop": None}
        return httpx.Response(201, json={"khoa_bai_lam": khoa, "bai_lam": self._bai_hs(self.bai[khoa])})

    def _luu(self, b: dict, cau: list[dict]):
        n = len(self.luot[b["ma"]]["cau"])
        da_luu, loi = [], []
        for c in cau:
            if not 1 <= c["so_thu_tu"] <= n:
                loi.append({"so_thu_tu": c["so_thu_tu"], "ma": "KHONG_CO_CAU", "thong_diep": "Không có câu này"})
                continue
            if c["tra_loi"] is None:
                b["tra_loi"].pop(c["so_thu_tu"], None)
            else:
                b["tra_loi"][c["so_thu_tu"]] = c["tra_loi"]
            da_luu.append(c["so_thu_tu"])
        return da_luu, loi

    def _nop(self, b: dict, cach: str):
        cau = self.luot[b["ma"]]["cau"]
        dong = []
        for i, c in enumerate(cau, start=1):
            if c["dang"] == "TL":
                dong.append({"so_thu_tu": i, "trang_thai": "CHO_GIAO_VIEN_CHAM", "nhan": "Chưa chấm",
                             "diem": None, "diem_toi_da": None})
                continue
            dung = b["tra_loi"].get(i) == c["dap_an"]
            dong.append({"so_thu_tu": i, "trang_thai": "DUNG" if dung else "SAI",
                         "nhan": "Đúng" if dung else "Sai", "diem": 0.5 if dung else 0.0, "diem_toi_da": 0.5})
        diem = sum(d["diem"] or 0 for d in dong)
        b["nop"] = {"cach": cach, "ket_qua": {
            "tong_diem": diem, "tong_diem_toi_da": 0.5 * (len(cau) - 1),
            "so_cau_cho_cham": 1, "cau": dong}}

    def _bai_hs(self, b: dict) -> dict:
        l = self.luot[b["ma"]]
        chung = {"ho_ten": b["ho_ten"], "tieu_de": l["tieu_de"], "bat_dau_luc": GIO.isoformat(),
                 "han_nop_luc": (GIO + timedelta(minutes=l["phut"])).isoformat() if l["phut"] else None,
                 "thoi_gian_phut": l["phut"], "gio_may_chu": GIO.isoformat()}
        if b["nop"]:
            return {**chung, "trang_thai": "DA_NOP", "nop_luc": GIO.isoformat(), "cach_nop": b["nop"]["cach"],
                    "cau": None, "tra_loi": None, "ket_qua": b["nop"]["ket_qua"]}
        cau = []
        for i, c in enumerate(l["cau"], start=1):
            cau.append({"so_thu_tu": i, "dang": c["dang"], "de_bai": c["de_bai"],
                        "phuong_an": c["phuong_an"], "khoi_du_kien": c.get("khoi_du_kien", ""),
                        "dan_khoi_du_kien": c.get("dan_khoi_du_kien", ""), "nhom": c.get("nhom"),
                        "diem_toi_da": 0.5, "anh": c.get("anh", {}), "anh_co": c.get("anh_co", {})})
        return {**chung, "trang_thai": "DANG_LAM", "nop_luc": None, "cach_nop": None, "cau": cau,
                "tra_loi": [{"so_thu_tu": k, "tra_loi": v, "luu_luc": GIO.isoformat()}
                            for k, v in sorted(b["tra_loi"].items())], "ket_qua": None}
