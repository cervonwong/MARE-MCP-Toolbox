# Phase 5: F-1 Image-Hash Fix - Research

**Researched:** 2026-05-12
**Domain:** Bash content-hashing for Docker cache invalidation + pytest regression test
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Hash Logic**
- **D-01:** The mcp-gateway content hash is already implemented inline at `run_docker.sh:212-229`. This phase verifies and hardens it — it does NOT rewrite the surrounding image-tag mechanism. The success-criteria assertion must continue using the same `DOCKERFILE_SHA` / `SHORT_SHA` / `HASH_IMAGE` variable names so downstream consumers (Docker tag, `[build] up to date` message, `tag :latest` step) are unaffected.
- **D-02:** Add `LC_ALL=C` to the `sort` invocation inside the hash subshell so file ordering is byte-deterministic across hosts (en_US.UTF-8 vs C vs zh_CN.UTF-8 currently produce different sort orders for non-ASCII names, which would flap the hash between developer machines). Single-line, low-risk.
- **D-03:** Keep the existing prune list as-is — `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.venv`, `*.egg-info`, `htmlcov`, `node_modules`, `dist`. Spec (Success Criterion 3) requires the first four; the rest are a strict superset, all benign, and prevent foreseeable flap from coverage/JS tool output. Do NOT remove items just because the spec doesn't name them.
- **D-04:** Do NOT add new ignored paths beyond the current list unless the regression test surfaces a real flap source. Premature ignore-list expansion is forbidden — only widen on demonstrated need with a test that reproduces the flap.

**Testability Refactor**
- **D-05:** Extract the hash computation into a standalone helper: `scripts/compute_image_hash.sh`. The helper:
  - Takes one positional arg: the build-root path (defaults to the repo root when run from `run_docker.sh`).
  - Reads optional env vars `INSTALL_BINARY_NINJA`, `BINARY_NINJA_ZIP`, `INSTALL_IDA_PRO`, `IDA_PRO_ZIP` (matching current run_docker.sh inputs).
  - Prints the 64-char sha256 hex hash to stdout, nothing else.
  - Exits non-zero on missing inputs with a clear stderr message.
- **D-06:** `run_docker.sh` replaces its inline hash subshell with a call to the helper. Behavior must be byte-identical to current output for any unchanged input — no semantic drift during the extraction.

**Test Design**
- **D-07:** Regression test lives at `mcp-gateway/tests/test_image_hash.py` (pytest — consistent with all 18 existing v1.0 test files in that directory).
- **D-08:** Tests operate on fixture trees built in `tmp_path` — they do NOT mutate the real `mcp-gateway/` tree. The fixture mirrors a minimal mcp-gateway layout: a `Dockerfile`, a `docker-bin/` dir with one file, a `mcp-gateway/` subdir with `src/x.py`, `pyproject.toml`, and at least one pruned path (e.g., `mcp-gateway/__pycache__/foo.pyc`, `mcp-gateway/.venv/lib/marker`).
- **D-09:** Required test cases (one assertion per Success Criterion):
  - SC-1: touch `mcp-gateway/src/x.py` → hash differs from baseline.
  - SC-2: touch `mcp-gateway/pyproject.toml` → hash differs from baseline.
  - SC-3a-d: write a new file under each pruned path (`__pycache__`, `.venv`, `*.egg-info`, `.pytest_cache`) → hash equals baseline.
  - SC-4: explicit assertion that touching `mcp-gateway/src/x.py` changes the hash returned by `scripts/compute_image_hash.sh` (this is the regression-test-of-record named in the success criteria).
- **D-10:** Tests invoke the helper via `subprocess.run` with a clean env (no Binja/IDA inputs configured for the baseline cases, since those branches require real zip files). A separate test asserts that toggling `INSTALL_BINARY_NINJA=0 → 1` with a stub zip changes the hash — this guards the existing Binja/IDA conditional from regressing.
- **D-11:** Test must be hermetic — no network, no docker, no real mcp-gateway dependency. Runs in <2s in CI.

### Claude's Discretion

User said "continue as you see fit, choose the most sound answer". Adjustments allowed within constraints:
- Exact helper script name (`compute_image_hash.sh` recommended; any descriptive name under `scripts/` acceptable).
- Internal layout of the pytest fixture (single fixture vs per-test) — required assertions are fixed, test-file structure is not.
- Whether to inline the helper as a bash function in a shared `lib/` file vs a standalone script — preserving the testable contract (callable from the test as a subprocess) is what matters.

### Deferred Ideas (OUT OF SCOPE)

- `./run_docker.sh --explain-hash` flag (developer-experience phase, not Phase 5).
- Hash-cache CI pre-flight check (future CI/release phase).
- `scripts/` directory convention doc (waits for Phases 6, 11 contributions).
- Locale-assertion fail-loud guard inside `compute_image_hash.sh` (over-engineered; revisit only if real-world miss occurs).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FOUND-01 | Agent edits to `mcp-gateway/src/` trigger a Docker image rebuild on the next `./run_docker.sh` invocation (F-1 carryover fix — content-hash includes gateway source) | Standard Stack §sha256sum/find/sort; Code Examples §Helper Script Skeleton; Validation Architecture §SC-1..SC-4 + Binja toggle |
</phase_requirements>

## Summary

Phase 5 is a small, surgical hardening of an already-correct content-hash subshell that lives at `run_docker.sh:212-229`. The phase has three deliverables: (1) add a single `LC_ALL=C` to make `sort` byte-deterministic across host locales (D-02); (2) extract the inline subshell into `scripts/compute_image_hash.sh` with byte-identical behavior so it can be tested (D-05, D-06); (3) add a hermetic pytest regression at `mcp-gateway/tests/test_image_hash.py` that asserts the four Success Criteria plus a Binja-toggle guard (D-07..D-11).

