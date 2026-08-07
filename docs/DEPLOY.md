# Deploy lên PROD — bản "nền tảng giáo trình" (cập nhật từ bản chat cũ)

> Prod đã tồn tại từ phiên bản trước (bản **chat/RAG**). Đây là **bản cập nhật**
> lớn: bỏ chat/exam/books/itest, chuyển sang nền tảng giáo trình có cấu trúc +
> gamification + trợ lý hỏi–đáp SGK + CMS. Vì vậy deploy KHÔNG chỉ là "up lại"
> mà kèm **migration xoá bảng** và **reseed danh mục**. Đọc hết mục ⚠️ trước khi chạy.

Kiến trúc prod (giữ nguyên như trước): `docker-compose.app.yml` chạy **api :8000**,
**worker** (Celery), **web :8080**, **web-admin :8081**, **redis :6380**, **qdrant :6333**.
Postgres dùng **native trên host** (không trong compose).

---

## 0. ⚠️ Ảnh hưởng dữ liệu (đọc kỹ)

Migration mới sẽ **DROP** các bảng `chat_sessions`, `messages`, `itest_questions`,
`itest_topic_map` → **mất lịch sử chat + mirror i-Test** (các tính năng này đã bỏ).
Bước reseed danh mục (nếu chạy) sẽ **xoá & thay** `curriculum_topics` +
`blueprint_cells` + `topic_content` + `student_progress`.

Trên prod bản-chat-cũ thì `topic_content`/`student_progress`/`student_stats` **chưa tồn
tại** (migration mới tạo, rỗng) nên reseed gần như không mất dữ liệu học thật; thứ
mất là danh mục auto cũ (bẩn) + ma trận cũ + chat history. **Vẫn phải backup trước.**

```bash
# BACKUP Postgres (đổi user/db cho khớp DATABASE_URL prod)
pg_dump -U <user> chat_learning > backup_$(date +%F).sql
```

---

## 1. Lấy code mới
Bạn tự `git pull` trên server về đúng commit đã push.

## 2. Cập nhật `.env` (trên server, KHÔNG commit)
Các biến quan trọng cho prod:

| Biến | Ý nghĩa |
|---|---|
| `AI_PLATFORM_API_KEY` | Key VNGCloud MaaS (bắt buộc — quiz/AI ingest/tutor cần) |
| `DATABASE_URL_DOCKER` | Postgres native, dùng `host.docker.internal` (vd `postgresql+asyncpg://user@host.docker.internal:5432/chat_learning`) |
| `JWT_SECRET` | Chuỗi ngẫu nhiên ≥32 ký tự |
| `PUBLIC_API_URL` | URL API mà **trình duyệt** gọi (vd `https://api.giasu-dtp.vn`). Frontend build nhúng biến này |
| `CORS_ORIGINS` | Các origin web + admin (vd `https://giasu-dtp.vn,https://quan-tri.giasu-dtp.vn`) |
| `ADMIN_BASE` | `/` nếu admin ở domain riêng; `/quan-tri/` nếu chung domain dưới subpath |

`ITEST_DATABASE_URL` để trống (i-Test đã bỏ). `LANGFUSE_*` tuỳ chọn.

> Lưu ý bảo mật: từng phát hiện token GitHub trong `.git/config` dạng plaintext —
> đảm bảo prod **không** commit secret; chỉ đặt trong `.env` của server.

## 3. Build lại image (chưa chạy)
```bash
docker compose -f docker-compose.app.yml build
```

## 4. Chạy migration (BẮT BUỘC — không tự chạy)
Container chỉ chạy `uvicorn`, không tự migrate. Chạy 1 lần:
```bash
docker compose -f docker-compose.app.yml run --rm api alembic upgrade head
```
Đưa DB từ `c3d4e5f6a7b8` (bản cũ) → `c9d0e1f2a3b4`: thêm cột user admin,
`topic_content`/`student_progress`/`student_stats`, `quiz_json`, `hoc_ky`; **drop**
bảng chat + i-Test.

