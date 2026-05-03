#!/usr/bin/env bash
set -euo pipefail
PROJECT_NAME=${COMPOSE_PROJECT_NAME:-video-analysis}

BACKUP_DIR=${1:?Usage: scripts/restore.sh backups/YYYYmmdd-HHMMSS}
[ -f "$BACKUP_DIR/db.sql.gz" ] || { echo "Missing $BACKUP_DIR/db.sql.gz"; exit 1; }
[ -f "$BACKUP_DIR/media.tar.gz" ] || { echo "Missing $BACKUP_DIR/media.tar.gz"; exit 1; }

echo "Restoring PostgreSQL from $BACKUP_DIR/db.sql.gz"
gunzip -c "$BACKUP_DIR/db.sql.gz" | docker compose exec -T postgres psql -U video_analysis -d video_analysis

echo "Restoring media volumes from $BACKUP_DIR/media.tar.gz"
docker run --rm \
  -v "${PROJECT_NAME}_app_uploads:/volumes/uploads" \
  -v "${PROJECT_NAME}_app_shots:/volumes/shots" \
  -v "${PROJECT_NAME}_app_thumbnails:/volumes/thumbnails" \
  -v "$(pwd)/$BACKUP_DIR:/backup:ro" \
  alpine sh -c 'cd /volumes && tar -xzf /backup/media.tar.gz'

echo "Restore complete"
