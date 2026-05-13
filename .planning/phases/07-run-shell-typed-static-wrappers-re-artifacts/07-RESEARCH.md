# Phase 7: run_shell + Typed Static Wrappers + re_artifacts — Research

**Researched:** 2026-05-13
**Domain:** Constrained shell over MCP + typed static-RE wrappers + artifact control helpers in a Kali Docker container with SYS_PTRACE + seccomp=unconfined
**Confidence:** HIGH (Phase 6 chokepoint primitive shipped & green; 35 locked decisions in CONTEXT.md; the few open risks are all OS-mechanism details, not architectural)

## Summary

Phase 7 is the **first MCP-visible v1.1 surface** layered over Phase 6's `ReToolRunner` + `artifacts_io` chokepoint. The build is mechanically straightforward — 4 new tool modules (`shell.py`, `re_static.py`, `re_artifacts.py`, `collision_check.py`), one new helper (`artifacts_io.ensure_mare_shell_access`), one new lifespan hook, two new pip deps (`capstone`, `ropper`), one new apt dep (`acl`), and a `mare-shell` UID in the Dockerfile. All decisions are locked (D-01..D-35).

The research surfaced **two operational risks** that require validation testing rather than design changes:

1. **POSIX-ACL persistence on Docker overlayfs / bind mounts** (D-03..D-06). The container's storage driver is `overlay2`. Historical reports — `moby/moby#15251`, `#32915`, `#40553` — say setfacl is unreliable inside overlay2 layers AND across image build steps. BUT this project's case-dirs live under `/agent/status/<case>/`, which is a **bind mount** from the host (`compose.yaml:11 — ${HOST_PWD:-.}:/agent`). On a bind mount the underlying filesystem is the host's, not Docker overlay — so setfacl succeeds iff the host fs supports ACLs (ext4/xfs do by default; modern kernels mount ext4 with `acl` implicitly). Risk: a user on a Mac host (Docker Desktop osxfs/gRPC-FUSE) or Windows-WSL host hits the "Operation not supported" error. **Mitigation already in CONTEXT.md (D-06): `ensure_mare_shell_access` raises `RuntimeError` on setfacl failure — never silently degrades.** A new pytest must assert ACL set+read round-trips on the actual test fs, gated `skip_if not_linux_native`.

2. **Capstone Python ImportError at container build time.** `capstone-5.0.7` ships manylinux2014 wheels which work on Kali rolling (glibc ≥ 2.17). Risk is low on AMD64 but documented for ARM/macOS hosts (`capstone-engine/capstone#2147`). Mitigation: keep `capstone>=5.0.0` lower-bound (current is 5.0.7), and run `python3 -c "import capstone; capstone.Cs(...)"` once at gateway lifespan startup so import failure is loud, not at first MCP call.

All other CONTEXT.md decisions verified as current and standard:

- `setpriv --reuid --regid --clear-groups --no-new-privs --inh-caps=-all` is the documented util-linux invocation; no deprecations (man7.org/setpriv.1).
- `capstone-5.0.7` (Feb 2026) and `ropper-1.13.13` (Feb 2025) are the current stable PyPI versions; both pure-Python with C extensions.
- `mcp.list_tools()` is the public stable API for enumerating gateway-native tools (already used in `tools/backend_passthrough.py:41`); `PinnedBackend.tool_cache` is the public attribute set by `refresh_backend_tools()` (`backend_passthrough.py:32`).
- MCP `resources/list` has no hard token cap in the 2025-03-26 spec; `maxMessageSize` 4 MB is the default at most reference implementations. Phase 7's `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES=1024` is safely below that envelope.

**Primary recommendation:** Implement the four modules verbatim per D-01..D-35. Add **eight test categories** (env scrub, UID assertion, ACL backfill, allowlist violation, collision hard-fail, in-proc result shape, resource depth-2 walk, paged tool-log read) plus the **mandatory 100 MB urandom rerun at the run_shell layer** (D-35). Wave 0 must register `slow` marker (already done in pyproject.toml) and create `tests/fixtures/` with three small public-domain binaries (D-34) before any wrapper test can turn green.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**`mare-shell` UID drop strategy:**
- **D-01:** `run_shell` invokes bash via `setpriv --reuid=mare-shell --regid=mare-shell --clear-groups --no-new-privs --inh-caps=-all -- bash -c <cmd>`.
- **D-02:** `bash -c`, never `bash -lc` (no `/etc/profile` sourcing).

**`mare-shell` ACL strategy:**
- **D-03:** Case-dirs writable by `mare-shell` via POSIX ACLs (`setfacl -m u:agent:rwx,g:mare-shell:rwx,o::---` + `setfacl -d -m …`); `mare-shell` is NOT added to the `agent` group.
- **D-04:** `acl` apt package added to Dockerfile alongside `yara upx-ucl qemu-user yq` (line 53); pytest asserts `shutil.which("setfacl")` not None.

**ACL backfill:**
- **D-05:** Lazy backfill via `artifacts_io.ensure_mare_shell_access(case_dir: Path) -> None`; called from `run_shell` / `write_artifact` / `append_artifact` before spawn/write; NOT called from `ensure_subdir`.
- **D-06:** `ensure_mare_shell_access` raises `RuntimeError` if `setfacl` missing OR either setfacl command exits non-zero — never silently degrades.

**`mare-shell` filesystem visibility:**
- **D-07:** Dockerfile final-stage entrypoint revokes `mare-shell` access on:
  - `/agent/.mcp-gateway-token` → `chown root:root && chmod 0400`
  - `/home/agent/.idapro/`, `/home/agent/.binaryninja/`, `/home/agent/.codex/`, `/home/agent/.claude/` → `chmod 0700`
  - `/root/` → `chmod 0700`
  - `/agent/uploads/` → ACL `u:mare-shell:r-x,d:u:mare-shell:r-x` (cross-case `strings ../uploads/<sha>`)
  - `/agent/scripts/` → world-readable (no secrets in scripts)
- **D-08:** Regression tests assert `id -u`, `cat /agent/.mcp-gateway-token`, `env | grep -E 'TOKEN|API_KEY|AWS_|ANTHROPIC_|OPENAI_'` posture from inside `run_shell`.

**`run_shell` env whitelist:**
- **D-09:** Build child env from scratch (NOT `os.environ` minus blacklist). Allowed keys: `PATH`, `HOME=/var/empty`, `TERM=dumb`, `NO_COLOR=1`, `COLUMNS=120`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `MARE_CASE_DIR`, `MARE_SAMPLE_PATH` (optional). Module-level frozenset `_RUN_SHELL_ALLOWED_KEYS` for test assertions.
- **D-10:** Explicitly excluded patterns: `MCP_GATEWAY_*`, `*_API_KEY`, `AWS_*`, `ANTHROPIC_*`, `OPENAI_*`, `BN_LICENSE_*`, `IDA_*`, `GITHUB_*`, `SSH_*`, `GPG_*` (the blacklist is documentation for the test, not enforcement).

**Tool-name collision hard-fail:**
- **D-11:** `tools/collision_check.py::assert_no_collisions(mcp)` called from `app.py::lifespan` AFTER `register_all_tools(mcp)` AND AFTER backend's first `refresh_backend_tools()` (so `pinned.tool_cache` is populated).
- **D-12:** Check ALL gateway-native tools (not just `run_*`) vs `pinned.tool_cache`.
- **D-13:** Failure → `RuntimeError` → exit code **78** (EX_CONFIG per sysexits.h); stderr logged with `mcp_gateway.collision_check` logger; no new health endpoint.
- **D-14:** Reverses v1.0 "backend wins" policy at `tools/backend_passthrough.py:8`; comment block updated; runtime dispatch unchanged (collision-free post-startup).
- **D-15:** `tests/test_collision_check.py` covers empty backend / one collision / multi-collision / stub-backend monkeypatch.

**Module split:**
- **D-16:** Four new files: `tools/shell.py` (run_shell), `tools/re_static.py` (11 wrappers), `tools/re_artifacts.py` (5 helpers), `tools/collision_check.py` (no register; exports `assert_no_collisions`).
- **D-17:** Test files mirror module split.

**Typed wrapper API shape:**
- **D-18:** Wrapper signatures locked (see CONTEXT.md table). All wrappers take `case_dir` first; all return the 12-key `ReToolRunner` dict + tool-specific keys; all use `samples.resolve_sample(sample)` and `confine_to(resolve_case_dir(case_dir), …)`.
- **D-19:** In-process wrappers (`run_capstone_disasm`, `run_ropper`) use `_inproc_result(case_dir, slug, output_text, log_relpath, started_at)` helper producing the same 12-key shape. Both write to `disassembly/` / `rop/` via `tool_log_path`-style naming.
- **D-20:** `capstone>=5.0.0` and `ropper>=1.13.10` added to `mcp-gateway/pyproject.toml`; image grows ~6 MB.

**Artifact-control helpers:**
- **D-21:** `write_artifact(case_dir, relpath, content, *, mode: "text"|"binary"="text", overwrite=False)` — base64 for binary; calls `ensure_mare_shell_access`; returns `{case_dir, relpath, bytes_written, mode, overwrote}`.
- **D-22:** `append_artifact(case_dir, relpath, content, *, mode="text")` — append-only; no overwrite flag.
- **D-23:** `list_artifacts(case_dir, subdir=None)` — flat one-dir listing; subdir validated against `EXPANDED_CASE_SUBDIRS + ("",)`; returns `{case_dir, subdir, files: [{name, size, mtime}]}`.
- **D-24:** `get_artifact_tree(case_dir)` — recursive walk with `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES` (1024) and `MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH` (8) caps; hidden files skipped; returns `{case_dir, tree, truncated, truncation_reason, file_count}`.
- **D-25:** `get_tool_log(case_dir, log_name, *, offset=0, length=65536)` — bytes-by-offset read; `confine_to(case_dir / "tool-logs", log_name)`; `length` capped at `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB * 4` bytes (1 MB default); returns `{case_dir, log_name, offset, length_requested, length_returned, total_size, content, eof, next_offset}`.

**MCP Resources:**
- **D-26:** `_build_resource_list` walks `EXPANDED_CASE_SUBDIRS` at depth ≤ 2; `extracted/<sub>/<file>` (depth 3) NOT exposed; cap = `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES` (1024) per `resources/list`.
- **D-27:** New env `MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH` (default `2`) independent of `MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH` (default `8`).

**`run_shell` operational:**
- **D-28:** `run_shell(case_dir, cmd, *, timeout=None)`; slug `"run_shell"`; docstring documents posture-not-isolation explicitly.
- **D-29:** Reject `cmd` if empty/whitespace, exceeds `MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES` (default 32768), or contains NUL byte. NO argv-pattern detection / "dangerous command" blacklist.

