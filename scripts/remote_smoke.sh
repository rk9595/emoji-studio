#!/usr/bin/env bash
set -euo pipefail
cd /workspace/emoji-studio
export HF_HOME=/workspace/huggingface
export UV_CACHE_DIR=/workspace/uv-cache
export HF_HUB_DISABLE_TELEMETRY=1
export HF_HUB_DOWNLOAD_TIMEOUT=120
export PYTHONUNBUFFERED=1
mkdir -p runs
nvidia-smi
python3 -m pip install --target /workspace/uv-cli 'uv==0.10.9'
export PATH="/workspace/uv-cli/bin:$PATH"
python3 scripts/remote_environment.py
.venv/bin/python -c 'import torch; print("CUDA", torch.version.cuda, "GPU", torch.cuda.get_device_name()); assert torch.cuda.is_available(); assert torch.cuda.is_bf16_supported()'
.venv/bin/python -m unittest discover -s tests -p test_core.py -v
case "${1:-smoke}" in
  smoke) suffix=smoke-v2 ;;
  sanity) suffix=sanity-1024 ;;
  *) exit 2 ;;
esac
timeout --signal=TERM --kill-after=30s 2400s .venv/bin/emoji-studio generate --plan "runs/sdxl-${suffix}/plan.json" --max-seconds 2200
timeout --signal=TERM --kill-after=30s 2400s .venv/bin/emoji-studio generate --plan "runs/klein-${suffix}/plan.json" --max-seconds 2200
