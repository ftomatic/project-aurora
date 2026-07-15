#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_FILE="$PROJECT_ROOT/data/aurora/daily_factory.lock"
OUT_LOG="$PROJECT_ROOT/data/aurora/logs/daily_factory.out.log"
ERR_LOG="$PROJECT_ROOT/data/aurora/logs/daily_factory.err.log"

mkdir -p "$PROJECT_ROOT/data/aurora/logs"

if ! mkdir "$LOCK_FILE" 2>/dev/null; then
  echo "Aurora daily factory already running; exiting safely." >> "$OUT_LOG"
  exit 0
fi

cleanup() {
  rmdir "$LOCK_FILE" 2>/dev/null || true
}
trap cleanup EXIT

cd "$PROJECT_ROOT"
if [ -f "$PROJECT_ROOT/config/aurora.local.env" ]; then
  set -a
  source "$PROJECT_ROOT/config/aurora.local.env"
  set +a
fi

"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/run_daily_factory.py" --count 10 --live --scheduled >> "$OUT_LOG" 2>> "$ERR_LOG"
