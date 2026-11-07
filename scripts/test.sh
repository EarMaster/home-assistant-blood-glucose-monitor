#!/usr/bin/env sh
# Run linting and tests in a Linux container (the Home Assistant test harness
# does not run reliably on Windows). Usage: scripts/test.sh [pytest args]
set -eu

cd "$(dirname "$0")/.."
REPO="$(pwd -W 2>/dev/null || pwd)"
IMAGE="bgm-test:py3.14"

docker build --quiet -t "$IMAGE" -f - . >/dev/null <<'EOF'
FROM python:3.14-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements_test.txt /tmp/requirements_test.txt
RUN pip install --no-cache-dir -r /tmp/requirements_test.txt
EOF

MSYS_NO_PATHCONV=1 docker run --rm -v "$REPO:/repo" -w /repo "$IMAGE" sh -c "
  ruff check . && ruff format --check . &&
  python -m pytest -p no:cacheprovider --cov --cov-report=term-missing $*
"