All tooling used is standard POSIX/coreutils that already runs in `run_docker.sh` today — `sha256sum`, `find -prune`, `sort`, `awk`, `printf`, `xargs`. No new dependencies in the gateway, no new Python libraries. The pytest is integrated into the existing `mcp-gateway/tests/` collection that already has 18 test files, an established `subprocess.run` pattern via `test_print_config.py`, and the conftest fixtures (`tmp_path`, `monkeypatch`) needed for hermetic execution.

**Primary recommendation:** Implement in three commits: (a) `LC_ALL=C` patch in `run_docker.sh` inline (so the inline form is byte-deterministic before extraction); (b) extract to `scripts/compute_image_hash.sh` with `set -euo pipefail` discipline and stderr error messages, replace the subshell in `run_docker.sh` with a single-line invocation; (c) add `mcp-gateway/tests/test_image_hash.py` per the contract in §Validation Architecture.

## CLAUDE.md-derived Project Constraints

CLAUDE.md enforces three properties that constrain the design:

| Constraint | Source | Implication for Phase 5 |
|------------|--------|--------------------------|
| Licensing: IDA Pro and Binary Ninja zips must never be baked into images | CLAUDE.md §Constraints | The helper script MUST preserve the existing `INSTALL_BINARY_NINJA` / `INSTALL_IDA_PRO` conditional branches verbatim — these gate whether the zip's sha256 contributes to the hash. Removing them would break licensing posture; replicating them wrongly would either always-rebuild (zip path required even when not installing) or never-rebuild (license-zip rotation goes unnoticed). |
| Backward compatibility: existing "agent inside container" mode unchanged | CLAUDE.md §Constraints | `DOCKERFILE_SHA`, `SHORT_SHA`, `HASH_IMAGE` variable names and downstream consumers (`docker image inspect`, `docker buildx build`, `docker tag :latest`) are unchanged. The helper must produce the same 64-char hex string the inline subshell does today (for unchanged inputs). |
| GSD Workflow Enforcement: file changes must come through a GSD command | CLAUDE.md §GSD Workflow | Phase 5 is the entry point — `/gsd-execute-phase 5` will spawn the implementer. Research only writes RESEARCH.md. |

CLAUDE.md tech-stack section is not material to Phase 5 (no MCP code is touched).

## Standard Stack

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| GNU coreutils (`sha256sum`, `sort`, `find`, `xargs`, `awk`, `printf`) | system | Hash computation primitives | Already used at `run_docker.sh:213-228`. No reason to change. `[VERIFIED: run_docker.sh:212-229 inline subshell uses exactly these tools]` |
| Bash | 4+ | Helper script runtime | Repo already standardizes on bash (`run_docker.sh` shebang). `set -euo pipefail` discipline already in use (line 2). `[VERIFIED: run_docker.sh:2]` |
| pytest | ≥8 | Test framework | `pyproject.toml` declares `pytest>=8` in dev deps; `testpaths = ["tests"]`; `asyncio_mode = "auto"`. `[VERIFIED: mcp-gateway/pyproject.toml]` |
| Python `subprocess.run` | stdlib (3.11+) | Invoke helper from test | Already the test-pattern of record for run_docker.sh-related tests. `[VERIFIED: mcp-gateway/tests/test_print_config.py:37-66]` |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| `pathlib.Path` | stdlib | Build fixture tree | Standard in existing tests (`test_print_config.py:5`, `test_readme_structure.py:3`) |
| `pytest.fixture` (function-scope, `tmp_path`) | pytest 8 | Per-test fixture tree | `tmp_path` is the established hermetic-dir pattern (`conftest.py:18`, `test_print_config.py:45`) |
| `pytest.MonkeyPatch` | pytest 8 | Env var injection for Binja/IDA toggle test | Already used in `conftest.py:18, 26` to set `MCP_GATEWAY_*` env vars |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Standalone `scripts/compute_image_hash.sh` | Inline bash function in a `lib/common.sh` sourced by run_docker.sh | D-05 calls out the standalone is recommended but a sourced function is acceptable. Standalone is preferred because it gives the test a clean subprocess boundary (no need to source bash from Python). Discretion allows either. |
| bats / shunit2 (bash test framework) | pytest (chosen) | D-07 locks pytest. The 18 existing tests all use pytest and there is no bash test infrastructure in the repo. Adopting bats would mean adding a CI dependency for a single test. |
| `git hash-object` over the tree | `sha256sum` over `find` output (current) | git-tree hashing would require the tree to be a clean git checkout — breaks for `./run_docker.sh` invoked over a working tree with uncommitted edits, which is the *exact* use case F-1 fixes. Current find+sha256 approach is correct. |

**Installation:** None required. All tooling already present.

**Version verification:** N/A — Phase 5 adds no new package dependencies. Pytest version is unchanged.

## Architecture Patterns

### Recommended Project Structure
```
.
├── run_docker.sh                          # MODIFIED: hash subshell replaced with helper call
├── scripts/                               # NEW directory
│   └── compute_image_hash.sh              # NEW: extracted hash helper
└── mcp-gateway/
    └── tests/
        ├── conftest.py                    # UNCHANGED
        ├── test_print_config.py           # UNCHANGED (model for subprocess pattern)
        └── test_image_hash.py             # NEW: regression test
```

### Pattern 1: `set -euo pipefail` + `trap` Discipline (existing repo convention)
**What:** Every shell script in the repo uses `set -euo pipefail`. `run_docker.sh` adds `trap cleanup_stages EXIT` for resource cleanup.
**When to use:** All new shell scripts under `scripts/`.
**Example:**
```bash
#!/usr/bin/env bash
# Source: run_docker.sh:1-2 (existing repo convention)
set -euo pipefail
```
The new helper does not require a `trap` — it has no temporary directories to clean up. But it must use `set -euo pipefail` to match house discipline. `[VERIFIED: run_docker.sh:2, only trap is at line 240 for BINJA/IDA_STAGE_DIR cleanup which lives in run_docker.sh proper, not in the hash subshell]`

