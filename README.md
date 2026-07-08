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

### Hạ tầng local (Postgres / Redis / Qdrant)

Postgres và Redis dùng bản **native** cài qua Homebrew (không chạy container riêng —
tránh trùng cổng 5432/6379 với service native đã có sẵn trên máy dev cho các project khác):

```bash
brew services list                     # xác nhận postgresql@16, redis đang "started"
createdb chat_learning                 # tạo 1 lần — DB riêng cho project này
redis-cli -n 1 ping                    # Redis DB index 1 (tránh đụng DB 0 của project khác)
```

Qdrant chưa có bản native tương đương nên chạy qua Docker:

```bash
docker compose up -d      # chỉ có qdrant, xem docker-compose.yml
curl localhost:6333/collections
```

k8s manifest cho môi trường production (autoscale, HPA riêng ingestion/API — xem
`full-system-spec.md` mục 10) **chưa triển khai**, để sau khi docker-compose ổn định.

## Cấu trúc nhánh

Mỗi thành phần trong backlog (`full-system-spec.md` mục 14) phát triển trên 1 nhánh
`feature/<ten-thanh-phan>`, xem `git branch` để biết danh sách hiện có.
