#!/usr/bin/env bash
# Run with: bash verifier/v2/run_remote_acceptance.sh
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="verifier/runs/remote_${STAMP}.log"
COMMAND="python3 verifier/v2/remote_verify.py"
START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
{
  printf 'timestamp_start_utc=%s\ncommand=%s\n' "$START" "$COMMAND"
  python3 verifier/v2/remote_verify.py
} >"$LOG" 2>&1
CODE=$?
END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STAMP="$STAMP" START="$START" END="$END" COMMAND="$COMMAND" CODE="$CODE" LOG="$LOG" python3 - <<'PY'
import json, os
from pathlib import Path
record = {
    "timestamp_start_utc": os.environ["START"],
    "timestamp_end_utc": os.environ["END"],
    "command": os.environ["COMMAND"],
    "exit_code": int(os.environ["CODE"]),
    "log": os.environ["LOG"],
}
with Path("verifier/runs/index.jsonl").open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
PY
cat "$LOG"
printf 'RUN_RECORD｜log=%s｜exit_code=%s\n' "$LOG" "$CODE"
exit "$CODE"
