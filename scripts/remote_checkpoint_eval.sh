#!/usr/bin/env bash
set -euo pipefail

cd /workspace/emoji-studio
max_seconds="${1:?max seconds required}"
case "$max_seconds" in
  ''|*[!0-9]*) echo "max seconds must be numeric" >&2; exit 2 ;;
esac
if (( max_seconds < 900 || max_seconds > 3600 )); then
  echo "max seconds outside locked range" >&2
  exit 2
fi

python3 scripts/remote_environment.py
uv run python scripts/evaluate_checkpoints.py --max-seconds "$max_seconds" 2>&1 | tee checkpoint-eval.log
