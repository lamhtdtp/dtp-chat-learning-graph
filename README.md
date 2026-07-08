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

## Cấu trúc nhánh

Mỗi thành phần trong backlog (`full-system-spec.md` mục 14) phát triển trên 1 nhánh
`feature/<ten-thanh-phan>`, xem `git branch` để biết danh sách hiện có.
