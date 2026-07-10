# Backend: FastAPI (API serving) + Celery worker (ingestion) dùng CHUNG image
# này, khác nhau ở lệnh chạy (xem docker-compose.app.yml). Tách 2 service để
# HPA/scale độc lập (API nhiều request nhỏ; worker batch nặng — nguyên tắc
# infra-observability Phần C).
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy source rồi cài (setuptools cần package app/ tồn tại lúc build wheel).
COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY alembic ./alembic
# Cài kèm extra [itest] (pymysql) để endpoint /itest/quiz query DB i-Test được.
RUN pip install --upgrade pip && pip install ".[itest]"

# Chạy dưới user không phải root
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Mặc định chạy API. Worker override command trong compose:
#   celery -A app.ingestion.celery_app worker --loglevel=info
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
