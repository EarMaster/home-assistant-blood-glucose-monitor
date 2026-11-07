#!/usr/bin/env sh
# Validate the integration with Home Assistant's hassfest (same as CI).
set -eu

cd "$(dirname "$0")/.."
REPO="$(pwd -W 2>/dev/null || pwd)"

MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$REPO/custom_components:/github/workspace/custom_components:ro" \
  ghcr.io/home-assistant/hassfest