## 5. Nạp dữ liệu giáo trình (chạy 1 lần khi lên bản này)
Chạy trong container `api` (đã có sẵn code + kết nối DB):
```bash
# 5a. Danh mục sạch 21 đơn vị / 10 mạch (⚠️ thay danh mục cũ)
docker compose -f docker-compose.app.yml run --rm api python -m app.seed_curriculum

# 5b. Ma trận đặc tả (yêu cầu cần đạt + mức độ) map vào danh mục sạch
docker compose -f docker-compose.app.yml run --rm api python -m app.seed_matrix

# 5c. (tuỳ chọn) AI soạn nháp nội dung cho các đơn vị trống — trạng thái draft
docker compose -f docker-compose.app.yml run --rm api python -m app.seed_all_lessons

# 5d. Tạo tài khoản quản trị (nếu prod chưa có admin)
docker compose -f docker-compose.app.yml run --rm api \
  python -m app.create_admin --email admin@giasu-dtp.vn --password '<MẬT_KHẨU_MẠNH>' --name 'Quản trị'
```
> Các script idempotent: `seed_curriculum` chạy lại cho đúng 21 đơn vị;
> `seed_matrix` khớp lại không tạo trùng; `seed_all_lessons` chỉ soạn đơn vị còn trống.

## 6. Khởi động
```bash
docker compose -f docker-compose.app.yml up -d
# kiểm tra
curl -s https://api.giasu-dtp.vn/health   # {"status":"ok"}
docker compose -f docker-compose.app.yml ps
docker compose -f docker-compose.app.yml logs -f api | head -40
```

## 7. Video AI (tuỳ chọn) — worker chạy trên HOST
Render video cần công cụ media của host (TTS/KaTeX/ffmpeg) nên **không** chạy trong
container Linux. Nếu dùng video, chạy worker hàng đợi `video` bằng venv trên host
(trỏ REDIS_URL vào `redis://localhost:6380/0`, QDRANT vào `http://localhost:6333`):
```bash
.venv/bin/celery -A app.ingestion.celery_app worker -Q video --loglevel=info
```
Worker container trong compose xử lý hàng đợi mặc định (ingest SGK → Qdrant, cần cho
trợ lý hỏi–đáp). Nếu prod chưa ingest SGK, trợ lý sẽ trả "chưa tìm thấy trong SGK".

---

## Kiểm tra sau deploy (smoke test)
- `GET /health` → 200; `POST /chat` → **404** (đã gỡ, đúng).
- Web (:8080 / domain học sinh): đăng nhập → mục lục 21 đơn vị, bài "Số nguyên tố" xuất bản, trợ lý hỏi–đáp bên phải.
- Admin (:8081 / domain quản trị): đăng nhập admin → Chương trình & nội dung (KPI + bảng), mở "Sửa" thấy Yêu cầu cần đạt; Người dùng.

## Rollback
- Code: `git checkout <commit-cũ>` rồi build/up lại.
- DB: `alembic downgrade c3d4e5f6a7b8` (tái tạo lại bảng chat/itest **rỗng** — dữ liệu cũ đã mất, dùng bản `pg_dump` để phục hồi đầy đủ).

## Những thay đổi ảnh hưởng vận hành so với bản cũ
- Bỏ endpoint `/chat`, `/sessions`, `/exam`, `/books`, `/itest` → nếu reverse-proxy/nginx có route riêng cho chúng, gỡ đi (giờ 404).
- Thêm endpoint: `/curriculum`, `/lessons/*`, `/progress`, `/quiz/submit`, `/me/stats`, `/tutor/ask`, `/cms/*`.
- Không còn LangGraph checkpointer khi khởi động API (start nhanh hơn); Redis giờ chỉ dùng cho cache LLM + giới hạn lượt hỏi trợ lý + broker Celery.