### Pattern 2: subprocess-driven hermetic test (existing repo convention)
**What:** Tests that exercise `run_docker.sh` (or other repo scripts) stage a copy into `tmp_path`, invoke via `subprocess.run(["bash", str(staged), ...], capture_output=True, text=True, timeout=10, cwd=tmp_path)`, and assert on `returncode`, `stdout`, `stderr`.
**When to use:** All `test_image_hash.py` test cases.
**Example:**
```python
# Source: mcp-gateway/tests/test_print_config.py:36-43
def test_help_documents_print_config():
    res = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert res.returncode == 0, res.stderr
    assert "--print-config" in res.stdout, res.stdout
```
Adapted for `compute_image_hash.sh`:
```python
REPO_ROOT = Path(__file__).resolve().parents[2]   # exact pattern from test_print_config.py:20
HELPER = REPO_ROOT / "scripts" / "compute_image_hash.sh"

def _run_helper(build_root: Path, env: dict | None = None) -> str:
    base_env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")}
    if env:
        base_env.update(env)
    res = subprocess.run(
        ["bash", str(HELPER), str(build_root)],
        capture_output=True, text=True, timeout=10, env=base_env,
    )
    assert res.returncode == 0, f"helper failed: {res.stderr}"
    out = res.stdout.strip()
    assert len(out) == 64 and all(c in "0123456789abcdef" for c in out), f"bad sha256: {out!r}"
    return out
```

### Pattern 3: Find + Prune + Sort + sha256sum
**What:** The canonical "checksum a tree, ignoring cache dirs" idiom.
**When to use:** The helper's core loop. Verbatim from current `run_docker.sh:216-220`.
**Example:**
```bash
# Source: run_docker.sh:212-229 (existing inline subshell)
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
```

**Critical detail (D-02):** `LC_ALL=C sort` MUST be applied to BOTH `sort` invocations (the `docker-bin` find and the `mcp-gateway` find). The current code at `run_docker.sh:215, 220` has `| sort |` without `LC_ALL=C` — both lines need patching. `[VERIFIED: run_docker.sh:215 and 220 grep — neither has LC_ALL=C currently]`

**Placement of `LC_ALL=C`:** The recommended idiom is to prefix the `sort` command directly (`LC_ALL=C sort`) rather than exporting at the top of the helper. Rationale: exporting `LC_ALL=C` at script top would also affect `sha256sum` and `find`, which is harmless but overreach; prefixing `sort` scopes the discipline to the operation that actually needs it and makes intent obvious to future readers. Either form produces the same hash. `[ASSUMED: ergonomic preference; both placements are byte-equivalent for the hash output]`

### Pattern 4: Conditional Binja/IDA Hashing (D-10 specific question)
The current code does TWO things for each disassembler:
1. ALWAYS emit a literal line `INSTALL_BINARY_NINJA=$INSTALL_BINARY_NINJA` (or `=0` when unset/empty) into the hash stream. This means toggling the env var alone changes the hash, even with no zip file present.
2. ONLY IF the toggle is `"1"`, append `sha256sum "$BINARY_NINJA_ZIP"`. This means rotating the zip file *only* affects the hash when the install is enabled.

**Therefore (answering the explicit research question):** the conditional branches are **sha256-of-zip** content, NOT path-existence. The zip is only hashed when the toggle is on. If the toggle is on but the zip is missing, `sha256sum` will fail with non-zero exit and crash the subshell (which under `set -euo pipefail` will propagate). The helper must replicate this exact two-step pattern verbatim. `[VERIFIED: run_docker.sh:221-228]`

**Empty env var handling:** Bash with `set -u` will fail on `$INSTALL_BINARY_NINJA` if unset. The current inline subshell runs inside the script's scope where these vars are guaranteed initialized (lines 189, 202 reference them). The standalone helper must handle the case where the vars are unset — use `${INSTALL_BINARY_NINJA:-0}` and `${INSTALL_IDA_PRO:-0}` (and similarly `${BINARY_NINJA_ZIP:-}` / `${IDA_PRO_ZIP:-}` for the path slots) so the helper is callable from a clean test env. `[VERIFIED: run_docker.sh sets these vars upstream of line 212 via the upstream flag-parsing block]`

### Anti-Patterns to Avoid
- **Sourcing `run_docker.sh` from the test:** Don't. The script has side effects (creates dirs, may invoke docker). The whole point of D-05 is a clean subprocess boundary.
- **`xargs` without `-0` or `-n`:** Filenames with spaces or newlines would break the pipeline. The current code accepts this risk because `mcp-gateway/` should never contain such files. Don't add `-0` defensiveness — it would change the byte-output of the inner `sha256sum` invocation and thus the hash, breaking D-06's "byte-identical" requirement.
- **Removing items from the prune list:** D-04 forbids. The list at `run_docker.sh:217-219` is locked in.
- **Computing the hash inside Python (e.g., hashlib):** Would diverge from `run_docker.sh`'s actual hash, defeating the regression test's purpose. Tests MUST invoke the shell helper.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tree-hashing | Custom Python tree walker | `find ... -prune -o -type f -print \| LC_ALL=C sort \| xargs sha256sum` | Current pattern; locale fix is D-02 |
| Test-fixture build | Hand-rolled tar/zip fixture | `tmp_path` + `Path.write_text` / `Path.write_bytes` (per-file) | Standard pytest pattern, sub-millisecond setup |
| Diffing two hashes | Custom assertion helpers | Python `==` / `!=` on the 64-char hex string | Hashes are strings; equality is the contract |
| sha256 wrapper script | Custom Python `hashlib` calls | Direct subprocess to `compute_image_hash.sh` | The test's *purpose* is to validate the shell helper, not duplicate it |

