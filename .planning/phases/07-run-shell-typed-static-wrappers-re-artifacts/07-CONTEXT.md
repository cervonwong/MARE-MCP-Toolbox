# Phase 7: run_shell + Typed Static Wrappers + re_artifacts - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

The first MCP-visible v1.1 tool surface that consumes Phase 6's
`ReToolRunner` + `artifacts_io`:

- **One constrained shell tool** — `run_shell(case_dir, cmd)` over MCP,
  executed under a dedicated non-root `mare-shell` UID with env scrub,
  cwd-confinement to `case_dir`, hard timeout, output cap, and
  auto-capture to `tool-logs/`.
- **Twelve typed static RE wrappers** — `run_file`, `run_die`,
  `run_xxd`, `run_readelf`, `run_objdump`, `run_nm`, `run_rabin2`,
  `run_capstone_disasm`, `run_ropper`, `run_jq`, `run_yq` (counts as 12
  per the roadmap; nine subprocess wrappers + two in-process library
  wrappers + the shell helpers exposed via these).
- **Five artifact-control helpers** — `write_artifact`, `append_artifact`,
  `list_artifacts`, `get_artifact_tree`, `get_tool_log`.
- **Tool-name collision hard-fail** at gateway lifespan startup —
  reverses v1.0's "backend wins" policy from `backend_passthrough.py:8`
  so STATIC wrappers can never be silently shadowed by a backend tool
  of the same name.
- **MCP Resources extension** — `mare://cases/<case>/<relpath>` now
  walks `EXPANDED_CASE_SUBDIRS` at depth ≤ 2 so captured tool logs,
  hex dumps, ROP gadgets, disassembly, etc. are exposed alongside the
  existing flat top-level artifacts.
- **Dockerfile changes** — create the `mare-shell` UID + entrypoint
  ACL setup; revoke read access on `/agent/.mcp-gateway-token` and
  the host-secret directories from the mare-shell group.

Scope:

- New module files:
  - `mcp-gateway/src/mcp_gateway/tools/shell.py`
  - `mcp-gateway/src/mcp_gateway/tools/re_static.py`
  - `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py`
  - `mcp-gateway/src/mcp_gateway/tools/collision_check.py`
- Extensions:
  - `mcp-gateway/src/mcp_gateway/artifacts_io.py` —
    `ensure_mare_shell_access(case_dir)` lazy ACL helper.
  - `mcp-gateway/src/mcp_gateway/tools/resources.py` — walk
    `EXPANDED_CASE_SUBDIRS` to depth 2.
  - `mcp-gateway/src/mcp_gateway/tools/__init__.py` — register the
    four new tool modules.
  - `mcp-gateway/src/mcp_gateway/app.py::lifespan` — invoke
    `collision_check.assert_no_collisions(mcp)` after backend connect,
    before serving.
- Dockerfile:
  - `useradd -r -s /usr/sbin/nologin -d /nonexistent mare-shell`
  - install `acl` package for setfacl (if not already present)
  - install `python3-capstone`, `ropper` (pip), `cstool` available
  - revoke `/agent/.mcp-gateway-token` group read; lock down
    `/home/agent/.idapro` / `.binaryninja` / `.codex` / `.claude` to
    `agent`-only (chmod 700)

Explicitly NOT in this phase (deferred to other phases):

- `sessions/` package or any `open_r2_session` / `r2_cmd` work
  (Phase 8).
- `jobs.py` / `BackgroundJobRegistry` / `start_tool_job` (Phase 9).
- Extraction tools (`run_binwalk`, `run_unblob`, `run_upx_*`,
  `promote_extracted_sample`) — Phase 10.
- Dynamic tools (`run_strace`, `run_ltrace`, `run_qemu_user`, gdb
  sessions) — Phase 11.
- `malware-analysis-orchestrator` skill update — Phase 12.
- Mount-namespace isolation for `run_shell` — deferred to v1.2
  (CAP_SYS_ADMIN cost); v1.1 confinement is posture-only.
- Per-`Mcp-Session-Id` scoping of `mare-shell` — deferred to v1.2.
- Convergence of `subprocess_runner.run_script` and `ReToolRunner` —
  deferred to v1.2.

</domain>

<decisions>
## Implementation Decisions

### `mare-shell` UID drop strategy

