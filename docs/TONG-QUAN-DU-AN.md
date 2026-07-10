# Tổng quan dự án — Chat Learning Toán (dtp-chat-learning-graph)

> Trợ lý học tập AI cho môn **Toán lớp 6** (chương trình Việt Nam), dựa trên nội dung Sách Giáo Khoa (SGK) chính thống.

---

## 1. Dự án này là gì?

**Chat Learning Toán** là hệ thống **RAG (Retrieval-Augmented Generation)** phục vụ dạy và học Toán lớp 6. Toàn bộ câu trả lời được **grounded (neo)** vào nội dung SGK thật, kèm **trích dẫn số trang**, nhằm hạn chế tối đa việc mô hình "bịa" (hallucination).

Ba năng lực cốt lõi:

1. **Hỏi đáp & giải bài Toán từng bước** — trả lời dựa trên đúng trang SGK, có trích dẫn `[tr.N]`.
2. **Sinh đề kiểm tra** cho giáo viên — bám theo **ma trận đặc tả** chính thức (phân bổ số câu theo mức độ khó một cách xác định, tính bằng code).
3. **Video AI ngắn minh hoạ câu trả lời** — công thức KaTeX + hoạt hình, sinh theo yêu cầu và cache theo khái niệm.

Toàn bộ giao diện, prompt và comment trong mã nguồn đều bằng **tiếng Việt**.

---

## 2. Công nghệ sử dụng

### Backend (Python ≥ 3.11, mục tiêu 3.12)
- **FastAPI** + **Uvicorn** — API server
- **LangGraph** (`langchain-core`) — điều phối luồng xử lý, checkpoint qua **Redis Stack** (cần RediSearch)
- **Qdrant** — vector DB lưu nội dung SGK đã ingest
- **PostgreSQL** — SQLAlchemy 2.0 async + `asyncpg` + **Alembic** (migration)
- **Celery** — worker chạy nền (ingest dữ liệu, render video)
- **SDK LLM**: dùng cả `anthropic` và `openai` để gọi **VNGCloud AI Platform (MaaS)** — không gọi thẳng Google
- Phụ trợ: `bcrypt` + `pyjwt` (auth), `python-docx` (đọc ma trận đề), `pillow` + `ffmpeg` (render video), `websockets` (đẩy trạng thái video)

### Frontend (`web/`)
- **React 18** + **TypeScript** + **Vite 5**
- **KaTeX** — render công thức Toán
- **Web Speech API** — nhập liệu bằng giọng nói (tiếng Việt)

### Hạ tầng
- Docker Compose, **nginx** phục vụ frontend tĩnh.

---

## 3. Cấu trúc thư mục

```
dtp-chat-learning-graph/
├── app/                 # Backend Python (xem mục 4)
├── web/                 # Frontend React/TS (xem mục 5)
├── alembic/             # Migration DB (alembic/versions/)
├── evals/               # Bộ đánh giá chất lượng (retrieval, ma trận, video)
├── tests/               # pytest (unit/mock + *_live.py gọi API thật, tự skip nếu thiếu key)
├── infra/               # backend.Dockerfile, frontend.Dockerfile, nginx.conf
├── data/                # books/ (ảnh trang SGK), matrix/ (.docx), videos/ (mp4)
├── data_processed/      # Cache OCR dạng markdown (chạy lại không cần OCR lại)
├── docs/                # Tài liệu (cost-estimate.md, file này…)
├── docker-compose.yml       # Hạ tầng dev: Qdrant + Redis Stack
├── docker-compose.app.yml   # Triển khai đầy đủ: api + worker + web + hạ tầng
└── .env.example             # Mẫu cấu hình
```

> Lưu ý: nội dung SGK **chỉ** nằm trong Qdrant. PostgreSQL giữ ma trận/phân loại/người dùng/lịch sử chat.

---

## 4. Kiến trúc Backend (`app/`)

