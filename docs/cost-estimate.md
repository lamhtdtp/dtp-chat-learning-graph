# Ước lượng chi phí AI — Chat Learning Toán

> Cập nhật: 2026-07-09. Dựa trên **token đo thật** qua VNGCloud AI Platform (mục 1),
> áp đơn giá tham chiếu (mục 2). VNGCloud tính theo **credit (1 credit = 1 VND)** và
> **không công bố đơn giá/token công khai** — số USD/VND dưới đây là **ước lượng tham
> khảo**, phải xác nhận lại trên Console VNGCloud trước khi cam kết ngân sách.

## 0. Cảnh báo giới hạn quan trọng

- **Rate limit 50 request/ngày** trên tier hiện tại (theo docs VNGCloud/GreenNode). OCR
  cả sách = **294 request** → KHÔNG chạy hết trong 1 ngày ở tier này. Cần: (a) nâng tier,
  hoặc (b) chia nhỏ nhiều ngày (~6 ngày), hoặc (c) xin tăng quota. Đây là chặn thực tế
  lớn hơn cả chi phí tiền.
- `gemini-2.5-flash-lite` từng bị `IAM_PERMISSION_DENIED` — đang dùng `gemini-3.1-flash-lite`
  (rẻ) + `gemini-3.1-pro-preview` (mạnh). Nếu đổi model, đo lại token.

## 1. Token đo thật (không phải giả định)

Đo trực tiếp qua API ngày 2026-07-09 trên trang SGK thật:

| Hạng mục | Model | Input token | Output token | Ghi chú |
|---|---|---|---|---|
| OCR 1 trang | `gemini-3.1-flash-lite` | **~1.241** | **~348** (dao động 154–506) | input gần như cố định (ảnh ~1.024 + prompt ~217); output tuỳ mật độ chữ/công thức |
| Embedding 1 chunk | `gemini-embedding-001` | ~21 (mẫu ngắn) → **ước ~150** (chunk thật) | — | chunk thật dài hơn mẫu; dim 3072 |
| 1 lượt hỏi-đáp (qa) | `gemini-3.1-flash-lite` | **~1.200** (5 chunk ngữ cảnh + câu hỏi + system) | **~500** | |
| 1 lượt giải bài (solve) | `gemini-3.1-pro-preview` | ~1.500 | **~2.500** (gồm ~2.000 reasoning token ẩn) | tầng mạnh, đắt hơn nhiều |

**Quy mô dữ liệu**: Tập 1 = 151 trang, Tập 2 = 143 trang → **294 trang**. Ước ~3 chunk/trang
nội dung → **~800–900 chunk** cho cả 2 tập.

## 2. Đơn giá tham chiếu (CẦN xác nhận VNGCloud)

Chưa có giá VNGCloud công khai. Dùng **đơn giá Google Gemini công bố làm proxy** (USD/1 triệu
token), tỉ giá ~25.400 VND/USD:

| Model | Input ($/1M) | Output ($/1M) | Nguồn |
|---|---|---|---|
| flash-lite (tầng rẻ) | ~0,10 | ~0,40 | proxy theo dòng flash-lite |
| pro-preview (tầng mạnh) | ~1,25 | ~10,00 | proxy theo dòng pro |
| embedding | ~0,15 | — | ai.google.dev |

> ⚠️ Đây là proxy. VNGCloud có thể tính khác (thường cộng phụ phí gateway). Công thức ở
> mục 3–4 giữ nguyên đúng khi thay đơn giá thật vào.

## 3. Chi phí MỘT LẦN — nạp sách (offline)

**OCR cả 294 trang** (flash-lite):
- Input: 294 × 1.241 = 364.854 token ≈ 0,365M → 0,365 × $0,10 = **$0,037**
- Output: 294 × 348 = 102.312 token ≈ 0,102M → 0,102 × $0,40 = **$0,041**
- **OCR ≈ $0,078 (~2.000 VND)** cho cả 2 tập.

**Embedding ~880 chunk**: 880 × 150 = 132.000 token ≈ 0,132M × $0,15 = **$0,02 (~500 VND)**.

**→ Tổng nạp cả bộ sách ≈ $0,10 (~2.500 VND), chạy 1 lần.** Không đáng kể về TIỀN — nhưng
vướng rate limit 50 req/ngày (mục 0). Nạp thêm sách khác thì nhân tuyến tính (mỗi cuốn
~150–300 trang ≈ vài nghìn VND).

## 4. Chi phí HÀNG THÁNG — phục vụ chat (online)

Giả định pilot: **300 học sinh × 8 câu/ngày × 26 ngày = 62.400 lượt/tháng**.

Chi phối chi phí là **tỉ lệ câu đi vào tầng mạnh** (solve/sinh đề, `pro-preview` đốt reasoning
token). Router phân loại chủ yếu bằng rule (miễn phí); embedding câu hỏi ~20 token (không đáng kể).

| Kịch bản | qa (flash-lite) | solve (pro-preview) | Ước tính/tháng |
|---|---|---|---|
| 100% hỏi-đáp | 62.400 × ~$0,00032 ≈ **$20** | 0 | **~$20 (~0,5 tr VND)** |
| 80% hỏi-đáp / 20% giải bài | 49.920 × $0,00032 ≈ $16 | 12.480 × ~$0,027 ≈ $337 | **~$353 (~9 tr VND)** |
| 50% / 50% | 31.200 × $0,00032 ≈ $10 | 31.200 × $0,027 ≈ $842 | **~$852 (~21,6 tr VND)** |

Chi tiết đơn giá/lượt:
- qa: 1.200×$0,10/M + 500×$0,40/M ≈ **$0,00032/câu**
- solve: 1.500×$1,25/M + 2.500×$10/M ≈ **$0,027/câu** (~84× đắt hơn qa, do reasoning token)

## 5. Kết luận & khuyến nghị

1. **Nạp sách gần như miễn phí về tiền** (~2.500 VND cả bộ) — đừng ngại chi phí OCR. Chặn
   thật là **rate limit 50 req/ngày**: xin nâng quota trước khi OCR 294 trang, hoặc chia ~6 ngày.
2. **Đòn bẩy chi phí lớn nhất = tầng mạnh (`pro-preview`)**. Mỗi câu giải bài đắt gấp ~84× câu
   hỏi-đáp. Cần: (a) chỉ route sang solve khi thật sự là bài tập (router đã làm), (b) cân nhắc
   giới hạn `max_tokens` reasoning, (c) bật **semantic cache** (đã thiết kế, chưa làm) cho câu
   lặp — giảm mạnh chi phí ở tầng mạnh.
3. **Xác nhận đơn giá thật trên Console VNGCloud** rồi thay vào mục 2 — số ở đây là proxy.
4. Chạy **pilot 1 chương (~15 trang)** đo chi phí thật/độ chính xác OCR trước khi nạp cả bộ.

## Phụ lục — cách đo lại

Token đo bằng script gọi trực tiếp endpoint (đọc `usage` từ OpenAI-compatible response).
Chạy lại khi đổi model/prompt. Giữ file này cập nhật cùng lúc với thay đổi model trong
`app/config.py`.
