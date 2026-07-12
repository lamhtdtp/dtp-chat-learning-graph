# Hướng dẫn: nạp (ingest) sách Tiếng Anh 6 vào hệ thống

Sách ảnh đã có sẵn: `data/books/english/6/*.png` (**132 trang**, i-Learn Smart World 6).
Luồng nạp: **ảnh trang → OCR (vision) → suy Unit/Bài → chunk → embed → Qdrant**
(giống Toán, xem `app/ingestion/`). Đã hỗ trợ đa môn — không cần đặt lại đường dẫn.

Khoá dùng: **`--mon tieng_anh --khoi lop_6 --tap 1 --sach smart_world_6`**.

---

## 0) Yêu cầu trước khi chạy
- **Qdrant đang chạy** (vector store). Bật hạ tầng bằng Docker:
  ```bash
  docker compose -f docker-compose.app.yml up -d qdrant redis
  # kiểm tra: mở http://localhost:6333/dashboard hoặc:
  curl -s http://localhost:6333/collections
  ```
- **`.env` có `AI_PLATFORM_API_KEY`** (OCR + embedding gọi qua VNGCloud). Postgres KHÔNG cần cho bước ingest (chỉ Qdrant).
- **venv** đã cài phụ thuộc:
  ```bash
  source .venv/bin/activate
  ```
> Ghi chú chi phí: OCR 132 trang tốn token/gọi API. **Luôn chạy PILOT vài trang trước.**

## 1) Pilot — OCR thử 5 trang, xem chất lượng
```bash
PYTHONPATH=. python -m app.ingestion.cli \
  --mon tieng_anh --khoi lop_6 --tap 1 --sach smart_world_6 --pages 5-9
```
Kết quả markdown mỗi trang được cache tại `data_processed/english/tap1/<trang>.md`.
Mở vài file kiểm tra OCR có đúng (tiếng Anh giữ nguyên, tiêu đề Unit/Lesson thành heading):
```bash
ls data_processed/english/tap1/
sed -n '1,40p' data_processed/english/tap1/7.md
```
Nếu OCR tốt → chạy tiếp bước 2. Nếu chưa ưng, chỉnh prompt trong
`app/ingestion/loaders/vision_page_loader.py` (`_GENERAL_PROMPT`) rồi chạy lại
pilot với `--force-ocr` để OCR lại (bỏ cache).

## 2) Nạp toàn bộ 132 trang
**Cách A — chạy inline** (đơn giản, thấy log ngay; các trang pilot đã cache sẽ bỏ qua OCR):
```bash
PYTHONPATH=. python -m app.ingestion.cli \
  --mon tieng_anh --khoi lop_6 --tap 1 --sach smart_world_6
# -> "Đã ghi N chunk vào Qdrant."
```
**Cách B — chạy nền qua Celery** (không chặn, đúng nguyên tắc nạp sách chạy nền):
```bash
# terminal 1: worker
PYTHONPATH=. celery -A app.ingestion.celery_app worker --loglevel=info
# terminal 2: đẩy job
PYTHONPATH=. python -m app.ingestion.cli \
  --mon tieng_anh --khoi lop_6 --tap 1 --sach smart_world_6 --queue
```

## 3) Kiểm tra dữ liệu đã vào Qdrant
```bash
PYTHONPATH=. python - <<'PY'
import asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from app.config import settings

async def main():
    c = AsyncQdrantClient(url=settings.qdrant_url)
    total = await c.count(settings.qdrant_collection,
        count_filter=Filter(must=[FieldCondition(key="mon", match=MatchValue(value="tieng_anh"))]))
    print("Số chunk Tiếng Anh trong Qdrant:", total.count)
asyncio.run(main())
PY
```
Chunk Tiếng Anh nằm CHUNG collection `sgk_toan` nhưng mang `payload.mon="tieng_anh"`,
truy vấn lọc theo `mon` nên không lẫn với Toán.

## 4) (Tuỳ chọn) Nạp lại / cập nhật
- OCR lại 1 dải trang khi cần: thêm `--pages 40-45 --force-ocr`.
- Ingest **idempotent** ở tầng OCR (cache theo trang) và Qdrant (id điểm ổn định theo trang/chunk) — chạy lại an toàn.

---

## Lưu ý quan trọng (để "tạo data" xong thì DÙNG được trong chat)
Nạp Qdrant mới chỉ là **có dữ liệu**. Để học sinh chat được môn Tiếng Anh còn cần
2 bước wiring (CHƯA làm — backend hiện chỉ phục vụ Toán):
1. **Mở khoá môn Anh ở UI**: đặt `unlocked: true` cho `anh` trong `web/src/subjects.ts`
   (hiện đang "Sắp ra mắt").
2. **Truyền `mon` theo môn vào retrieval**: hiện `retrieve_node` lọc cứng
   `mon="toan"`. Cần cho graph nhận `mon` từ phiên chat (ChatRequest đã có
   `subject`) và map `anh -> tieng_anh` khi filter Qdrant, để câu hỏi môn Anh
   truy đúng chunk Tiếng Anh.

Nói mình nếu muốn làm tiếp 2 bước wiring này sau khi ingest xong.
