#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export MOCK_APP_URL="${MOCK_APP_URL:-http://127.0.0.1:8000}"
export HEADLESS="${HEADLESS:-true}"
export CHAOS="${CHAOS:-0}"

# Load repo .env into the shell so child processes always see OPENAI_API_KEY.
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

uv run python scripts/seed_reset.py

# Boot mock app in background
uv run uvicorn mock_app.main:app --host 127.0.0.1 --port 8000 &
APP_PID=$!
cleanup() {
  kill "$APP_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for health
for i in $(seq 1 40); do
  if curl -sf "$MOCK_APP_URL/" >/dev/null; then
    break
  fi
  sleep 0.25
done

# Default task lives in cli.py — avoid nested quotes in bash.
if [[ $# -gt 0 ]]; then
  uv run python cli.py "$1"
else
  uv run python cli.py
fi
