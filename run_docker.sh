#!/usr/bin/env bash
set -euo pipefail

# build context = directory containing this script (Dockerfile + compose.yaml)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

# runtime mount = workspace subdirectory (mounted at /agent in the container)
HOST_PWD="$SCRIPT_DIR/workspace"

# buildx builder (idempotent)
docker buildx create --use --name training >/dev/null 2>&1 || docker buildx use training
docker buildx inspect --bootstrap >/dev/null 2>&1 || true

# Binary Ninja archive: optional for build-time headless install.
# Place binaryninja.zip in the repository root, or set BINARY_NINJA_ZIP explicitly.
BINARY_NINJA_ZIP="${BINARY_NINJA_ZIP:-}"
if [[ -z "$BINARY_NINJA_ZIP" && -f "$SCRIPT_DIR/binaryninja.zip" ]]; then
  BINARY_NINJA_ZIP="$SCRIPT_DIR/binaryninja.zip"
fi
INSTALL_BINARY_NINJA=0
if [[ -n "$BINARY_NINJA_ZIP" && -f "$BINARY_NINJA_ZIP" ]]; then
  INSTALL_BINARY_NINJA=1
  echo "[info] using Binary Ninja archive: $BINARY_NINJA_ZIP"
else
  BINARY_NINJA_ZIP=""
  echo "[info] no Binary Ninja zip found; building without Binary Ninja"
fi

# IDA Pro archive: optional for build-time headless install.
# Place idapro.zip in the repository root, or set IDA_PRO_ZIP explicitly.
IDA_PRO_ZIP="${IDA_PRO_ZIP:-}"
if [[ -z "$IDA_PRO_ZIP" && -f "$SCRIPT_DIR/idapro.zip" ]]; then
  IDA_PRO_ZIP="$SCRIPT_DIR/idapro.zip"
fi
INSTALL_IDA_PRO=0
if [[ -n "$IDA_PRO_ZIP" && -f "$IDA_PRO_ZIP" ]]; then
  INSTALL_IDA_PRO=1
  echo "[info] using IDA Pro archive: $IDA_PRO_ZIP"
else
  IDA_PRO_ZIP=""
  echo "[info] no IDA Pro zip found; building without IDA Pro"
fi

MCP_DIR="$HOST_PWD/mcp"
mkdir -p "$MCP_DIR"
BINJA_MCP_REPO_URL="${BINJA_MCP_REPO_URL:-https://github.com/mrphrazer/binary-ninja-headless-mcp.git}"
GHIDRA_MCP_REPO_URL="${GHIDRA_MCP_REPO_URL:-https://github.com/mrphrazer/ghidra-headless-mcp.git}"

ensure_mcp_repo() {
  local name="$1"
  local url="$2"
  local dest="$MCP_DIR/$name"

  if [[ -d "$dest/.git" ]]; then
    echo "[mcp] updating $name"
    git -C "$dest" pull --ff-only
    return
  fi

  if [[ -e "$dest" ]]; then
    echo "[warn] MCP path exists and is not a git checkout: $dest" >&2
    echo "[warn] leaving it unchanged" >&2
    return
  fi

  echo "[mcp] cloning $name"
  git clone --depth 1 "$url" "$dest"
}

if [[ "$INSTALL_BINARY_NINJA" == "1" ]]; then
  ensure_mcp_repo "binary-ninja-headless-mcp" "$BINJA_MCP_REPO_URL"
else
  ensure_mcp_repo "ghidra-headless-mcp" "$GHIDRA_MCP_REPO_URL"
fi

# Persist Binary Ninja settings/license/plugins on the host.
BINARY_NINJA_USER_DIR="${BINARY_NINJA_USER_DIR:-$HOME/.binaryninja-docker}"
mkdir -p "$BINARY_NINJA_USER_DIR"

# Persist IDA Pro settings/license on the host.
IDA_USER_DIR="${IDA_USER_DIR:-$HOME/.idapro-docker}"
mkdir -p "$IDA_USER_DIR"

# Persist Claude auth/settings on the host.
CLAUDE_USER_DIR="${CLAUDE_USER_DIR:-$HOME/.claude-docker}"
mkdir -p "$CLAUDE_USER_DIR"

# Persist Codex auth/state on the host.
CODEX_USER_DIR="${CODEX_USER_DIR:-$HOME/.codex-docker}"
mkdir -p "$CODEX_USER_DIR"

# Seed a dedicated Docker user dir with an existing host license.dat when available.
if [[ ! -f "$BINARY_NINJA_USER_DIR/license.dat" && -f "$HOME/.binaryninja/license.dat" ]]; then
  cp "$HOME/.binaryninja/license.dat" "$BINARY_NINJA_USER_DIR/license.dat"
  echo "[info] copied Binary Ninja license.dat into $BINARY_NINJA_USER_DIR"
fi
if [[ "$INSTALL_BINARY_NINJA" == "1" && ! -f "$BINARY_NINJA_USER_DIR/license.dat" ]]; then
  echo "[warn] no Binary Ninja license.dat found in $BINARY_NINJA_USER_DIR" >&2
fi

# Seed IDA Pro license from host if available
if [[ ! -f "$IDA_USER_DIR/ida.key" && -f "$HOME/.idapro/ida.key" ]]; then
  cp "$HOME/.idapro/ida.key" "$IDA_USER_DIR/ida.key"
  echo "[info] copied IDA Pro ida.key into $IDA_USER_DIR"
