"""Client dịch vụ PHÁT ĐỀ của DTP Testbank — đường ĐỐI TÁC `/doi-tac/*`, mức 1 (US-30).

Khác mức 0 (`delivery.py`, đường học sinh): không có khoá bài làm. Máy chủ learning đăng nhập bằng
tài khoản dịch vụ (vai `DOI_TAC_ON_LUYEN`, token do `TestbankClient` giữ — dùng chung với mọi lời
gọi Testbank khác), vào thi kèm mã + họ tên của học sinh, nhận `bai_lam_id`; mọi lời gọi sau gắn id
đó vào URL. Testbank tự bảo đảm mỗi học sinh một bài trên mỗi lượt phát (vào lại trả đúng bài cũ),
nên mất phản hồi giữa chừng thì gọi lại là an toàn.

Đối chiếu mã Testbank thật: `services/delivery/.../routers/doi_tac.py` và `schemas.py`. Lưu ý bí
mật: `bai_lam_id` nằm trong URL nên KHÔNG ghi URL vào log (kể cả log INFO của chính `httpx`, tắt ở
cuối file) — chỉ ghi đường mẫu, mã trạng thái và độ trễ.
"""
import logging
import time
from typing import Any

from app.integrations.testbank.client import TestbankClient, TestbankLoi
from app.integrations.testbank.delivery import TIMEOUT, DeliveryClient, DeliveryLoi

log = logging.getLogger(__name__)

# `httpx` ghi "HTTP Request: GET <url>" ở mức INFO — URL có mã bài làm Testbank (US-30 KB 23).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

#: Mã lỗi nghiệp vụ Testbank (`detail.ma`) learning phải phân biệt.
MA_KHONG_DUNG = "MA_KHONG_DUNG"
MA_HS_NHAP_SAI_NHIEU = "NHAP_SAI_QUA_NHIEU"
MA_DOI_TAC_NHAP_SAI_NHIEU = "DOI_TAC_NHAP_SAI_QUA_NHIEU"
MA_KHONG_THAY_BAI = "KHONG_TIM_THAY_BAI_LAM"


class DoiTacClient:
    """`goc` là gốc dịch vụ phát đề (cùng `TESTBANK_DELIVERY_URL` của mức 0); `tb` giữ token."""

    def __init__(self, goc: str, tb: TestbankClient):
        self.goc = goc.strip().rstrip("/")
        self._tb = tb

    async def _goi(self, method: str, duong_mau: str, duong: str, body: Any = None) -> Any:
        """`duong_mau` (không có id) để ghi log, `duong` là đường thật."""
        t0 = time.monotonic()
        try:
            r = await self._tb.goi_tho(method, f"{self.goc}/doi-tac{duong}", body=body, timeout=TIMEOUT)
        except TestbankLoi as e:
            log.warning("doi-tac %s %s loi_ket_noi %.0fms", method, duong_mau, (time.monotonic() - t0) * 1000)
            # Mạng hỏng: tạm thời. Đăng nhập bị từ chối / thiếu cấu hình: thử lại không khỏi.
            raise DeliveryLoi(None if e.tam_thoi else 401, ma="TOKEN", thong_diep=str(e)) from e
        log.info("doi-tac %s %s -> %s %.0fms", method, duong_mau, r.status_code, (time.monotonic() - t0) * 1000)
        return DeliveryClient._kiem(r)

    async def vao_thi(self, ma: str, hoc_sinh_ma: str, ho_ten: str) -> tuple[str, bool, dict]:
        """`(bai_lam_id, vao_lai, BaiLamHs)`. Gọi lại cho cùng (học sinh, mã) trả đúng bài cũ."""
        d = await self._goi("POST", "/vao-thi", "/vao-thi",
                               {"ma": ma, "hoc_sinh": {"ma": hoc_sinh_ma, "ho_ten": ho_ten}})
        return d["bai_lam_id"], bool(d.get("vao_lai")), d["bai_lam"]

    async def xem(self, bai_id: str) -> dict:
        return await self._goi("GET", "/bai-lam/{id}", f"/bai-lam/{bai_id}")

    async def luu(self, bai_id: str, cau: list[dict]) -> dict:
        # 422 của Testbank KHÔNG phải lỗi: có câu sai định dạng nhưng các câu hợp lệ khác ĐÃ lưu,
        # thân vẫn là LuuOut (như đường học sinh).
        try:
            return await self._goi("PUT", "/bai-lam/{id}/tra-loi", f"/bai-lam/{bai_id}/tra-loi",
                                   {"cau": cau})
        except DeliveryLoi as e:
            if e.status == 422 and e.luu_out is not None:
                return e.luu_out
            raise

    async def nop(self, bai_id: str, cau: list[dict]) -> dict:
        return await self._goi("POST", "/bai-lam/{id}/nop", f"/bai-lam/{bai_id}/nop", {"cau": cau})

    async def chi_tiet(self, bai_id: str) -> dict:
        """T5: chi tiết bài ĐÃ NỘP. Chưa nộp -> 409 `CHUA_NOP`; quá 30 ngày sau khi đóng -> 410."""
        return await self._goi("GET", "/bai-lam/{id}/chi-tiet", f"/bai-lam/{bai_id}/chi-tiet")