### Điểm vào — `app/main.py`
FastAPI app; lifespan dựng sẵn LangGraph chat graph + Redis checkpointer một lần khi khởi động (`build_graph_with_redis`), lưu ở `app.state.graph`. Có CORS, `/health`. Router: `auth, chat, sessions, books, exam, video`.

### Cấu hình — `app/config.py`
`pydantic-settings` đọc `.env`: key/URL AI platform, tên model, Qdrant, Postgres, Redis, JWT, Langfuse, CORS và cấu hình video (`sgk_version`, `video_enabled`, `video_tts_voice`, min/max giây).

### Cổng LLM (LLM Gateway) — `app/llm/gateway.py`
**Điểm gọi model duy nhất** — các node **không** gọi SDK trực tiếp. Điểm đặc biệt: provider là **VNGCloud AI Platform**, và **mỗi model dùng một giao thức SDK khác nhau** (đã kiểm chứng thực tế trong `_PROTOCOL_BY_MODEL`):
- `gemini/gemini-2.5-pro` → giao thức Anthropic messages
- `gemini/gemini-2.5-flash`, `gemini-3.1-flash-lite`, `gemini-3.1-pro-preview` → OpenAI chat
- Embedding → OpenAI SDK (`text-embedding-3-large`, dim 3072)

Hai tầng qua `TASK_TIER`:
- **cheap**: `route_intent`, `qa`, `ocr_page`, `video_script`, `review_suggestion`
- **strong**: `solve`, `exam_gen`

Hàm chính: `complete(task, messages, …)`, `embed(texts)`. Gặp 429/quota → ném `LLMUnavailable` → API trả HTTP 503. `app/llm/cache.py` là semantic cache trên Redis cho các task cheap có thể cache.

### Chat graph — `app/graph/`
- `state.py` — `ChatState`; `Intent = hoi_dap | giai_bai | sinh_de | on_tap`
- `build.py` — luồng: `START → router → retrieve → {qa | solve | on_tap} → END`
- `router.py` — `route_intent`: **ưu tiên luật (regex/keyword)** rẻ & xác định, fallback sang LLM cheap
- `grounding.py` — `has_grounding()`, hằng `KHONG_TIM_THAY` (chặn bịa khi không có ngữ cảnh)
- `nodes/retrieve.py` — truy vấn Qdrant, ngưỡng điểm **0.4**, top_k=5, lọc `mon=toan, khoi=lop_6`
- `nodes/qa.py` — trả lời RAG kèm hướng dẫn trích dẫn `[tr.N]`, có semantic cache
- `nodes/solve.py` — giải từng bước (tầng **strong**)
- `nodes/on_tap.py` — ôn tập/tóm tắt + câu hỏi luyện tập
- `exam_build.py` / `exam_state.py` / `nodes/exam_gen.py` — **graph riêng có vòng lặp thật**: `exam_gen → check → (tiep_tuc → exam_gen | dung → END)`, giới hạn `MAX_LAN_LAP=3`

### Truy hồi — `app/retrieval/retriever.py`
`RetrievedChunk`; luôn lọc theo metadata (mon/khoi, tuỳ chọn sach/chuong/loai_noi_dung); embed truy vấn bằng đúng model dùng khi ingest.

### Sinh đề — `app/exam/`
`service.py` (`sinh_de`: nạp blueprint từ Postgres → tính số câu theo mức độ bằng **largest-remainder** → chạy exam graph), `blueprint.py`, `check.py` (`kiem_tra_ti_le`, `tinh_phan_thieu`), `matrix_loader.py`, `matrix_parser.py`. **Đếm số câu bằng code (xác định); LLM chỉ viết nội dung câu hỏi.**

### Ingestion (offline) — `app/ingestion/`
`cli.py` (`python -m app.ingestion.cli --tap 1 --sach … --pages 5-8 [--queue]`), `tasks.py` (`ingest_book`: PNG → OCR → cấu trúc chương/bài → chunk → embed → Qdrant), `loaders/vision_page_loader.py` (OCR có cache), `page_structure.py`, `chunking.py`, `qdrant_store.py`, `celery_app.py`.

