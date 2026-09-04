#!/usr/bin/env bash
# Helper deploy/vận hành trên SERVER DEV (Ubuntu + Docker).
# Gói sẵn cặp compose file (app + override dev-server) để khỏi gõ dài.
#
#   ./deploy.sh up                  # build + chạy nền (api, worker, web, redis, qdrant)
#   ./deploy.sh migrate             # alembic upgrade head (RDS)
#   ./deploy.sh ingest --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8
#   ./deploy.sh seed-matrix                     # nạp ma trận đặc tả
#   ./deploy.sh seed --phan --media              # soạn nội dung đủ 7 mục
#   ./deploy.sh seed --hinh-vi-du                # vẽ hình cho ví dụ hình học
#   ./deploy.sh phan-status --thieu              # còn thiếu mục nào
#   ./deploy.sh video-up            # bật worker render video (queue 'video')
#   ./deploy.sh pregen-video        # dựng sẵn video cho các khái niệm (inline)
#   ./deploy.sh requeue-video       # cứu job video mồ côi sau khi sửa REDIS_URL
#   ./deploy.sh llm-check           # 500 ở đường gọi AI? chạy cái này trước
#   ./deploy.sh logs api            # xem log 1 service
#   ./deploy.sh ps | down | restart | build | exec ...
set -euo pipefail

cd "$(dirname "$0")"

DC="docker compose -f docker-compose.app.yml -f docker-compose.dev-server.yml"

# Cảnh báo nếu chưa có .env
[ -f .env ] || echo "⚠️  Chưa có file .env ở gốc repo — xem DEPLOY-DEV.md §4."

cmd="${1:-help}"; shift || true

case "$cmd" in
  up)          $DC up -d --build "$@" ;;
  down)        $DC down "$@" ;;
  ps)          $DC ps "$@" ;;
  build)       $DC build "$@" ;;
  restart)     $DC restart "$@" ;;
  logs)        $DC logs -f "${@:-api}" ;;
  exec)        $DC exec "$@" ;;
  # Chạy một lệnh trong container MỚI (không cần service đang sống) — dùng cho
  # `alembic current` / `alembic downgrade`, xem docs/RUNBOOK-DEPLOY.md.
  run)         $DC run "$@" ;;

  migrate)     $DC run --rm --no-deps api alembic upgrade head ;;

  ingest)      # ./deploy.sh ingest --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8
               $DC run --rm worker python -m app.ingestion.cli "$@" ;;

  # ── Dựng lại nội dung bằng AI ─────────────────────────────────────────────
  # Chạy qua `worker` (không phải `api`): lệnh chạy hàng chục phút, để trong
  # request của api là treo cả web. `run --rm` nên không đụng worker đang chạy.
  seed-matrix) # nạp ma trận đặc tả -> yêu cầu cần đạt + ánh xạ đơn vị
               $DC run --rm worker python -m app.seed_matrix "$@" ;;
  seed)        # soạn nháp nội dung bài học bằng AI (idempotent, bỏ qua bài đã có)
               $DC run --rm worker python -m app.seed_all_lessons "$@" ;;
  phan-status) # còn thiếu mục nào ở bài nào (chạy sau mỗi lượt seed)
               $DC run --rm --no-deps worker python -m app.bao_cao_phan "$@" ;;

  video-up)    # worker render video on-demand (queue 'video')
               $DC up -d --build video ;;
  pregen-video)# dựng sẵn video cho mọi khái niệm (đồng bộ, không cần worker sống)
               $DC run --rm video python -m app.video.pregenerate --inline ;;
  requeue-video)# CỨU HỘ: đẩy lại job QUEUED bị mồ côi vì broker chết lúc tạo
               $DC run --rm worker python -m app.video.pregenerate --requeue ;;

  llm-check)   # 500 ở các đường gọi AI -> chạy cái này TRƯỚC khi đọc traceback
               $DC run --rm --no-deps api python -m app.llm.tu_kiem ;;

  health)      curl -fsS "${PUBLIC_API_URL:-http://localhost:8000}/health" && echo ;;

  help|*)
    cat <<'USAGE'
deploy.sh — lệnh vận hành server dev

  up [services...]        build + up -d (mặc định tất cả)
  down                    dừng, giữ volume
  ps                      trạng thái services
  build [services...]     build image
  restart [services...]   restart
  logs [service]          theo dõi log (mặc định: api)
  exec <svc> <cmd...>     exec vào container đang chạy
  run <args...>           docker compose run (vd: run --rm --no-deps api alembic current)

  migrate                 alembic upgrade head (chạy trên RDS qua container api)
  ingest <cli args...>    nạp SGK -> Qdrant (vd: ingest --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8)
  seed-matrix [args]      nạp ma trận đặc tả (yêu cầu cần đạt) + ánh xạ đơn vị
  phan-status [--thieu]   độ phủ 7 mục: bài nào thiếu mục nào, đã xuất bản chưa
  seed [args]             soạn nội dung bài học bằng AI. KHÔNG cờ = chỉ 2/7 mục!
                            --phan    + Khởi động/Hoạt động/Luyện tập/Bài tập
                            --media   + ảnh minh hoạ, đặt hàng video
                            --hinh-vi-du + hình cho ví dụ "như hình vẽ"
                            --force   SOẠN LẠI cả cái đã có (ghi đè chữ, giữ ảnh)
                            --publish xuất bản luôn (mặc định để nháp)
                          => đủ 7 mục: ./deploy.sh seed --phan --media
  video-up                bật worker render video (queue 'video')
  pregen-video            dựng sẵn video các khái niệm (inline)
  requeue-video           đẩy lại job video QUEUED mồ côi (Redis chết lúc tạo job)
  llm-check               tự kiểm LLM: key, danh sách model, gọi thử từng tầng
  health                  gọi /health (PUBLIC_API_URL hoặc localhost:8000)
USAGE
    ;;
esac