**Key insight:** The phase is deliberately tiny. Adding any Python-side hashing logic would create a parallel implementation that drifts from the actual `run_docker.sh` behavior — the exact kind of bug F-1 caused in v1.0 UAT.

## Runtime State Inventory

This is a refactor/extract phase. Inventory:

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — phase has no data layer. | None. |
| Live service config | None — phase does not touch the gateway, container, or any running service. The hash is computed at build time, not runtime. | None. |
| OS-registered state | None — no systemd units, cron jobs, launchd entries, or scheduled tasks reference `DOCKERFILE_SHA` or the inline hash. The only OS-level consumer is `docker image inspect`/`docker buildx build`, which already reads `HASH_IMAGE` from script scope and is unaffected. | None. |
| Secrets/env vars | `INSTALL_BINARY_NINJA`, `BINARY_NINJA_ZIP`, `INSTALL_IDA_PRO`, `IDA_PRO_ZIP` are read by the hash subshell. After extraction, the helper must read these from its own env. `run_docker.sh` must `export` them before invoking the helper (or pass them as env via `env VAR=val bash scripts/compute_image_hash.sh ...`). No new secrets introduced. | Verify the helper-call site in `run_docker.sh` exports these four vars to the subprocess environment. |
| Build artifacts | The current Docker image tag `kali-re-tools:<short-sha>` for an existing checkout will NOT change as a result of fixing the locale bug *unless* the developer is on a non-C locale with non-ASCII filenames in the tree — which is unlikely today. However, the very first `./run_docker.sh` after the fix will likely produce a *different* `SHORT_SHA` than the previous run (because the inline subshell is being replaced with a helper invocation — even with byte-identical output, sourcing of env vars could differ). Acceptable: forces one rebuild after the fix, which is the desired behavior (post-fix the cache is correct). No old image cleanup needed; old tags age out naturally. | None — accept one-time rebuild on first post-fix invocation. |

**The canonical question (answered):** After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered? — Only Docker's image cache may hold an image tagged with the pre-fix `DOCKERFILE_SHA`. That cache is correct (the image was built from the pre-fix source); the post-fix run will produce a new tag and rebuild once. This is *exactly the rebuild trigger F-1 set out to enable*.

## Common Pitfalls

### Pitfall 1: Locale-Sensitive `sort` (D-02 — the bug this phase fixes)
**What goes wrong:** `sort` without `LC_ALL=C` uses the system locale's collation. `en_US.UTF-8` and `zh_CN.UTF-8` order non-ASCII filenames differently from `C` locale, so the same tree yields a different hash on different developer machines, flapping cache.
**Why it happens:** GNU `sort` defaults to locale-aware collation since coreutils 6.9+ (2007).
**How to avoid:** Prefix `LC_ALL=C` on every `sort` invocation in the helper.
**Warning signs:** Hash differs between CI and dev for the same git SHA; `[build] up to date` appears on one machine while `[build] building ...` appears on another for the same checkout. `[CITED: https://www.gnu.org/software/coreutils/manual/html_node/sort-invocation.html — sort respects LC_COLLATE]`

### Pitfall 2: `xargs sha256sum` Empty-Input Behavior
**What goes wrong:** If `find ... | sort` produces zero lines (empty directory), `xargs sha256sum` will invoke `sha256sum` with no args, which by default reads from stdin and waits forever. In CI this looks like a hang.
**Why it happens:** Default `xargs` behavior runs the command once even with empty input.
**How to avoid:** Use `xargs --no-run-if-empty` (GNU extension) OR ensure the target directories always contain at least one file. The current `mcp-gateway/` and `docker-bin/` both always contain files in a real checkout, so this is not a practical risk in `run_docker.sh` proper. **For the test fixture tree, the helper must handle the case where a subdir is empty** — recommend `xargs -r` (or `--no-run-if-empty`) for robustness in the test environment. `[ASSUMED: based on standard xargs documentation — needs verification in the actual test fixture, where SC-3 prune-only writes might leave docker-bin empty]`

**Practical mitigation:** Fixture tree must always include at least one file in `docker-bin/` and one non-pruned file in `mcp-gateway/` so the production code path (no `-r` flag) works unchanged. D-08 explicitly requires this: "a `docker-bin/` dir with one file" and "`src/x.py`" both populated. Honor that.

### Pitfall 3: Environment Bleed Between Tests
**What goes wrong:** A previous test sets `INSTALL_BINARY_NINJA=1` via `monkeypatch.setenv`, the next test inherits it, baseline assertion fails because Binja branch is now active.
**Why it happens:** `monkeypatch` auto-undoes per-test, but if the test invokes `subprocess.run` and passes `env=os.environ`, modifications leak. Worse: the developer's own shell may have `INSTALL_*` set, polluting `os.environ` at test discovery time.
**How to avoid:** All test subprocess invocations pass an explicit `env=` dict with only `PATH` and `HOME`. Never pass `env=os.environ`. The helper test's `_run_helper(env=...)` should *replace* env, not extend it.
**Warning signs:** Test passes on dev machine, fails in CI (or vice versa); SC-1 fails intermittently with hash drift on rerun.

### Pitfall 4: `sha256sum` Output Includes the Filename
**What goes wrong:** `sha256sum /path/Dockerfile` outputs `<hex>  /path/Dockerfile\n`. If the test fixture's path varies between runs (e.g., `pytest-of-cervon-0/test_foo0/...`), the inner hash stream includes those paths, so the *outer* sha256 differs even for byte-identical file content.
**Why it happens:** The current inline subshell already has this property — that's by design (the path inside `mcp-gateway/` is part of the hash input). But it means **the test must invoke the helper twice against the same fixture path, mutate the file, then invoke again** — NOT build two fixtures in different `tmp_path`s and compare.
**How to avoid:** Test pattern: build fixture once → compute baseline hash → mutate → recompute → compare. Use a single per-test fixture (function-scope `tmp_path`).
**Warning signs:** Two consecutive runs of the test fail because the `tmp_path` is different each time and you're comparing across runs.