### Video (Epic-09) — `app/video/`
- `concept.py` — ánh xạ câu hỏi tự do → `concept_key = {slug}::{sgk_version}` (cache 1 video/khái niệm dùng chung mọi học sinh)
- `pipeline.py` — `build_video_for_job`: câu trả lời grounded → script → guard → render → storage; mọi lỗi → FAILED (không publish video hỏng)
- `script.py` — `generate_script` → `Storyboard`/`Slide` JSON qua LLM
- `guard.py` — cổng xác định: mọi công thức trong script phải truy được về câu trả lời grounded (`check_formulas`, `check_script`)
- `animate.py` — hoạt hình giải thích (Pillow → ffmpeg → mp4 h264); validate KaTeX trước; lời thoại TTS hiển thị dạng phụ đề
- `render.py` (`katex_validate`, `latex_to_unicode`), `illustrations.py`, `tts.py` (macOS `say`, chỉ chạy trên host), `storage.py`, `cache.py` (vòng đời job QUEUED→RENDERING→DONE/FAILED), `tasks.py`

### CSDL — `app/db/models.py`
`Subject, Grade, Book, CurriculumTopic, Blueprint, BlueprintCell (nhom_ti_le, ti_le, so_cau), User (role hoc_sinh|giao_vien), ChatSession, Message (citations_json), VideoJob (concept_key+sgk_version unique)`.

### API — `app/api/`
- `auth.py` — register/login/me, JWT
- `chat.py` — `POST /chat`: chạy graph với `thread_id = {user_id}:{session_id}`, lưu message, gợi ý video qua `_maybe_video`
- `sessions.py` — lịch sử chat
- `books.py` — trả ảnh trang SGK cho trích dẫn
- `exam.py` — `POST /exam/generate` (chỉ giáo viên)
- `video.py` — `POST /video/generate` (theo yêu cầu), `GET /video/jobs/{id}`, `GET /video/files/{name}`, WebSocket `/video/ws/{job_id}`
- `deps.py` (`get_current_user`), `security.py`

---

## 5. Kiến trúc Frontend (`web/`)

Điểm vào `web/src/main.tsx` → `App.tsx`. Khôi phục phiên qua `/auth/me`, rồi định tuyến theo vai trò: **giáo viên → `ExamView`**, **học sinh → `ChatView`**.

- `api.ts` — fetch wrapper có type, JWT lưu localStorage (`tokenStore`)
- `config.ts` — `API_BASE` (từ `VITE_API_URL`)
- `types.ts` — type dùng chung (Role, ChatResponse, VideoInfo…)
- Component: `LoginView`, `ChatView`, `ExamView`, `Sidebar`, `MessageBubble`, `ChatInput`, `TopicPanel`, `BookPageModal` (xem lại trang SGK gốc của trích dẫn), `VideoBlock`
- `VideoBlock.tsx` — video theo yêu cầu: hiện nút "🎬 Tạo video minh hoạ" khi status=OFFERED; poll trạng thái mỗi 3s khi QUEUED/RENDERING; render `<video>` khi DONE
- `markdown.tsx` — markdown + chip trích dẫn (`📖 Trang N · Bài M`) + KaTeX
- `hooks/useSpeech.ts` — nhập giọng nói tiếng Việt
- `vite.config.ts` — proxy dev `/auth /chat /sessions /books /exam /video /health` → `localhost:8000`

---

## 6. Tính năng chính

1. **Hỏi đáp RAG grounded** kèm trích dẫn trang `[tr.N]`; từ chối trả lời ngoài ngữ cảnh SGK.
2. **Giải bài từng bước** (LLM tầng strong).
3. **Ôn tập (`on_tap`)** — intent thứ 4 của router (tóm tắt + câu hỏi luyện tập).
4. **Sinh đề** bám ma trận, đếm câu xác định, có vòng lặp sinh–kiểm tra.
5. **Video AI ngắn** — cache theo khái niệm, grounded (guard chặn công thức bịa), validate KaTeX, render ffmpeg kèm phụ đề; sinh theo yêu cầu, cập nhật trạng thái qua WebSocket/poll.
6. **Semantic cache** cho câu trả lời tầng cheap trên Redis.
7. **Auth & vai trò** (giao diện học sinh / giáo viên riêng), lịch sử chat.
8. **Nhập giọng nói** (tiếng Việt) và **xem ảnh trang SGK** từ trích dẫn.

