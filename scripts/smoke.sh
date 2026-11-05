#!/usr/bin/env bash
# Smoke test a running deployment: reset the demo data, run demo sample S01, expect it to be approved.
# Usage: scripts/smoke.sh [base_url]     (default http://localhost:8000)
set -euo pipefail
BASE="${1:-http://localhost:8000}"

# first occurrence of "key": "value" in a JSON body (the case's own fields come before its findings)
field() { grep -o "\"$1\": *\"[^\"]*\"" | head -1 | sed -E 's/.*: *"([^"]*)"$/\1/'; }

curl -fsS "$BASE/api/health" > /dev/null
# NOTE: resets the demo data to the seeded history, so the sample is not a duplicate of an earlier run
curl -fsS -X POST "$BASE/api/demo/reset" > /dev/null

CASE=$(curl -fsS -X POST "$BASE/api/cases" -F sample_id=S01 -F pace=fast | field case_id)
echo "started case $CASE"
STATUS=running
for _ in $(seq 1 180); do
  BODY=$(curl -fsS "$BASE/api/cases/$CASE")
  STATUS=$(echo "$BODY" | field status)
  [ "$STATUS" != "running" ] && break
  sleep 1
done
LABEL=$(echo "$BODY" | field outcome_label || true)
CODE=$(echo "$BODY" | field primary_code || true)
echo "status=$STATUS outcome=${LABEL:-none} code=${CODE:-none}"
if [ "$LABEL" = "Approved" ]; then echo "APPROVED"; else echo "smoke test failed" >&2; exit 1; fi
