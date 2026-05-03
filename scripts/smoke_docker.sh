#!/usr/bin/env bash
set -euo pipefail
export COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-video-analysis}
export DOCKER_BUILDKIT=${DOCKER_BUILDKIT:-0}
export COMPOSE_DOCKER_CLI_BUILD=${COMPOSE_DOCKER_CLI_BUILD:-0}

BASE_URL=${BASE_URL:-http://localhost:${APP_PORT:-8080}}
TIMEOUT=${TIMEOUT:-180}

echo "Validating compose config..."
docker compose config >/dev/null

echo "Building images..."
docker compose build backend frontend

echo "Starting stack..."
docker compose up -d --no-build

# If backend was recreated, Nginx may keep the old upstream IP until restart.
docker compose restart frontend >/dev/null

echo "Waiting for health at $BASE_URL/health"
end=$((SECONDS + TIMEOUT))
until curl -fsS "$BASE_URL/health" >/dev/null; do
  if [ "$SECONDS" -ge "$end" ]; then
    echo "Timed out waiting for backend health"
    docker compose ps
    docker compose logs --tail=120 backend worker frontend
    exit 1
  fi
  sleep 2
done

echo "Checking frontend..."
curl -fsS "$BASE_URL" >/dev/null

echo "Checking auth endpoint..."
EMAIL="smoke-$(date +%s)@example.com"
PASSWORD="smoke-$(date +%s)-$RANDOM"
COOKIE_JAR=$(mktemp)
curl -fsS -c "$COOKIE_JAR" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"display_name\":\"Smoke\"}" \
  "$BASE_URL/api/auth/register" >/dev/null
curl -fsS -b "$COOKIE_JAR" "$BASE_URL/api/auth/me" >/dev/null
rm -f "$COOKIE_JAR"

echo "Smoke test passed: $BASE_URL"
