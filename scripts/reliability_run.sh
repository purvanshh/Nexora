#!/usr/bin/env bash
# Run primary and leave scenarios N times with AUTO_APPROVE=1.
# Writes results to traces/reliability_YYYYMMDD.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

N="${N:-10}"
PRIMARY='Find the latest invoice from Acme Corp in the mail app, extract amount and due date, enter it into the finance system, and confirm it is saved.'
LEAVE='File a leave request for employee 42 from 2025-04-01 to 2025-04-05 with reason family.'
OUT="traces/reliability_$(date -u +%Y%m%d).md"

mkdir -p traces
primary_pass=0
leave_pass=0
primary_fail_notes=()
leave_fail_notes=()

run_one() {
  local label="$1"
  local task="$2"
  local i="$3"
  echo "--- ${label} run ${i}/${N} ---"
  if AUTO_APPROVE=1 bash scripts/run_demo.sh "${task}" >/tmp/nexora_rel_${label}_${i}.log 2>&1; then
    echo "PASS ${label} ${i}"
    return 0
  fi
  echo "FAIL ${label} ${i}"
  tail -n 40 "/tmp/nexora_rel_${label}_${i}.log" || true
  return 1
}

for i in $(seq 1 "$N"); do
  if run_one primary "$PRIMARY" "$i"; then
    primary_pass=$((primary_pass + 1))
  else
    primary_fail_notes+=("${i}")
  fi
done

for i in $(seq 1 "$N"); do
  if run_one leave "$LEAVE" "$i"; then
    leave_pass=$((leave_pass + 1))
  else
    leave_fail_notes+=("${i}")
  fi
done

{
  echo "# Reliability sample (temperature 0, AUTO_APPROVE=1)"
  echo
  echo "Generated: $(date -u +%Y-%m-%dT%H:%MZ)"
  echo "Model: \`${AGENT_MODEL:-gpt-4o-mini}\`"
  echo
  echo "| Scenario | Passes | Runs | Notes |"
  echo "|---|---:|---:|---|"
  echo "| Primary (Acme invoice + decoy mail) | ${primary_pass} | ${N} | failed runs: ${primary_fail_notes[*]:-none} |"
  echo "| Leave write | ${leave_pass} | ${N} | failed runs: ${leave_fail_notes[*]:-none} |"
  echo
  echo "Wall-clock times are not compared across interactive vs auto-approve runs."
} | tee "$OUT"

echo "Wrote ${OUT}"
test "$primary_pass" -eq "$N" && test "$leave_pass" -eq "$N"