### Pitfall 5: `cwd` vs Build-Root Confusion
**What goes wrong:** The helper takes the build-root path as positional arg (D-05). If `run_docker.sh` invokes it without an arg, the helper must default to its own `SCRIPT_DIR/..` (or to `$PWD`, depending on choice). Wrong default → helper hashes the wrong tree → cache miss every time.
**How to avoid:** Helper's default should be the repo root computed from its own location: `BUILD_ROOT="${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)}"`. This mirrors `run_docker.sh:5`'s `SCRIPT_DIR` pattern.
**Warning signs:** Helper exits 0 but `DOCKERFILE_SHA` doesn't match the inline result; new image tag every run.

### Pitfall 6: `set -e` + `xargs` Exit Code Masking
**What goes wrong:** Under `set -euo pipefail`, a failure in `find` (e.g., permission denied on a subdir) or `sha256sum` (missing file) will tear down the pipeline. But `xargs`'s exit code is the last one — partial failures can be silently lost without `pipefail`. The current script has `pipefail`, so this is handled. The helper must keep it.
**How to avoid:** Helper's first lines must be `set -euo pipefail`. Verified that the current script does the same (line 2).
**Warning signs:** Helper exits 0 but stdout is empty or truncated.

## Code Examples

### Helper Script Skeleton (canonical pattern, D-05 + D-06)
```bash
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
```

**Discipline checklist (matches `run_docker.sh:2` conventions):**
- `set -euo pipefail` — yes, line 3.
- No `trap` needed — helper allocates no resources.
- All env vars defaulted (`:-`) so `set -u` doesn't crash in test invocations.
- Errors go to stderr; only the 64-char hex goes to stdout (D-05 contract).
- Non-zero exit codes are categorized: 2 for missing build root / Dockerfile, 3 for missing zip when install toggle is on.

### `run_docker.sh` Call-Site Patch (D-06)
Replace `run_docker.sh:212-229` with:
```bash
DOCKERFILE_SHA="$(
  INSTALL_BINARY_NINJA="$INSTALL_BINARY_NINJA" \
  BINARY_NINJA_ZIP="$BINARY_NINJA_ZIP" \
  INSTALL_IDA_PRO="$INSTALL_IDA_PRO" \
  IDA_PRO_ZIP="$IDA_PRO_ZIP" \
  bash "$SCRIPT_DIR/scripts/compute_image_hash.sh" "$SCRIPT_DIR"
)"
SHORT_SHA="${DOCKERFILE_SHA:0:12}"
HASH_IMAGE="${IMAGE_REPO}:${SHORT_SHA}"
```
Note the env-var prefix syntax — variables are explicitly forwarded rather than `export`ed globally, scoping side effects. `SCRIPT_DIR` is already in scope (line 5).

