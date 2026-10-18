"""Lấy nội dung câu — `POST /questions:resolve` của content-service.

- Tối đa 200 QID mỗi lần (quá thì 422) -> chia lô.
- Kết quả giữ đúng thứ tự QID gửi lên.
- QID không thuộc kho mình thấy bị BỎ QUA LẶNG LẼ. Chỗ gọi phải so số câu nhận
  được với số đã gửi để phát hiện.
- `include_answers=True` mới có `answer_key` + `explanation`. Hai trường đó chỉ
  được ở máy chủ learning, không bao giờ xuống trình duyệt trước khi nộp.
"""
from app.integrations.testbank.client import TestbankClient

_LO = 200


async def lay_cau(tb: TestbankClient, qids: list[str], *, include_answers: bool = True) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(qids), _LO):
        lo = qids[i:i + _LO]
        out.extend(await tb.goi("content", "/questions:resolve",
                                {"qids": lo, "include_answers": include_answers}))
    return out