- **D-01:** `run_shell` invokes its bash payload via **`setpriv`**,
  not `gosu` / `runuser`. Exact argv (Python list passed to
  `ReToolRunner.run`):

  ```python
  argv = [
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

  *Rationale:* `setpriv` (util-linux, already in the image) gives
  three defense-in-depth knobs `gosu` does not: `--clear-groups`
  wipes supplementary groups, `--no-new-privs` blocks setuid escalation
  inside the shell (matters because the container runs with
  `SYS_PTRACE` + `seccomp=unconfined`), and `--inh-caps=-all` drops the
  inheritable capability set. The gateway already drops to `agent` at
  the entrypoint via `gosu`, so `gosu`-vs-`setpriv` is a Phase 7-only
  decision; we pick the stricter one.

- **D-02:** `run_shell` uses `bash -c <cmd>`, **never** `bash -lc`.
  The `-l` flag triggers `/etc/profile` + `~/.bash_profile` sourcing,
  which would re-introduce environment we just scrubbed and which
  defeats the slug-and-capture model. Documented in the `run_shell`
  docstring (also satisfies SHELL-03's "structural posture, not
  isolation" disclosure).

### `mare-shell` ACL strategy

- **D-03:** Case-dirs are made writable by `mare-shell` via **POSIX
  ACLs** (`setfacl`), not chmod / SGID-dir / chgrp. The exact ACL
  applied to every case-dir on first `run_shell` (or `write_artifact`)
  call is:

  ```bash
  setfacl  -m  u:agent:rwx,g:mare-shell:rwx,o::---  <case_dir>
  setfacl  -d  -m  u:agent:rwx,g:mare-shell:rwx,o::---  <case_dir>
  ```

  The default-ACL (`-d`) means files run_shell creates under
  `case_dir/` inherit the same agent:rwx + mare-shell:rwx, no
  set-group-id directory needed. Owner stays `agent`, primary group
  stays `agent`, so external (non-gateway) inspection by `agent`
  remains unaffected. `mare-shell` is **NOT** added to the `agent`
  group — the ACL alone grants access.

  *Rationale:* SGID-dir + chgrp would require `mare-shell` to be in
  `agent`'s group (or vice-versa), which broadens the privilege
  gradient and can leak via any `agent`-readable file that gets
  group-readable bits set elsewhere. POSIX ACLs scope the grant
  precisely to `g:mare-shell` on case-dirs only. Default-ACL means
  no per-file fixup is ever needed.

- **D-04:** The `acl` package is added to the Dockerfile apt install
  list (alongside `yara upx-ucl qemu-user yq` on the existing line at
  Dockerfile:53), so `setfacl` is available in the runtime image. A
  one-line pytest at `mcp-gateway/tests/test_acl_available.py`
  asserts `shutil.which("setfacl")` is not None — fail-fast on image
  drift.

### ACL backfill for pre-existing case-dirs

- **D-05:** Lazy backfill, **not** eager. A new public helper
  `artifacts_io.ensure_mare_shell_access(case_dir: Path) -> None` runs
  the two `setfacl` commands in D-03 if they have not yet been
  applied (cheap idempotent re-run; setfacl is a no-op when the ACL
  is already set). The helper is invoked from `run_shell` *before*
  ReToolRunner spawn and from `write_artifact` / `append_artifact`
  *before* the write. It is NOT called from `ensure_subdir` —
  read-only artifact creators (the runner writing tool-logs) don't
  need mare-shell ACLs because the gateway writes them as `agent`.

  *Rationale:* Eager backfill at lifespan would add linear-in-cases
  startup work and a failure mode (one bad case-dir blocks gateway
  start). Lazy is amortized to the first shell call per case-dir.

- **D-06:** `ensure_mare_shell_access` raises `RuntimeError` if
  `setfacl` is missing from PATH or if either command exits non-zero
  — never silently degrades to "shell can't write to its own
  case_dir." Phase 7 ships with ACLs required, not optional.

### `mare-shell` filesystem visibility (Pitfall 2 mitigation)

- **D-07:** The Dockerfile final-stage entrypoint revokes
  `mare-shell`'s read access on every secret-bearing host path
  before exec'ing the agent process:

  | Path | Action | Why |
  |------|--------|-----|
  | `/agent/.mcp-gateway-token` | `chown root:root`, `chmod 0400` | Bearer token; only `gateway-agent` reads it via env at startup. |
  | `/home/agent/.idapro/` | `chmod 0700` (agent-only) | IDA license + Hex-Rays state |
  | `/home/agent/.binaryninja/` | `chmod 0700` | BN license |
  | `/home/agent/.codex/`, `/home/agent/.claude/` | `chmod 0700` | Agent CLI auth state |
  | `/root/` | `chmod 0700` (already root-only, double-check) | Defense-in-depth |
  | `/agent/uploads/` | ACL: `u:mare-shell:r-x,d:u:mare-shell:r-x` | Lets `run_shell` `strings ../uploads/<sha>` cross-case |
  | `/agent/scripts/` | World-readable (no secrets in scripts) | Lets `run_shell` reuse `collect_*` etc. |

  These revocations are baked into the image (Dockerfile + entrypoint)
  so they survive container restart without runtime fixup.

- **D-07a:** *(Revision addendum to D-07 — formalises the
  recursive-uploads-ACL step that was already required by Pitfall 4.)*
  The Dockerfile entrypoint snippet re-applies the `/agent/uploads/` ACL
  recursively on every container start, because volume re-mounts at
  container start can re-introduce files without the `mare-shell` ACL:

  ```sh
  # Default ACL: every NEW file/dir under /agent/uploads inherits r-x for mare-shell
  setfacl -d -m u:mare-shell:r-x /agent/uploads
  # Backfill: every EXISTING file/dir under /agent/uploads gets the same ACL now
  find /agent/uploads -mindepth 1 -exec setfacl -m u:mare-shell:r-x {} \;
  ```

  This runs once per container start (entrypoint, before `exec`-ing the
  agent process). Cost is small (one walk of `/agent/uploads/`) and
  guarantees cross-case sample readability survives `docker compose
  restart` and host-volume churn. Implemented in plan 07-01 Task 1
  entrypoint heredoc. Resolves RESEARCH Open Question 1.

- **D-08:** Three regression tests assert the posture (added to
  `mcp-gateway/tests/test_run_shell.py`):

  - `run_shell("id -u")` returns the `mare-shell` UID, not `agent`.
  - `run_shell("cat /agent/.mcp-gateway-token")` returns non-zero
    exit + empty stdout (or `Permission denied` in stderr).
  - `run_shell("env | grep -E 'TOKEN|API_KEY|AWS_|ANTHROPIC_|OPENAI_'")`
    returns empty stdout (env scrub asserted in addition to ACL
    asserts).

### `run_shell` environment whitelist

- **D-09:** `run_shell` builds the child env from scratch (NOT from
  `os.environ` minus a blacklist), via this whitelist function:

  ```python
  def _build_shell_env(case_dir: Path, sample_path: Path | None) -> dict[str, str]:
      env = {
          "PATH":   "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
          "HOME":   "/var/empty",              # mare-shell has no home; deny ~/.* writes
          "TERM":   "dumb",                    # no terminal capabilities
          "NO_COLOR": "1",                     # https://no-color.org/
          "COLUMNS": "120",                    # deterministic xxd / objdump width
          "LANG":   "C.UTF-8",                 # predictable locale, UTF-8 safe
          "LC_ALL": "C.UTF-8",                 # overrides any leaked LC_*
          "MARE_CASE_DIR": str(case_dir),      # agent-introspection: $MARE_CASE_DIR/extracted
      }
      if sample_path is not None:
          env["MARE_SAMPLE_PATH"] = str(sample_path)  # cross-case sample reference
      return env
  ```

  `PWD` is set by bash from `cwd=case_dir`. `SHLVL` is set by bash.
  No other env vars leak in. The whitelist is the **complete** set,
  enumerated as a module-level frozenset
  `_RUN_SHELL_ALLOWED_KEYS` so tests can assert no extra keys.

  *Rationale:* Whitelist (allowlist) over blacklist matches research
  consensus (PITFALLS Pitfall 2 + SUMMARY's "explicit allowlist").
  Blacklist is one missed env var away from leaking a secret;
  whitelist requires the leak to be added explicitly. Two
  `MARE_*` vars make `run_shell` self-locating — agents can `cd
  $MARE_CASE_DIR/extracted` without re-passing the case_dir.

- **D-10:** Explicitly **excluded** keys, enumerated for the
  regression test that asserts they never reach the shell:

  | Pattern | Examples |
  |---------|----------|
  | `MCP_GATEWAY_*` | `MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_RUNNER_*`, `MCP_GATEWAY_MAX_JOB_LOG_MB`, … |
  | `*_API_KEY` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BRAVE_API_KEY`, … |
  | `AWS_*` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` |
  | `ANTHROPIC_*` | Anthropic CLI/SDK state |
  | `OPENAI_*` | OpenAI CLI/SDK state |
  | `BN_LICENSE_*` | Binary Ninja license env |
  | `IDA_*` | IDA license + Hex-Rays env |
  | `GITHUB_*` | GH/CI tokens if container ever runs in CI |
  | `SSH_*`, `GPG_*` | Forwarded auth sockets |

  The whitelist's hard "build from scratch" approach (D-09) makes
  this list pure documentation, not enforcement — but the test
  asserts `run_shell("env")` output contains none of these keys, so
  a future contributor who replaces the whitelist with a blacklist
  fails the test instead of leaking silently.

### Tool-name collision hard-fail

- **D-11:** A new module `tools/collision_check.py` exposes:

  ```python
  def assert_no_collisions(mcp: FastMCP) -> None:
      """Hard-fail at lifespan if gateway-native and backend tool names overlap.

      Called from app.py::lifespan AFTER register_all_tools(mcp) and
      AFTER PinnedBackend has populated its tool_cache (i.e., after the
      first refresh_backend_tools() call), BEFORE the app starts serving.

      Raises RuntimeError(EX_CONFIG = 78) on collision; the message
      lists every colliding name + the backend that owns it so the
      operator's first journalctl line is actionable.
      """
  ```

- **D-12:** Scope: **ALL** gateway-native tools (not just `run_*`),
  checked against the active backend's `list_tools()`. This protects
  v1.0 tools (`init_case`, `collect_strings`, `get_artifact`, etc.)
  too — if IDA Pro starts shipping a `get_artifact` tool tomorrow,
  the gateway should refuse to start rather than silently shadow
  ours.

- **D-13:** Failure mode: `RuntimeError` raised in lifespan →
  Starlette refuses to serve → gateway exit code **78** (EX_CONFIG
  per `sysexits.h`), distinguishing config errors from generic
  failures. Operator-facing surface:

  - **stderr** (`logging.getLogger("mcp_gateway.collision_check").error(...)`):
    `FATAL: gateway-native tool names collide with backend '<name>': ['toolA', 'toolB']`
  - The exit code matters because `compose.yaml`'s `restart: on-failure`
    semantics treat code 78 the same as any other non-zero, but a
    grep for EX_CONFIG in operator runbooks is cleaner than reading
    full logs.
  - No new health endpoint — keeps the surface area unchanged.

- **D-13a:** *(Revision addendum to D-13 — pins the Python-level
  raise mechanism.)* `assert_no_collisions` raises the collision failure
  by calling `sys.exit(78)` (not `raise RuntimeError(...)`) so that
  Starlette / uvicorn cannot catch-and-translate the failure during
  lifespan startup. The exit-code-78 contract from D-13 is preserved
  verbatim; only the Python-level raise mechanism is pinned:

  ```python
  log.error("FATAL: gateway-native tool names collide with backend %r: %s",
            backend_name, sorted(colliding))
  sys.exit(_EX_CONFIG)   # _EX_CONFIG = 78  (sysexits.h)
  ```

  Wave 0 RED test in plan 07-01 (`tests/test_collision_check.py`) asserts
  the contract with `pytest.raises(SystemExit) as exc: ...; assert
  exc.value.code == 78`. Plan 07-03 (collision_check.py implementation)
  and plan 07-08 (app.py lifespan wiring) are already internally
  consistent on this choice. Resolves RESEARCH Open Question 2.

- **D-14:** This **reverses** v1.0's "backend wins" policy stated
  in `mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py:8`.
  The comment block at the top of that file is updated to reflect
  the new policy ("Conflict policy: hard-fail at gateway lifespan
  startup. See tools/collision_check.py"). The runtime dispatcher
  in `call_gateway_or_backend_tool` still keys by name — since
  startup guarantees no overlaps, the "if pinned and name in
  backend_tools" branch is reachable only for unambiguously
  backend-owned names. No semantic change post-startup.

- **D-15:** A new test `mcp-gateway/tests/test_collision_check.py`
  covers:
  - Empty backend (no collision) → returns cleanly.
  - Backend with one colliding tool → raises `RuntimeError`,
    message contains the colliding name.
  - Backend with multiple colliding tools → all names appear in
    the error message (sorted, deterministic).
  - Stub-backend test that monkeypatches `session_state.PINNED_BACKEND`
    so no real IDA/BN/Ghidra is needed.

### Module split for Phase 7 tools

- **D-16:** Four new files under `mcp-gateway/src/mcp_gateway/tools/`,
  each with its own `register(mcp)` entry point called from
  `tools/__init__.py::register_all_tools` (matching the existing
  pattern in `__init__.py:17-22`):

  | File | Tools registered |
  |------|------------------|
  | `tools/shell.py` | `run_shell` |
  | `tools/re_static.py` | `run_file`, `run_die`, `run_xxd`, `run_readelf`, `run_objdump`, `run_nm`, `run_rabin2`, `run_capstone_disasm`, `run_ropper`, `run_jq`, `run_yq` (11 tools — count of 12 in the roadmap is satisfied with `run_shell` + 11 typed wrappers) |
  | `tools/re_artifacts.py` | `write_artifact`, `append_artifact`, `list_artifacts`, `get_artifact_tree`, `get_tool_log` |
  | `tools/collision_check.py` | (no `register`; exports `assert_no_collisions(mcp)` for `app.py::lifespan` to call) |

  *Rationale:* Three feature-coherent files plus the small collision
  module is the research consensus. Splitting `re_static.py` further
  (disasm-only / filemeta-only) would scatter related tests; combining
  it with shell would muddy the "constrained shell vs structured
  wrapper" line in tooling docs.

- **D-17:** Test files mirror the module split:
  `tests/test_run_shell.py`, `tests/test_re_static.py`,
  `tests/test_re_artifacts.py`, `tests/test_collision_check.py`.

### Typed wrapper API shape

- **D-18:** **Wrapper-by-wrapper** API contract. All wrappers
  take `case_dir` as their first positional arg (matching the
  v1.0 convention in `tools/artifacts.py:115`) and return a dict
  that **always** layers on top of `ReToolRunner`'s 12-key shape
  (D-03 of Phase 6) — or its in-process equivalent (D-19) for
  capstone / ropper.

  | Tool | Signature | Slug | Returns (in addition to base 12 keys) |
  |------|-----------|------|----------------------------------------|
  | `run_file` | `(case_dir, sample)` | `run_file` | `magic: str` (the single-line libmagic verdict) |
  | `run_die` | `(case_dir, sample)` | `run_die` | `detections: list[dict]` (parsed from `die -j`) |
  | `run_xxd` | `(case_dir, sample, offset: int = 0, length: int = 1024)` | `run_xxd` | `hex_dump: str` (capped at 64 KB), `hex_path: str` (case-rel path to full slice under `hex/`) |
  | `run_readelf` | `(case_dir, sample, sections: list[str])` | `run_readelf` | `output: str` (head; full in `log_path`) — `sections` validated against allowlist `{"-h","-l","-d","-S","-s","-r","-a","-W"}`; raises `ValueError` on disallowed flag |
  | `run_objdump` | `(case_dir, sample, mode: Literal["headers","disasm","syms","relocs","all"])` | `run_objdump` | `output: str` — `mode` mapped internally to argv flags |
  | `run_nm` | `(case_dir, sample, mode: Literal["all","dynamic","undefined","defined"])` | `run_nm` | `symbols: list[dict]` parsed when `mode != "all"`; raw `output` otherwise |
  | `run_rabin2` | `(case_dir, sample, command: Literal["i","is","iI","ii","iE","iz","zz","iL"])` | `run_rabin2` | argv = `["rabin2", "-j", command, sample]`; returns parsed `json_output: Any` |
  | `run_capstone_disasm` | `(arch: str, mode: str, bytes_hex: str, base_addr: int = 0, case_dir: str \| None = None)` | `run_capstone_disasm` | **In-process** (capstone Python lib). Returns `instructions: list[{address, mnemonic, op_str, bytes}]`. If `case_dir` provided, JSON dump to `disassembly/capstone-<rand4>.json`. |
  | `run_ropper` | `(case_dir, sample, arch: str, filter: str \| None = None, badbytes: str \| None = None, max_gadgets: int = 1024)` | `run_ropper` | **In-process** (ropper Python lib). Returns `gadgets: list[{address, instructions, bytes}]` (capped at `max_gadgets`). Full gadget list JSON-dumped to `rop/ropper-<rand4>.json`. |
  | `run_jq` | `(case_dir, artifact_path, expr)` | `run_jq` | `result: str` (head); argv = `["jq", expr, <confined artifact path>]` |
  | `run_yq` | `(case_dir, artifact_path, expr)` | `run_yq` | `result: str`; argv = `["yq", expr, <confined artifact path>]` |

  `sample` is always resolved via `samples.resolve_sample(sample)` (the
  v1.0 sha256 / case-dir resolver). `artifact_path` is always resolved
  via `confine_to(resolved_case_dir, artifact_path)`.

- **D-19:** For the **in-process** wrappers (`run_capstone_disasm`,
  `run_ropper`), a small helper in `tools/re_static.py` produces a
  ReToolRunner-compatible return dict so MCP clients see uniform
  shape:

  ```python
  def _inproc_result(case_dir, slug, output_text, log_relpath, started_at) -> dict:
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
          "log_path": log_relpath,   # case-dir-relative
          "argv": [slug, "(in-process)"],
          "slug": slug,
      }
  ```

  *Rationale:* Capstone and Ropper produce typed JSON natively from
  their Python bindings — paying a subprocess spawn + cstool/ropper
  text-parse round-trip just for "uniformity with the runner" would
  cost ~50 ms per call and risk parse-error variance. The in-proc
  wrappers keep the contract uniform at the MCP boundary without
  the round-trip.

  Both wrappers still write to `disassembly/` / `rop/` via
  `tool_log_path(case_dir, slug)`-style naming so the artifact
  capture story is identical to subprocess-runner wrappers.

- **D-20:** `run_capstone_disasm` and `run_ropper` add two pip deps
  pinned in `mcp-gateway/pyproject.toml`:

  ```toml
  "capstone>=5.0.0",
  "ropper>=1.13.10",
  ```

  Both are pure-Python with C extensions; no new apt deps needed.
  These are net-new deps (not in v1.0's pin set); container image
  size grows by ~6 MB.

### Artifact-control helper semantics

- **D-21:** `write_artifact(case_dir, relpath, content, *, mode:
  Literal["text","binary"] = "text", overwrite: bool = False) ->
  dict`. Behavior:

  - `text`: `content` is a `str`, written as UTF-8.
  - `binary`: `content` is a base64-encoded `str` in the MCP wire
    payload; decoded to bytes server-side.
  - `overwrite=False` (default): raises `FileExistsError` if the
    target file already exists.
  - `overwrite=True`: replaces.
  - Calls `confine_to(resolve_case_dir(case_dir), relpath)` first;
    rejects path-traversal per Phase 6 D-11.
  - Calls `artifacts_io.ensure_mare_shell_access(case_dir)` so a
    subsequent `run_shell` can read what was written.
  - Returns `{case_dir, relpath, bytes_written, mode, overwrote: bool}`.

- **D-22:** `append_artifact(case_dir, relpath, content, *, mode:
  Literal["text","binary"] = "text") -> dict`. Append-only; creates
  the file if missing; no `overwrite` flag (append is always
  additive). Useful for log-streaming patterns (run-by-hand `tee`-style
  workflows from `run_shell`).

- **D-23:** `list_artifacts(case_dir, subdir: str | None = None) ->
  dict`. Flat listing of one directory (top-level case-dir if
  `subdir` is None, else `case_dir/<subdir>` validated against
  `EXPANDED_CASE_SUBDIRS + ("",)`). Returns:

  ```python
  {
      "case_dir": str,
      "subdir": str | None,
      "files": [{"name": str, "size": int, "mtime": float}, ...],
  }
  ```

  Does NOT recurse. For recursive view, use `get_artifact_tree`.

- **D-24:** `get_artifact_tree(case_dir) -> dict`. Recursive tree
  walk of `case_dir` with bounded fan-out:

  ```python
  {
      "case_dir": str,
      "tree": {
          "name": str,
          "type": "dir" | "file",
          "size": int,             # files only
          "children": [...],       # dirs only
      },
      "truncated": bool,
      "truncation_reason": str | None,   # "max_files" | "max_depth" | None
      "file_count": int,
  }
  ```

  Caps configurable via env vars (same pattern as Phase 6 D-08):

  | Env var | Default | Purpose |
  |---------|---------|---------|
  | `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES` | `1024` | Stop walking once this many files are visited; set `truncated=True`. |
  | `MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH` | `8` | Refuse to recurse past this depth (handles malicious symlink loops in `extracted/`). |

  Hidden files (`.gsd_state`, dot-prefixed) are skipped (consistent
  with `tools/artifacts.py:_is_invalid_filename`).

- **D-25:** `get_tool_log(case_dir, log_name, *, offset: int = 0,
  length: int = 65536) -> dict`. Bytes-by-offset range read for
  large captured logs (Phase 6 caps per-log at 256 MB, far above
  the MCP 25k-token response cap). Returns:

  ```python
  {
      "case_dir": str,
      "log_name": str,             # the path relative to case_dir/tool-logs/
      "offset": int,
      "length_requested": int,
      "length_returned": int,      # ≤ length_requested; bounded by file size
      "total_size": int,           # full file size
      "content": str,              # UTF-8-safe-truncated (Phase 6's truncate helper)
      "eof": bool,                 # true iff offset+length_returned == total_size
      "next_offset": int,          # offset + length_returned; convenience for paged reads
  }
  ```

  Path resolution: `confine_to(case_dir / "tool-logs", log_name)`.
  Cap on `length` argument: max `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB * 4`
  bytes (default 1 MB) per call — prevents accidental
  agent-issued giant reads.

  *Rationale:* Bytes-by-offset matches Phase 6's head-cap mental model
  exactly, and bytes are what the tool actually wrote. Lines-by-number
  would need line-index bookkeeping per file. UTF-8-safe truncation
  reuses Phase 6's helper.

### MCP Resources expansion

- **D-26:** `tools/resources.py::_build_resource_list` is extended
  to walk `EXPANDED_CASE_SUBDIRS` at depth ≤ 2 under each case-dir,
  in addition to the existing top-level flat artifact enumeration.
  URI form remains `mare://cases/<case>/<relpath>` where `<relpath>`
  may now include one subdir component:

  ```
  mare://cases/<case>/<artifact>                       # existing v1.0 (depth 1)
  mare://cases/<case>/tool-logs/<file>                 # new (depth 2)
  mare://cases/<case>/hex/<file>                       # new
  mare://cases/<case>/rop/<file>                       # new
  mare://cases/<case>/disassembly/<file>               # new
  mare://cases/<case>/decompilation/<file>             # new
  mare://cases/<case>/xrefs/<file>                     # new
  mare://cases/<case>/extracted/<file>                 # new (extracted/<sub>/ not exposed; Phase 10 will revisit)
  ```

  Cap: at most `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES` (1024) resources
  per `resources/list` response across all cases, to avoid blowing
  the MCP wire on a directory full of extracted children.
  `extracted/<sub>/<file>` (depth 3) is NOT exposed in Phase 7;
  Phase 10's extraction tier will decide whether to recurse.

