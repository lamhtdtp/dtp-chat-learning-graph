# Hướng dẫn deploy lên server DEV

Triển khai **Chat Learning Toán** lên 1 server **Ubuntu chạy Docker**, dùng:

- **1 Ubuntu** + Docker (chạy: API, Celery worker, web/nginx, **Qdrant**, và **Redis Stack**)
- **1 RDS PostgreSQL** (managed, ngoài) — lưu ma trận/taxonomy/users/lịch sử chat
- **1 Redis** (xem cảnh báo RediSearch ở [§3](#3-redis--bắt-buộc-có-redisearch))

> ⚠️ **Đọc trước 2 điểm dễ vướng:**
> 1. Dự án **còn cần Qdrant** (vector DB chứa nội dung SGK) — không chỉ Postgres + Redis. Hướng dẫn này chạy Qdrant bằng Docker ngay trên server.
> 2. Redis **bắt buộc có module RediSearch** (checkpointer LangGraph cần lệnh `FT._LIST`). **AWS ElastiCache Redis KHÔNG có** → sẽ lỗi. Mặc định hướng dẫn dùng **Redis Stack chạy bằng Docker** trên server (đã có RediSearch). Xem [§3](#3-redis--bắt-buộc-có-redisearch).

---

## Kiến trúc khi chạy

```
                    ┌──────────────── Ubuntu + Docker ─────────────────┐
  Trình duyệt ──▶ web:8080 (nginx, React tĩnh)                          │
       │          api:8000 (FastAPI) ──┬─▶ redis:6379 (Redis Stack, Docker)
       └────────────────────────────────┤                              │
                    worker (Celery) ─────┼─▶ qdrant:6333 (Docker)       │
                    └──────────────────────┼──────────────────────────┘
                                           ▼
                                  RDS PostgreSQL (ngoài, :5432)
```

Trình duyệt gọi **thẳng** api:8000 (không proxy qua web), nên `api` phải mở ra ngoài và URL của nó được "nướng" vào bản build web (biến `PUBLIC_API_URL`).

---

## 1. Chuẩn bị server Ubuntu

```bash
# Cài Docker Engine + plugin compose (Ubuntu 22.04/24.04)
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Cho user hiện tại chạy docker không cần sudo (đăng nhập lại sau lệnh này)
sudo usermod -aG docker $USER

# Kiểm tra
docker --version && docker compose version
```

**Mở cổng** (Security Group / ufw):
- Nếu có domain + nginx (khuyến nghị, xem [§13](#13-nginx-reverse-proxy--domain--https)): chỉ mở `80` và `443`; **đóng** `8000`/`8080` với public (chỉ nginx host truy cập qua `127.0.0.1`).
- Nếu truy cập trực tiếp bằng IP (không domain): mở `8080` (web) và `8000` (api).

---

## 2. RDS PostgreSQL

1. **Security Group của RDS**: cho phép inbound `5432` từ IP/Security Group của server Ubuntu.
2. **Tạo database** (nếu chưa có):
   ```bash
   # Từ server Ubuntu (cài psql client: sudo apt-get install -y postgresql-client)
   psql "postgresql://<master_user>:<pass>@<rds-endpoint>:5432/postgres" -c "CREATE DATABASE chat_learning;"
   ```
3. **Chuỗi kết nối** (dùng ở `.env`, driver **asyncpg**):
   ```
   DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<rds-endpoint>:5432/chat_learning
   ```
   - Mật khẩu có ký tự đặc biệt phải **URL-encode**: `@`→`%40`, `#`→`%23`, `/`→`%2F`…
   - RDS thường **bật SSL**: nếu kết nối lỗi, thêm `?ssl=require` vào cuối URL:
     `...:5432/chat_learning?ssl=require`

Migration schema sẽ chạy ở [§6](#6-chạy-migration-tạo-bảng).

---

## 3. Redis — BẮT BUỘC có RediSearch

Checkpointer của LangGraph (`langgraph-checkpoint-redis` → `redisvl`) cần module **RediSearch** (`FT._LIST`). Có 2 lựa chọn:

**A. (Khuyến nghị) Dùng Redis Stack chạy bằng Docker trên server** — đã bật sẵn trong compose, không cần làm gì thêm. Để trống `REDIS_URL` trong `.env`.

**B. Dùng Redis managed sẵn có của bạn** — CHỈ được nếu nó có RediSearch:
| Loại Redis | Có RediSearch? |
|---|---|
| Redis Stack (tự host) | ✅ |
| Redis Cloud / Redis Enterprise | ✅ |
| **AWS ElastiCache (Redis/Valkey)** | ❌ **không dùng được cho checkpointer** |
| Redis OSS thường (apt install redis) | ❌ |

Nếu Redis của bạn thuộc nhóm ✅, đặt trong `.env`:
```
REDIS_URL=redis://<redis-host>:6379/0
```
(và có thể bỏ service `redis` bundled cho gọn — xem [§10](#10-vận-hành)).

> Nếu không chắc, **cứ dùng phương án A** (Redis Stack Docker) cho dev — đơn giản và chắc chắn chạy.

---

## 4. Lấy mã nguồn + tạo `.env`

```bash
git clone <repo-url> dtp-chat-learning-graph
cd dtp-chat-learning-graph
```

Tạo file `.env` ở gốc repo:

```dotenv
# --- AI Platform (VNGCloud MaaS) ---
AI_PLATFORM_API_KEY=<key-that>
AI_PLATFORM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn

# --- RDS Postgres (asyncpg) ---
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<rds-endpoint>:5432/chat_learning

# --- Redis: để TRỐNG => dùng Redis Stack bundled (khuyến nghị).
# Chỉ điền nếu Redis ngoài CÓ RediSearch:
# REDIS_URL=redis://<redis-host>:6379/0

# --- Auth ---
JWT_SECRET=<chuoi-ngau-nhien-32+ky-tu>   # tạo: openssl rand -hex 32

# --- URL công khai (trình duyệt gọi tới) ---
# Truy cập bằng IP:
PUBLIC_API_URL=http://<SERVER_PUBLIC_IP>:8000
CORS_ORIGINS=http://<SERVER_PUBLIC_IP>:8080
# Có domain + nginx (§13): dùng CÙNG origin, hết CORS:
#   PUBLIC_API_URL=https://dev.example.com
#   CORS_ORIGINS=https://dev.example.com

# --- (Tuỳ chọn) i-Test quiz — xem §8 ---
# ITEST_DATABASE_URL=mysql+pymysql://<user>:<pass>@<host>:3306/<db>
```

> `PUBLIC_API_URL` được build-time nướng vào web (Vite). Đổi IP/domain → phải **build lại** service `web`.

---

## 5. Build & chạy

Dùng base + override cho server dev (Postgres = RDS):

```bash
docker compose -f docker-compose.app.yml -f docker-compose.dev-server.yml up -d --build
```

Lệnh này khởi động: `redis` (Redis Stack), `qdrant`, `api`, `worker`, `web`.

```bash
docker compose -f docker-compose.app.yml -f docker-compose.dev-server.yml ps
```

---

## 6. Chạy migration (tạo bảng)

```bash
docker compose -f docker-compose.app.yml -f docker-compose.dev-server.yml \
  exec api alembic upgrade head
```
Chạy trong container `api` → dùng đúng `DATABASE_URL` (RDS). Kết quả: tạo các bảng `subjects, grades, books, curriculum_topics, blueprints, blueprint_cells, users, chat_sessions, messages, video_jobs, itest_questions, itest_topic_map`.

---

## 7. Nạp dữ liệu SGK vào Qdrant (ingest)

Chat chỉ trả lời được khi Qdrant có nội dung SGK. Cần **ảnh trang SGK** trong `./data/books/...` (đã mount read-only vào container).

```bash
# Ví dụ nạp trang 5-8 tập 1
docker compose -f docker-compose.app.yml -f docker-compose.dev-server.yml \
  exec worker python -m app.ingestion.cli --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8
```
> Nạp học liệu cần gọi OCR + embedding qua AI Platform (tốn quota). Có thể nạp dần.

Nạp ma trận đề (cho tính năng sinh đề / gợi ý i-Test) — đặt file `.docx` trong `./data/matrix/` rồi chạy loader tương ứng (xem `app/exam/matrix_loader.py`).

---

## 8. (Tuỳ chọn) Bật i-Test quiz

Tính năng "Luyện tập với i-Test" query DB i-Test (MySQL) trực tiếp, **read-only**. Cần 2 việc:

1. **Thêm driver MySQL vào image backend** — sửa dòng cài trong `infra/backend.Dockerfile`:
   ```dockerfile
   RUN pip install --upgrade pip && pip install ".[itest]"
   ```
   (đưa `pymysql` vào image; mặc định image chỉ cài `.`).
2. **Cấu hình `.env`** với credential CHỈ-ĐỌC:
   ```
   ITEST_DATABASE_URL=mysql+pymysql://<user>:<pass>@<host>:3306/<db>
   ```
3. Rồi truyền biến này vào container: thêm `ITEST_DATABASE_URL: ${ITEST_DATABASE_URL:-}` vào `environment` của `api` (và `worker` nếu chạy đồng bộ) trong `docker-compose.dev-server.yml`, và **build lại**:
   ```bash
   docker compose -f docker-compose.app.yml -f docker-compose.dev-server.yml up -d --build api worker
   ```

Bỏ qua bước này thì tính năng i-Test tự tắt (chat vẫn chạy bình thường).

---

## 9. Kiểm tra

```bash
# API sống?
curl http://<SERVER_PUBLIC_IP>:8000/health        # -> {"status":"ok"}

# Web
# Mở trình duyệt: http://<SERVER_PUBLIC_IP>:8080  -> đăng ký/đăng nhập -> hỏi thử
```
Nếu web gọi API lỗi CORS/URL: kiểm `PUBLIC_API_URL` (đã build đúng chưa) và `CORS_ORIGINS` (khớp origin web).

---

## 10. Vận hành

```bash
BASE="-f docker-compose.app.yml -f docker-compose.dev-server.yml"

docker compose $BASE logs -f api        # xem log API
docker compose $BASE logs -f worker     # log Celery
docker compose $BASE restart api        # restart 1 service
docker compose $BASE down               # dừng tất cả (giữ volume)
docker compose $BASE up -d --build      # cập nhật code: kéo git rồi build lại
```

**Cập nhật mã nguồn:**
```bash
git pull
docker compose $BASE up -d --build
docker compose $BASE exec api alembic upgrade head   # nếu có migration mới
```

**Nếu dùng Redis ngoài** (§3-B) và muốn bỏ Redis bundled: chạy tường minh các service cần thiết:
```bash
docker compose $BASE up -d --build qdrant api worker web   # không khởi động 'redis'
```
(đảm bảo `REDIS_URL` trong `.env` trỏ Redis ngoài có RediSearch).

---

## 11. Render video minh hoạ (Epic-09) trên Linux

Task **render video** đi queue riêng `video`, cần `ffmpeg` + `node`+KaTeX + font tiếng Việt. Đã đóng gói sẵn trong **image riêng** [infra/video.Dockerfile](infra/video.Dockerfile) + service `video` (trong `docker-compose.dev-server.yml`). TTS dùng **cloud (VNGCloud)** nên **không cần `say` của macOS** → chạy được trên Linux. Font tự chọn theo máy ([app/video/fonts.py](app/video/fonts.py): DejaVu/Noto trên Linux).

```bash
# Bật worker render video (xử lý khi học sinh bấm "Tạo video")
./deploy.sh video-up          # = docker compose ... up -d --build video

# Dựng SẴN video cho các khái niệm trọng tâm (cache hit, học sinh không phải chờ)
./deploy.sh pregen-video      # = run --rm video python -m app.video.pregenerate --inline
```

- Cần Qdrant đã có nội dung SGK (video grounding từ đó) → nạp Qdrant (§7) trước khi pre-render.
- Lỗi 1 video (vd hết quota sinh ảnh) → job đó `FAILED`, **không** làm hỏng video khác / chat.
- Muốn tắt hẳn video ở dev: thêm `VIDEO_ENABLED=false` vào env `api`.

> Dùng `deploy.sh` cho gọn: `./deploy.sh up | migrate | ingest ... | video-up | pregen-video | logs | ps` (xem `./deploy.sh help`).

---

## 12. Bảng biến môi trường

| Biến | Bắt buộc | Ý nghĩa |
|---|---|---|
| `AI_PLATFORM_API_KEY` | ✅ | Key VNGCloud AI Platform |
| `AI_PLATFORM_BASE_URL` | ✅ | `https://maas-llm-aiplatform-hcm.api.vngcloud.vn` |
| `DATABASE_URL` | ✅ | RDS: `postgresql+asyncpg://user:pass@endpoint:5432/db` (SSL: `?ssl=require`) |
| `REDIS_URL` | — | Trống = Redis Stack bundled; hoặc Redis ngoài **có RediSearch** |
| `JWT_SECRET` | ✅ | ≥32 ký tự ngẫu nhiên |
| `PUBLIC_API_URL` | ✅ | URL api trình duyệt gọi (build-time cho web) |
| `CORS_ORIGINS` | ✅ | Origin của web (vd `http://IP:8080`) |
| `ITEST_DATABASE_URL` | — | Bật i-Test quiz (MySQL, read-only) — xem §8 |
| `EMBEDDING_MODEL` / `GEMINI_MODEL_*` | — | Override model (mặc định trong `app/config.py`) |

`QDRANT_URL` và (khi dùng bundled) `REDIS_URL` đã được compose set sẵn trỏ vào container nội bộ — không cần khai trong `.env`.

---

## 13. Nginx reverse proxy + domain + HTTPS

Đặt 1 nginx **trên host** làm cổng vào duy nhất cho 1 **domain**, gom web + api về **cùng origin** (hết CORS) và bật HTTPS. Sơ đồ:

```
Trình duyệt ──▶ https://dev.example.com (nginx host :80/:443)
                   ├─ /auth /chat /sessions /books /exam /video /itest /health ─▶ 127.0.0.1:8000 (api)
                   └─ mọi path khác (SPA + asset) ───────────────────────────────▶ 127.0.0.1:8080 (web)
```

### 13.1. Trỏ DNS
Tạo bản ghi **A** cho `dev.example.com` → IP công khai của server. Chờ DNS phân giải (`dig +short dev.example.com`).

### 13.2. Cài nginx + certbot
```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

### 13.3. Cấu hình site (dùng file mẫu trong repo)
```bash
sudo cp infra/nginx-dev-domain.conf.example /etc/nginx/conf.d/chat-learning.conf
sudo sed -i 's/dev.example.com/<DOMAIN_THẬT>/' /etc/nginx/conf.d/chat-learning.conf
sudo nginx -t && sudo systemctl reload nginx
```
File mẫu [infra/nginx-dev-domain.conf.example](infra/nginx-dev-domain.conf.example) đã route sẵn các tiền tố API sang `api:8000`, phần còn lại sang `web:8080`, kèm nâng cấp **WebSocket** cho `/video/ws/*` và nới `proxy_read_timeout` cho câu trả lời LLM lâu.

> Nếu Ubuntu dùng kiểu `sites-available/sites-enabled`: đặt file vào `/etc/nginx/sites-available/chat-learning` rồi `ln -s` sang `sites-enabled/` (và bỏ `default`). Dùng `conf.d/*.conf` thì không cần bước symlink.

### 13.4. Bật HTTPS (Let's Encrypt)
```bash
sudo certbot --nginx -d <DOMAIN_THẬT>
```
Certbot tự chèn block `listen 443 ssl` + chứng chỉ + chuyển hướng 80→443. Gia hạn tự động qua systemd timer (`systemctl status certbot.timer`).

### 13.5. Cập nhật `.env` rồi build lại web
Vì web gọi API **cùng domain**:
```dotenv
PUBLIC_API_URL=https://<DOMAIN_THẬT>
CORS_ORIGINS=https://<DOMAIN_THẬT>
```
```bash
docker compose -f docker-compose.app.yml -f docker-compose.dev-server.yml up -d --build web api
```
(`PUBLIC_API_URL` nướng vào lúc build nên **phải build lại `web`**; `CORS_ORIGINS` áp cho `api`.)

### 13.6. Khoá cổng nội bộ (nên làm)
Chỉ để nginx (80/443) ra ngoài, chặn public `8000`/`8080`:
```bash
sudo ufw allow 22,80,443/tcp
sudo ufw deny 8000/tcp
sudo ufw deny 8080/tcp
sudo ufw enable
```
> nginx host vẫn tới được api/web qua `127.0.0.1` dù container publish trên `0.0.0.0`, nên chặn public không ảnh hưởng proxy. (Trên cloud, nên chặn ở Security Group thay vì ufw.)

### 13.7. Kiểm tra
```bash
curl https://<DOMAIN_THẬT>/health           # -> {"status":"ok"} (qua nginx -> api)
# Mở trình duyệt: https://<DOMAIN_THẬT>      # web + chat, ổ khoá HTTPS xanh
```
Nếu 502: kiểm `docker compose ... ps` (api/web up chưa) và `sudo tail -f /var/log/nginx/error.log`.