### Test File Skeleton (pattern from `test_print_config.py`)
```python
# mcp-gateway/tests/test_image_hash.py
"""FOUND-01 / Phase 5: regression test for the mcp-gateway content hash.

Invariants:
  SC-1: editing any file under mcp-gateway/src/ changes the hash.
  SC-2: editing mcp-gateway/pyproject.toml changes the hash.
  SC-3: writes into pruned paths (__pycache__, .venv, *.egg-info, .pytest_cache)
        do NOT change the hash.
  SC-4: the regression-test-of-record — same as SC-1, named explicitly.
  Bonus: toggling INSTALL_BINARY_NINJA=0->1 (with a stub zip) changes the hash.
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "compute_image_hash.sh"


@pytest.fixture
def build_root(tmp_path: Path) -> Path:
    """Minimal mcp-gateway build-root mirror (D-08)."""
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    (tmp_path / "docker-bin").mkdir()
    (tmp_path / "docker-bin" / "tool.sh").write_text("#!/bin/bash\necho hi\n")
    gw = tmp_path / "mcp-gateway"
    (gw / "src").mkdir(parents=True)
    (gw / "src" / "x.py").write_text("x = 1\n")
    (gw / "pyproject.toml").write_text("[project]\nname='mcp-gateway'\n")
    # Pruned paths — must not contribute to hash.
    (gw / "__pycache__").mkdir()
    (gw / "__pycache__" / "stale.pyc").write_bytes(b"\x00\x01")
    (gw / ".venv" / "lib").mkdir(parents=True)
    (gw / ".venv" / "lib" / "marker").write_text("venv\n")
    (gw / "mcp_gateway.egg-info").mkdir()
    (gw / "mcp_gateway.egg-info" / "PKG-INFO").write_text("metadata\n")
    (gw / ".pytest_cache").mkdir()
    (gw / ".pytest_cache" / "CACHEDIR.TAG").write_text("Signature\n")
    return tmp_path


def _hash(build_root: Path, env_extra: dict | None = None) -> str:
    base_env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    if env_extra:
        base_env.update(env_extra)
    res = subprocess.run(
        ["bash", str(HELPER), str(build_root)],
        capture_output=True, text=True, timeout=10, env=base_env,
    )
    assert res.returncode == 0, f"helper failed: stderr={res.stderr!r}"
    out = res.stdout.strip()
    assert len(out) == 64, f"expected 64-char hex, got {out!r}"
    return out


def test_helper_exists_and_executable():
    assert HELPER.is_file(), f"missing helper at {HELPER}"
    assert os.access(HELPER, os.X_OK), f"helper not executable: {HELPER}"


def test_baseline_hash_stable(build_root):
    """Same fixture invoked twice produces the same hash."""
    assert _hash(build_root) == _hash(build_root)


def test_sc1_src_edit_changes_hash(build_root):
    """SC-1 + SC-4: editing mcp-gateway/src/x.py changes the hash."""
    baseline = _hash(build_root)
    (build_root / "mcp-gateway" / "src" / "x.py").write_text("x = 2  # changed\n")
    assert _hash(build_root) != baseline


def test_sc2_pyproject_edit_changes_hash(build_root):
    """SC-2: editing mcp-gateway/pyproject.toml changes the hash."""
    baseline = _hash(build_root)
    (build_root / "mcp-gateway" / "pyproject.toml").write_text(
        "[project]\nname='mcp-gateway-edited'\n"
    )
    assert _hash(build_root) != baseline


@pytest.mark.parametrize("pruned_subdir,filename", [
    ("__pycache__", "new.pyc"),
    (".venv", "new-file"),
    ("mcp_gateway.egg-info", "new-meta"),
    (".pytest_cache", "new-cache"),
])
def test_sc3_pruned_writes_do_not_change_hash(build_root, pruned_subdir, filename):
    """SC-3a-d: writes under pruned paths do not flap the hash."""
    baseline = _hash(build_root)
    target = build_root / "mcp-gateway" / pruned_subdir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"new content")
    assert _hash(build_root) == baseline


def test_binja_toggle_changes_hash(build_root, tmp_path):
    """D-10 bonus: toggling INSTALL_BINARY_NINJA with a stub zip changes the hash."""
    stub_zip = tmp_path / "binja.zip"
    stub_zip.write_bytes(b"PK\x03\x04stub")
    baseline = _hash(build_root)
    toggled = _hash(build_root, env_extra={
        "INSTALL_BINARY_NINJA": "1",
        "BINARY_NINJA_ZIP": str(stub_zip),
    })
    assert toggled != baseline


def test_helper_clean_env_no_binja_inputs(build_root):
    """D-10: clean-env invocation succeeds with no Binja/IDA env vars set."""
    # Just asserts _hash() works with the default base env (no INSTALL_* vars).
    out = _hash(build_root)
    assert len(out) == 64


def test_missing_dockerfile_exits_nonzero(tmp_path):
    """D-05 contract: clear stderr message on missing inputs."""
    (tmp_path / "docker-bin").mkdir()
    (tmp_path / "mcp-gateway").mkdir()
    res = subprocess.run(
        ["bash", str(HELPER), str(tmp_path)],
        capture_output=True, text=True, timeout=10,
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")},
    )
    assert res.returncode != 0
    assert "Dockerfile" in res.stderr
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline subshell at `run_docker.sh:212-229` (untestable) | Extract to `scripts/compute_image_hash.sh`, test via subprocess | This phase (2026-05-12) | Regression guard against future hash drift |
| `sort` without `LC_ALL=C` (locale-flapping) | `LC_ALL=C sort` (deterministic across locales) | This phase (2026-05-12) | Cross-machine hash stability |
| `mcp-gateway/` excluded from hash entirely | `mcp-gateway/` included with pruned cache dirs | v1.0→v1.1 transition (pre-instrumented by user; F-1 comment at line 209-211) | Gateway edits actually trigger rebuilds (the original F-1 bug fix) |

**Deprecated/outdated:** None — this is purely additive hardening.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `xargs -r` / `--no-run-if-empty` would be needed only if a fixture leaves `docker-bin/` or non-pruned `mcp-gateway/` empty. D-08 mandates at least one file in each, so plain `xargs` is fine. | Common Pitfalls §Pitfall 2 | If the planner writes a fixture missing one of these, `xargs sha256sum` hangs on empty stdin. Mitigate: write fixture per D-08 verbatim. |
| A2 | Prefix `LC_ALL=C sort` is byte-equivalent to `export LC_ALL=C` at script top, for the helper's output. | Code Examples §Pattern 3 | If wrong, the hash would differ between two equally-correct implementations. Verify by writing the helper, computing hash with both forms over the same tree, asserting equality. |
| A3 | The phase will produce one rebuild on first post-fix run because the inline-subshell → helper-call refactor will yield the same output bytes only if the implementation is exact. A single rebuild after the patch is acceptable. | Runtime State Inventory | If unacceptable, the planner could add a "byte-equivalence" verification step that diffs the old and new hash outputs *before* shipping. |
| A4 | Helper script default `BUILD_ROOT` should be `$(dirname $0)/..` because `scripts/` lives at repo root and `run_docker.sh` always invokes with explicit `$SCRIPT_DIR`. Default is only used when the test invokes the helper without an arg. | Common Pitfalls §Pitfall 5 | If wrong, the helper defaults to `$PWD` and hashes whatever the caller's cwd is. Risk is bounded — `run_docker.sh` passes the arg explicitly. |

## Open Questions

1. **Should the helper be executable (`chmod +x`) or always invoked via `bash <path>`?**
   - What we know: `run_docker.sh` is `chmod +x` (mode 0755 verified by `test_print_config.py:31` which re-applies it). Helper scripts in `docker-bin/configure-agent-mcp.sh` are also `0755`.
   - What's unclear: Discretion.
   - Recommendation: Make `scripts/compute_image_hash.sh` executable (`chmod +x`) for symmetry with the rest of the repo. `run_docker.sh` should still invoke it via `bash "$SCRIPT_DIR/scripts/compute_image_hash.sh"` rather than relying on the +x bit — this is more portable and matches how the test invokes it.

2. **Should the test be marked as part of the existing pytest collection or as a separate marker?**
   - What we know: `pyproject.toml` has `testpaths = ["tests"]` and `addopts = "-ra"`, no markers configured.
   - What's unclear: Whether to add a `@pytest.mark.slow` or similar — the spec D-11 says <2s, so no.
   - Recommendation: No special marker. Test lives at `mcp-gateway/tests/test_image_hash.py` and is collected by default.

3. **Does `Dockerfile` ever differ between dev machines (line endings on Windows checkouts)?**
   - What we know: This is a Linux-targeting repo (Kali container). Windows hosts via Docker Desktop / WSL would normalize line endings. Not a Phase 5 concern.
   - Recommendation: Out of scope. Document in a future "dev environment" doc only if a real flap is reported.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `bash` | Helper script + test subprocess invocation | ✓ | system default | — |
| `sha256sum` | Hash computation | ✓ | GNU coreutils | — |
| `find` | Tree walk | ✓ | GNU findutils | — |
| `sort` | Determinism | ✓ | GNU coreutils | — |
| `awk` | Extract first field | ✓ | GNU awk / mawk | — |
| `xargs` | Batch sha256sum | ✓ | GNU findutils | — |
| pytest ≥8 | Test framework | ✓ | declared in pyproject.toml dev extras | — |
| Python 3.11+ | Test runtime | ✓ | already required by `mcp-gateway` | — |
| Docker / docker buildx | NOT NEEDED — test must be hermetic per D-11 | n/a | n/a | n/a |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

All tools required are already exercised by the current inline subshell at `run_docker.sh:212-229` and by the existing pytest collection at `mcp-gateway/tests/`. Phase 5 introduces zero new environment requirements.

## Validation Architecture

Validation per Nyquist Dimension 8 (observability/verification proving the hash invariant).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest ≥8 with `asyncio_mode = "auto"` (asyncio not used here) |
| Config file | `mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest mcp-gateway/tests/test_image_hash.py -x` |
| Full suite command | `pytest mcp-gateway/tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| FOUND-01 / SC-1 | Edit to `mcp-gateway/src/x.py` changes the hash | unit (subprocess) | `pytest mcp-gateway/tests/test_image_hash.py::test_sc1_src_edit_changes_hash -x` | ❌ Wave 0 |
| FOUND-01 / SC-2 | Edit to `mcp-gateway/pyproject.toml` changes the hash | unit (subprocess) | `pytest mcp-gateway/tests/test_image_hash.py::test_sc2_pyproject_edit_changes_hash -x` | ❌ Wave 0 |
| FOUND-01 / SC-3a | Write to `__pycache__/` does NOT change hash | unit (subprocess, parametrize) | `pytest 'mcp-gateway/tests/test_image_hash.py::test_sc3_pruned_writes_do_not_change_hash[__pycache__-new.pyc]' -x` | ❌ Wave 0 |
| FOUND-01 / SC-3b | Write to `.venv/` does NOT change hash | unit (subprocess, parametrize) | `pytest 'mcp-gateway/tests/test_image_hash.py::test_sc3_pruned_writes_do_not_change_hash[.venv-new-file]' -x` | ❌ Wave 0 |
| FOUND-01 / SC-3c | Write to `*.egg-info/` does NOT change hash | unit (subprocess, parametrize) | `pytest 'mcp-gateway/tests/test_image_hash.py::test_sc3_pruned_writes_do_not_change_hash[mcp_gateway.egg-info-new-meta]' -x` | ❌ Wave 0 |
| FOUND-01 / SC-3d | Write to `.pytest_cache/` does NOT change hash | unit (subprocess, parametrize) | `pytest 'mcp-gateway/tests/test_image_hash.py::test_sc3_pruned_writes_do_not_change_hash[.pytest_cache-new-cache]' -x` | ❌ Wave 0 |
| FOUND-01 / SC-4 | Touch `mcp-gateway/src/x.py` → hash from `scripts/compute_image_hash.sh` differs from baseline (regression-of-record) | unit (subprocess) | `pytest mcp-gateway/tests/test_image_hash.py::test_sc1_src_edit_changes_hash -x` (same test as SC-1 by D-09) | ❌ Wave 0 |
| FOUND-01 / bonus | Toggling `INSTALL_BINARY_NINJA=0→1` with stub zip changes hash (D-10) | unit (subprocess, env injection) | `pytest mcp-gateway/tests/test_image_hash.py::test_binja_toggle_changes_hash -x` | ❌ Wave 0 |
| FOUND-01 / stability | Same fixture twice → same hash (sanity baseline) | unit | `pytest mcp-gateway/tests/test_image_hash.py::test_baseline_hash_stable -x` | ❌ Wave 0 |
| FOUND-01 / contract | Helper exits non-zero on missing Dockerfile (D-05 stderr contract) | unit | `pytest mcp-gateway/tests/test_image_hash.py::test_missing_dockerfile_exits_nonzero -x` | ❌ Wave 0 |
| FOUND-01 / hygiene | Helper file exists and is executable | structural | `pytest mcp-gateway/tests/test_image_hash.py::test_helper_exists_and_executable -x` | ❌ Wave 0 |

