#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Capture caller overrides BEFORE sourcing .env (which may set CHAOS=0).
_CALLER_CHAOS="${CHAOS-}"
_CALLER_HEADLESS="${HEADLESS-}"
_CALLER_MOCK_URL="${MOCK_APP_URL-}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

# Restore intentional overrides from `make chaos-demo` etc.
if [[ -n "${_CALLER_CHAOS}" ]]; then
  export CHAOS="${_CALLER_CHAOS}"
fi
if [[ -n "${_CALLER_HEADLESS}" ]]; then
  export HEADLESS="${_CALLER_HEADLESS}"
fi
if [[ -n "${_CALLER_MOCK_URL}" ]]; then
  export MOCK_APP_URL="${_CALLER_MOCK_URL}"
fi

export MOCK_APP_URL="${MOCK_APP_URL:-http://127.0.0.1:8000}"
export HEADLESS="${HEADLESS:-true}"
export CHAOS="${CHAOS:-0}"

if [[ -z "${OPENAI_API_KEY:-}" || "${OPENAI_API_KEY}" == sk-... ]]; then
  echo "OPENAI_API_KEY missing. Copy .env.example → .env and set your key." >&2
  exit 2
fi

echo "Starting demo (CHAOS=${CHAOS}, HEADLESS=${HEADLESS}, MOCK_APP_URL=${MOCK_APP_URL})"

uv run python scripts/seed_reset.py

# Boot mock app in background with explicit CHAOS for the child process.
CHAOS="${CHAOS}" MOCK_APP_URL="${MOCK_APP_URL}" \
  uv run uvicorn mock_app.main:app --host 127.0.0.1 --port 8000 &
APP_PID=$!
cleanup() {
  kill "$APP_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for /health
for _ in $(seq 1 40); do
  if curl -sf "${MOCK_APP_URL}/health" >/dev/null; then
    break
  fi
  sleep 0.25
done

if ! curl -sf "${MOCK_APP_URL}/health" >/dev/null; then
  echo "Mock app failed to become healthy at ${MOCK_APP_URL}/health" >&2
  exit 1
fi

PRIMARY_DEFAULT='Find the latest invoice from Acme Corp in the mail app, extract amount and due date, enter it into the finance system, and confirm it is saved.'

if [[ $# -gt 0 ]]; then
  TASK="$1"
else
  TASK="${PRIMARY_DEFAULT}"
fi

uv run python cli.py "${TASK}"
