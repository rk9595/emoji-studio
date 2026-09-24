#!/usr/bin/env bash
set -euo pipefail

cd /workspace/emoji-studio
hourly_cost="${1:?hourly cost required}"
export PATH="/root/.local/bin:${PATH}"

python3 scripts/remote_environment.py > alpha-bootstrap.log 2>&1
nohup env \
  EMOJI_STUDIO_ROOT=/workspace/emoji-studio \
  EMOJI_STUDIO_USERS_FILE=/workspace/emoji-studio/configs/alpha-users.json \
  EMOJI_STUDIO_RENDERER=flux \
  EMOJI_STUDIO_HOURLY_COST_DOLLARS="$hourly_cost" \
  EMOJI_STUDIO_IDLE_UNLOAD_SECONDS=600 \
  EMOJI_STUDIO_RETENTION_DAYS=7 \
  EMOJI_STUDIO_TRIAL_IMAGE_CAP=100 \
  PORT=8000 \
  uv run emoji-studio-api > alpha-service.log 2>&1 < /dev/null &
echo "$!" > alpha-service.pid