### Test Cases — Detailed Assertion Contracts

| Test | Setup | Action | Assertion |
|------|-------|--------|-----------|
| `test_helper_exists_and_executable` | (none) | (none) | `HELPER.is_file()` AND `os.access(HELPER, os.X_OK)` |
| `test_baseline_hash_stable` | Fixture per `build_root` | Compute hash twice | `_hash(build_root) == _hash(build_root)` |
| `test_sc1_src_edit_changes_hash` | Fixture | Overwrite `mcp-gateway/src/x.py` | Second hash != baseline |
| `test_sc2_pyproject_edit_changes_hash` | Fixture | Overwrite `mcp-gateway/pyproject.toml` | Second hash != baseline |
| `test_sc3_pruned_writes_do_not_change_hash[__pycache__-new.pyc]` | Fixture | Write `mcp-gateway/__pycache__/new.pyc` | Second hash == baseline |
| `test_sc3_pruned_writes_do_not_change_hash[.venv-new-file]` | Fixture | Write `mcp-gateway/.venv/new-file` | Second hash == baseline |
| `test_sc3_pruned_writes_do_not_change_hash[mcp_gateway.egg-info-new-meta]` | Fixture | Write `mcp-gateway/mcp_gateway.egg-info/new-meta` | Second hash == baseline |
| `test_sc3_pruned_writes_do_not_change_hash[.pytest_cache-new-cache]` | Fixture | Write `mcp-gateway/.pytest_cache/new-cache` | Second hash == baseline |
| `test_binja_toggle_changes_hash` | Fixture + stub `binja.zip` | Invoke helper with `INSTALL_BINARY_NINJA=1 BINARY_NINJA_ZIP=<stub>` | Toggled hash != baseline |
| `test_helper_clean_env_no_binja_inputs` | Fixture | Invoke helper with no `INSTALL_*` env vars | Returns valid 64-char hex |
| `test_missing_dockerfile_exits_nonzero` | Empty tmp_path with `docker-bin/`+`mcp-gateway/` dirs but no Dockerfile | Invoke helper | `returncode != 0`; "Dockerfile" appears in stderr |

