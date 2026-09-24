#!/usr/bin/env bash
set -euo pipefail

cd /workspace/emoji-studio
max_seconds="${1:?max seconds required}"
hourly_cost="${2:?hourly cost required}"
case "$max_seconds" in
  ''|*[!0-9]*) echo "max seconds must be numeric" >&2; exit 2 ;;
esac
if (( max_seconds < 900 || max_seconds > 2700 )); then
  echo "max seconds outside locked range" >&2
  exit 2
fi

python3 scripts/remote_environment.py
uv run python scripts/remote_service_test.py \
  --hourly-cost "$hourly_cost" --requests 16 --concurrency 4 \
  2>&1 | tee service-test.log