- **D-27:** A new env var `MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH`
  (default `2`) caps the resource walk independently of
  `MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH` (default `8`). Resources are
  shallower because the MCP client downloads the full URI list
  every `resources/list`.

### `run_shell` operational details

- **D-28:** `run_shell(case_dir: str, cmd: str, *, timeout: float |
  None = None) -> dict` is registered with `@mcp.tool()`. Slug is
  `"run_shell"`. Timeout default = ReToolRunner's default (55 s via
  `MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S`); callers may override
  per-call.

  Docstring (per SHELL-03) explicitly states:

  > Executes `cmd` as a bash one-liner inside the case directory.
  > Confinement is **posture, not isolation**: the shell runs as a
  > dedicated non-root `mare-shell` UID with a stripped environment,
  > a cwd pinned to `case_dir`, a hard timeout, an output cap, and
  > auto-capture to `tool-logs/`. The `MCP_GATEWAY_TOKEN`, API keys,
  > and AWS credentials are NOT reachable from inside the shell.
  > A determined attacker controlling the agent CAN still read the
  > container's world-readable filesystem. Mount-namespace isolation
  > and network egress controls are deferred to v1.2.

- **D-29:** `cmd` is rejected with `ValueError` if:
  - It is empty / whitespace-only.
  - It exceeds `MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES` (default
    `32_768` — 32 KiB; agents that need more should
    `write_artifact` a script and `bash <script.sh>` instead).
  - It contains a NUL byte (defensive — bash chokes on these and
    they're never legitimate).

  No further argv-parsing or "dangerous command" detection — that's
  precisely what Pitfall 2 rejects ("the entire shell language is
  the surface; argv-parse for safety is fool's errand").

### Cross-tool conventions

- **D-30:** Every wrapper in `re_static.py` accepts an optional
  `timeout: float | None = None` kwarg, forwarded to
  `ReToolRunner.run_tool(...)`. No wrapper hard-codes a timeout
  below the runner default; tools that legitimately need longer
  (e.g., `run_ropper` on a 50 MB binary) document the recommended
  override in their docstring.

- **D-31:** Every wrapper sets its `slug` to its public tool name
  (e.g., `run_xxd`, `run_objdump`), matching the regex in Phase 6
  D-09 `^[a-z0-9][a-z0-9_-]{0,39}$`. This makes the tool-log
  filename instantly recognizable
  (`tool-logs/20260513T142301Z-run_xxd-a3f7.txt`).

- **D-32:** Every wrapper raises early (before any subprocess spawn)
  on:
  - `case_dir` failing `resolve_case_dir`.
  - `sample` failing `resolve_sample`.
  - Any allowlist violation (`run_readelf` sections, `run_objdump`
    mode, `run_rabin2` command, etc.).

  Validation errors are `ValueError`s with descriptive messages so
  the agent gets actionable feedback over MCP (matches v1.0 tools'
  error semantics).

### Test design

- **D-33:** Test layout (one file per module + the runner-replay
  test):
  - `tests/test_run_shell.py` — env scrub, UID assertion, token
    inaccessibility, cwd confinement, timeout/output cap parity
    with Phase 6, ANSI strip, NUL byte rejection, cmd-size cap.
  - `tests/test_re_static.py` — one happy-path test per wrapper
    (`run_file` against a known ELF in `tests/fixtures/`,
    `run_capstone_disasm` against a hand-crafted byte sequence, etc.)
    plus allowlist-violation tests for `run_readelf` / `run_objdump`
    / `run_nm` / `run_rabin2`.
  - `tests/test_re_artifacts.py` — `write_artifact` text + binary,
    `overwrite=False` raises, `append_artifact` appends,
    `list_artifacts` enumerates, `get_artifact_tree` returns
    tree-with-caps, `get_tool_log` paged-read with `next_offset`.
  - `tests/test_collision_check.py` — covered in D-15.
  - `tests/test_resources.py` — extension assertion: a case-dir
    with files under `tool-logs/` / `hex/` / `rop/` produces
    resources at depth-2 URIs, count is capped, hidden files
    skipped, depth-3 `extracted/<sub>/<file>` NOT exposed.

- **D-34:** `tests/fixtures/` is created (new subdirectory under
  `mcp-gateway/tests/`) with three small public-domain ELF/PE
  binaries (e.g., a `Hello World` ELF compiled in CI from inline
  asm, a tiny PE built with mingw, a stripped object file). Source
  code for each binary lives alongside the binary so contributors
  can regenerate. Fixtures are <200 KB total — kept in-repo.

- **D-35:** The 100 MB-of-`/dev/urandom` test from Phase 6 is
  **rerun** at the run_shell layer (`run_shell("head -c
  104857600 /dev/urandom")`) to assert the chokepoint integrity
  is preserved through the full STATIC stack — not just at the
  bare ReToolRunner layer. Marked `slow` (same fixture as
  Phase 6).

### Claude's Discretion (within these constraints)

- Exact internal layout of the `_inproc_result` helper —
  whether it lives in `tools/re_static.py` or moves to
  `artifacts_io.py` is the planner's call (recommendation:
  `re_static.py` since capstone/ropper are its only consumers).
- Whether `run_readelf`'s allowlist `{"-h","-l","-d","-S","-s",
  "-r","-a","-W"}` includes a couple more harmless flags
  (`-n` for notes, `-V` for version info) is the planner's call.
- Whether the Dockerfile creates `mare-shell` with a specific
  UID (e.g., `useradd -r -u 700 mare-shell`) or lets useradd
  pick — recommendation: pin to `700` so docker-image-diff is
  deterministic across rebuilds.
- Whether `get_tool_log`'s response includes a `sha256` of the
  full file (helps verify chunked reads reassemble correctly) —
  recommended yes, but not load-bearing.
- Whether `run_jq` / `run_yq` impose a max-result-size cap
  beyond the runner's stdout head — agents tend to `--compact-output`
  these for a reason; recommendation: leave at runner default.
- Whether `MARE_SAMPLE_PATH` in the env (D-09) is set when the
  sample isn't resolvable (e.g., `run_shell` was called without a
  sample arg) — recommendation: omit the key entirely rather than
  set to empty string, so bash `[ -z "$MARE_SAMPLE_PATH" ]` works.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase spec
- `.planning/ROADMAP.md` §"Phase 7: run_shell + Typed Static Wrappers + re_artifacts" — 6 success criteria (SC-1..SC-6)
- `.planning/REQUIREMENTS.md` §Constrained Shell (SHELL-01..03), §Typed Static Wrappers (STATIC-01..10), §Artifact Tree & Control Helpers (ARTIF-01..05)
- `.planning/PROJECT.md` §"Current Milestone: v1.1 Remote RE Tool Expansion" — `run_shell` + typed wrappers + artifact helpers bullets
- `.planning/STATE.md` §Pending Todos — Phase 7's two open decisions (env whitelist, mare-shell ACL) are CLOSED by this CONTEXT

### Prior-phase contracts (lock-ins this phase consumes)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` §Decisions — D-01..D-04 (runner API), D-08 (env-var config knobs), D-09 (tool-log filename), D-11..D-14 (`confine_to`), D-15..D-16 (`ensure_subdir`, `EXPANDED_CASE_SUBDIRS`), D-17..D-18 (process-group cleanup)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-PLAN.md` (waves 0/1/2) — concrete shapes of the runner / artifacts_io modules Phase 7 imports from

### Research consensus (cross-document positions)
- `.planning/research/SUMMARY.md` §"Phase 3: `run_shell` + Typed Static Wrappers + `re_artifacts`" — rationale, deliverable list, Pitfalls addressed
- `.planning/research/SUMMARY.md` §"Critical Pitfalls" — Pitfalls 2 (run_shell posture), 3 (output bombs + ANSI), 7 (confine_to canonical helper), 12 (head+log_path), 17 (tool-name collisions)
- `.planning/research/SUMMARY.md` §"Open Decisions Flagged for Phase Planning" — Phase 3's env whitelist + ACL questions (CLOSED in this CONTEXT)
- `.planning/research/PITFALLS.md` §Pitfall 2 — run_shell cwd-escape mitigation; the `id -u` + `cat /agent/.mcp-gateway-token` test cases (D-08 in this CONTEXT)
- `.planning/research/PITFALLS.md` §Pitfall 3 — ANSI strip + slow-loris + output-bomb assertions (inherited from Phase 6 runner; rerun via run_shell in D-35)
- `.planning/research/PITFALLS.md` §Pitfall 7 — `confine_to` canonical helper (Phase 6's D-11 delivers this; Phase 7 consumes it on every path-accepting tool)
- `.planning/research/PITFALLS.md` §Pitfall 17 — tool-name collisions (D-11..D-15 in this CONTEXT)
- `.planning/research/ARCHITECTURE.md` — additive-changes diagram (Phase 7 adds 4 new tool modules + 1 helper module + 1 lifespan hook; no v1.0 file rewritten except `backend_passthrough.py` comment update at top)
- `.planning/research/STACK.md` — confirms new pip deps `capstone`, `ropper`; confirms apt deps satisfied (the existing `yara upx-ucl qemu-user yq` apt line already includes the bulk; `acl` is the only new apt addition)

### Code to modify or extend
- `mcp-gateway/src/mcp_gateway/runner.py` — read-only consumer (`run_tool(...)`)
- `mcp-gateway/src/mcp_gateway/artifacts_io.py` — **extend** with `ensure_mare_shell_access(case_dir)` (D-05/D-06)
- `mcp-gateway/src/mcp_gateway/tools/__init__.py:14-22` — register the four new tool modules (D-16)
- `mcp-gateway/src/mcp_gateway/app.py::lifespan` — invoke `collision_check.assert_no_collisions(mcp)` after backend connect, before serving (D-11)
- `mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py:1-10` — comment block top update only; runtime dispatch unchanged (D-14)
- `mcp-gateway/src/mcp_gateway/tools/resources.py:70` — extend `_build_resource_list` to walk `EXPANDED_CASE_SUBDIRS` at depth ≤ 2 (D-26..D-27)
- `mcp-gateway/src/mcp_gateway/tools/case_dirs.py::resolve_case_dir` — read-only consumer
- `mcp-gateway/src/mcp_gateway/tools/samples.py::resolve_sample` — read-only consumer (used by every typed wrapper)
- `mcp-gateway/src/mcp_gateway/tools/artifacts.py:115-139` — pattern reference for path resolution; Phase 7's `write_artifact` etc. live in `tools/re_artifacts.py`, not here
- `mcp-gateway/pyproject.toml` — add `capstone>=5.0.0`, `ropper>=1.13.10` to deps (D-20)
- `Dockerfile:35-53` apt install — add `acl` package (D-04); add `python3-capstone` if not already present
- `Dockerfile:165-176` — add `mare-shell` UID 700 (D-01); apply `/agent/.mcp-gateway-token` chmod 0400, `/home/agent/.idapro` chmod 0700, etc. (D-07)
- `docker-bin/configure-agent-mcp.sh` or new entrypoint snippet — re-apply file-permission revocations on container start (resilient to volume re-mount)

### Test pattern references
- `mcp-gateway/tests/test_image_hash.py` (Phase 5) — hermetic-subprocess pattern, single fixture per test
- `mcp-gateway/tests/test_runner.py` (Phase 6) — 100 MB-of-`/dev/urandom` slow test (rerun at the run_shell layer per D-35); ReToolRunner integration patterns
- `mcp-gateway/tests/test_artifacts_io.py` (Phase 6) — `confine_to` matrix tests; new ACL tests in Phase 7 should mirror this shape
- `mcp-gateway/tests/test_subprocess_runner_shell_safety.py` (or equivalent) — `shell=True`-rejection grep; carries over to `run_shell` tests (asserts `ReToolRunner` is the only subprocess path)
- `mcp-gateway/tests/test_print_config.py` — clean-env subprocess pattern for `test_run_shell.py`'s env-scrub assertion

### Constraint references
- `CLAUDE.md` §Constraints — container runs with SYS_PTRACE + seccomp=unconfined; `--no-new-privs` in setpriv (D-01) is the mitigation for this widened cap surface inside run_shell
- `CLAUDE.md` §"Recommended Stack > Authentication & Security" — Bearer token model; D-07's token-file revocation is what makes run_shell unable to leak it
- `.planning/REQUIREMENTS.md` §"Out of Scope (v1.1)" — Mount-namespace isolation deferred (Phase 7 ships posture-only confinement; this is documented in the `run_shell` docstring per D-28)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- **`mcp-gateway/src/mcp_gateway/runner.py::run_tool`** — the
  one-shot convenience helper (Phase 6 D-02). Every typed subprocess
  wrapper calls `await run_tool(case_dir, argv, slug=..., timeout=...)`
  and decorates the return.
- **`mcp-gateway/src/mcp_gateway/artifacts_io.py::confine_to`,
  `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS`** —
  Phase 6's leaf module. Phase 7 adds `ensure_mare_shell_access`
  but does NOT modify the existing primitives.
- **`mcp-gateway/src/mcp_gateway/tools/case_dirs.py::resolve_case_dir`** —
  STATUS_ROOT-aware case-dir guard. Composed with `confine_to` per
  Phase 6 D-14.
- **`mcp-gateway/src/mcp_gateway/tools/samples.py::resolve_sample`** —
  v1.0 sha256 / case-dir sample resolver. Every typed wrapper that
  takes a `sample` argument calls this first.
- **`mcp-gateway/src/mcp_gateway/tools/artifacts.py:115-139`** — the
  inline canonicalize-and-compare-prefix pattern; `confine_to` now
  generalizes this (a separate refactor of `get_artifact` to use
  `confine_to` is permitted but not required by Phase 7 — see
  Phase 6 deferred ideas).
- **`mcp-gateway/src/mcp_gateway/tools/resources.py:106-134`** — the
  `register` pattern for MCP Resources (template + low-level
  `list_resources`). Phase 7 extends `_build_resource_list`, not the
  registration surface.
- **`mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py`** —
  read-only reference; Phase 7 only updates the comment-block top
  (D-14) and adds `collision_check.assert_no_collisions(mcp)` in
  lifespan.

### Established patterns
- All v1.0 / v1.1 subprocess work uses `asyncio.create_subprocess_exec`
  via the runner; **no `shell=True`** anywhere. Phase 7 inherits this
  via every wrapper going through `run_tool`. (The fact that
  `run_shell` invokes `bash -c` is not a violation — `bash` is the
  argv[0]; Python never shell-interpolates.)
- All v1.0 tests are pytest under `mcp-gateway/tests/`. Single
  fixture per test (Phase 5/6 discipline). Phase 7 inherits.
- Env vars influencing runtime defaults are read once at module
  import and validated at startup (`uploads._max_bytes`, Phase 6's
  four runner knobs). D-24, D-25, D-27, D-29 add four more env vars
  following the exact same pattern.
- Module-level constants are UPPER_SNAKE; functions are
  lower_snake; classes are PascalCase.
- Tool registration: each tool module exposes `register(mcp)` and is
  invoked from `tools/__init__.py::register_all_tools`.

### Integration points
- `app.py::lifespan` gains exactly ONE new line: a call to
  `collision_check.assert_no_collisions(mcp)` after
  `register_all_tools(mcp)` AND after `PinnedBackend` has populated
  its `tool_cache`. This must run **after** the backend's first
  `list_tools()` (i.e., after `refresh_backend_tools()` is called
  during backend connect), otherwise the collision check sees an
  empty backend and passes spuriously.
- `tools/__init__.py::register_all_tools` gains four lines: import
  + register call for each of `shell`, `re_static`, `re_artifacts`,
  and (no register, just import) `collision_check`.
- `tools/resources.py::_build_resource_list` gains a per-case
  inner loop walking `EXPANDED_CASE_SUBDIRS`.
- `artifacts_io.py` gains one function: `ensure_mare_shell_access`.
  Phase 8 (sessions) and Phase 9 (jobs) will also call it when they
  create case-dir-scoped artifacts.
- No change to `cases.py`, `disasm.py`, `workflows.py`,
  `backend_passthrough.py` runtime, `subprocess_runner.py`, or
  `session_state.py`.

</code_context>

<specifics>
## Specific Ideas

- User mandate at discuss-phase (consistent with Phase 6): "Choose
  the best and most robust architecture for me." All D-01..D-35
  decisions above are the most-robust default under that mandate;
  the planner/executor may adjust within the constraints listed under
  "Claude's Discretion" but not the locked decisions.
- Defense-in-depth carried forward: `setpriv` over `gosu` (D-01) for
  `--clear-groups + --no-new-privs + --inh-caps=-all`; POSIX ACLs over
  SGID + chgrp (D-03) to keep the privilege gradient narrow;
  whitelist over blacklist for env scrub (D-09) so the next leaked
  secret doesn't quietly become reachable from the shell; hard-fail
  on tool-name collision (D-11) over silent-shadow.
- Two `MARE_*` env vars (`MARE_CASE_DIR`, `MARE_SAMPLE_PATH`) make
  `run_shell` self-locating without round-tripping. Bash agents can
  do `cd $MARE_CASE_DIR/extracted` or `xxd $MARE_SAMPLE_PATH | less`
  without re-pasting the path the orchestrator already knows.
- The `_inproc_result` helper (D-19) makes `run_capstone_disasm` /
  `run_ropper` indistinguishable from subprocess wrappers at the MCP
  layer — same 12 keys, same `log_path`, same artifact-capture story.
  Agents writing generic "retry on `timed_out`" or "tail the
  log_path" logic don't need to special-case in-proc tools.
- The collision check (D-11..D-15) is small (~30 LoC) but
  high-leverage: it catches the entire class of "future backend
  ships a tool that silently shadows ours" failures at boot, not at
  first call. Operationally cheap; failure cost otherwise is a
  silent functional regression.
- The 100 MB urandom test rerun at the run_shell layer (D-35) is
  the chokepoint-integrity assertion: it proves the shell wrapper
  didn't accidentally re-introduce a PIPE deadlock by intercepting
  stdout, ANSI-stripping the wrong direction, or otherwise breaking
  Phase 6's invariants.

</specifics>

<deferred>
## Deferred Ideas

- **Mount-namespace isolation for `run_shell`** — requires
  CAP_SYS_ADMIN; explicitly deferred to v1.2 in `.planning/REQUIREMENTS.md`
  §"Out of Scope (v1.1)" and §"Future Requirements". Phase 7 ships
  posture-only confinement; `run_shell`'s docstring (D-28) documents
  this loudly.
- **Per-`Mcp-Session-Id` keying of `mare-shell`** — same blocker as
  per-session for sessions and jobs (`GW-V2-03` ticket). v1.1 keeps
  single-tenant mare-shell.
- **Sandboxed-network mode for run_shell** — `unshare --net` per
  call is Phase 11 (dynamic mode) territory; Phase 7's run_shell
  inherits the container's egress (no special netns).
- **Recursive `extracted/<sub>/<file>` resources** — Phase 7's
  resource walk stops at depth 2 (D-26). Phase 10 (extraction tier)
  decides whether to recurse deeper, since unblob/binwalk produce
  deeply-nested trees that may need their own pagination.
- **Composite shell-helper wrappers** (e.g., `run_strings_filtered`,
  `run_hex_search`) — agent prompts dressed as tools; remain in the
  orchestrator skill (Phase 12). `run_shell` covers the long tail.
- **Replacing `tools/artifacts.py::get_artifact` with `confine_to`**
  — semantically-equivalent refactor noted in Phase 6 deferred; not
  required by Phase 7. If touched, it should be a single-commit
  cleanup PR, not bundled with Phase 7's surface area.
- **`run_strings` as a typed wrapper** — explicitly excluded by
  REQUIREMENTS §"Out of Scope (v1.1)" (`collect_strings` already
  covers it; ad-hoc use goes through `run_shell`).
- **`run_capstone_disasm` / `run_ropper` as CLI subprocesses** —
  considered and rejected (D-19); revisit only if the Python
  bindings prove unreliable in CI.
- **Per-tool argv allowlist for the Kali long tail** — explicitly
  rejected by REQUIREMENTS §"Out of Scope (v1.1)": `run_shell`
  covers ad-hoc, wrappers exist where parsing pays off.
- **`run_shell` argv-pattern detection / refusal** (e.g., reject
  `rm -rf /`) — agent-trust tool; argv-parse for safety is fool's
  errand per Pitfall 2. Not added.

</deferred>

---

*Phase: 07-run-shell-typed-static-wrappers-re-artifacts*
*Context gathered: 2026-05-13*