### Fixture Contents — Exact Specification (per D-08)

The `build_root` pytest fixture creates this tree under `tmp_path`:

```
tmp_path/
├── Dockerfile                                  ("FROM scratch\n")
├── docker-bin/
│   └── tool.sh                                 ("#!/bin/bash\necho hi\n")
└── mcp-gateway/
    ├── pyproject.toml                          ("[project]\nname='mcp-gateway'\n")
    ├── src/
    │   └── x.py                                ("x = 1\n")
    ├── __pycache__/
    │   └── stale.pyc                           (b"\x00\x01")
    ├── .venv/
    │   └── lib/
    │       └── marker                          ("venv\n")
    ├── mcp_gateway.egg-info/
    │   └── PKG-INFO                            ("metadata\n")
    └── .pytest_cache/
        └── CACHEDIR.TAG                        ("Signature\n")
```

Properties this fixture guarantees:
- At least one file in `docker-bin/` (prevents `xargs sha256sum` empty-stdin issue, A1).
- At least one file in `mcp-gateway/` outside any pruned dir (`src/x.py` and `pyproject.toml`).
- At least one file in EACH of the four spec-named pruned dirs (`__pycache__`, `.venv`, `*.egg-info`, `.pytest_cache`) — so SC-3 can later add *another* file to each and assert no change.
- No symlinks, no FIFOs, no non-ASCII filenames (keeps test deterministic across CI hosts regardless of A2).

### Sampling Rate
- **Per task commit:** `pytest mcp-gateway/tests/test_image_hash.py -x` (≈11 tests, <2s per D-11)
- **Per wave merge:** `pytest mcp-gateway/tests/ -x` (full mcp-gateway suite; ~19 files)
- **Phase gate:** Full suite green before `/gsd-verify-work`; PLUS manual smoke: `./run_docker.sh --help` exits 0 (asserts the refactor didn't break flag parsing).

### Wave 0 Gaps
- [ ] `mcp-gateway/tests/test_image_hash.py` — new file covering all 11 test cases above (FOUND-01)
- [ ] `scripts/compute_image_hash.sh` — new helper (extracted from `run_docker.sh:212-229`, with `LC_ALL=C` added per D-02)
- [ ] `scripts/` directory — does not yet exist (`ls /scripts/` → not found); must be created
- [ ] `run_docker.sh:212-232` — replace inline subshell with call to new helper, preserving `DOCKERFILE_SHA`/`SHORT_SHA`/`HASH_IMAGE` variable scope and names

No framework install needed — pytest ≥8 is already in `mcp-gateway/pyproject.toml` `[project.optional-dependencies] dev`.

## Sources

### Primary (HIGH confidence)
- `run_docker.sh:1-280` — current image-build script including the inline hash subshell (lines 212-229), `set -euo pipefail` (line 2), trap cleanup (line 240). Verified via Read.
- `mcp-gateway/tests/conftest.py:1-50` — existing pytest fixtures (`bearer_token`, `tmp_upload_dir`, `tmp_status_dir`, `fake_backend_mcp`). Verified via Read.
- `mcp-gateway/tests/test_print_config.py:1-74` — the subprocess test pattern of record. Verified via Read.
- `mcp-gateway/tests/test_readme_structure.py:1-75` — structural test pattern. Verified via Read.
- `mcp-gateway/pyproject.toml` — pytest 8 declared, asyncio_mode = "auto", testpaths = ["tests"]. Verified via Read.
- `.planning/phases/05-f-1-image-hash-fix/05-CONTEXT.md` — all D-01..D-11 decisions. Verified via Read.
- `.planning/REQUIREMENTS.md` — FOUND-01 wording. Verified via Read.
- `.planning/ROADMAP.md` Phase 5 — four Success Criteria. Verified via Read.
- `.planning/MILESTONES.md` §F-1 — origin bug context (2026-05-11 UAT failure). Verified via grep.
- `CLAUDE.md` §Constraints — licensing rule preserved by Binja/IDA conditional pattern. Verified via system context.

### Secondary (MEDIUM confidence)
- GNU coreutils `sort` documentation — confirms locale-aware default. [CITED: https://www.gnu.org/software/coreutils/manual/html_node/sort-invocation.html]
- pytest `tmp_path` documentation — function-scope per-test temp directory pattern.

### Tertiary (LOW confidence)
- A1 `xargs --no-run-if-empty` behavior assumption — not exercised in this phase but flagged for the planner.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all tools verified in-tree; nothing new.
- Architecture: HIGH — fixture, subprocess, and assertion patterns directly mirror an existing repo test (`test_print_config.py`).
- Pitfalls: HIGH — locale (Pitfall 1) is the documented root cause per D-02; the other five pitfalls are derived from inspecting the exact code being refactored.
- Validation: HIGH — every test case is one-to-one with a Success Criterion or a D-09/D-10 obligation; fixture contents are byte-spec'd.

**Research date:** 2026-05-12
**Valid until:** 2026-06-11 (30 days — phase scope is hyper-local; no upstream library changes can invalidate)
