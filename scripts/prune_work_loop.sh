#!/usr/bin/env bash
# Keep artifacts/swebench/work/ flat while a batch is running.
#
# Only needed for batches started before per-run work cleanup landed: that code
# deletes each checkout as soon as the patch is extracted, but a process already
# running has the old module loaded and keeps accumulating ~63MB per run.
#
# Salvages patches into predictions/ first, then deletes the checkouts behind them.
# Exits on its own once the batch process is gone, so nothing is left behind.
#
#   ./scripts/prune_work_loop.sh <exp_dir> [interval_seconds]
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXP_DIR="${1:?usage: prune_work_loop.sh <exp_dir> [interval_seconds]}"
INTERVAL="${2:-1200}"
PATTERN="run_swebench.py"

cd "$ROOT" || exit 1
echo "[$(date '+%F %T')] watching $EXP_DIR, pruning every ${INTERVAL}s"

while pgrep -f "$PATTERN" >/dev/null; do
    sleep "$INTERVAL"
    pgrep -f "$PATTERN" >/dev/null || break
    echo "[$(date '+%F %T')] rows=$(wc -l < "$EXP_DIR/rows.jsonl" 2>/dev/null) free=$(df -h / | awk 'NR==2{print $4}')"
    .venv/bin/python scripts/salvage_predictions.py "$EXP_DIR" --prune 2>&1 | tail -2
done

echo "[$(date '+%F %T')] batch finished — final prune"
.venv/bin/python scripts/salvage_predictions.py "$EXP_DIR" --prune 2>&1 | tail -2
echo "[$(date '+%F %T')] done"