---

## 7. Cách cài đặt & chạy

> Chi tiết đầy đủ trong [RUN.md](../RUN.md). Yêu cầu: Python 3.12, Docker Desktop, PostgreSQL native (host, cổng 5432), Node 20+, key VNGCloud AI Platform.

### Cách A — venv (dev)
```bash
# 1. Hạ tầng
createdb chat_learning
docker compose up -d                 # Qdrant :6333 + Redis Stack :6380 (bắt buộc Redis Stack cho RediSearch)

# 2. Môi trường Python
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Cấu hình
cp .env.example .env                 # điền AI_PLATFORM_API_KEY, JWT_SECRET, DATABASE_URL

# 4. Migration
alembic upgrade head

# 5. Ingest dữ liệu
python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8

# 6. Chạy
uvicorn app.main:app --reload --port 8000
celery -A app.ingestion.celery_app worker         # worker nền
cd web && npm install && npm run dev              # → http://localhost:5173
```

### Cách B — Docker (giống production)
```bash
docker compose -f docker-compose.app.yml up -d --build     # web :8080, api :8000
docker compose -f docker-compose.app.yml exec api alembic upgrade head
```
> Postgres vẫn chạy native trên host (truy cập qua `host.docker.internal`, biến `DATABASE_URL_DOCKER`). Worker video phải chạy trên host (cần `say`/ffmpeg/KaTeX của macOS).

### Test & Eval
```bash
pytest                                  # đầy đủ (cần hạ tầng + key)
python -m evals.run_retrieval_eval      # recall@5, ngưỡng 0.85
python -m evals.run_matrix_eval         # khớp ma trận 100%
```

---

## 8. Biến môi trường (`.env`)

| Biến | Ý nghĩa |
|------|---------|
| `AI_PLATFORM_API_KEY` | **Bắt buộc** — key VNGCloud AI Platform |
| `AI_PLATFORM_BASE_URL` | `https://maas-llm-aiplatform-hcm.api.vngcloud.vn` |
| `GEMINI_MODEL_CHEAP` | `gemini/gemini-3.1-flash-lite` (giữ prefix `gemini/`, bỏ sẽ 404) |
| `GEMINI_MODEL_STRONG` | `gemini/gemini-3.1-pro-preview` |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-large` (dim 3072 — đổi dim phải ingest lại Qdrant) |
| `QDRANT_URL` / `QDRANT_COLLECTION` | `http://localhost:6333` / `sgk_toan` |
| `DATABASE_URL` / `DATABASE_URL_DOCKER` | Postgres asyncpg (native / `host.docker.internal`) |
| `REDIS_URL` | `redis://localhost:6380/0` (Redis Stack, cổng 6380 tránh đụng Redis native :6379) |
| `JWT_SECRET` | ≥ 32 ký tự ngẫu nhiên |
| `LANGFUSE_*` | Observability (đã cấu hình, **chưa** đấu nối) |
| `CORS_ORIGINS` | Origin cho phép |

---

## 9. Ràng buộc & lưu ý đã biết

- **Giới hạn tier VNGCloud: ~50 request/ngày** → gặp HTTP **429** là bình thường, không phải bug (xem RUN.md §9).
- Tên model **phải giữ prefix `gemini/`**, nếu không sẽ 404.
- **Langfuse** đã cấu hình nhưng **chưa** đấu nối tracing.
- **k8s manifest** được nhắc trong spec nhưng **chưa** hiện thực.
- Nguồn chân lý của spec nằm ở repo anh em `dtp-chat-learning-tdd/specs/full-system-spec.md`.
- Comment trong mã nguồn phong phú, bằng tiếng Việt, thường trích số mục của spec và user story (US-16..US-19).
