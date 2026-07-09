# Chạy local — Chat Learning Toán

Hướng dẫn chạy toàn bộ hệ thống trên máy dev. Có **2 cách**:
- **A. Chạy trực tiếp (venv)** — tiện dev, nóng-nạp code. Đọc mục 1–6.
- **B. Chạy bằng Docker** — giống production. Đọc mục 7.

> Mọi lệnh chạy từ thư mục gốc repo. Các số đo/chi phí AI: xem `docs/cost-estimate.md`.
> ⚠️ VNGCloud giới hạn **50 request/ngày** ở tier hiện tại — OCR nhiều trang hoặc chat
> nhiều dễ chạm `HTTP 429`. Không phải lỗi code; chờ quota reset hoặc nâng tier.

---

## 0. Yêu cầu

- **Python 3.12** (khuyến nghị qua pyenv)
- **Docker Desktop** (chạy Qdrant + Redis Stack)
- **PostgreSQL** chạy sẵn trên máy (bản native Homebrew ở cổng 5432)
- **Node 20+** (chỉ cần cho frontend)
- **API key VNGCloud AI Platform** (LLM + embedding)

---

## 1. Hạ tầng

Postgres dùng bản **native** (đã có sẵn). Qdrant + Redis Stack chạy qua Docker.
Redis phải là **Redis Stack** (không phải Redis native) vì checkpointer LangGraph cần
module RediSearch — chạy ở cổng **6380** để không đụng Redis native 6379.

```bash
# Postgres native
createdb chat_learning                      # tạo 1 lần

# Qdrant (6333) + Redis Stack (6380) qua Docker
docker compose up -d
docker compose exec redis redis-cli MODULE LIST | grep -i search   # xác nhận RediSearch
curl -s localhost:6333/collections                                 # Qdrant sống
```

---

## 2. Cài đặt Python

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## 3. Cấu hình môi trường

```bash
cp .env.example .env
```

Mở `.env`, điền/kiểm:
- `AI_PLATFORM_API_KEY` — **bắt buộc** (LLM + embedding). Không có thì chat/ingest/embedding lỗi.
- `DATABASE_URL` — đổi user cho khớp Postgres máy bạn, ví dụ
  `postgresql+asyncpg://<user>@localhost:5432/chat_learning`.
- `REDIS_URL=redis://localhost:6380/0` (Redis Stack, cổng 6380).
- `QDRANT_URL=http://localhost:6333`.
- `JWT_SECRET` — chuỗi ngẫu nhiên ≥32 ký tự (`openssl rand -hex 32`).

---

## 4. Tạo schema (Postgres)

```bash
alembic upgrade head          # tạo bảng users/blueprints/curriculum_topics...
```

---

## 5. Nạp dữ liệu SGK (offline)

OCR tốn token + đụng rate limit → **chạy thử vài trang trước**:

```bash
# pilot vài trang (đủ để test chat)
python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8

# cả tập (chạm 50 req/ngày -> chia nhiều ngày hoặc dùng --queue qua worker)
python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1
```

Kết quả markdown OCR được cache ở `data_processed/` (chạy lại không gọi OCR lại).

(Tuỳ chọn) nạp ma trận đề vào Postgres cho tính năng sinh đề — hiện gọi qua code
`app.exam.matrix_loader.load_matrix(session, "data/matrix/TOAN_6_HK1.docx", hoc_ky="hk1")`.

---

## 6. Chạy ứng dụng

Mở 2–3 terminal (đều `source .venv/bin/activate` trước):

```bash
# Terminal 1 — API (FastAPI)
uvicorn app.main:app --reload --port 8000
# health: curl localhost:8000/health

# Terminal 2 — Celery worker (chỉ cần khi ingest qua --queue)
celery -A app.ingestion.celery_app worker --loglevel=info

# Terminal 3 — Frontend (Vite dev, proxy /auth /chat sang :8000)
cd web && npm install && npm run dev
# mở http://localhost:5173
```

Luồng thử: mở web → **Đăng ký** (email/mật khẩu, chọn Học sinh) → hỏi
"Tập hợp là gì?" → nhận câu trả lời bám SGK kèm trích dẫn trang.

---

## 7. Cách B — chạy bằng Docker (giống production)

Đóng gói app + Qdrant + Redis Stack. **Postgres KHÔNG chạy trong Docker** — dùng
Postgres native trên host (giống môi trường vận hành).

Trong container, `localhost` là chính container — muốn thấy Postgres trên host
phải dùng **`host.docker.internal`**. Compose đã đặt sẵn default
`DATABASE_URL_DOCKER=postgresql+asyncpg://lamthanh@host.docker.internal:5432/chat_learning`
(không đụng `DATABASE_URL=localhost` mà venv dùng). Chỉ đặt `DATABASE_URL_DOCKER`
trong `.env` nếu user/DB khác mặc định. Trên Docker Desktop (Mac/Win),
`host.docker.internal` tự tới host — thường KHÔNG cần chỉnh `listen_addresses`.
(Nếu container báo Postgres "connection refused": mở `listen_addresses`/`pg_hba`
cho phép kết nối từ Docker rồi restart Postgres.)

```bash
cp .env.example .env    # điền AI_PLATFORM_API_KEY, JWT_SECRET (DATABASE_URL_DOCKER có default)
docker compose -f docker-compose.app.yml up -d --build
# web:  http://localhost:8080
# api:  http://localhost:8000

# tạo schema lần đầu (chạy migration trong container api)
docker compose -f docker-compose.app.yml exec api alembic upgrade head

# nạp SGK (ảnh mount read-only vào worker qua ./data)
docker compose -f docker-compose.app.yml exec worker \
  python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8
```

---

## 8. Chạy test

```bash
# Toàn bộ (cần Postgres + Qdrant + Redis + API key còn quota)
pytest

# Chỉ unit/mock — không gọi API/infra thật (108 test, luôn chạy được)
pytest --ignore=tests/llm/test_gateway_live.py \
       --ignore=tests/retrieval/test_retriever_live.py \
       --ignore=tests/graph/test_build_live.py \
       --ignore=tests/evals/test_evals.py
```

Các test `*_live.py` (và `tests/evals/`) gọi API/infra thật; chúng tự **skip** khi
thiếu API key hoặc Qdrant rỗng, nhưng nếu chạm rate limit sẽ báo `429` — chờ quota
reset chứ không phải lỗi code.

---

## 9. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `unknown command 'FT._LIST'` | Redis native (không có RediSearch) | Dùng Redis Stack ở 6380 (mục 1) |
| `HTTP 429 API rate limit` | Chạm 50 req/ngày VNGCloud | Chờ reset / nâng tier / chia nhỏ |
| `404 model not found` | Tên model thiếu tiền tố `gemini/` | Giữ nguyên `gemini/...` trong `.env` |
| `role "..." does not exist` (Postgres) | `DATABASE_URL` sai user | Sửa user cho khớp Postgres máy bạn |
| Port 5432/6379 bận | Postgres/Redis native đang chạy | Đúng như thiết kế — dùng native 5432, Redis Stack ở 6380 |
