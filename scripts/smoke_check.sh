#!/usr/bin/env bash
# Internal pre-submit checklist (not part of the public README).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== secrets =="
if git ls-files | grep -E '\.env$'; then
  echo "FAIL: .env is tracked" >&2
  exit 1
fi
echo "ok: .env not tracked"

echo "== video link =="
grep -iE 'loom|youtube|video|drive\.google' README.md Readme.md 2>/dev/null | head -3

echo "== tests =="
make test

echo "== auto-approve demos =="
AUTO_APPROVE=1 make demo
AUTO_APPROVE=1 make chaos-demo
AUTO_APPROVE=1 make secondary
AUTO_APPROVE=1 make leave-demo
echo "Note: escalate-demo still needs a human abort; skip in smoke."

echo "smoke_check ok"
