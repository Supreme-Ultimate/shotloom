#!/usr/bin/env bash
set -euo pipefail
PROJECT_NAME=${COMPOSE_PROJECT_NAME:-video-analysis}

STAMP=${1:-$(date +%Y%m%d-%H%M%S)}
OUT_DIR=${BACKUP_DIR:-backups/$STAMP}
mkdir -p "$OUT_DIR"

echo "Backing up PostgreSQL to $OUT_DIR/db.sql.gz"
docker compose exec -T postgres pg_dump -U video_analysis video_analysis | gzip > "$OUT_DIR/db.sql.gz"

echo "Backing up media volumes to $OUT_DIR/media.tar.gz"
docker run --rm \
  -v "${PROJECT_NAME}_app_uploads:/volumes/uploads:ro" \
  -v "${PROJECT_NAME}_app_shots:/volumes/shots:ro" \
  -v "${PROJECT_NAME}_app_thumbnails:/volumes/thumbnails:ro" \
  -v "$(pwd)/$OUT_DIR:/backup" \
  alpine sh -c 'tar -czf /backup/media.tar.gz -C /volumes uploads shots thumbnails'

echo "Backup complete: $OUT_DIR"
