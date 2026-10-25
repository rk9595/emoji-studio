FROM docker.io/rocm/pytorch@sha256:bcb2efa1d43f66cc59fa45a1975d621a50b2b06d21a2abdfa2ba821ab32763e4

USER root
WORKDIR /app
ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# Only the reviewed staging script may supply this context. Never COPY the repo.
COPY app/ /app/
COPY audit_runtime.py /opt/emoji-runtime/audit_runtime.py

RUN python3 /opt/emoji-runtime/audit_runtime.py base \
    && python3 -m pip --isolated install --disable-pip-version-check \
       --no-cache-dir --require-hashes --no-deps --only-binary=:all: \
       --index-url https://pypi.org/simple \
       -r /app/configs/amd-overlay-linux-py312.txt

# Runtime imports and tests cannot download model weights or access providers.
RUN --network=none python3 /opt/emoji-runtime/audit_runtime.py verify

CMD ["python3", "-m", "emoji_studio.mock_smoke_executor"]
