#!/usr/bin/env bash
# scripts/compute_image_hash.sh
# Source: extracted from run_docker.sh:212-229 with LC_ALL=C added (D-02).
set -euo pipefail

# Default to repo root computed from this script's location (matches run_docker.sh:5 idiom).
BUILD_ROOT="${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)}"

if [[ ! -d "$BUILD_ROOT" ]]; then
  echo "[error] build root not a directory: $BUILD_ROOT" >&2
  exit 2
fi
if [[ ! -f "$BUILD_ROOT/Dockerfile" ]]; then
  echo "[error] no Dockerfile at $BUILD_ROOT/Dockerfile" >&2
  exit 2
fi

# Defaults so the helper is invocable from a clean env (e.g., the test).
INSTALL_BINARY_NINJA="${INSTALL_BINARY_NINJA:-0}"
INSTALL_IDA_PRO="${INSTALL_IDA_PRO:-0}"
BINARY_NINJA_ZIP="${BINARY_NINJA_ZIP:-}"
IDA_PRO_ZIP="${IDA_PRO_ZIP:-}"

if [[ "$INSTALL_BINARY_NINJA" == "1" && ! -f "$BINARY_NINJA_ZIP" ]]; then
  echo "[error] INSTALL_BINARY_NINJA=1 but BINARY_NINJA_ZIP not found at: $BINARY_NINJA_ZIP" >&2
  exit 3
fi
if [[ "$INSTALL_IDA_PRO" == "1" && ! -f "$IDA_PRO_ZIP" ]]; then
  echo "[error] INSTALL_IDA_PRO=1 but IDA_PRO_ZIP not found at: $IDA_PRO_ZIP" >&2
  exit 3
fi

{
  sha256sum "$BUILD_ROOT/Dockerfile"
  find "$BUILD_ROOT/docker-bin" -type f -print | LC_ALL=C sort | xargs sha256sum
  find "$BUILD_ROOT/mcp-gateway" \
    -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \
               -o -name .venv -o -name '*.egg-info' -o -name htmlcov \
               -o -name node_modules -o -name dist \) -prune \
    -o -type f -print | LC_ALL=C sort | xargs sha256sum
  printf '%s\n' "INSTALL_BINARY_NINJA=$INSTALL_BINARY_NINJA"
  if [[ "$INSTALL_BINARY_NINJA" == "1" ]]; then
    sha256sum "$BINARY_NINJA_ZIP"
  fi
  printf '%s\n' "INSTALL_IDA_PRO=$INSTALL_IDA_PRO"
  if [[ "$INSTALL_IDA_PRO" == "1" ]]; then
    sha256sum "$IDA_PRO_ZIP"
  fi
} | sha256sum | awk '{print $1}'
