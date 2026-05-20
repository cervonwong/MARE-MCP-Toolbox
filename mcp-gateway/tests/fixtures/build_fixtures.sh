#!/usr/bin/env bash
# Phase 11 Plan 06: build the C fixtures needed for slow integration tests.
# Idempotent: skips if binary exists and is newer than source.
# Pattern mirrors Phase 7's best-effort fallback approach.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

build_native() {
    local src="$1" out="${1%.c}"
    if [[ -f "$out" && "$out" -nt "$src" ]]; then
        echo "[skip] $out is newer than $src"
        return 0
    fi
    if command -v gcc >/dev/null 2>&1; then
        echo "[build] gcc -o $out $src"
        # Try static first, fall back to dynamic linking
        gcc -static -o "$out" "$src" 2>/dev/null || gcc -o "$out" "$src"
        return 0
    fi
    echo "[warn] gcc not available; cannot build $src" >&2
    return 1
}

build_arm() {
    local out="hello_arm.bin"
    if [[ -f "$out" ]]; then
        echo "[skip] $out exists"
        return 0
    fi
    # Try the Debian/Kali cross-compiler
    if command -v arm-linux-gnueabihf-gcc >/dev/null 2>&1; then
        local tmp_src
        tmp_src="$(mktemp --suffix=.c)"
        cat >"$tmp_src" <<'C'
#include <stdio.h>
int main(void) { puts("Hello from ARM"); return 0; }
C
        echo "[build] arm-linux-gnueabihf-gcc -static -o $out"
        arm-linux-gnueabihf-gcc -static -o "$out" "$tmp_src"
        rm -f "$tmp_src"
        return 0
    fi
    echo "[warn] arm-linux-gnueabihf-gcc not available; hello_arm.bin will not be built" >&2
    return 1
}

# Native fixtures (dns_lookup, setsid_escape)
build_native dns_lookup.c    || true
build_native setsid_escape.c || true
# Foreign-arch fixture (hello_arm.bin) -- best-effort
build_arm || true

echo "=== fixtures built ==="
ls -la dns_lookup setsid_escape hello_arm.bin 2>/dev/null || true
