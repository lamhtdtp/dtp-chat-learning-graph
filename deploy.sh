#!/usr/bin/env bash
# Helper deploy/vận hành trên SERVER DEV (Ubuntu + Docker).
# Gói sẵn cặp compose file (app + override dev-server) để khỏi gõ dài.
#
#   ./deploy.sh up                  # build + chạy nền (api, worker, web, redis, qdrant)
#   ./deploy.sh migrate             # alembic upgrade head (RDS)
#   ./deploy.sh ingest --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8
#   ./deploy.sh video-up            # bật worker render video (queue 'video')
#   ./deploy.sh pregen-video        # dựng sẵn video cho các khái niệm (inline)
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

  migrate)     $DC run --rm --no-deps api alembic upgrade head ;;

  ingest)      # ./deploy.sh ingest --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8
               $DC run --rm worker python -m app.ingestion.cli "$@" ;;

  video-up)    # worker render video on-demand (queue 'video')
               $DC up -d --build video ;;
  pregen-video)# dựng sẵn video cho mọi khái niệm (đồng bộ, không cần worker sống)
               $DC run --rm video python -m app.video.pregenerate --inline ;;

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

  migrate                 alembic upgrade head (chạy trên RDS qua container api)
  ingest <cli args...>    nạp SGK -> Qdrant (vd: ingest --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8)
  video-up                bật worker render video (queue 'video')
  pregen-video            dựng sẵn video các khái niệm (inline)
  health                  gọi /health (PUBLIC_API_URL hoặc localhost:8000)
USAGE
    ;;
esac
