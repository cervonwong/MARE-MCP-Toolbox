#!/usr/bin/env bash
# Phase 11 operator helper: probes the same surface as mcp_gateway.dynamic.probe_all().
# Run inside the container to verify dynamic-mode readiness BEFORE opening gdb / starting trace jobs.
#
# Mirrors scripts/probe_extraction_tools.sh (Phase 10) print pattern.

set -euo pipefail

say_ok()   { printf "[OK]   %s\n" "$*"; }
say_warn() { printf "[WARN] %s\n" "$*"; }
say_info() { printf "[INFO] %s\n" "$*"; }

fail=0

echo "=== MARE Dynamic-Mode Capability Probe ==="
echo

# 1. unshare (util-linux)
if command -v unshare >/dev/null 2>&1; then
    say_ok "unshare: $(command -v unshare) ($(unshare --version 2>&1 | head -1))"
else
    say_warn "unshare NOT FOUND -- install util-linux"
    fail=1
fi

# 2. unshare --net round-trip (the load-bearing seccomp check -- Pitfall #2)
if unshare --net true 2>/dev/null; then
    say_ok "unshare --net round-trip: passes (seccomp permits)"
else
    say_warn "unshare --net FAILS -- container needs --security-opt seccomp=unconfined"
    fail=1
fi

# 3. ptrace_scope (host-controlled per Pitfall #7)
if [[ -r /proc/sys/kernel/yama/ptrace_scope ]]; then
    scope=$(cat /proc/sys/kernel/yama/ptrace_scope 2>/dev/null || echo "?")
    if [[ "$scope" == "0" || "$scope" == "1" ]]; then
        say_ok "ptrace_scope=$scope (parent-child tracing permitted)"
    else
        say_warn "ptrace_scope=$scope -- host operator must: sudo sysctl -w kernel.yama.ptrace_scope=0"
        fail=1
    fi
else
    say_warn "/proc/sys/kernel/yama/ptrace_scope NOT READABLE"
fi

# 4. gdb (MI3 requires gdb >= 9.1; Kali ships 13+)
if command -v gdb >/dev/null 2>&1; then
    ver=$(gdb --version 2>&1 | head -1)
    say_ok "gdb: $(command -v gdb) ($ver)"
else
    say_warn "gdb NOT FOUND -- install gdb"
    fail=1
fi

# 5. strace
if command -v strace >/dev/null 2>&1; then
    say_ok "strace: $(command -v strace) ($(strace --version 2>&1 | head -1))"
else
    say_warn "strace NOT FOUND"
    fail=1
fi

# 6. ltrace (Pitfall #4: 0.7.3 is unmaintained)
if command -v ltrace >/dev/null 2>&1; then
    say_ok "ltrace: $(command -v ltrace)"
    say_info "ltrace 0.7.3 is unmaintained; prefer strace on modern binaries"
else
    say_warn "ltrace NOT FOUND"
fi

# 7. binfmt_misc mount + F-flag check (Pitfall #6 / Pitfall #10)
if [[ -d /proc/sys/fs/binfmt_misc ]]; then
    say_ok "/proc/sys/fs/binfmt_misc is mounted"
    f_count=0
    for f in /proc/sys/fs/binfmt_misc/qemu-*; do
        [[ -e "$f" ]] || continue
        if grep -q "^flags:.*F" "$f" 2>/dev/null; then
            f_count=$((f_count + 1))
        fi
    done
    if [[ "$f_count" -gt 0 ]]; then
        say_ok "binfmt_misc: $f_count qemu-* entries with F flag (in-container exec works)"
    else
        say_info "binfmt_misc: no qemu-* entries with F flag (run_qemu_user bypasses binfmt via explicit qemu-<arch>-static)"
    fi
else
    say_warn "/proc/sys/fs/binfmt_misc not mounted"
fi

# 8. qemu-user-static binaries
qemu_count=0
for arch in arm aarch64 mips mipsel ppc ppc64 i386 x86_64 riscv64 sparc; do
    if command -v "qemu-${arch}-static" >/dev/null 2>&1; then
        qemu_count=$((qemu_count + 1))
    fi
done
if [[ "$qemu_count" -gt 0 ]]; then
    say_ok "qemu-*-static binaries available: $qemu_count arches"
else
    say_warn "no qemu-<arch>-static binaries on PATH -- install qemu-user-static"
    fail=1
fi

# 9. SYS_PTRACE capability (best-effort -- try a trivial ptrace operation)
if python3 -c "import ctypes; libc=ctypes.CDLL('libc.so.6'); rc=libc.ptrace(0,0,0,0); exit(0 if rc==0 else 1)" 2>/dev/null; then
    say_ok "PTRACE_TRACEME smoke test: passes (SYS_PTRACE granted)"
else
    say_warn "PTRACE_TRACEME smoke test FAILED -- container needs --cap-add=SYS_PTRACE"
    fail=1
fi

echo
if [[ "$fail" == "0" ]]; then
    echo "=== Dynamic mode is READY ==="
    exit 0
else
    echo "=== Dynamic mode has missing capabilities (see [WARN] lines above) ==="
    exit 1
fi
