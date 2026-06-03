#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[deploy] Pulling latest images and building services"
docker compose pull || true
docker compose build

echo "[deploy] Applying migrations"
docker compose run --rm api alembic upgrade head

echo "[deploy] Restarting stack"
docker compose up -d --remove-orphans

echo "[deploy] Health check"
curl -fsS http://127.0.0.1:8000/health && echo

echo "[deploy] Done"
