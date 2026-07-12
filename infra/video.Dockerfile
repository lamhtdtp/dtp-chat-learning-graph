# Image RENDER VIDEO (Epic-09) cho Linux. Khác backend.Dockerfile: cài thêm công
# cụ media mà pipeline cần:
#   - ffmpeg           : ghép frame -> mp4, ghép tiếng TTS
#   - nodejs + katex   : app/video/render.py validate công thức (node -e require(katex))
#   - font DejaVu/Noto : vẽ chữ tiếng Việt (app/video/fonts.py tự chọn)
# TTS dùng cloud (VNGCloud) nên KHÔNG cần `say` của macOS.
#
# Worker chạy queue "video" (render_video route vào đây, xem celery_app.py):
#   celery -A app.ingestion.celery_app worker -Q video --loglevel=info
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs npm \
        fonts-dejavu-core fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY alembic ./alembic
RUN pip install --upgrade pip && pip install ".[itest]"

# KaTeX cho render.py — phải nằm đúng ./web/node_modules/katex (parents[2]/web/...).
# Cùng dòng katex 0.16 với frontend (web/package.json).
RUN mkdir -p web && cd web \
    && npm init -y >/dev/null 2>&1 \
    && npm install --no-audit --no-fund katex@0.16

# Logo đóng dấu góc video (tuỳ chọn; thiếu thì bỏ qua nhẹ nhàng).
COPY web/public ./web/public

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

CMD ["celery", "-A", "app.ingestion.celery_app", "worker", "-Q", "video", "--loglevel=info"]
