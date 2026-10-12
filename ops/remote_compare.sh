#!/usr/bin/env bash
set -uo pipefail
cd /shared-docker/emoji-studio
docker exec -e HF_HOME=/shared-docker/hf-cache -w /shared-docker/emoji-studio rocm \
  bash -lc 'python3 -m pip install --disable-pip-version-check -r docker/rocm-requirements.txt && python3 scripts/amd_compare.py run --max-seconds 2400'
worker_code=$?
printf '%s\n' "$worker_code" > worker.exit
exit "$worker_code"