**Cross-tool conventions:**
- **D-30:** Every wrapper accepts optional `timeout: float | None = None` forwarded to `run_tool`.
- **D-31:** Every wrapper sets `slug` = public tool name (regex `^[a-z0-9][a-z0-9_-]{0,39}$`).
- **D-32:** Every wrapper raises `ValueError` early on `case_dir` / `sample` / allowlist violation.

**Test design:**
- **D-33:** Tests at `tests/test_run_shell.py`, `tests/test_re_static.py`, `tests/test_re_artifacts.py`, `tests/test_collision_check.py`, `tests/test_resources.py`.
- **D-34:** `tests/fixtures/` new subdirectory with three small public-domain binaries (ELF Hello World from inline asm, tiny PE from mingw, stripped object file); <200 KB total; source code beside binaries.
- **D-35:** 100 MB `/dev/urandom` test from Phase 6 rerun at `run_shell` layer; `@pytest.mark.slow`.

### Claude's Discretion

- Internal layout of `_inproc_result` (recommendation: `tools/re_static.py`).
- `run_readelf` allowlist extension with `-n` notes / `-V` version (planner's call).
- `mare-shell` UID number — recommendation: pin to `useradd -r -u 700 mare-shell` for deterministic image diffs.
- `get_tool_log` response sha256 of full file (recommended yes; not load-bearing).
- `run_jq` / `run_yq` max-result-size cap beyond runner default (recommendation: leave at runner default).
- `MARE_SAMPLE_PATH` omitted vs empty when sample unresolvable (recommendation: omit key entirely).

### Deferred Ideas (OUT OF SCOPE)

- Mount-namespace isolation for `run_shell` — Phase 7 ships posture-only confinement; v1.2 if CAP_SYS_ADMIN becomes acceptable.
- Per-`Mcp-Session-Id` keying of `mare-shell` — v1.2 (`GW-V2-03`).
- Sandboxed-network mode for `run_shell` — Phase 11 territory.
- Recursive `extracted/<sub>/<file>` resources — Phase 10 decides.
- Composite shell-helper wrappers (`run_strings_filtered`, `run_hex_search`) — Phase 12 (orchestrator skill).
- Replacing `tools/artifacts.py::get_artifact` with `confine_to` — Phase 6 deferred.
- `run_strings` as a typed wrapper — explicitly excluded by REQUIREMENTS (v1.0 `collect_strings` covers it).
- `run_capstone_disasm` / `run_ropper` as CLI subprocesses — considered and rejected (D-19).
- Per-tool argv allowlist for the Kali long tail — explicitly rejected.
- `run_shell` argv-pattern detection — Pitfall 2 rejects this.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SHELL-01 | `run_shell(case_dir, cmd)` with cwd pinned, output captured, hard timeout | D-28 (mcp.tool registration), D-01 (setpriv argv), Phase 6 `ReToolRunner` (chokepoint), D-25 (paged log read) |
| SHELL-02 | `run_shell` runs as non-root `mare-shell` UID with env-var whitelist excluding `MCP_GATEWAY_TOKEN`, API keys, AWS creds | D-01 (setpriv `--reuid=mare-shell`), D-09 (`_build_shell_env` allowlist), D-10 (explicit-excludes regression test) |
| SHELL-03 | `run_shell` docstring documents posture-not-isolation | D-28 (docstring spec) |
| STATIC-01 | `run_file(case_dir, sample)` returns libmagic output | D-18 row 1 (`magic: str` key, slug `run_file`) |
| STATIC-02 | `run_die(case_dir, sample)` returns DIE JSON | D-18 row 2 (`detections: list[dict]` parsed from `die -j`) |
| STATIC-03 | `run_xxd(case_dir, sample, offset, length)` with bounded slice and full output saved to `hex/` | D-18 row 3 (`hex_dump: str` capped at 64 KB + `hex_path` under `hex/`) |
| STATIC-04 | `run_readelf(case_dir, sample, sections)` with allowlisted section flags | D-18 row 4 (allowlist `{"-h","-l","-d","-S","-s","-r","-a","-W"}`), D-32 (raises `ValueError` on disallowed flag) |
| STATIC-05 | `run_objdump` + `run_nm` with structured output | D-18 rows 5-6 (`mode: Literal[...]` allowlist) |
| STATIC-06 | `run_rabin2(case_dir, sample, command)` JSON via `-j` | D-18 row 7 (`command: Literal["i","is","iI","ii","iE","iz","zz","iL"]`, argv = `["rabin2","-j",command,sample]`) |
| STATIC-07 | `run_capstone_disasm(arch, mode, bytes_hex, base_addr)` typed JSON | D-18 row 8 (in-process), D-19 (uniform 12-key shape via `_inproc_result`), D-20 (capstone>=5.0.0 pin) |
| STATIC-08 | `run_ropper(case_dir, sample, arch, filter, badbytes)` typed JSON; full list to `rop/` | D-18 row 9 (in-process), D-19, D-20 (ropper>=1.13.10 pin) |
| STATIC-09 | `run_jq` + `run_yq` over case artifacts | D-18 rows 10-11 (`jq`/`yq` argv; `confine_to(resolved_case_dir, artifact_path)`) |
| STATIC-10 | STATIC wrappers reject tool-name collisions with backend pass-through at startup (hard-fail) | D-11..D-15 (`collision_check.assert_no_collisions`), D-14 (reverses v1.0 "backend wins"), exit code 78 |
| ARTIF-01 | Each case-dir supports lazily-created subdirs (9 names) | Phase 6 D-15/D-16 (`ensure_subdir` + `EXPANDED_CASE_SUBDIRS`); Phase 7 consumes only |
| ARTIF-02 | `write_artifact` + `append_artifact` with `confine_to` enforced | D-21 (write), D-22 (append), Phase 6 D-11 (confine_to) |
| ARTIF-03 | `list_artifacts` + `get_artifact_tree` | D-23 (flat list), D-24 (recursive with caps) |
| ARTIF-04 | `get_tool_log(case_dir, log_name, offset, length)` paged read | D-25 (bytes-by-offset, `next_offset`, UTF-8-safe truncate, 1 MB per-call cap) |
| ARTIF-05 | MCP Resources expose `mare://cases/<case>/tool-logs/<file>` | D-26 (depth-2 walk over `EXPANDED_CASE_SUBDIRS`), D-27 (independent depth env) |

## Project Constraints (from CLAUDE.md)

| Constraint | How Phase 7 Honors It |
|------------|------------------------|
| IDA Pro and Binary Ninja licenses never baked into images | D-07 chmods `/home/agent/.idapro` and `.binaryninja` to 0700 — locks them OUT of `mare-shell`; no new license exposure |
| Container runs with `SYS_PTRACE` + `seccomp=unconfined` | D-01's `--no-new-privs` + `--inh-caps=-all` are explicitly the mitigation for this widened cap surface inside `run_shell` |
| Remote MCP needs auth/network exposure consideration | D-07 chmods `/agent/.mcp-gateway-token` to 0400 root-only — bearer token unreachable from `mare-shell` |
| Backward compatibility: existing "agent inside container" mode unchanged | Phase 7 is purely additive; only `backend_passthrough.py` comment block at line 1-10 is modified (D-14); runtime dispatch unchanged |
| GSD Workflow Enforcement: edits must go through GSD command | Phase 7 work executes via `/gsd:execute-phase 7` per CLAUDE.md §"GSD Workflow Enforcement" |

## Standard Stack

### Core (already pinned in Dockerfile / Phase 6 — no version bumps)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` SDK | 1.27.x (already pinned in pyproject.toml) | FastMCP `@mcp.tool()` decorator; `mcp.list_tools()` for collision check | Phase 7 consumes Phase 6/v1.0 surface unchanged |
| `setpriv` (util-linux) | system | UID drop + cap drop + no-new-privs in one syscall | The `setpriv(--reuid --regid --clear-groups --no-new-privs --inh-caps=-all)` form is the documented current util-linux invocation (man7.org/setpriv.1) |
| `acl` (Debian/Kali apt) | system | `setfacl` for D-03 POSIX ACLs | Standard POSIX ACL toolkit; required by D-04 |

### New (added by this phase — verified versions)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `capstone` (PyPI) | `>=5.0.0` (current 5.0.7, manylinux2014 wheels Feb 2026) | In-process disassembly for `run_capstone_disasm` | Industry-standard multi-arch disassembler; typed `CsInsn` JSON output beats text-parsing `cstool` [CITED: pypi.org/project/capstone/] |
| `ropper` (PyPI) | `>=1.13.10` (current 1.13.13, Feb 2025) | In-process ROP gadget search for `run_ropper` | Python `RopperService` returns typed `Gadget` objects; avoids fragile CLI text parsing [CITED: pypi.org/project/ropper/, github.com/sashs/Ropper] |

### Already in Dockerfile (verified) — no install needed
| Tool | Verified by Dockerfile line |
|------|------------------------------|
| `file` (libmagic) | line 44 (`file`) |
| `detect-it-easy` / `die` alias | line 46 (`detect-it-easy`); line 161 (`die` symlink) |
| `xxd` | line 47 (`xxd`) |
| `readelf` / `elfutils` | line 44 (`elfutils`) |
| `objdump` / `nm` (`binutils-multiarch`) | line 44 (`binutils-multiarch`) |
| `rabin2` (radare2) | line 46 (`radare2`) |
| `jq` | line 45 (`jq`) |
| `yq` | line 53 (`yq`) |
| `capstone` (Python) | line 61 (already pip-installed system-wide) — Phase 7 adds the version pin in `pyproject.toml` |
| `ropper` (Python) | line 61 (already pip-installed system-wide) — Phase 7 adds the version pin in `pyproject.toml` |

### Apt deps to add at line 53 (D-04)
```dockerfile
yara upx-ucl qemu-user yq acl
```

**Version verification** [VERIFIED: web search 2026-05-13]:
- `capstone-5.0.7`: latest stable, manylinux2014 wheels uploaded 2026-02-09 — works on Kali rolling (glibc 2.17+).
- `ropper-1.13.13`: latest stable, released 2025-02-28.
- `setpriv` flags `--reuid --regid --clear-groups --no-new-privs --inh-caps`: all documented current in `setpriv(1)` (man7.org/Arch/Debian/Ubuntu manpages) — no deprecations.

### Installation diff

`mcp-gateway/pyproject.toml` (D-20):
```toml
dependencies = [
    "mcp>=1.27,<1.28",
    "starlette>=0.37",
    "uvicorn>=0.27",
    "python-multipart>=0.0.9",
    "httpx>=0.27",
    "anyio>=4.5",
    "capstone>=5.0.0",       # NEW: D-20
    "ropper>=1.13.10",       # NEW: D-20
]
```

`Dockerfile:53` (D-04):
```dockerfile
yara upx-ucl qemu-user yq acl \
```

`Dockerfile` post-line-170 (mare-shell UID — D-01, D-07):
```dockerfile
# Create dedicated low-privilege shell UID for run_shell (Phase 7 D-01).
# UID 700 is pinned for deterministic image-diff (Claude's Discretion in CONTEXT).
RUN useradd -r -u 700 -s /usr/sbin/nologin -d /nonexistent mare-shell
# D-07: revoke access to secret-bearing paths
RUN chmod 0700 /home/agent/.idapro /home/agent/.binaryninja /home/agent/.codex /home/agent/.claude /root \
 && chmod 0755 /agent/scripts || true \
 && setfacl -m u:mare-shell:r-x,d:u:mare-shell:r-x /agent/uploads || true
```

The `mcp-gateway-token` chmod 0400 lives in the entrypoint (it's only written at container start), not the build. Add to `agent-entrypoint.sh` after token-file generation.

## Architecture Patterns

### Recommended Module Layout
```
mcp-gateway/src/mcp_gateway/
├── runner.py                       # Phase 6, unchanged
├── artifacts_io.py                 # Phase 6 + new ensure_mare_shell_access()
├── tools/
│   ├── __init__.py                 # +4 import lines (D-16)
│   ├── shell.py                    # NEW: run_shell (D-16)
│   ├── re_static.py                # NEW: 11 typed wrappers (D-16, D-18)
│   ├── re_artifacts.py             # NEW: 5 artifact helpers (D-16)
│   ├── collision_check.py          # NEW: assert_no_collisions (D-11..D-15)
│   ├── backend_passthrough.py      # COMMENT BLOCK ONLY (D-14)
│   ├── resources.py                # _build_resource_list extended (D-26)
│   ├── case_dirs.py                # unchanged
│   ├── samples.py                  # unchanged
│   └── artifacts.py                # unchanged (refactor deferred)
└── app.py                          # lifespan +1 line: assert_no_collisions(mcp)

mcp-gateway/tests/
├── fixtures/                       # NEW: D-34 — small PE/ELF/object binaries + source
│   ├── hello_elf                   # static ELF, <50 KB
│   ├── hello_elf.S                 # NASM source
│   ├── hello_pe.exe                # mingw-cross PE, <100 KB
│   ├── hello_pe.c                  # source
│   ├── stripped.o                  # ELF object, <20 KB
│   └── stripped.S
├── test_run_shell.py               # NEW: D-17, D-33
├── test_re_static.py               # NEW
├── test_re_artifacts.py            # NEW
├── test_collision_check.py         # NEW
└── test_resources.py               # may already exist; extend per D-33
```

### Pattern 1: Typed wrapper layered over `run_tool` (D-18, D-19)

**What:** Every subprocess wrapper validates eagerly, calls `run_tool`, decorates the result.

**When to use:** All 9 subprocess wrappers in `re_static.py`.

**Example:**
```python
# Source: extrapolated from existing mcp-gateway/src/mcp_gateway/tools/artifacts.py:115-139 + Phase 6 D-02 (run_tool)
import json
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from ..runner import run_tool
from ..artifacts_io import confine_to
from .case_dirs import resolve_case_dir
from .samples import resolve_sample

_RABIN2_ALLOWED = frozenset({"i", "is", "iI", "ii", "iE", "iz", "zz", "iL"})

def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def run_rabin2(
        case_dir: str,
        sample: str,
        command: Literal["i", "is", "iI", "ii", "iE", "iz", "zz", "iL"],
        timeout: Optional[float] = None,
    ) -> dict:
        """Bounded rabin2 query (STATIC-06). JSON-first via -j."""
        # D-32: eager validation before any subprocess spawn
        if command not in _RABIN2_ALLOWED:
            raise ValueError(f"command must be one of {sorted(_RABIN2_ALLOWED)}, got {command!r}")
        resolved_case = resolve_case_dir(case_dir)
        resolved_sample = resolve_sample(sample)
        argv = ["rabin2", "-j", command, resolved_sample]
        # D-31: slug equals public tool name
        result = await run_tool(resolved_case, argv, slug="run_rabin2", timeout=timeout)
        # Parse JSON when exit_code==0; carry parse errors as a separate key
        if result["exit_code"] == 0:
            try:
                result["json_output"] = json.loads(result["stdout_head"])
            except json.JSONDecodeError as exc:
                result["json_output"] = None
                result["json_parse_error"] = str(exc)
        return result
```

### Pattern 2: In-process wrapper with uniform shape (D-19)

**What:** `run_capstone_disasm` and `run_ropper` produce typed JSON natively from Python bindings; `_inproc_result` makes them indistinguishable from subprocess wrappers at the MCP layer.

**Example:**
```python
# Source: D-19 in CONTEXT.md + Phase 6 D-03 12-key shape
import time

_STDOUT_HEAD_BYTES = 256 * 1024  # mirrors STDOUT_HEAD_KB at MCP boundary

def _inproc_result(case_dir, slug, output_text, log_relpath, started_at) -> dict:
    """ReToolRunner-compatible return shape for in-process tools (D-19)."""
    return {
        "exit_code": 0,
        "timed_out": False,
        "duration_s": time.monotonic() - started_at,
        "stdout_head": output_text[:_STDOUT_HEAD_BYTES],
        "stdout_truncated": len(output_text) > _STDOUT_HEAD_BYTES,
        "stdout_bytes_total": len(output_text),
        "stderr_head": "",
        "stderr_truncated": False,
        "stderr_bytes_total": 0,
        "log_path": log_relpath,
        "argv": [slug, "(in-process)"],
        "slug": slug,
    }
```

### Pattern 3: `run_shell` env build-from-scratch (D-09)

**What:** Build env dict literal, NEVER inherit from `os.environ`.

**Example:**
```python
# Source: D-09 in CONTEXT.md
from pathlib import Path

_RUN_SHELL_ALLOWED_KEYS = frozenset({
    "PATH", "HOME", "TERM", "NO_COLOR", "COLUMNS",
    "LANG", "LC_ALL", "MARE_CASE_DIR", "MARE_SAMPLE_PATH",
})

def _build_shell_env(case_dir: Path, sample_path: Optional[Path]) -> dict[str, str]:
    env = {
        "PATH":     "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME":     "/var/empty",
        "TERM":     "dumb",
        "NO_COLOR": "1",
        "COLUMNS":  "120",
        "LANG":     "C.UTF-8",
        "LC_ALL":   "C.UTF-8",
        "MARE_CASE_DIR": str(case_dir),
    }
    if sample_path is not None:
        env["MARE_SAMPLE_PATH"] = str(sample_path)
    # Defensive: extra-keys are a bug (the test will catch them, but assert here too)
    assert set(env) <= _RUN_SHELL_ALLOWED_KEYS, f"env leaked extra keys: {set(env) - _RUN_SHELL_ALLOWED_KEYS}"
    return env
```

### Pattern 4: setpriv-prefixed argv passed to `ReToolRunner` (D-01)

**What:** `run_shell` builds `argv = ["setpriv", …, "bash", "-c", cmd]` and hands it to `run_tool`. `ReToolRunner.run` already passes this argv to `asyncio.create_subprocess_exec` — no `shell=True`, Python never interpolates.

**Example:**
```python
# Source: D-01 in CONTEXT.md + Phase 6 runner.py:217 (create_subprocess_exec spawn site)
def _build_setpriv_argv(cmd: str) -> list[str]:
    return [
        "setpriv",
        "--reuid=mare-shell",
        "--regid=mare-shell",
        "--clear-groups",
        "--no-new-privs",
        "--inh-caps=-all",
        "--",
        "bash",
        "-c",
        cmd,
    ]
```

### Pattern 5: Idempotent ACL backfill (D-05, D-06)

**What:** `ensure_mare_shell_access` runs `setfacl` twice (default-ACL + base-ACL); both are no-ops if the ACL already matches.

**Example:**
```python
# Source: D-05, D-06 in CONTEXT.md
import shutil
import subprocess
from pathlib import Path

def ensure_mare_shell_access(case_dir: Path) -> None:
    """Idempotent POSIX ACL grant for mare-shell on case_dir (D-05, D-06).

    Raises RuntimeError if setfacl is missing OR either call exits non-zero.
    Never silently degrades to 'mare-shell cannot write its own case_dir'.
    """
    if shutil.which("setfacl") is None:
        raise RuntimeError("setfacl not on PATH; Phase 7 requires apt 'acl' package")
    base = ["setfacl", "-m", "u:agent:rwx,g:mare-shell:rwx,o::---", str(case_dir)]
    default = ["setfacl", "-d", "-m", "u:agent:rwx,g:mare-shell:rwx,o::---", str(case_dir)]
    for cmd in (base, default):
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"setfacl failed ({' '.join(cmd)!r}): exit={res.returncode} stderr={res.stderr.strip()!r}"
            )
```

### Pattern 6: `assert_no_collisions` against live mcp instance (D-11, D-12)

**What:** Use the public `mcp.list_tools()` API (already used at `tools/backend_passthrough.py:41`) — never the private `_tool_manager` attribute.

**Example:**
```python
# Source: tools/backend_passthrough.py:41 (existing pattern) + D-11..D-15
import logging
import sys

from mcp.server.fastmcp import FastMCP

from .. import session_state

log = logging.getLogger("mcp_gateway.collision_check")

async def assert_no_collisions(mcp: FastMCP) -> None:
    """Hard-fail at lifespan if gateway-native and backend tool names overlap (D-11..D-15)."""
    gateway_tools = await mcp.list_tools()
    gateway_names = {t.name for t in gateway_tools}
    pinned = session_state.PINNED_BACKEND
    backend_tools = getattr(pinned, "tool_cache", {}) or {}
    backend_names = set(backend_tools.keys())
    collisions = sorted(gateway_names & backend_names)
    if collisions:
        backend_label = getattr(pinned, "backend_name", "<unknown>")
        msg = f"FATAL: gateway-native tool names collide with backend '{backend_label}': {collisions}"
        log.error(msg)
        # D-13: exit code 78 (EX_CONFIG per sysexits.h)
        sys.exit(78)
```

> **Note on D-13 exit-78 mechanism:** Raising `RuntimeError` from within `lifespan` does propagate up but Starlette/uvicorn may translate it to a generic non-zero exit. A clean `sys.exit(78)` inside `assert_no_collisions` after logging the message is the most reliable way to get the EX_CONFIG code through. Planner may also wrap in `try/except` at `app.py::lifespan` for the same effect.

### Pattern 7: Resource depth-2 walk (D-26)

**What:** Extend `_build_resource_list` with a per-case inner loop walking `EXPANDED_CASE_SUBDIRS`. URI is `mare://cases/<case>/<subdir>/<file>` for depth 2. Cap = `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES` (1024) across all cases.

**Example:**
```python
# Source: existing tools/resources.py:70 (_build_resource_list) + D-26
from ..artifacts_io import EXPANDED_CASE_SUBDIRS

def _build_resource_list() -> list[mcp_types.Resource]:
    out: list[mcp_types.Resource] = []
    cap = int(os.environ.get("MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES", "1024"))
    for case in _list_cases():
        case_root = STATUS_ROOT / case
        # Existing: depth-1 flat artifacts (unchanged)
        for artifact in ARTIFACTS:
            if len(out) >= cap:
                return out
            uri = f"mare://cases/{case}/{artifact}"
            out.append(mcp_types.Resource(
                uri=AnyUrl(uri), name=f"{case}/{artifact}",
                description=f"Pipeline artifact for case {case}",
                mimeType=_mime_for(case_root / artifact),
            ))
        # NEW (D-26): depth-2 walk over EXPANDED_CASE_SUBDIRS
        for sub in EXPANDED_CASE_SUBDIRS:
            sub_root = case_root / sub
            if not sub_root.is_dir():
                continue
            for child in sorted(sub_root.iterdir()):
                if len(out) >= cap:
                    return out
                if not child.is_file() or child.name.startswith("."):
                    continue
                uri = f"mare://cases/{case}/{sub}/{child.name}"
                out.append(mcp_types.Resource(
                    uri=AnyUrl(uri), name=f"{case}/{sub}/{child.name}",
                    description=f"Captured {sub} artifact for case {case}",
                    mimeType=_mime_for(child),
                ))
    return out
```

### Anti-Patterns to Avoid

- **`bash -lc`:** triggers login-shell init files; defeats env scrub (D-02).
- **Blacklist env scrub:** one missed var leaks the next secret (D-09 — whitelist is mandatory).
- **`shell=True` anywhere:** runner.py is the chokepoint; tests grep for this (test_runner.py:33).
- **Auto-deriving slug from `argv[0]`:** Phase 6 D-09 rationale — argv[0] may be `setpriv`, `bash`, `/agent/scripts/foo.sh`; pass slug explicitly.
- **Adding `mare-shell` to the `agent` group:** broadens privilege gradient; D-03 mandates ACL-only.
- **Argv-parsing `cmd` for "dangerous" patterns:** Pitfall 2 explicitly rejects (`rm -rf /` detection is fool's errand).
- **Eager ACL backfill at lifespan:** D-05 mandates lazy — one bad case-dir would block gateway start.
- **Calling `ensure_mare_shell_access` from `ensure_subdir`:** D-05 — read-only artifact creators don't need mare-shell ACLs.
- **Mixing private FastMCP APIs (`mcp._tool_manager._tools`):** use public `await mcp.list_tools()` (D-12, Pattern 6); stable across SDK versions.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| UID/cap drop for a single subprocess | Custom Python `os.setresuid` + `setresgid` + `prctl(PR_SET_NO_NEW_PRIVS)` + cap drops | `setpriv --reuid --regid --clear-groups --no-new-privs --inh-caps=-all` | One audited tool from util-linux does all four atomically; man-page docs ensure semantic stability |
| POSIX ACL manipulation | Python `os.setxattr("system.posix_acl_access", …)` | `setfacl -m … && setfacl -d -m …` via `subprocess.run` | xattr-level manipulation requires understanding the ACL binary format; `setfacl` is the canonical tool, idempotent, and ships with `acl` apt package |
| In-process disassembly | Custom decoder per arch | `capstone>=5.0.0` (`capstone.Cs(arch, mode).disasm(bytes, addr)`) | Industry standard; typed `CsInsn` objects with `address`, `mnemonic`, `op_str`, `bytes` |
| ROP gadget search | Custom regex-pattern scanner | `ropper.RopperService` (in-process API) | Multi-arch, badbyte filtering, gadget categorization; CLI text parsing is fragile |
| `cmd` "safety" allowlist for `run_shell` | Custom argv parser to refuse `rm -rf /` etc. | Posture-only confinement (UID + env + cwd + timeout + capture) | Pitfall 2: "the entire shell language is the surface; argv-parse for safety is fool's errand"; CONTEXT D-29 forbids this |
| Tool-name collision detection | Loop over private `_tool_manager._tools` | `await mcp.list_tools()` + `pinned.tool_cache` (already public; used in `backend_passthrough.py`) | Public SDK API — stable across mcp 1.27 → 1.28 |
| Bytes-by-line range read | Line-index bookkeeping per log file | Bytes-by-offset (D-25); UTF-8-safe truncate (`runner._truncate_to_utf8_boundary`) | Bytes match Phase 6's head-cap mental model exactly; lines need a per-file index |
| ANSI-strip for `run_shell` | Custom ANSI parser | `runner._ANSI_ESCAPE` regex (already in Phase 6) | Already applied to `stdout_head` / `stderr_head` by the chokepoint; no special-case needed |
| Path-traversal guard for `relpath` / `artifact_path` | Inline `os.path.commonpath` | `artifacts_io.confine_to(resolve_case_dir(case_dir), path)` | Phase 6 D-11..D-14 chokepoint; tested in `tests/test_artifacts_io.py` |

**Key insight:** Every "build it yourself" temptation in Phase 7 is a small wrapper around an already-correct chokepoint. The unique wrapper logic per tool is the **JSON shape decoration**, not the safety properties.

## Runtime State Inventory

**NOT APPLICABLE** — Phase 7 is purely additive code (no rename/refactor/migration). The only modification to existing code is the comment block at the top of `tools/backend_passthrough.py:1-10` (D-14); runtime dispatch is unchanged.

## Common Pitfalls

### Pitfall 1: `setpriv` fails because `mare-shell` UID was never created at image build

**What goes wrong:** `run_shell` returns `exit_code: <nonzero>`, stderr says "setpriv: cannot find user 'mare-shell'".

**Why it happens:** Dockerfile changes for `useradd -r -u 700 mare-shell` weren't applied (F-1 fix from Phase 5 should now catch this — image rebuilds on `mcp-gateway/src/` edits but Dockerfile is always in the hash; gateway-source edit DOES NOT include Dockerfile edits in the F-1 hash unless the planner is careful).

**How to avoid:** A Wave-0 RED test `tests/test_run_shell.py::test_mare_shell_user_exists` asserts `pwd.getpwnam("mare-shell").pw_uid == 700` — runs at the container layer where the user must exist. Image build fails fast if `useradd` line was forgotten.

**Warning signs:** First `run_shell` call returns non-zero with `setpriv: cannot find user`. Distinguishable from D-29 cmd-validation errors by the stderr text.

### Pitfall 2: setfacl on a bind-mounted host filesystem that lacks `acl` mount option

**What goes wrong:** `ensure_mare_shell_access` raises `RuntimeError: setfacl failed … 'Operation not supported'` on first `run_shell` call.

**Why it happens:** Host filesystems vary. ext4 mounts with `acl` enabled by default since kernel 2.6.39; xfs always; btrfs always; but some NFS / SMB / FUSE filesystems do NOT support ACLs. Docker Desktop for Mac (osxfs/gRPC-FUSE) and Docker Desktop for Windows (CIFS-backed bind mounts) routinely fail setfacl. [VERIFIED: moby/moby#15251, docker-desktop/desktop-linux#167]

**How to avoid:** Document host-filesystem requirement in README; recommend Linux host for the gateway. Pre-flight check at gateway lifespan startup: `setfacl -m u:agent:rwx /agent/status && getfacl /agent/status | grep -q "user:agent:rwx"` — if it fails, log a loud warning so the operator knows before the first `run_shell` call. (Optional planner-discretion improvement; D-06 fail-loud already covers correctness.)

**Warning signs:** Test environment differs from production — CI Linux runners work, Mac dev box fails. The pre-flight log line is the only operator-visible signal.

### Pitfall 3: ACL doesn't persist across Docker image build steps

**What goes wrong:** `setfacl -m u:mare-shell:r-x /agent/uploads` in the Dockerfile build phase works inside that `RUN`, but the ACL is missing in the final image.

**Why it happens:** Docker overlayfs storage driver does not always persist xattr-level ACL data across image layers. [VERIFIED: moby/moby#40553, #32915]

**How to avoid:** Re-apply ACLs in the entrypoint, not in the Dockerfile `RUN`. The entrypoint runs once per container start, against the actual mounted filesystem. The Dockerfile `RUN` is best-effort (kept for documentation); the entrypoint is load-bearing. Adapt the pattern that's already used for `/agent/.mcp-gateway-token` (generated at startup, not baked in).

**Warning signs:** `getfacl /agent/uploads` immediately after container start shows no `user:mare-shell:r-x` entry, even though the Dockerfile had a `setfacl` line.

### Pitfall 4: `mare-shell` cannot read `/agent/uploads/<sha>/<file>` for cross-case `strings ../uploads/...`

**What goes wrong:** `run_shell("strings $MARE_SAMPLE_PATH")` returns "Permission denied" when `MARE_SAMPLE_PATH` points to `/agent/uploads/...`.

**Why it happens:** D-07 grants `u:mare-shell:r-x` ACL on `/agent/uploads/` (the directory), but each `<sha>` subdir under it was created with permissions before that ACL was added. The default-ACL `d:u:mare-shell:r-x` only inherits to children created AFTER the ACL was set.

**How to avoid:** Apply both base and default ACLs recursively on first container start. Entrypoint pattern: `find /agent/uploads -exec setfacl -m u:mare-shell:r-x {} \;` once, then default-ACL ensures new uploads inherit. (Alternative: tests fail-loud on this; planner-discretion to add.)

**Warning signs:** New uploads work; pre-existing uploads (from container restart) silently fail.

### Pitfall 5: `bash -c` inherits environment from `setpriv`'s parent even with `--clear-groups`

**What goes wrong:** `setpriv` doesn't scrub env vars — that's `env -i` or explicit `env=` to `create_subprocess_exec`. If the Phase 7 implementation hands `env=os.environ.copy()` to `run_tool` (the default), bash will see every var.

**Why it happens:** `--clear-groups` only clears supplementary GIDs; environment is unchanged. Phase 7 must explicitly pass `env=_build_shell_env(...)` so `ReToolRunner` overrides its default `os.environ.copy()`.

**How to avoid:** D-09's `_build_shell_env` MUST be passed as the `env` kwarg to `run_tool`. The regression test in D-08 / D-10 (`run_shell("env | grep -E 'TOKEN|API_KEY|AWS_'")` returns empty) catches this exact bug.

**Warning signs:** The D-08 test fails — `cat /agent/.mcp-gateway-token` succeeds (token reachable) or `env | grep MCP_GATEWAY_TOKEN` is non-empty.

### Pitfall 6: Capstone C extension fails to load (`ImportError`)

**What goes wrong:** `import capstone` raises `ImportError: ERROR: fail to load the dynamic library`.

**Why it happens:** Capstone bundles `libcapstone.so` inside the manylinux2014 wheel; if the wheel isn't selected (wrong arch / older glibc), pip falls back to source build. Source build needs `cmake`, which the Dockerfile has — but the wheel path is preferred for repeatability. [CITED: github.com/capstone-engine/capstone#2147]

**How to avoid:** Pin `capstone>=5.0.0` (already in D-20); test wheel-availability at gateway startup by running `python3 -c "import capstone; capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)"` once, log success/failure. If the smoke test fails, the gateway should refuse to register `run_capstone_disasm` rather than fail at first MCP call.

**Warning signs:** Build succeeds on x86_64 Linux, fails on ARM Mac (Docker Desktop) or aarch64 hosts.

### Pitfall 7: FastMCP `mcp.list_tools()` returns empty during lifespan startup (collision check misses real tools)

**What goes wrong:** `assert_no_collisions(mcp)` is called from `lifespan` before tools are fully registered or before backend tool_cache is populated; collisions go undetected.

**Why it happens:** D-11 specifies the exact ordering: AFTER `register_all_tools(mcp)` AND AFTER `PinnedBackend.__aenter__` (which calls `refresh_backend_tools()`). In `app.py::lifespan`, the current code path is:
1. `register_all_tools(mcp)` — line 82 (BEFORE lifespan)
2. `async with PinnedBackend(...) as pinned` — line 101 (refresh_backend_tools called in __aenter__)
3. **HERE: insert `await assert_no_collisions(mcp)`** — must be AFTER #2, BEFORE `async with mcp.session_manager.run()` on line 104

**How to avoid:** Place the call between lines 102 and 103 of current `app.py`. Test `tests/test_collision_check.py` constructs a stub `PinnedBackend` whose `tool_cache` is pre-populated to assert ordering.

**Warning signs:** `assert_no_collisions` runs but `pinned.tool_cache` is empty — collision check passes spuriously even when a real backend has overlapping tools.

### Pitfall 8: `get_artifact_tree` chokes on symlink loops in `extracted/`

**What goes wrong:** A malicious uploaded ZIP contains a symlink loop; `get_artifact_tree` recurses infinitely.

**Why it happens:** Extracted children (Phase 10 territory but already reserved subdir) may contain hostile symlinks. D-24's `MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH=8` cap stops recursion at depth 8 but only on depth, not on cycle detection.

**How to avoid:** D-24's depth cap is sufficient — the walker `pathlib.Path.iterdir()` follows symlinks by default, and depth-8 stops the loop. The test in `test_re_artifacts.py` includes a symlink-loop case asserting `truncated=True, truncation_reason="max_depth"`. Alternative (planner-discretion): use `os.scandir()` with `follow_symlinks=False` — but D-24 doesn't mandate this.

**Warning signs:** `get_artifact_tree` returns `truncated=True` with `truncation_reason="max_depth"` on cases that have no real depth — symlink loop.

### Pitfall 9: `setpriv` PID-namespace signal forwarding

**What goes wrong:** `ReToolRunner` SIGKILLs the process group on timeout, but `setpriv` swallows the signal and the child `bash` survives briefly.

**Why it happens:** `setpriv` is a thin syscall wrapper — it `execve`s into the target program. After `execve`, `setpriv` is REPLACED by `bash`; there is no "setpriv process" to signal. The pgroup is set by `start_new_session=True` BEFORE setpriv runs, so `killpg` finds the right pgroup. **Verified safe.**

**How to avoid:** No mitigation needed; this is verified-correct behavior. The Phase 6 test `test_timeout_kills_process_group` already asserts < 200 ms cleanup; the D-35 100 MB urandom test reruns this through `run_shell`.

**Warning signs:** Phase 6's timeout test passes, but D-35 (Phase 7's rerun) shows > 200 ms cleanup — would indicate setpriv inserted PID-namespace indirection. Not expected.

### Pitfall 10: `MARE_CASE_DIR` env var leaks the resolved (canonical) path, not the case-name string the agent passed

**What goes wrong:** Agent calls `run_shell("/agent/status/001-malware.bin", "echo $MARE_CASE_DIR")`; the echoed path is `/agent/status/001-malware.bin` (resolved). Functionally correct but may surprise agents that expect their input back verbatim.

**Why it happens:** D-09 mandates `MARE_CASE_DIR=str(case_dir)` where `case_dir` is the resolved Path from `resolve_case_dir`. The resolved form is intentional — bash `cd $MARE_CASE_DIR` must work regardless of symlinks in the input.

**How to avoid:** Document explicitly in `run_shell` docstring. The chosen behavior (resolved path) is correct; the test should assert resolved-form is what bash sees.

**Warning signs:** None — by design.

## Code Examples

### Wave-0 RED test: `mare-shell` UID exists
```python
# Source: extrapolated from Phase 6 conftest pattern + D-01
import pwd
import pytest

def test_mare_shell_user_exists():
    """D-01: mare-shell UID must be created at image build."""
    try:
        entry = pwd.getpwnam("mare-shell")
    except KeyError:
        pytest.fail("Dockerfile missing 'useradd -r -u 700 mare-shell' (D-01)")
    assert entry.pw_uid == 700, f"expected UID 700 (Claude's-Discretion pin), got {entry.pw_uid}"
    assert entry.pw_shell in ("/usr/sbin/nologin", "/sbin/nologin")
```

### `run_shell` UID-drop end-to-end test (D-08)
```python
# Source: D-08 in CONTEXT.md
async def test_run_shell_drops_to_mare_shell_uid(tmp_path):
    case = _make_case_dir(tmp_path)  # tmp_path-based; requires setfacl support on host fs
    # ensure_mare_shell_access will run on first call
    result = await run_shell(str(case), "id -u")
    assert result["exit_code"] == 0
    assert result["stdout_head"].strip() == "700"  # D-01 + Claude's-Discretion UID pin

async def test_run_shell_cannot_read_token(tmp_path, monkeypatch):
    case = _make_case_dir(tmp_path)
    # Token file path may be mocked via env var per existing pattern
    result = await run_shell(str(case), "cat /agent/.mcp-gateway-token 2>&1 || echo DENIED")
    assert "DENIED" in result["stdout_head"] or "Permission denied" in result["stdout_head"]

async def test_run_shell_env_no_secrets(tmp_path, monkeypatch):
    case = _make_case_dir(tmp_path)
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "should-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-shouldnotleak")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIASHOULDNOTLEAK")
    result = await run_shell(str(case), "env")
    assert "MCP_GATEWAY_TOKEN" not in result["stdout_head"]
    assert "ANTHROPIC_API_KEY" not in result["stdout_head"]
    assert "AWS_ACCESS_KEY_ID" not in result["stdout_head"]
```

### `run_capstone_disasm` happy path
```python
# Source: D-18 row 8 + Phase 6 _inproc_result pattern
async def test_run_capstone_disasm_x86_64_simple(tmp_path):
    """X86_64 disassembly of 'nop; ret'."""
    result = await run_capstone_disasm(
        arch="x86", mode="64",
        bytes_hex="90c3",
        base_addr=0x1000,
        case_dir=None,  # no artifact dump
    )
    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    insns = result["instructions"]
    assert len(insns) == 2
    assert insns[0] == {"address": 0x1000, "mnemonic": "nop", "op_str": "", "bytes": "90"}
    assert insns[1]["mnemonic"] == "ret"
```

### Collision-check test (stub backend)
```python
# Source: D-15 in CONTEXT.md
import pytest

async def test_assert_no_collisions_empty_backend(monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from mcp_gateway.tools import register_all_tools
    from mcp_gateway.tools.collision_check import assert_no_collisions
    from mcp_gateway import session_state

    class _StubBackend:
        tool_cache = {}
        backend_name = "stub"
    monkeypatch.setattr(session_state, "PINNED_BACKEND", _StubBackend())

    mcp = FastMCP("test")
    register_all_tools(mcp)
    await assert_no_collisions(mcp)  # must NOT raise

async def test_assert_no_collisions_one_overlap(monkeypatch):
    import mcp.types as mt
    from mcp.server.fastmcp import FastMCP
    from mcp_gateway.tools import register_all_tools
    from mcp_gateway.tools.collision_check import assert_no_collisions
    from mcp_gateway import session_state

    class _StubBackend:
        tool_cache = {"run_xxd": mt.Tool(name="run_xxd", description="x", inputSchema={"type": "object"})}
        backend_name = "stub-evil"
    monkeypatch.setattr(session_state, "PINNED_BACKEND", _StubBackend())

    mcp = FastMCP("test")
    register_all_tools(mcp)
    with pytest.raises(SystemExit) as exc:
        await assert_no_collisions(mcp)
    assert exc.value.code == 78  # D-13 EX_CONFIG
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `bash -lc` for shell wrapping | `bash -c` only | N/A (best practice always) | Avoids `/etc/profile` env re-leak (D-02) |
| `gosu` / `runuser` for UID drop | `setpriv` with `--no-new-privs --clear-groups --inh-caps=-all` | Adopted in modern container hardening 2020+ | Adds three independent defense-in-depth knobs (D-01) |
| chmod / chgrp / SGID-dir for shared writability | POSIX ACL with default-ACL inheritance | Linux kernel ≥ 4.9 supports ACLs in overlayfs; ext4 mounts with `acl` since 2.6.39 | Narrower privilege gradient than group sharing (D-03) |
| Blacklist env scrub | Whitelist env build-from-scratch | Container-hardening best practice since ~2019 | New leaked secrets don't quietly become reachable (D-09) |
| Subprocess shell to capstone / ropper CLI | In-process Python bindings | Capstone Python bindings since 5.0 (Dec 2024); ropper Python API stable since 1.13 | ~50 ms latency saved per call; typed JSON output (D-19) |
| MCP `resources/list` flat depth-1 enumeration | Depth-2 walk over canonical subdirs | Phase 7 extension (D-26) | Captured tool-logs / hex / rop become MCP-discoverable |
| SSE transport (deprecated) | Streamable HTTP (2025-03-26 spec) | v1.0 already uses Streamable HTTP; Phase 7 inherits | Inherited from v1.0 — no Phase 7 concern |

**Deprecated/outdated within Phase 7's scope:**
- `gosu`-only UID drop (no cap drop, no no-new-privs) — superseded by `setpriv`.
- `chmod 770` + chgrp for case-dir sharing — superseded by POSIX ACL.
- CLI-text-parsing of capstone (`cstool`) / ropper output — superseded by in-process Python bindings.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `setpriv --inh-caps=-all` is supported in Kali rolling's util-linux version (the most relevant flag) | Standard Stack | Low — flag documented in man7.org/setpriv.1; failure mode is a clean error at first `run_shell` call, caught by Pitfall 1 test. |
| A2 | Capstone-5.0.7 manylinux2014 wheel is selected on Kali rolling AMD64 | Standard Stack | Medium — fails on ARM/macOS hosts (Pitfall 6). Mitigated by lifespan smoke test (recommended). |
| A3 | Ropper-1.13.13's Python `RopperService` API still returns typed `Gadget` objects with `.address`, `.lines`, `.bytes` | Pattern 2 / D-19 | Low — public API stable since 1.13.x; if changed, the in-process wrapper's `gadgets: list[dict]` shape is the only thing affected. |
| A4 | Docker overlay2 storage driver does NOT degrade setfacl on bind-mounted host directories | Pitfall 2 | Verified by multiple moby issue threads — but host fs varies. Pre-flight check recommended; D-06 fail-loud already handles the failure case. |
| A5 | `mcp.list_tools()` returns ALL registered tools at lifespan time (not just a subset) | Pattern 6 | Low — `backend_passthrough.py:41` already uses this exact call and works in v1.0; same SDK version pinned. |
| A6 | Kali base image already mounts ext4 with `acl` option (or the host bind-mount inherits the host's `acl` flag) | Pattern 5 | Low — kernel 2.6.39+ mounts ext4 with `acl` by default; standard Linux fs. Mac/Windows hosts fail loud per D-06. |

**This table is non-empty by design** — these are the OS-mechanism details Phase 7 inherits from the runtime environment. None block the plan; each has a fail-loud mitigation via D-06 / smoke tests / Pitfall 1 test.

## Open Questions (RESOLVED)

1. **Should the entrypoint re-apply the `/agent/uploads/` ACL recursively on every container start (Pitfall 4)?**
   - What we know: D-07 sets the ACL on `/agent/uploads/` itself; default-ACL covers new uploads.
   - What's unclear: Existing uploads (from previous container runs) don't have the inherited ACL.
   - **RESOLVED:** plan 07-01 Task 1 (Dockerfile entrypoint heredoc) applies `find /agent/uploads -mindepth 1 -exec setfacl -m u:mare-shell:r-x {} \;` plus the matching default-ACL line on every container start. Formalised in CONTEXT.md D-07a addendum. Recommendation adopted: yes.

2. **Should `assert_no_collisions` use `sys.exit(78)` or `raise RuntimeError`?**
   - What we know: D-13 specifies exit code 78; `sys.exit` guarantees it; `raise` from lifespan goes through Starlette and may translate.
   - What's unclear: Whether Starlette propagates `SystemExit` cleanly (vs catching and exiting non-zero generically).
   - **RESOLVED:** plan 07-03 implements `assert_no_collisions` via `sys.exit(_EX_CONFIG)` (where `_EX_CONFIG = 78`) after `log.error(...)`. Formalised in CONTEXT.md D-13a addendum (D-13's exit-code-78 contract preserved; only the Python-level raise mechanism is pinned to `sys.exit`). Wave 0 RED test in plan 07-01 asserts `pytest.raises(SystemExit); exc.value.code == 78`. Recommendation adopted: `sys.exit(78)`.

3. **Should `run_capstone_disasm` validate `arch` / `mode` against an explicit allowlist or accept whatever capstone supports?**
   - What we know: D-18 row 8 doesn't pin an allowlist; capstone supports ~12 architectures.
   - What's unclear: Whether opening to all caps is a discoverability win or a footgun (typo `arm6` instead of `arm64`).
   - **RESOLVED:** plan 07-06 `run_capstone_disasm` accepts any capstone-supported arch/mode and raises `ValueError` with the actual capstone-supported list on unknown input. Capstone's own `CsError` is wrapped into the same `ValueError` surface for a uniform error contract. Recommendation adopted.

4. **What should `_inproc_result.argv` look like for in-process tools (D-19)?**
   - What we know: D-19 example shows `[slug, "(in-process)"]`.
   - What's unclear: Whether MCP clients use `argv` for anything other than audit display.
   - **RESOLVED:** plan 07-06 keeps `argv = [slug, "(in-process)"]` for every in-process tool (`run_capstone_disasm`, future `run_yara_inproc`, etc.) per D-19. Audit-trail semantic matches the documented pattern; no client currently consumes `argv` for routing. Recommendation adopted.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `setpriv` (util-linux) | `run_shell` (D-01) | ✓ (system) | util-linux 2.39+ (Kali rolling) | None — Phase 7 requires |
| `setfacl` (acl pkg) | `ensure_mare_shell_access` (D-03..D-06) | ✗ at present | — | None — Phase 7 adds `acl` to Dockerfile line 53 (D-04) |
| `bash` | `run_shell` argv (D-01) | ✓ (system) | bash 5+ | None |
| `file` (libmagic) | `run_file` (STATIC-01) | ✓ (Dockerfile:44) | system | None |
| `die` / `diec` (detect-it-easy) | `run_die` (STATIC-02) | ✓ (Dockerfile:46 + symlink line 161) | system | None |
| `xxd` | `run_xxd` (STATIC-03) | ✓ (Dockerfile:47) | system | None |
| `readelf` / `elfutils` | `run_readelf` (STATIC-04) | ✓ (Dockerfile:44) | system | None |
| `objdump` / `nm` (binutils-multiarch) | `run_objdump` / `run_nm` (STATIC-05) | ✓ (Dockerfile:44) | system | None |
| `rabin2` (radare2) | `run_rabin2` (STATIC-06) | ✓ (Dockerfile:46) | system | None |
| `capstone` Python | `run_capstone_disasm` (STATIC-07) | ✓ (Dockerfile:61 pip install) | 5.x | Phase 7 adds version pin `>=5.0.0` (D-20) |
| `ropper` Python | `run_ropper` (STATIC-08) | ✓ (Dockerfile:61 pip install) | 1.13.x | Phase 7 adds version pin `>=1.13.10` (D-20) |
| `jq` | `run_jq` (STATIC-09) | ✓ (Dockerfile:45) | system | None |
| `yq` | `run_yq` (STATIC-09) | ✓ (Dockerfile:53) | system | None |
| `mare-shell` UID 700 | `setpriv --reuid=mare-shell` (D-01) | ✗ at present | — | None — Phase 7 adds via `useradd -r -u 700 mare-shell` in Dockerfile (D-01) |
| Host fs supports POSIX ACL | `setfacl` on case-dirs (D-03) | ⚠ Linux native: ✓; Docker Desktop Mac/Win: ✗ | — | None — D-06 fail-loud; document as platform requirement |
| Python `pwd`, `subprocess`, `pathlib`, `base64`, `secrets` | All Phase 7 modules | ✓ (stdlib) | 3.11+ | None |

**Missing dependencies with no fallback (blocking, Phase 7 owns the install):**
- `acl` apt package — Phase 7 adds at Dockerfile:53.
- `mare-shell` UID — Phase 7 adds via `useradd` in Dockerfile.
- `capstone>=5.0.0` / `ropper>=1.13.10` version pins in `pyproject.toml` — Phase 7 adds.

**Missing dependencies with fallback:**
- None — all are either present or installed by Phase 7.

**Platform constraint:**
- Phase 7 functionality REQUIRES a Linux-native host filesystem for the `${HOST_PWD}:/agent` bind mount. Docker Desktop Mac and Windows-WSL2 (with `\\wsl$\…` paths bound through) may fail at `setfacl`. The fail-loud behavior of D-06 catches this immediately; document as a known platform requirement in v1.1 README (Phase 12 territory).

## Validation Architecture

> Nyquist Dimension 8 — mandatory per `.planning/config.json` `workflow.nyquist_validation: true`.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8+ with `pytest-asyncio` (asyncio_mode = "auto") |
| Config file | `mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]` (already exists) |
| Quick run command | `cd mcp-gateway && pytest -m "not slow" -q` |
| Full suite command | `cd mcp-gateway && pytest -q` (includes `slow`-marked tests) |
| Slow marker | already registered in `pyproject.toml` line 35 (Phase 6) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SHELL-01 (cwd pinned) | `run_shell("pwd")` returns resolved case_dir | integration | `pytest tests/test_run_shell.py::test_run_shell_pwd_equals_case_dir -x` | ❌ Wave 0 |
| SHELL-01 (timeout) | `run_shell("sleep 60", timeout=0.5)` returns `timed_out=True` within budget | integration | `pytest tests/test_run_shell.py::test_run_shell_timeout_kills_pgroup -x` | ❌ Wave 0 |
| SHELL-01 (output cap) | `run_shell("head -c 1048576 /dev/zero")` returns `stdout_truncated=True` | integration | `pytest tests/test_run_shell.py::test_run_shell_stdout_cap -x` | ❌ Wave 0 |
| SHELL-01 (auto-capture) | `run_shell("echo X")` produces `tool-logs/<ts>-run_shell-<r4>.txt` with full output | integration | `pytest tests/test_run_shell.py::test_run_shell_log_capture -x` | ❌ Wave 0 |
| SHELL-02 (mare-shell UID) | `run_shell("id -u")` returns "700" | integration | `pytest tests/test_run_shell.py::test_run_shell_drops_to_mare_shell_uid -x` | ❌ Wave 0 |
| SHELL-02 (env whitelist — token unreachable) | `run_shell("env")` does not contain `MCP_GATEWAY_TOKEN` even when set in parent env | integration | `pytest tests/test_run_shell.py::test_run_shell_env_no_secrets -x` | ❌ Wave 0 |
| SHELL-02 (env whitelist — API_KEY unreachable) | `run_shell("env")` does not contain `*_API_KEY`, `AWS_*` keys | integration | (same test as above with monkeypatch matrix) | ❌ Wave 0 |
| SHELL-02 (token file unreachable) | `run_shell("cat /agent/.mcp-gateway-token")` returns non-zero | integration | `pytest tests/test_run_shell.py::test_run_shell_cannot_read_token -x` | ❌ Wave 0 |
| SHELL-02 (`_RUN_SHELL_ALLOWED_KEYS` complete) | The whitelist frozenset exactly matches keys in `_build_shell_env`'s output | unit | `pytest tests/test_run_shell.py::test_allowed_keys_frozenset -x` | ❌ Wave 0 |
| SHELL-03 (docstring) | `run_shell.__doc__` contains "posture, not isolation" | unit | `pytest tests/test_run_shell.py::test_run_shell_docstring_posture -x` | ❌ Wave 0 |
| STATIC-01 | `run_file(case, fixtures/hello_elf)` returns `magic` field with "ELF" substring | integration | `pytest tests/test_re_static.py::test_run_file_elf -x` | ❌ Wave 0 |
| STATIC-02 | `run_die(case, fixtures/hello_pe.exe)` returns `detections` list | integration | `pytest tests/test_re_static.py::test_run_die_pe -x` | ❌ Wave 0 |
| STATIC-03 | `run_xxd(case, sample, offset=0, length=64)` returns `hex_dump` ≤ 64 KB + `hex_path` under `hex/` | integration | `pytest tests/test_re_static.py::test_run_xxd_bounded -x` | ❌ Wave 0 |
| STATIC-04 (allowlist) | `run_readelf(case, sample, ["-Z"])` raises `ValueError` | unit | `pytest tests/test_re_static.py::test_run_readelf_rejects_disallowed_flag -x` | ❌ Wave 0 |
| STATIC-04 (happy) | `run_readelf(case, fixtures/hello_elf, ["-h"])` returns ELF header text | integration | `pytest tests/test_re_static.py::test_run_readelf_header -x` | ❌ Wave 0 |
| STATIC-05 (objdump) | `run_objdump(case, fixtures/hello_elf, mode="headers")` returns headers | integration | `pytest tests/test_re_static.py::test_run_objdump_headers -x` | ❌ Wave 0 |
| STATIC-05 (nm) | `run_nm(case, fixtures/hello_elf, mode="all")` returns symbol list | integration | `pytest tests/test_re_static.py::test_run_nm_all -x` | ❌ Wave 0 |
| STATIC-06 (allowlist) | `run_rabin2(case, sample, command="zzz")` raises `ValueError` | unit | `pytest tests/test_re_static.py::test_run_rabin2_rejects_invalid_command -x` | ❌ Wave 0 |
| STATIC-06 (happy) | `run_rabin2(case, fixtures/hello_elf, command="i")` returns parsed JSON | integration | `pytest tests/test_re_static.py::test_run_rabin2_info -x` | ❌ Wave 0 |
| STATIC-07 (in-proc shape) | `run_capstone_disasm("x86","64","90c3")` returns 12-key shape + `instructions` | unit | `pytest tests/test_re_static.py::test_run_capstone_disasm_x86_64 -x` | ❌ Wave 0 |
| STATIC-08 (gadgets) | `run_ropper(case, fixtures/hello_elf, "x86_64", max_gadgets=10)` returns `gadgets: list` | integration | `pytest tests/test_re_static.py::test_run_ropper_x86_64 -x` | ❌ Wave 0 |
| STATIC-09 (jq) | `run_jq(case, "CURRENT_STATE.json", ".")` returns content | integration | `pytest tests/test_re_static.py::test_run_jq_artifact -x` | ❌ Wave 0 |
| STATIC-09 (yq) | `run_yq(case, fixture_yaml_artifact, ".")` returns content | integration | `pytest tests/test_re_static.py::test_run_yq_artifact -x` | ❌ Wave 0 |
| STATIC-10 (hard-fail) | Stub backend with colliding `run_xxd` triggers `SystemExit(78)` from `assert_no_collisions` | unit | `pytest tests/test_collision_check.py::test_assert_no_collisions_one_overlap -x` | ❌ Wave 0 |
| STATIC-10 (empty-OK) | Stub backend with no tools passes `assert_no_collisions` cleanly | unit | `pytest tests/test_collision_check.py::test_assert_no_collisions_empty_backend -x` | ❌ Wave 0 |
| STATIC-10 (multi-collision) | Multi-collision error message lists all names sorted | unit | `pytest tests/test_collision_check.py::test_assert_no_collisions_multiple_overlap -x` | ❌ Wave 0 |
| ARTIF-01 | `EXPANDED_CASE_SUBDIRS` contains the 9 names; `ensure_subdir` creates each lazily | unit | `pytest tests/test_artifacts_io.py::test_ensure_subdir_lazy` (extend Phase 6 test) | ✅ exists; extend if needed |
| ARTIF-02 (write text) | `write_artifact(case, "x.txt", "hello")` writes file; `bytes_written=5` | integration | `pytest tests/test_re_artifacts.py::test_write_artifact_text -x` | ❌ Wave 0 |
| ARTIF-02 (write binary) | `write_artifact(case, "x.bin", base64(b"hello"), mode="binary")` writes 5 bytes | integration | `pytest tests/test_re_artifacts.py::test_write_artifact_binary -x` | ❌ Wave 0 |
| ARTIF-02 (overwrite=False) | Second write to same path raises `FileExistsError` | unit | `pytest tests/test_re_artifacts.py::test_write_artifact_overwrite_false -x` | ❌ Wave 0 |
| ARTIF-02 (confine_to) | `write_artifact(case, "../escape.txt", "x")` raises `ValueError` | unit | `pytest tests/test_re_artifacts.py::test_write_artifact_rejects_traversal -x` | ❌ Wave 0 |
| ARTIF-02 (append) | `append_artifact` appends; creates if missing | integration | `pytest tests/test_re_artifacts.py::test_append_artifact -x` | ❌ Wave 0 |
| ARTIF-02 (ACL backfill) | `write_artifact` invokes `ensure_mare_shell_access`; subsequent `run_shell` can read | integration | `pytest tests/test_re_artifacts.py::test_write_artifact_grants_mare_shell -x` | ❌ Wave 0 |
| ARTIF-03 (list_artifacts) | `list_artifacts(case)` returns top-level files only | integration | `pytest tests/test_re_artifacts.py::test_list_artifacts_flat -x` | ❌ Wave 0 |
| ARTIF-03 (list_artifacts subdir) | `list_artifacts(case, subdir="tool-logs")` returns log files | integration | `pytest tests/test_re_artifacts.py::test_list_artifacts_subdir -x` | ❌ Wave 0 |
| ARTIF-03 (subdir allowlist) | `list_artifacts(case, subdir="../etc")` raises `ValueError` | unit | `pytest tests/test_re_artifacts.py::test_list_artifacts_rejects_bad_subdir -x` | ❌ Wave 0 |
| ARTIF-03 (tree) | `get_artifact_tree(case)` returns nested dict with `children` | integration | `pytest tests/test_re_artifacts.py::test_get_artifact_tree -x` | ❌ Wave 0 |
| ARTIF-03 (tree max_files cap) | Tree with > MAX_FILES files returns `truncated=True, truncation_reason="max_files"` | integration | `pytest tests/test_re_artifacts.py::test_get_artifact_tree_max_files -x` | ❌ Wave 0 |
| ARTIF-03 (tree max_depth cap) | Symlink loop in case-dir → `truncated=True, truncation_reason="max_depth"` | integration | `pytest tests/test_re_artifacts.py::test_get_artifact_tree_symlink_loop -x` | ❌ Wave 0 |
| ARTIF-04 (paged read) | `get_tool_log(case, log, offset=0, length=256)` returns 256 bytes + `next_offset=256` | integration | `pytest tests/test_re_artifacts.py::test_get_tool_log_paged -x` | ❌ Wave 0 |
| ARTIF-04 (eof) | Reading past end returns `eof=True, length_returned=0` | unit | `pytest tests/test_re_artifacts.py::test_get_tool_log_eof -x` | ❌ Wave 0 |
| ARTIF-04 (length cap) | `length > MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB*4` is clamped | unit | `pytest tests/test_re_artifacts.py::test_get_tool_log_length_cap -x` | ❌ Wave 0 |
| ARTIF-05 (resources depth-2) | Case with `tool-logs/x.txt`, `hex/y.bin`, `rop/z.json` → 3 depth-2 resources | integration | `pytest tests/test_resources.py::test_resources_depth_2 -x` | ❌ Wave 0 |
| ARTIF-05 (depth-3 NOT exposed) | `extracted/<sub>/<file>` (depth 3) is absent from `resources/list` | integration | `pytest tests/test_resources.py::test_resources_no_depth_3 -x` | ❌ Wave 0 |
| ARTIF-05 (hidden files skipped) | `.dotfile` in `tool-logs/` is not enumerated | unit | `pytest tests/test_resources.py::test_resources_skip_hidden -x` | ❌ Wave 0 |
| ARTIF-05 (resource count cap) | Case-dir with > 1024 files → resources truncated at cap | integration | `pytest tests/test_resources.py::test_resources_max_files_cap -x` | ❌ Wave 0 |
| D-35 (100 MB urandom rerun) | `run_shell("head -c 104857600 /dev/urandom")` exits cleanly, bounded RSS | integration (slow) | `pytest -m slow tests/test_run_shell.py::test_run_shell_100mb_urandom -x` | ❌ Wave 0 |
| D-29 (cmd validation: empty) | `run_shell(case, "")` raises `ValueError` | unit | `pytest tests/test_run_shell.py::test_run_shell_rejects_empty_cmd -x` | ❌ Wave 0 |
| D-29 (cmd validation: too long) | `run_shell(case, "x" * 32769)` raises `ValueError` | unit | `pytest tests/test_run_shell.py::test_run_shell_rejects_long_cmd -x` | ❌ Wave 0 |
| D-29 (cmd validation: NUL byte) | `run_shell(case, "echo\x00x")` raises `ValueError` | unit | `pytest tests/test_run_shell.py::test_run_shell_rejects_nul_byte -x` | ❌ Wave 0 |
| D-04 (`setfacl` available) | `shutil.which("setfacl")` is not None | unit | `pytest tests/test_acl_available.py::test_setfacl_on_path -x` | ❌ Wave 0 |
| D-05 (ACL idempotency) | `ensure_mare_shell_access(case)` called twice — second call no-op, no exception | unit | `pytest tests/test_artifacts_io.py::test_ensure_mare_shell_access_idempotent` (extend Phase 6 test file) | ❌ Wave 0 (extend) |
| D-06 (ACL fail-loud) | `ensure_mare_shell_access` raises `RuntimeError` if setfacl missing (mock `shutil.which`) | unit | `pytest tests/test_artifacts_io.py::test_ensure_mare_shell_access_fail_loud` | ❌ Wave 0 (extend) |
| Pitfall 1 (mare-shell exists) | `pwd.getpwnam("mare-shell").pw_uid == 700` | unit | `pytest tests/test_run_shell.py::test_mare_shell_user_exists -x` | ❌ Wave 0 |

**Total new test functions:** ~52 across 5 new test files + 2 extensions to existing files.

### Sampling Rate

- **Per task commit:** `cd mcp-gateway && pytest -m "not slow" -q` — runs all unit + non-slow integration tests; expected < 30 s.
- **Per wave merge:** `cd mcp-gateway && pytest -q` — full suite including D-35 100 MB urandom test; expected < 90 s.
- **Phase gate (before `/gsd-verify-work`):** Full suite green; collision check tested with stub backend; `mare-shell` UID exists in image; setfacl smoke test passes on host fs.

### Wave 0 Gaps

- [ ] `mcp-gateway/tests/fixtures/` directory + 3 small public-domain binaries (D-34) — `hello_elf` (ELF), `hello_pe.exe` (PE), `stripped.o` (object); each ≤ 100 KB; build instructions / source code in `fixtures/README.md`.
- [ ] `mcp-gateway/tests/test_run_shell.py` — RED stubs for all SHELL-* and Pitfall-1 / D-29 / D-35 tests.
- [ ] `mcp-gateway/tests/test_re_static.py` — RED stubs for all STATIC-* tests.
- [ ] `mcp-gateway/tests/test_re_artifacts.py` — RED stubs for all ARTIF-* tests.
- [ ] `mcp-gateway/tests/test_collision_check.py` — RED stubs for D-15 cases.
- [ ] `mcp-gateway/tests/test_acl_available.py` — RED stub for D-04.
- [ ] Extension to `mcp-gateway/tests/test_artifacts_io.py` — RED stubs for `ensure_mare_shell_access` idempotency + fail-loud tests.
- [ ] Extension to `mcp-gateway/tests/test_resources.py` (or `test_resources_unit.py`) — RED stubs for depth-2 walk, no-depth-3, cap, hidden-skip tests.

Wave 0 deliverable: every test function exists and FAILS (RED) referencing not-yet-existing modules (`tools.shell`, `tools.re_static`, `tools.re_artifacts`, `tools.collision_check`); Wave 1 / Wave 2 implementation flips them GREEN.

## Security Domain

> Required: `.planning/config.json` does not explicitly disable `security_enforcement`. Default = on.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partially | Inherited from v1.0 bearer auth; Phase 7 adds D-07 token-file 0400 (defense in depth) |
| V3 Session Management | no | Phase 7 has no session state; sessions are Phase 8 |
| V4 Access Control | yes | UID drop (D-01 setpriv), POSIX ACL grant/revoke (D-03 / D-07), env scrub (D-09) |
| V5 Input Validation | yes | `cmd` length + NUL (D-29); `case_dir` / `sample` / `relpath` via `confine_to` + `resolve_case_dir` + `resolve_sample`; `command` allowlists (`run_rabin2`, `run_readelf`, `run_objdump`, `run_nm`) |
| V6 Cryptography | no | No new crypto; bearer token unchanged from v1.0 |
| V7 Error Handling | yes | `RuntimeError` on setfacl failure (D-06); `ValueError` on validation errors (D-32); structured 12-key result on subprocess errors (Phase 6 D-04) |
| V8 Data Protection | yes | Token file 0400 (D-07); license dirs 0700 (D-07); ACL grants narrowest possible (D-03 — single GID, no group membership) |
| V12 File / Resources | yes | `confine_to` + `resolve_case_dir` + `resolve_sample` reject path traversal; `EXPANDED_CASE_SUBDIRS` allowlist for `list_artifacts` subdir; tree caps (D-24) for symlink loops |
| V13 Configuration | yes | Env-var allowlist explicit (D-09); env-var validation at module import (Phase 6 pattern); fail-loud on setfacl missing (D-06) |

### Known Threat Patterns for run_shell + typed-wrapper stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via `cmd` (`cat ../../etc/passwd`) | Information Disclosure | Posture-only — bash can `cd /etc` but `mare-shell` UID lacks read on root-owned secrets (D-07); world-readable files remain readable (documented in D-28 docstring) |
| Path traversal via `relpath` / `artifact_path` | Tampering / Info Disclosure | `confine_to(resolve_case_dir(case_dir), path)` chokepoint (Phase 6 D-11..D-14); covered by `test_artifacts_io.py` symlink-escape matrix |
| Env-var secret leak to `bash -c` | Information Disclosure | Build-from-scratch whitelist `_build_shell_env` (D-09); regression test asserts `MCP_GATEWAY_TOKEN`, `*_API_KEY`, `AWS_*`, `ANTHROPIC_*` absent (D-10) |
| Bearer-token file read from `run_shell` | Information Disclosure | Token file 0400 root-only (D-07); `mare-shell` UID gets EACCES; regression test `cat /agent/.mcp-gateway-token` returns non-zero |
| Setuid binary escalation inside `run_shell` | Privilege Escalation | `setpriv --no-new-privs` blocks (D-01); `--inh-caps=-all` drops inheritable caps |
| Supplementary-group abuse | Privilege Escalation | `setpriv --clear-groups` (D-01) |
| Argv injection via `command` parameter | Tampering | All `run_*` wrappers use `Literal[...]` allowlist for command/mode/sections; reject unknown values (D-18 + D-32) |
| Backend tool silently shadowing gateway-native tool | Spoofing | `collision_check.assert_no_collisions` hard-fail at lifespan (D-11..D-15); reverses v1.0 "backend wins" (D-14) |
| Symlink loop in `get_artifact_tree` recursion | DoS | Depth cap `MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH=8` (D-24); file count cap `MAX_FILES=1024` |
| Resource-list flood | DoS | Per-`resources/list` cap of `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES=1024` resources (D-26) |
| `run_shell` PIPE deadlock on large stdout | DoS | Inherited from Phase 6: concurrent stream drain + head buffer + file sink (verified by D-35 100 MB urandom rerun) |
| `run_shell` SIGKILL not delivered to bash subprocesses | DoS / Resource Leak | Phase 6 `start_new_session=True` + `killpg` (verified); setpriv exec-then-replace doesn't add indirection (Pitfall 9) |
| `cmd` size DoS (100 GB string) | DoS | `MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES=32768` cap (D-29) |
| `get_tool_log` giant read | DoS | `length` capped at `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB*4` (1 MB) per call (D-25) |
| Token-bound multi-tenant leak via shared `mare-shell` | Info Disclosure (across tenants) | Acknowledged limitation; v1.1 single-tenant (per `Mcp-Session-Id` keying deferred to v1.2); documented in run_shell docstring (D-28) |
| ACL silently broken on Docker Desktop Mac/Win | Tampering (false sense of security) | D-06 fail-loud `RuntimeError` on first `run_shell` call; documented platform requirement |

**Out of scope (acknowledged, deferred to v1.2+):**
- Mount-namespace isolation (would require CAP_SYS_ADMIN).
- Network egress controls per-call (Phase 11 / dynamic mode territory).
- Per-`Mcp-Session-Id` keying of `mare-shell`.

## Sources

### Primary (HIGH confidence)
- `mcp-gateway/src/mcp_gateway/runner.py` (verified shipped) — Phase 6 chokepoint, 12-key shape locked.
- `mcp-gateway/src/mcp_gateway/artifacts_io.py` (verified shipped) — `confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS`.
- `mcp-gateway/src/mcp_gateway/app.py` (verified) — `lifespan` integration point identified (line 102-103 insertion).
- `mcp-gateway/src/mcp_gateway/tools/__init__.py` (verified) — `register_all_tools` extension point.
- `mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py` (verified) — public `mcp.list_tools()` / `pinned.tool_cache` pattern.
- `mcp-gateway/src/mcp_gateway/tools/resources.py` (verified) — `_build_resource_list` extension point.
- `mcp-gateway/src/mcp_gateway/tools/case_dirs.py`, `samples.py`, `artifacts.py` (verified) — chokepoints for path/sample/artifact resolution.
- `Dockerfile` lines 35-53 (apt install — verified) and 165-176 (user setup — verified).
- `compose.yaml` (verified) — `${HOST_PWD}:/agent` bind mount confirms host-fs ACL feasibility.
- `mcp-gateway/tests/conftest.py`, `test_runner.py`, `test_artifacts_io.py` (verified) — hermetic `tmp_path` test pattern; `slow` marker registered.
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` — 35 locked decisions D-01..D-35.
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` — Phase 6 contracts Phase 7 consumes (D-01..D-21).
- `.planning/REQUIREMENTS.md` — SHELL-01..03, STATIC-01..10, ARTIF-01..05.
- `.planning/research/SUMMARY.md`, `PITFALLS.md`, `ARCHITECTURE.md`, `STACK.md` — research consensus.
- `setpriv(1)` man page — [https://man7.org/linux/man-pages/man1/setpriv.1.html](https://man7.org/linux/man-pages/man1/setpriv.1.html) — `--reuid`, `--regid`, `--clear-groups`, `--no-new-privs`, `--inh-caps` documented current.

### Secondary (MEDIUM confidence)
- [capstone PyPI](https://pypi.org/project/capstone/) — 5.0.7 (Feb 2026), manylinux2014 wheels [VERIFIED via web search].
- [ropper PyPI](https://pypi.org/project/ropper/) — 1.13.13 (Feb 2025), Python `RopperService` API [VERIFIED].
- [Ropper GitHub (sashs/Ropper)](https://github.com/sashs/Ropper) — multi-arch, capstone-backed.
- [moby/moby#15251](https://github.com/moby/moby/issues/15251) — ACL limitations inside containers.
- [moby/moby#40553](https://github.com/moby/moby/issues/40553) — setfacl not persisted during Docker build.
- [moby/moby#32915](https://github.com/moby/moby/issues/32915) — setfacl on Debian host with overlay2.
- [docker-desktop/desktop-linux#167](https://github.com/docker/desktop-linux/issues/167) — setfacl on bind mounts under Docker Desktop.
- [MCP Transports spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP, `maxMessageSize` 4 MB default.
- [ida-pro-mcp tool catalog](https://github.com/mrexodia/ida-pro-mcp) — verified no tool-name overlap with Phase 7's `run_*` / `write_artifact` / etc.

### Tertiary (LOW confidence — flagged for validation)
- [github.com/capstone-engine/capstone#2147](https://github.com/capstone-engine/capstone/issues/2147) — capstone import-error reports on non-x86_64 Mac; gateway smoke test recommended.
- LWN OverlayFS POSIX ACL article — ACL support in overlayfs added in kernel 4.9; not blocking since case-dirs are bind-mounted from host.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — every dep verified on PyPI / in Dockerfile / in man pages; versions current.
- Architecture: **HIGH** — additive only; all chokepoints (`run_tool`, `confine_to`, `mcp.list_tools()`, `EXPANDED_CASE_SUBDIRS`) shipped and tested in Phase 6 / v1.0.
- Pitfalls: **HIGH** — Pitfalls 1, 4, 5, 6 are deterministic and have direct mitigations; Pitfalls 2, 3 are host-fs dependent with fail-loud handling (D-06).
- Validation: **HIGH** — every requirement (SHELL-*, STATIC-*, ARTIF-*) maps to ≥ 1 concrete test name + command.
- Security: **HIGH** — all 12 STRIDE patterns mapped to a locked decision; no hand-rolled crypto or auth changes.

**Research date:** 2026-05-13
**Valid until:** 2026-06-12 (30 days — stable stack; capstone/ropper version pins may want re-check before milestone close).
