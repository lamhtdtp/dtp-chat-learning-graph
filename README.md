# dtp-chat-learning-graph

Chat Learning — RAG hỏi đáp + giải bài Toán, sinh đề kiểm tra theo ma trận đặc tả.
Kiến trúc: FastAPI + LangGraph + Qdrant + Postgres + Redis + Gemini (chat, OCR, embedding).

Spec đầy đủ: xem repo `dtp-chat-learning-tdd/specs/full-system-spec.md` (kiến trúc, quyết định
công nghệ, backlog) và `dtp-chat-learning-tdd/CLAUDE.md` + `.claude/skills/*` (nguyên tắc/quy ước).

## Setup dev

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # điền GOOGLE_API_KEY và các credential khác
pytest
```

### Hạ tầng local (Postgres / Redis Stack / Qdrant)

Postgres dùng bản **native** (Homebrew) đã có sẵn ở cổng 5432. Qdrant và Redis Stack
chạy qua Docker. Lưu ý: Redis phải là **Redis Stack** (không phải Redis native) vì
checkpointer LangGraph cần module RediSearch — chạy ở cổng 6380 để không đụng Redis
native 6379 các project khác đang dùng.

```bash
brew services list                     # xác nhận postgresql@16 đang "started"
createdb chat_learning                 # tạo 1 lần — DB riêng cho project này

docker compose up -d                   # qdrant (6333) + redis-stack (6380)
curl localhost:6333/collections
docker compose exec redis redis-cli MODULE LIST | grep -i search   # xác nhận RediSearch
```

Nạp thử dữ liệu SGK vào Qdrant (OCR tốn token, pilot vài trang trước):

```bash
python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8   # inline
python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1 --queue        # qua Celery
```

Nạp cả sách nên chạy nền qua Celery (không chặn chat) — cần worker:

```bash
celery -A app.ingestion.celery_app worker --loglevel=info
```

### Eval (chất lượng, chạy riêng — không chặn merge)

```bash
python -m evals.run_retrieval_eval   # recall@5 trên dataset câu hỏi (ngưỡng 0.85)
python -m evals.run_matrix_eval      # khớp ma trận: đếm deterministic, ngưỡng 100%
```

Eval cũng chạy được qua pytest ở `tests/evals/` (skip nếu thiếu API key / Qdrant rỗng).
Khi đổi model embedding/prompt, chạy eval so baseline TRƯỚC khi merge.

### Đóng gói & chạy bằng Docker (production-shaped)

```bash
# build + chạy cả app (api + worker + web) và hạ tầng
cp .env.example .env   # điền AI_PLATFORM_API_KEY, JWT_SECRET...
docker compose -f docker-compose.app.yml up -d --build
# web: http://localhost:8080  ·  api: http://localhost:8000
```

Image: `infra/backend.Dockerfile` (API + worker dùng chung, khác lệnh chạy),
`infra/frontend.Dockerfile` (build tĩnh + nginx). `.dockerignore` loại data/ và
node_modules khỏi build context.

k8s manifest cho môi trường production (autoscale, HPA riêng ingestion/API — xem
`full-system-spec.md` mục 10) **chưa triển khai**, để sau khi docker-compose ổn định.

## Cấu trúc nhánh

Mỗi thành phần trong backlog (`full-system-spec.md` mục 14) phát triển trên 1 nhánh
`feature/<ten-thanh-phan>`, xem `git branch` để biết danh sách hiện có.