fi
if [[ ! -f "$IDA_USER_DIR/ida.hexlic" && -f "$HOME/.idapro/ida.hexlic" ]]; then
  cp "$HOME/.idapro/ida.hexlic" "$IDA_USER_DIR/ida.hexlic"
  echo "[info] copied IDA Pro ida.hexlic into $IDA_USER_DIR"
fi
if [[ "$INSTALL_IDA_PRO" == "1" && ! -f "$IDA_USER_DIR/ida.key" && ! -f "$IDA_USER_DIR/ida.hexlic" ]]; then
  echo "[warn] no IDA Pro license found in $IDA_USER_DIR" >&2
fi

IMAGE_REPO="kali-re-tools"

# Build input checksum tag (short)
DOCKERFILE_SHA="$(
  {
    sha256sum "$SCRIPT_DIR/Dockerfile"
    find "$SCRIPT_DIR/docker-bin" -type f -print | sort | xargs sha256sum
    printf '%s\n' "INSTALL_BINARY_NINJA=$INSTALL_BINARY_NINJA"
    if [[ "$INSTALL_BINARY_NINJA" == "1" ]]; then
      sha256sum "$BINARY_NINJA_ZIP"
    fi
    printf '%s\n' "INSTALL_IDA_PRO=$INSTALL_IDA_PRO"
    if [[ "$INSTALL_IDA_PRO" == "1" ]]; then
      sha256sum "$IDA_PRO_ZIP"
    fi
  } | sha256sum | awk '{print $1}'
)"
SHORT_SHA="${DOCKERFILE_SHA:0:12}"
HASH_IMAGE="${IMAGE_REPO}:${SHORT_SHA}"

# Stage the Binary Ninja zip (if any) into a temporary directory so it can be
# passed as a named build context.  Using --secret is not viable because
# BuildKit limits secrets to 500 KB, far too small for the BN archive.
BINJA_STAGE_DIR="$(mktemp -d)"
IDA_STAGE_DIR="$(mktemp -d)"
cleanup_stages() { rm -rf "$BINJA_STAGE_DIR" "$IDA_STAGE_DIR"; }
trap cleanup_stages EXIT

if [[ "$INSTALL_BINARY_NINJA" == "1" ]]; then
  ln "$BINARY_NINJA_ZIP" "$BINJA_STAGE_DIR/$(basename "$BINARY_NINJA_ZIP")" 2>/dev/null \
    || cp "$BINARY_NINJA_ZIP" "$BINJA_STAGE_DIR/$(basename "$BINARY_NINJA_ZIP")"
fi

if [[ "$INSTALL_IDA_PRO" == "1" ]]; then
  ln "$IDA_PRO_ZIP" "$IDA_STAGE_DIR/$(basename "$IDA_PRO_ZIP")" 2>/dev/null \
    || cp "$IDA_PRO_ZIP" "$IDA_STAGE_DIR/$(basename "$IDA_PRO_ZIP")"
fi

# Build only if missing
if ! docker image inspect "$HASH_IMAGE" >/dev/null 2>&1; then
  echo "[build] building $HASH_IMAGE"
  build_args=(
    --build-arg "INSTALL_BINARY_NINJA=$INSTALL_BINARY_NINJA"
    --build-context "binja-stage=$BINJA_STAGE_DIR"
    --build-arg "INSTALL_IDA_PRO=$INSTALL_IDA_PRO"
    --build-context "ida-stage=$IDA_STAGE_DIR"
    -t "$HASH_IMAGE"
    --load
    "$SCRIPT_DIR"
  )
  docker buildx build "${build_args[@]}"
else
  echo "[build] up to date ($HASH_IMAGE)"
fi

# Convenience tag
docker tag "$HASH_IMAGE" "${IMAGE_REPO}:latest" >/dev/null 2>&1 || true

# Seed the Docker-specific Codex directory from a host auth file when available.
if [[ ! -f "$CODEX_USER_DIR/auth.json" && -f "$HOME/.codex/auth.json" ]]; then
  cp "$HOME/.codex/auth.json" "$CODEX_USER_DIR/auth.json"
fi

# Seed the Docker-specific Claude directory from a host Linux credentials file when available.
if [[ ! -f "$CLAUDE_USER_DIR/.credentials.json" && -f "$HOME/.claude/.credentials.json" ]]; then
  cp "$HOME/.claude/.credentials.json" "$CLAUDE_USER_DIR/.credentials.json"
fi
# Claude state (previously a separate file mount) now lives inside the Claude dir.
# Migrate old host state file into the directory if present.
if [[ ! -f "$CLAUDE_USER_DIR/state.json" ]]; then
  OLD_STATE="${CLAUDE_STATE_FILE:-$HOME/.claude-docker.json}"
  if [[ -s "$OLD_STATE" ]]; then
    cp "$OLD_STATE" "$CLAUDE_USER_DIR/state.json"
  elif [[ -f "$HOME/.claude.json" ]]; then
    cp "$HOME/.claude.json" "$CLAUDE_USER_DIR/state.json"
  fi
fi

# These must be in the environment of the docker compose process
HOST_PWD="$HOST_PWD" \
BINARY_NINJA_USER_DIR="$BINARY_NINJA_USER_DIR" \
IDA_USER_DIR="$IDA_USER_DIR" \
CLAUDE_USER_DIR="$CLAUDE_USER_DIR" \
CODEX_USER_DIR="$CODEX_USER_DIR" \
IMAGE_TAG="$SHORT_SHA" \
exec docker compose \
  --project-directory "$SCRIPT_DIR" \
  -f "$SCRIPT_DIR/compose.yaml" \
  run --rm --pull never kali "$@"
