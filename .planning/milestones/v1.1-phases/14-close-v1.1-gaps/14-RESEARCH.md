# Phase 14: Close v1.1 Milestone Gaps - Research

**Researched:** 2026-05-21
**Domain:** Milestone closure / test-isolation fixes / planning-state sync / container UAT
**Confidence:** HIGH (all findings cross-verified against the working tree)

## Summary

Phase 14 is a closure phase, not a feature phase. The work splits cleanly into three workstreams: (1) **two narrow Python test-isolation bugs** (~10–20 LoC of source changes) caused by `importlib.reload` invalidating value-bound class references, (2) **planning-state checkbox/text flips** — most of which are already structurally in place; the work is mostly toggling `[ ]` to `[x]` and editing one progress table + a few prose blocks, and (3) **15 outstanding live-container UAT recordings** that need a rebuilt image and transcript capture. The success oracle is `/gsd-audit-milestone v1.1` returning `status: passed`.

**Critical scope discovery:** `REQUIREMENTS.md` already contains the 9 Phase 13 requirement BODIES (lines 94-102), the 9 traceability ROWS (lines 199-207), AND the `61/61` coverage header (line 209). The audit report under-stated this — what remains is `[ ]` → `[x]` checkbox flips on 5 stale Phase 7 items (line 22, 39-42) + 9 HARDEN/SESS-CAP/JOBS-CAP items (line 94-102) and `Pending` → `[x]` on 14 traceability rows. **D-05 is a checkbox flip, not a body insertion.**

**Primary recommendation:** Order workstreams as: **(A) fix `r2_sessions.py` + `sessions/__init__.py` first** so the test suite goes green → **(B) flip planning-state checkboxes and ROADMAP table in parallel** (no source dependencies) → **(C) rebuild container with the test-fixes baked in and execute the 15 UAT items**. The test fixes MUST land before the container UAT image build so the rebuilt image carries the fix; otherwise UAT-recorded behaviour is from a stale image.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Test-Order Failures (Phase 13 regression):**
- **D-01.** `src/mcp_gateway/tools/r2_sessions.py` MUST catch `SessionCapReached` by **module attribute** (`sessions.SessionCapReached` — or equivalent `mcp_gateway.sessions._base.SessionCapReached` resolved at raise time), NOT a stale imported class. The current `from X import SessionCapReached` binding survives module load but escapes the `except` block after `mcp_gateway.sessions._base` is reloaded, because the raised exception class becomes a new object. The fix MUST survive `importlib.reload` of `mcp_gateway.sessions._base`.
  - **Reproducer that MUST go green after fix:**
    ```
    cd mcp-gateway && uv run pytest \
      tests/test_gdb_session.py::test_gdb_env_validates_bad_values \
      tests/test_r2_sessions.py::test_unsafe_shares_combined_cap -q
    ```
- **D-02.** `src/mcp_gateway/sessions/__init__.py` MUST expose `r2` and `gdb` as **package attributes** that survive the gdb-env reload cleanup path. The 6 `tests/test_sessions_concurrency.py` failures are caused by `monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", ...)` failing after the package was popped/re-imported. Acceptable alternative: change the affected tests to import the submodule directly (`from mcp_gateway.sessions import r2 as r2_mod`) AND document the justification in a code comment. **Preferred:** fix the package so existing tests continue to work — fewer test rewrites, future-proof.
- **D-03.** Final acceptance gate: `cd mcp-gateway && uv run pytest -m 'not slow'` MUST exit 0 with `0 failed` in a single non-isolated invocation.

**Host ACL Test Contract:**
- **D-04.** `tests/test_acl_available.py::test_setfacl_on_path` MUST have an explicit host/container contract. **Picked: Option A** — mark the test container-only via `@pytest.mark.skipif(shutil.which("setfacl") is None, reason="setfacl host-binary missing; container-only contract")`. Add a one-line module docstring explaining the contract.

**REQUIREMENTS.md Sync:**
- **D-05.** Add Phase 13 requirement **bodies** to `.planning/REQUIREMENTS.md` (HARDEN-01..07, SESS-CAP-01, JOBS-CAP-01). Each gets a checked `[x]` checkbox since `13-VERIFICATION.md` already marks them satisfied at the automated/code level (live HARDEN-03 sandbox check is closed in D-13 below).
- **D-06.** Add 9 corresponding **traceability rows** to the REQUIREMENTS.md traceability table — one per Phase 13 requirement, pointing at the relevant phase plan(s) and `13-VERIFICATION.md`. Mark `Verified` as `[x]` for all 9 after the live HARDEN-03 sandbox check (D-13) is recorded.
- **D-07.** The coverage line in `REQUIREMENTS.md` MUST read **`61/61`** after the additions (52 original + 9 Phase 13).
- **D-08.** Re-check (`[x]`) the stale unchecked items reflecting Phase 7 verification: `SHELL-03`, `ARTIF-01`, `ARTIF-02`, `ARTIF-03`, `ARTIF-04`. Read `07-VERIFICATION.md` to confirm before flipping. Update their traceability `Verified` columns to match.

**ROADMAP.md Progress Sync:**
- **D-09.** Mark Phases **5, 6, 7, 8, 9** as `Complete` in the v1.1 ROADMAP progress table with their actual completion dates from each phase's `*-VERIFICATION.md` frontmatter. Do NOT use `2026-05-21` as a placeholder.

**STATE.md Body Sync:**
- **D-10.** Update the body text in `.planning/STATE.md` so it matches its frontmatter (9/9 phases complete pre-Phase-14). Remove any "Next phase" / "in progress" stale text that disagrees with `phases_complete: 9`.

**VALIDATION.md Frontmatter Sync:**
- **D-11.** Set `nyquist_compliant: true` in the frontmatter of: `05-VALIDATION.md`, `06-VALIDATION.md`, `12-VALIDATION.md`, `13-VALIDATION.md`. **Precondition:** the corresponding `*-VERIFICATION.md` MUST contain a passed verdict for nyquist compliance. If not, the flag stays `false` and the gap is recorded in `14-VERIFICATION.md`.

**Live Container UAT:**
- **D-12.** All 15 outstanding human-verification items MUST be executed in a freshly rebuilt container (`docker compose build --no-cache && docker compose up -d`, exact recipe to be confirmed against `docker-compose.yml`). Items by phase: Phase 7 ×3, Phase 8 ×2, Phase 10 ×4, Phase 11 ×5, Phase 13 ×1.
- **D-13.** Recording format per item: append to relevant `*-VERIFICATION.md` under a new `## Live UAT Results (Phase 14 closure)` section. Each entry includes: item description, command run, ISO-8601 UTC timestamp, container image SHA or build date, and ≥10 lines of transcript (truncated with `…` only when output exceeds 200 lines).

**Audit Re-run Gate:**
- **D-14.** Phase NOT complete until `/gsd-audit-milestone` returns `status: passed` with no gaps. Final task in the phase.

### Claude's Discretion

- Plan wave structure and parallelization across the 5 work-streams (test fixes / REQUIREMENTS.md sync / ROADMAP.md sync / STATE.md sync / VALIDATION.md sync) provided dependencies are honored. Live UAT (D-12/D-13) must follow test fixes (D-01/D-02/D-03) because UAT runs in a rebuilt container whose image MUST include the test fixes.
- Whether to add new tests guarding against the `importlib.reload` regression — recommended but not strictly required. If added, place them where they will be picked up by `pytest -m 'not slow'`.
- Exact wording of `REQUIREMENTS.md` Phase 13 entries (must be faithful to ROADMAP + VERIFICATION but copy/edit is at planner discretion).
- Exact section formatting of the appended `## Live UAT Results` blocks in each phase's `VERIFICATION.md`, provided D-13's required fields are present.
- Whether to commit per-fix atomically vs. per-workstream, provided commits are scoped (no mixing of test fix + planning state in the same commit).

### Deferred Ideas (OUT OF SCOPE)

- New regression tests for the `importlib.reload` class-identity pitfall (recommended but non-blocking; may defer to v1.2).
- Refactoring `mcp_gateway.sessions` package layout beyond the minimal D-02 fix.
- Adding new HARDEN requirements (only the existing 9 are in scope).
- Re-running `/gsd-secure-phase` for any phase.
- CI workflow updates to enforce host-vs-container test contract.
</user_constraints>

## Project Constraints (from CLAUDE.md)

- **GSD workflow enforcement:** every Edit/Write must originate from a GSD command. Phase 14 must be executed via `/gsd-execute-phase` (or compatible).
- **Commit-message style (user-global):** single-line, sentence-cased imperative verb, no conventional-commit prefix. Example: `Fix r2_sessions SessionCapReached reload binding`.
- **Licensing constraint (unchanged from project):** IDA Pro / Binary Ninja licenses are never baked into images. UAT rebuild commands must NOT alter that posture.
- **Security constraint:** container runs with `SYS_PTRACE` + `seccomp=unconfined`; this is the baseline that the UAT is meant to verify, not change.
- **Backward compatibility:** "agent inside container" mode must continue working unchanged. UAT verifies the remote-MCP mode, not a swap.

## Phase Boundary (from CONTEXT.md)

Three work-streams, three success oracles:

1. **Test-suite cleanliness** — `cd mcp-gateway && uv run pytest -m 'not slow'` exits `0 failed` in ONE non-isolated invocation. Today: `8 failed, 586 passed, 48 skipped, 13 deselected`.
2. **Planning-state sync** — `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, four `VALIDATION.md` files match reality.
3. **Live container UAT** — 15 items recorded in their respective `*-VERIFICATION.md` files under a new section.

Re-running `/gsd-audit-milestone v1.1` and seeing `status: passed` is the integrated oracle.

## Standard Stack

Phase 14 introduces no new libraries — it modifies existing code and planning docs. The relevant tooling is already pinned:

| Library / Tool | Version | Purpose | Role in Phase 14 | Confidence |
|----------------|---------|---------|------------------|------------|
| Python | 3.11+ | Runtime for mcp-gateway | Host for the test-isolation fixes [VERIFIED: pyproject.toml] | HIGH |
| pytest | (pinned via pyproject) | Test runner | Reproducer chain in D-01..D-03 [VERIFIED: working tree] | HIGH |
| pytest-asyncio | from uv.lock | Async test runner | Drives the 6 sessions-concurrency tests [VERIFIED: test files] | HIGH |
| uv | from project | Package manager + script runner | `uv run pytest -m 'not slow'` is the acceptance gate [VERIFIED: CONTEXT.md] | HIGH |
| `mcp` (Python SDK) | 1.27.x | MCP server framework | Untouched in Phase 14 [VERIFIED: CLAUDE.md] | HIGH |
| `asyncio.BoundedSemaphore` | stdlib | Cap-enforcement primitive | Touched by the reload bug; semantics preserved [VERIFIED: _base.py:194] | HIGH |
| Docker / `docker compose` | host-supplied | Container build + run | UAT image rebuild via `docker compose build --no-cache` [VERIFIED: docker-compose.yml absent — use `compose.yaml` / `compose.remote.yaml`] | HIGH |
| radare2 / r2 | 6.0.5 in Kali image | r2 session backend | Required for Phase 8/13 live tests [VERIFIED: 13-VERIFICATION.md hot-fix block] | HIGH |
| gdb (MI3) | from Kali image | gdb session backend | Required for Phase 11 dynamic UAT [VERIFIED: probe_dynamic_tools.sh] | HIGH |
| strace / ltrace / qemu-user-static / unblob / binwalk3 / upx | from Kali image | Phase 10/11 UAT subjects | Required for UAT items [VERIFIED: Dockerfile + probe scripts] | HIGH |
| setfacl (`acl` apt package) | from Kali image | ACL-revocation in container | Container-only; D-04 marks test skipif on host [VERIFIED: test_acl_available.py] | HIGH |

**No alternatives to consider.** Phase 14 is closure work; the stack is already locked.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| (none — phase has no new requirement IDs; success oracle is `/gsd-audit-milestone` passed) | Phase 14 closes existing requirements (mostly already verified at code level). The closure work is: (a) fix tests so the suite oracle passes, (b) flip 14 stale checkboxes + 4 VALIDATION frontmatter flags + 1 progress table to honestly reflect reality, (c) record 15 UAT transcripts. | The 9 Phase 13 requirements (HARDEN-01..07, SESS-CAP-01, JOBS-CAP-01) ARE the closure-targets at the traceability level — see §"Q9: Phase 13 requirement body drafts" below. |

## Architecture Patterns

### Pattern 1: Module-attribute access survives `importlib.reload`

**What:** When code may be hot-reloaded (live or in tests), classes referenced by `from pkg import Cls` become **stale** after reload because the local name still points at the pre-reload class object. Catching with `except Cls` then misses freshly-raised instances of the post-reload class.

**When to use:** Any file participating in a module that might be reloaded by tests (verified pattern across this codebase — `tools/r2_sessions.py:28-31` already documents this constraint in a comment but does it WRONG for `SessionCapReached`).

**Correct form (already used in the same file for env-var constants `sessions.MAX_SESSIONS`, `sessions.R2_CMD_TIMEOUT_S`, line 173, 254, 384):**
```python
from mcp_gateway import sessions as _sessions_pkg
# ...
except _sessions_pkg.SessionCapReached as e:
    return e.to_dict()
```

This works because attribute lookup happens at `except`-eval time. When the package reloads, the package's `__dict__` rebinds `SessionCapReached` to the new class; the next `except` correctly catches it.

**Alternative resolved at exception-catch time (module-relative form):**
```python
import importlib
# ...
except getattr(importlib.import_module("mcp_gateway.sessions"), "SessionCapReached") as e:
    ...
```
Verbose; the first form is preferred and matches the existing convention.

**Anti-pattern (current buggy form in `tools/r2_sessions.py:36-41`):**
```python
from mcp_gateway.sessions import (
    SessionCapReached,
    check_dangerous_cmd,
    strip_ansi,
    truncate_for_response,
)
# ...
except SessionCapReached as e:   # ← stale class object after reload!
    return e.to_dict()
```

[VERIFIED: working tree, mcp-gateway/src/mcp_gateway/tools/r2_sessions.py lines 28-41, 183, 464]

### Pattern 2: Package `__init__.py` must repopulate child modules on reload

**What:** When `tests/test_gdb_session.py::test_gdb_env_validates_bad_values` does `sys.modules.pop("mcp_gateway.sessions.gdb", None)` and `sys.modules.pop("mcp_gateway.sessions", None)` and then `import mcp_gateway.sessions`, Python re-executes `sessions/__init__.py`. That file currently iterates submodules (`_base`, `r2`, `gdb`) and calls `importlib.reload()` **only if the module is already in `sys.modules`**. After the test pops the parent package, `mcp_gateway.sessions.r2` may still be in `sys.modules` (it was not popped), so it gets reloaded. But the re-imported parent package's `__dict__` does NOT pick up the `r2` and `gdb` submodules as **attributes**.

**Why this matters:** `monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", ...)` resolves the dotted path by walking `mcp_gateway.sessions` → look up attribute `r2`. If the package was just re-imported and `r2` is in `sys.modules["mcp_gateway.sessions.r2"]` but NOT bound as an attribute on the newly-loaded package object, the lookup fails (or worse, succeeds against a stale module if the import system synthesizes the attribute from `sys.modules`).

**Fix pattern (preferred per CONTEXT.md D-02):** Make `sessions/__init__.py` explicitly bind submodules as package attributes after the reload sweep:
```python
import sys
# ... existing reload loop ...
for _name in ("_base", "r2", "gdb"):
    _full = f"mcp_gateway.sessions.{_name}"
    _mod = sys.modules.get(_full)
    if _mod is not None:
        # Always rebind as a package attribute so reload after popping the
        # parent leaves submodules reachable via attribute access (e.g.
        # monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", ...)).
        sys.modules[__name__].__dict__.setdefault(_name, _mod)
        # Use plain assignment if we want re-bind-on-reload semantics:
        setattr(sys.modules[__name__], _name, _mod)
```

The existing `from ._base import (...)` / `from .r2 import (...)` / `from .gdb import (...)` re-exports also need to fire after the reload loop — which they already do. The missing piece is **the parent package's `r2` and `gdb` attributes** (not `from .r2 import R2Session` — that imports symbols FROM r2, not the `r2` module itself).

**Alternative (CONTEXT.md D-02 fallback):** rewrite the 6 sessions-concurrency tests to use `from mcp_gateway.sessions import r2 as r2_mod` and then `monkeypatch.setattr(r2_mod, "_open_r2", ...)`. Smaller risk, but it spreads the workaround across test files instead of fixing the package once.

[VERIFIED: mcp-gateway/src/mcp_gateway/sessions/__init__.py lines 20-29; tests/test_gdb_session.py:200-214; tests/test_sessions_concurrency.py:154-156, 192-195, 234-238, 274-277, 290-293, 345-347]

### Pattern 3: Per-phase VERIFICATION.md "Live UAT Results" append section

**What:** D-13 mandates appending (not editing in place) a new `## Live UAT Results (Phase 14 closure)` section at the bottom of each affected phase's `*-VERIFICATION.md`. This preserves the original verification record while adding the missing live-arm evidence.

**Template (matches CONTEXT.md skeleton):**
```markdown
## Live UAT Results (Phase 14 closure)

### Item 1: [verbatim item description from human_verification frontmatter]
- **Date:** 2026-05-21T14:32:00Z
- **Container image:** mare-toolbox:<sha-or-build-date>
- **Command:**
  ```
  docker compose exec kali bash -c 'cd /agent/mcp-gateway && uv run pytest ...'
  ```
- **Outcome:** passed
- **Transcript (≥10 lines):**
  ```
  <first 10–200 lines of real output>
  ```
```

**Idempotency:** Once the section exists for a phase, subsequent items extend it (numbered subheadings). Do NOT overwrite.

### Pattern 4: Container rebuild recipe

**What:** UAT image must include the D-01/D-02 fixes. The repo uses `compose.yaml` (local) + `compose.remote.yaml` (remote mode) and a `run_docker.sh` wrapper that drives `docker buildx build` from `Dockerfile`. `--no-cache` is NOT supported by the wrapper directly; the planner must either invoke `docker compose build --no-cache` explicitly, OR remove the cached image and let `run_docker.sh` rebuild via its image-hash logic.

**Recommended rebuild commands (verified against repo layout):**
```bash
# 1. Ensure source fixes are committed first (so the image-hash includes them — Phase 5 FOUND-01).
# 2. Remove cached images so the next build is fresh:
docker image rm $(docker images -q kali-re-tools) 2>/dev/null || true

# 3. Standard remote-mode rebuild (the v1.1 reference path):
./run_docker.sh --remote
# (For dynamic-mode UAT items in Phase 11, use ./run_docker.sh --remote --dynamic)

# 4. Inside the container, run probe scripts to confirm READY state:
docker compose exec kali bash /agent/scripts/probe_extraction_tools.sh
docker compose exec kali bash /agent/scripts/probe_dynamic_tools.sh   # exit 0 = READY
```

**Probe READY shapes (verified output expectations):**
- `probe_extraction_tools.sh`: prints `binwalk3` / `unblob` / `upx-ucl` version blocks; succeeds silently. No explicit "READY" line — the absence of error and the `(no --depth flag found -- confirms binwalk3)` line is the success signal. [VERIFIED: scripts/probe_extraction_tools.sh]
- `probe_dynamic_tools.sh`: prints `[OK]` / `[WARN]` / `[INFO]` lines per capability and ends with `=== Dynamic mode is READY ===` on exit 0, OR `=== Dynamic mode has missing capabilities ===` on exit 1. [VERIFIED: scripts/probe_dynamic_tools.sh:114-119]

[VERIFIED: compose.yaml, run_docker.sh:264-284, scripts/probe_*]

### Anti-Patterns to Avoid

- **Editing planning files inside a test-fix commit (or vice-versa).** CONTEXT.md Claude's Discretion explicitly forbids mixing scopes. Commits should be: (a) test fixes, (b) planning sync per file or per workstream, (c) UAT transcript additions per phase.
- **Using `2026-05-21` as a placeholder completion date.** D-09 explicitly forbids this. Pull real dates from each phase's `*-VERIFICATION.md` frontmatter (table below in §"Q3").
- **Force-flipping `nyquist_compliant: true` when VERIFICATION.md does not confirm compliance.** D-11 mandates a precondition check. The table in §"Q6" below records the actual state per phase.
- **Running UAT against a container built BEFORE the test fixes land.** UAT image MUST be the post-fix image. The Phase 5 FOUND-01 fix (image-hash includes `mcp-gateway/src/`) already guarantees rebuild-on-edit; the planner just needs to verify the rebuild happened (e.g., by comparing image SHA pre-/post-fix).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Defining a new "section ordering" for the appended UAT block | A custom YAML schema | Verbatim copy of the human_verification frontmatter `test:` and `expected:` strings | The audit oracle keys on grep-able text in VERIFICATION.md; deviating from existing wording could break re-audit matching |
| Re-deriving completion dates from git log | `git log --diff-filter=A --format=%cI` | Each phase's `*-VERIFICATION.md` `verified:` frontmatter field | Already authoritative and in the same format the ROADMAP table uses. Table below in §"Q3" |
| Custom "container UAT runner" framework | A pytest plugin or shell-script orchestrator | `docker compose exec kali bash -c '...'` invocations recorded as commands | The 15 items are heterogeneous; their existing test commands are already documented in human_verification frontmatter. Just run them and capture output |
| Rewriting `sessions/__init__.py` to drop the reload loop | A v2 sessions package architecture | A 2-line `setattr` after the existing reload loop | D-02 keeps the fix surgical. Refactoring is in the Deferred Ideas list |
| Replacing `JobCapReached` value-binding in `tools/jobs.py` | A broad sweep of all `from mcp_gateway.X import Y` patterns | LEAVE `tools/jobs.py` ALONE in Phase 14 unless it also fails the suite | The audit specifically lists r2_sessions.py + sessions/__init__.py. Don't expand scope unless `pytest -m 'not slow'` flags a `jobs.py` regression. (See §"Open Questions" for a note.) |

**Key insight:** Phase 14 is closure work. Every "shouldn't we also fix X?" is automatically out of scope unless `/gsd-audit-milestone` after the fix still reports a gap.

## Runtime State Inventory

This phase is mostly file/doc edits — no databases, no stored data migrations, no OS-registered state. But it DOES involve a container rebuild, which is build-artifact state that needs accounting.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None. No databases or persistent stores carry phase-14-related identifiers. | None — verified by grep against `.planning/` for migration references. |
| Live service config | None inside scope. (The MCP gateway runs in a container that is REBUILT for UAT, which discards any in-memory config from the prior image.) | None — verified by reviewing compose.yaml + run_docker.sh. |
| OS-registered state | None. No systemd / launchd / Task Scheduler entries. | None. |
| Secrets / env vars | `MCP_GATEWAY_TOKEN` is generated at container start; UAT rebuild will rotate it. UAT commands MUST use the freshly-generated token (visible in `workspace/.mcp-gateway-token` after `./run_docker.sh --remote`). | Plan must mention: "after rebuild, source the token from `.mcp-gateway-token` before running the live-MCP-client items in Phase 7 / 10 / 11." |
| Build artifacts / installed packages | The Kali image cache MAY be stale (carries pre-fix code). The Phase 5 FOUND-01 image-hash mechanism rebuilds automatically when `mcp-gateway/src/` changes; but if Phase 14's source changes are committed and the planner doesn't trigger `./run_docker.sh`, the rebuild won't happen. | Plan must include an explicit `./run_docker.sh --remote` invocation AFTER the D-01/D-02 fixes are committed, and BEFORE the UAT items run. Confirm image rebuild via `docker images kali-re-tools` (new SHA). |

## Environment Availability

| Dependency | Required By | Available on dev host | Version | Fallback |
|------------|------------|-----------------------|---------|----------|
| Python 3.11+ + uv | D-01/D-02 test reproducer | ✓ (verified — mcp-gateway runs locally) | from uv.lock | — |
| pytest + pytest-asyncio | D-01/D-02 reproducer | ✓ | from uv.lock | — |
| Docker / docker compose | D-12 UAT rebuild | ✗ on bare host? (executor varies — the audit ran tests without Docker) | n/a | UAT MUST be deferred to a host that has Docker installed; cannot run UAT items on a Docker-less host. **Planner must call this out as a precondition for the UAT workstream.** |
| radare2 (r2) | Phase 8 + Phase 13 UAT items | ✗ on dev host (audit confirms: "r2 unavailable on dev host") [VERIFIED: 13-VERIFICATION.md line 35, 93] | container-only | Container-only path; tests skip cleanly on host via `_require_r2_or_skip()`. |
| gdb / strace / ltrace / qemu-user-static | Phase 11 UAT items | ✗ on dev host | container-only | Container-only; tests skip cleanly. |
| binwalk3 / unblob / upx-ucl | Phase 10 UAT items | ✗ on dev host | container-only | Container-only; tests skip cleanly. |
| setfacl (`acl` package) | Phase 7 UAT + `test_acl_available.py` | ✗ on dev host (audit confirms) | container-only | D-04 marks the test skipif on host. |

**Missing dependencies with no fallback:**
- **Docker on the UAT-runner host.** The 15 UAT items cannot be executed without it. If the planner spawns sub-agents that run on a Docker-less host, the UAT workstream must be deferred to a Docker-equipped operator. CONTEXT.md does not explicitly handle this — flag as an open question if the executor host lacks Docker.

**Missing dependencies with fallback:**
- All container-only tools (r2, gdb, strace, etc.) — fallback is "the test correctly skips on host". No action needed; the existing test architecture already accounts for this.

## Common Pitfalls

### Pitfall 1: Fixing only `tools/r2_sessions.py` and forgetting `tools/jobs.py`

**What goes wrong:** `tools/jobs.py:28-34` uses the SAME value-binding antipattern as r2_sessions.py:
```python
from mcp_gateway.jobs import (
    BackgroundJobRegistry,
    InvalidKwargs,
    JobCapReached,
    JobNotFound,
    UnknownJobTool,
)
```
If `mcp_gateway.jobs` is ever reloaded by a future test (or even by the existing `tests/jobs/conftest.py` `registry_factory` fixture that already does `importlib.reload(mcp_gateway.jobs)`), the same bug will surface for JobCapReached.

**Why it happens:** The audit doesn't list jobs concurrency in the failing set today, so the bug is latent.

**How to avoid:** Phase 14 scope per D-01/D-02 is narrow — DO fix r2_sessions.py + sessions/__init__.py. **OPTIONALLY** sweep `tools/jobs.py` with the same module-attribute pattern; cost is ~5 LoC. Leave the decision to the planner — Claude's Discretion area. The conservative choice is to leave it alone unless a regression surfaces.

**Warning signs:** Any future `tests/jobs/test_*.py` that calls `importlib.reload(jobs)` and then triggers a cap-rejection path.

[VERIFIED: mcp-gateway/src/mcp_gateway/tools/jobs.py:28-34; tests/jobs/conftest.py uses `importlib.reload(jobs)` per STATE.md Plan 09-04 note]

### Pitfall 2: Re-running `test_gdb_env_validates_bad_values` AFTER the fix without verifying it still raises

**What goes wrong:** The fix to `sessions/__init__.py` makes the package more robust to reload. If the planner over-fixes (e.g., catches the env-var RuntimeError during the reload loop), `test_gdb_env_validates_bad_values` would silently pass without exercising the actual validation. That test is the only assertion that env-var bad values raise.

**Why it happens:** The fix targets attribute rebinding; the RuntimeError-on-bad-env-var behavior is in `_base.py:53/65`. They're orthogonal — but a sloppy `try: ... except: pass` wrapper around the reload loop would swallow both.

**How to avoid:** D-02 is specifically about **attribute rebinding**, not about catching exceptions. The patch should add `setattr(sys.modules[__name__], _name, _mod)` lines, NOT add `try/except` around the existing `importlib.reload(_m)` call.

**Warning signs:** `test_gdb_env_validates_bad_values` flips from "raises RuntimeError" to "no error" → the env validation got silenced.

### Pitfall 3: VALIDATION.md frontmatter flip without VERIFICATION.md support

**What goes wrong:** D-11 says flip `nyquist_compliant: false` → `true` for phases 5, 6, 12, 13. If `13-VERIFICATION.md` does NOT explicitly say nyquist-compliant (and it doesn't — it has a HUMAN NEEDED note for one item), flipping the flag is dishonest.

**Why it happens:** Pattern-matching on the four phases without reading their VERIFICATION.md files.

**How to avoid:** Per-phase precondition check (table in §"Q6" below). Phase 13 VERIFICATION.md shows `status: PASS` post-hot-fix, score `9/9 must-haves verified (automated)` + `11/11 automated truths`. After Phase 14's live HARDEN-03 UAT item runs and is recorded, the `human_needed` aspect drops away. Only THEN flip the flag.

[VERIFIED: 13-VERIFICATION.md frontmatter `status: PASS` line 4, score line 5]

### Pitfall 4: Recording UAT transcripts against a STALE container image

**What goes wrong:** If the planner runs UAT items in a container built before the D-01/D-02 fixes (because the image hash didn't change, or because they reused an old `kali-re-tools:latest` tag), the recorded transcripts capture the BUGGY behaviour, and the audit re-run is meaningless.

**Why it happens:** Docker image caching is sneaky. Even after `./run_docker.sh --remote`, if `mcp-gateway/src/` was edited AFTER the hash was computed, the image won't rebuild.

**How to avoid:** Plan must include a step: "After committing D-01/D-02 fixes, run `./run_docker.sh --remote` and capture the new `kali-re-tools` image SHA. Every UAT transcript MUST cite this SHA in its `Container image:` field (D-13)."

**Warning signs:** Two UAT transcripts dated minutes apart cite different image SHAs (means the rebuild happened mid-workstream).

### Pitfall 5: Forgetting that `compose.yaml` is the file name (not `docker-compose.yml`)

**What goes wrong:** CONTEXT.md D-12 says "exact recipe to be confirmed against `docker-compose.yml`". But the repo has `compose.yaml` and `compose.remote.yaml`, not `docker-compose.yml`. Commands hard-coded against `docker-compose.yml` will fail.

**Why it happens:** Docker Compose v2 dropped the `docker-compose.yml` naming convention; the project uses the modern name.

**How to avoid:** Use `docker compose` (v2 CLI; auto-detects `compose.yaml`). For explicit file targeting use `-f compose.yaml -f compose.remote.yaml` per `run_docker.sh:325-326, 346-349`.

[VERIFIED: ls -la output; run_docker.sh lines 325-349]

### Pitfall 6: STATE.md frontmatter says 9/9 but the body says "Phase 13 EXECUTING"

**What goes wrong:** Internal inconsistency in STATE.md confuses both humans and `/gsd-audit-milestone`.

**Specific stale phrases in STATE.md body** (line numbers from working tree):
- Line 25: `**Current focus:** Phase 13 — harden-concurrency-caps-and-r2-sandboxing`
- Line 30: `Phase: 13 (harden-concurrency-caps-and-r2-sandboxing) — EXECUTING`
- Line 31: `Plan: 4 of 4` (this matches 13's 4 plans, but as the active position it's stale)
- Line 33: `Last activity: 2026-05-21 - Completed quick task 260521-d6l: Phase 13 hot-fix r2 sandbox latching via stdin instead of argv`
- Line 35: `Progress: [          ] 0% (0/8 phases complete)` — **wrong on its face; frontmatter says 9/9**

**How to fix per D-10:** Update body to reflect 9/9 complete pre-Phase-14, current focus = Phase 14 (closure). Drop the 0%/0/8 progress bar line or recompute.

[VERIFIED: STATE.md lines 25, 30-35]

### Pitfall 7: Sub-agent UAT recording context loss

**What goes wrong:** If the planner spawns sub-agents per phase to record UAT, each sub-agent's transcript output may not be persisted to the right phase's VERIFICATION.md unless the orchestration is explicit.

**How to avoid:** Per-phase UAT execution should be plan-as-task pattern: each task `<action>` carries the exact phase VERIFICATION.md path and the exact item to append. Plan-checker should verify each UAT task names ONE target file and ONE item.

## Code Examples

### Example 1: r2_sessions.py SessionCapReached fix (D-01)

**Source: working tree mcp-gateway/src/mcp_gateway/tools/r2_sessions.py:28-41, 183, 464**

**Before (BUGGY):**
```python
from mcp_gateway import session_state
from mcp_gateway import sessions
from mcp_gateway.artifacts_io import ensure_subdir, tool_log_path
from mcp_gateway.runner import STDOUT_HEAD_KB
from mcp_gateway.sessions import (
    SessionCapReached,         # ← stale binding after reload
    check_dangerous_cmd,
    strip_ansi,
    truncate_for_response,
)
# ...
# Line 183:
    except SessionCapReached as e:   # ← misses post-reload class
        return e.to_dict()
# ...
# Line 464 (open_r2_session_unsafe):
    except SessionCapReached as e:
        return e.to_dict()
```

**After (FIXED — preferred form, matches existing `sessions.MAX_SESSIONS` convention at line 173/254/384):**
```python
from mcp_gateway import session_state
from mcp_gateway import sessions
from mcp_gateway.artifacts_io import ensure_subdir, tool_log_path
from mcp_gateway.runner import STDOUT_HEAD_KB
# Note: SessionCapReached is intentionally NOT imported by name. It is resolved
# at exception-catch time via `sessions.SessionCapReached` (module-attribute
# access) so importlib.reload(sessions) in tests propagates the new class
# identity through the except clauses. The remaining names (check_dangerous_cmd,
# strip_ansi, truncate_for_response) are pure helpers with no reload-class-identity
# coupling, so `from X import Y` is fine for them.
from mcp_gateway.sessions import (
    check_dangerous_cmd,
    strip_ansi,
    truncate_for_response,
)
# ...
# Line 183:
    except sessions.SessionCapReached as e:   # ← resolves at except-eval time
        return e.to_dict()
# ...
# Line 464:
    except sessions.SessionCapReached as e:
        return e.to_dict()
```

**Exact line ranges to edit:**
- Lines 36-41: remove `SessionCapReached` from the `from mcp_gateway.sessions import (...)` tuple
- Line 183: change `except SessionCapReached` → `except sessions.SessionCapReached`
- Line 464: change `except SessionCapReached` → `except sessions.SessionCapReached`
- (Line 434 is a docstring mention — no code change needed.)

**Other places in codebase doing the same antipattern:**
- `mcp-gateway/src/mcp_gateway/tools/jobs.py:28-34` — value-binds `JobCapReached`, `JobNotFound`, `InvalidKwargs`, `UnknownJobTool` (latent bug; not in audit failure set today). See Pitfall 1.
- `mcp-gateway/src/mcp_gateway/tools/dynamic.py:326` — already does the right thing inline: `from mcp_gateway.sessions import SessionCapReached` is inside an `except Exception` block, so it re-resolves on each catch. No fix needed here.

### Example 2: sessions/__init__.py package-attribute rebinding (D-02)

**Source: working tree mcp-gateway/src/mcp_gateway/sessions/__init__.py:11-29**

**Current (only force-reloads, doesn't rebind submodules as attrs):**
```python
import importlib
import sys

# Force-reload submodules when this package is reloaded ...
for _submod in (
    "mcp_gateway.sessions._base",
    "mcp_gateway.sessions.r2",
    "mcp_gateway.sessions.gdb",
):
    _m = sys.modules.get(_submod)
    if _m is not None:
        importlib.reload(_m)

from ._base import (...)
from .r2 import (...)
from .gdb import (...)
```

**After (D-02 fix — adds attribute rebinding):**
```python
import importlib
import sys

# Force-reload submodules when this package is reloaded ...
for _submod in (
    "mcp_gateway.sessions._base",
    "mcp_gateway.sessions.r2",
    "mcp_gateway.sessions.gdb",
):
    _m = sys.modules.get(_submod)
    if _m is not None:
        importlib.reload(_m)

# Phase 14 D-02 fix: explicitly bind submodules as package attributes so
# `monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", ...)` resolves
# correctly even after a test pops mcp_gateway.sessions from sys.modules
# and re-imports it (see tests/test_gdb_session.py::test_gdb_env_validates_bad_values).
# Without this, the parent package's __dict__ lacks the `r2` / `gdb` attribute
# binding even though sys.modules["mcp_gateway.sessions.r2"] exists, and the
# attribute lookup walked by setattr/getattr fails.
for _name in ("_base", "r2", "gdb"):
    _full = f"mcp_gateway.sessions.{_name}"
    _mod = sys.modules.get(_full)
    if _mod is not None:
        setattr(sys.modules[__name__], _name, _mod)

from ._base import (...)
from .r2 import (...)
from .gdb import (...)
```

**Acceptance check** (manually verify after fix):
```bash
cd mcp-gateway && uv run python -c "
import sys
# Simulate the gdb test's pollution path
import mcp_gateway.sessions
sys.modules.pop('mcp_gateway.sessions.gdb', None)
sys.modules.pop('mcp_gateway.sessions', None)
import mcp_gateway.sessions
print('r2 attr:', hasattr(mcp_gateway.sessions, 'r2'))
print('gdb attr:', hasattr(mcp_gateway.sessions, 'gdb'))
print('_base attr:', hasattr(mcp_gateway.sessions, '_base'))
"
# Expect: r2 attr: True, gdb attr: True, _base attr: True
```

### Example 3: ACL test container-only contract (D-04)

**Source: working tree mcp-gateway/tests/test_acl_available.py**

**Current:**
```python
"""Phase 7 D-04: setfacl must be on PATH inside the container.
...
"""
from __future__ import annotations

import shutil


def test_setfacl_on_path() -> None:
    """D-04: `shutil.which('setfacl')` is not None."""
    assert shutil.which("setfacl") is not None, (
        "Phase 7 D-04 requires apt package 'acl' (provides setfacl). "
        "Dockerfile apt install list must include 'acl'."
    )
```

**After (D-04 fix per CONTEXT Option A):**
```python
"""Phase 7 D-04: setfacl must be on PATH inside the container.

Container-only contract (Phase 14 D-04): this test is skipped on hosts
without setfacl because the project's reference run environment is the
Kali Linux Docker container; host-bare runs should not fail loudly on
environmental ACL absence. The Dockerfile installs acl at build time.
"""
from __future__ import annotations

import shutil

import pytest


@pytest.mark.skipif(
    shutil.which("setfacl") is None,
    reason="setfacl host-binary missing; container-only contract (Phase 14 D-04)",
)
def test_setfacl_on_path() -> None:
    """D-04: `shutil.which('setfacl')` is not None."""
    assert shutil.which("setfacl") is not None, (
        "Phase 7 D-04 requires apt package 'acl' (provides setfacl). "
        "Dockerfile apt install list must include 'acl'."
    )
```

### Example 4: ROADMAP.md progress table edit (D-09)

**Source: working tree .planning/ROADMAP.md:178-194**

**Current rows (stale):**
```markdown
| 5. F-1 Image-Hash Fix          | v1.1      | 0/3   | Not started | -          |
| 6. ReToolRunner Foundation     | v1.1      | 0/3   | Not started | -          |
| 7. run_shell + Static Wrappers | v1.1      | 0/?   | Not started | -          |
| 8. Session-Scoped r2           | v1.1      | 0/5   | Not started | -          |
| 9. Background Job System       | v1.1      | 0/?   | Not started | -          |
```

**After (D-09 fix; dates pulled from VERIFICATION.md frontmatter — see §"Q3"):**
```markdown
| 5. F-1 Image-Hash Fix          | v1.1      | 3/3   | Complete    | 2026-05-12 |
| 6. ReToolRunner Foundation     | v1.1      | 3/3   | Complete    | 2026-05-13 |
| 7. run_shell + Static Wrappers | v1.1      | 8/8   | Complete    | 2026-05-13 |
| 8. Session-Scoped r2           | v1.1      | 5/5   | Complete    | 2026-05-18 |
| 9. Background Job System       | v1.1      | 5/5   | Complete    | 2026-05-19 |
```

Plan counts confirmed from STATE.md (line 220-230) and `.planning/phases/0X-*/0X-0Y-PLAN.md` file presence.

## State of the Art

No "state of the art" technology shifts apply to Phase 14 — it operates entirely within the existing codebase's primitives. Notable patterns already in use that the fix preserves:

| Old approach (rejected) | Current approach | Why |
|-------------------------|------------------|-----|
| `from X import Y` binding for module-attribute-shaped names | `from X import X_module; X_module.Y` resolution at call time | Survives `importlib.reload(X)` |
| Per-test `sys.modules.pop` for re-import semantics | Tests pop and `import` again | Standard pytest pattern for module-load-side-effects tests |
| Submodule `from .X import names` only | Submodule `from .X import names` PLUS `setattr(self, 'X', X)` for monkeypatch reachability | Module-as-attribute access pattern |

**Deprecated / outdated:**
- None applicable to Phase 14.

## Q1: r2_sessions.py SessionCapReached fix — exact line ranges and other antipattern sites

**File:** `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py`

**Lines to change:**
- **Line 36-41:** Remove `SessionCapReached,` from the import tuple. Final form:
  ```python
  from mcp_gateway.sessions import (
      check_dangerous_cmd,
      strip_ansi,
      truncate_for_response,
  )
  ```
- **Line 183:** `except SessionCapReached as e:` → `except sessions.SessionCapReached as e:`
- **Line 464:** `except SessionCapReached as e:` → `except sessions.SessionCapReached as e:`
- **Line 434:** Docstring reference `"returns the SessionCapReached error dict ..."` — no code change. Leave as-is (it's prose).

**Replacement snippet style:** module-attribute access via `sessions.SessionCapReached` (Pattern 1 above). The `from mcp_gateway import sessions` line at module-line 33 is already present and ALREADY used elsewhere in the file for `sessions.MAX_SESSIONS` (line 173, 193, 384), `sessions.R2_CMD_TIMEOUT_S` (line 254), `sessions.SESSION_OPEN_TIMEOUT_S` (line 173, 453). The fix conforms to the existing convention.

**Other places with the same value-binding antipattern (audit grep):**

| File | Line | Symbol | Severity | In Phase 14 Scope? |
|------|------|--------|----------|----|
| `tools/r2_sessions.py:36-41` | 36-41 | `SessionCapReached` | High (active failure) | **YES — D-01** |
| `tools/jobs.py:28-34` | 28-34 | `JobCapReached`, `JobNotFound`, `InvalidKwargs`, `UnknownJobTool` | Low (latent — no test exercises it today) | NO (Pitfall 1; optional sweep) |
| `tools/dynamic.py:326` | 326 | `SessionCapReached` (in `except` block, re-imports each catch) | None — correct pattern | N/A |
| `sessions/__init__.py:33` | 33 | `SessionCapReached` (re-export) | None — package init, attribute is alive | N/A |

[VERIFIED via grep: `SessionCapReached\|JobCapReached` across `mcp-gateway/src/`]

## Q2: sessions/__init__.py reload re-binding fix

**File:** `mcp-gateway/src/mcp_gateway/sessions/__init__.py`

**Where the bug fires:**
1. `tests/test_gdb_session.py:200-214` (`test_gdb_env_validates_bad_values`) does:
   ```python
   monkeypatch.setenv("MCP_GATEWAY_GDB_CMD_TIMEOUT_S", "not_a_float")
   sys.modules.pop("mcp_gateway.sessions.gdb", None)
   with pytest.raises(RuntimeError):
       import mcp_gateway.sessions.gdb
   monkeypatch.delenv("MCP_GATEWAY_GDB_CMD_TIMEOUT_S", raising=False)
   sys.modules.pop("mcp_gateway.sessions.gdb", None)
   sys.modules.pop("mcp_gateway.sessions", None)   # ← parent package is popped
   import mcp_gateway.sessions   # ← re-executes __init__.py
   ```
2. After this, `sys.modules["mcp_gateway.sessions.r2"]` still exists (it was never popped). The new `mcp_gateway.sessions` module re-executes its `for _submod` reload loop. The reload of `mcp_gateway.sessions.r2` succeeds. BUT the new `mcp_gateway.sessions` package object's `__dict__` is freshly populated — it contains the `from .r2 import R2Session, ...` names but NOT the `r2` submodule as an attribute.
3. Subsequent test `tests/test_sessions_concurrency.py::*` calls `monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", lambda ...)`. `monkeypatch.setattr` resolves the dotted path by `getattr(mcp_gateway.sessions, "r2")` which fails (`AttributeError`).

**Minimal patch (Pattern 2 above):** Add an explicit submodule-as-attribute binding loop after the existing reload loop in `sessions/__init__.py`:

```python
# Phase 14 D-02 fix: explicitly bind submodules as package attributes so
# monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", ...) resolves
# correctly even after a test pops the package and re-imports it.
for _name in ("_base", "r2", "gdb"):
    _full = f"mcp_gateway.sessions.{_name}"
    _mod = sys.modules.get(_full)
    if _mod is not None:
        setattr(sys.modules[__name__], _name, _mod)
```

Insert AFTER line 28 (`        importlib.reload(_m)`), BEFORE the `from ._base import (...)` on line 30. ~7 LoC plus comment.

**Confirm the pattern works:** the existing comment block at lines 6-8 says "DO NOT use `from .X import *` -- Pitfall #11 specifies explicit names". This patch is consistent — it adds explicit module-as-attribute names without using `*`.

**Cleaner pattern already used in the codebase?** No — this is the canonical fix for the package-attribute issue. The codebase elsewhere (e.g., `tools/r2_sessions.py:33`) uses `from mcp_gateway import sessions as _sessions_pkg` to get the package object, which works because the IMPORTING module captures the attribute at import time. The patch above is the package-side counterpart.

[VERIFIED: sessions/__init__.py:20-29; test_gdb_session.py:200-214; test_sessions_concurrency.py:154-156]

## Q3: Phase 5-9 completion dates from VERIFICATION.md frontmatter

| Phase | Completion date (from `verified:` frontmatter) | Source file |
|-------|------------------------------------------------|-------------|
| 5 | **2026-05-12** | `.planning/phases/05-f-1-image-hash-fix/05-VERIFICATION.md:3` |
| 6 | **2026-05-13** | `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-VERIFICATION.md:3` |
| 7 | **2026-05-13** | `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-VERIFICATION.md:3` |
| 8 | **2026-05-18** | `.planning/phases/08-session-scoped-r2/08-VERIFICATION.md:3` |
| 9 | **2026-05-19** | `.planning/phases/09-background-job-system/09-VERIFICATION.md:3` |
| 10 | 2026-05-19 (already in table) | `.planning/phases/10-extraction-tier/10-VERIFICATION.md:3` |
| 11 | 2026-05-20 (already in table) | `.planning/phases/11-dynamic-lab-mode-env-gated/11-VERIFICATION.md:3` |
| 12 | 2026-05-20 (already in table) | `.planning/phases/12-orchestrator-skill-update/12-VERIFICATION.md:3` |
| 13 | 2026-05-21 (already in table, but listed as 2026-05-20 — see drift note) | `.planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/13-VERIFICATION.md:3` |

**Drift note:** ROADMAP.md line 192 lists Phase 13 completion as `2026-05-20`. The Phase 13 VERIFICATION.md frontmatter says `verified: 2026-05-21T12:00:00Z` (post-hot-fix re-verification). The planner should decide whether to update the Phase 13 ROADMAP row to `2026-05-21` for consistency, but this is outside D-09's strict scope (D-09 names phases 5-9 only). Recommend updating it for honesty — flag as discretionary.

[VERIFIED via `grep "^verified:"` across all phase VERIFICATION.md files]

## Q4: REQUIREMENTS.md current state — what actually needs editing

**Critical finding:** The audit understated the actual state. The 9 Phase 13 requirement BODIES, 9 TRACEABILITY ROWS, and the `61/61` COVERAGE LINE are ALREADY in REQUIREMENTS.md. What needs editing is mostly checkbox-flipping.

**Header coverage line (D-07):**
- **Line 209:** `**Coverage:** 61/61 v1.1 requirements mapped (100%). Phase-13 hardening rows (HARDEN-01..07, SESS-CAP-01, JOBS-CAP-01) were verified at the code/test level by 13-VERIFICATION.md; Phase 14 owns their traceability + live-container HARDEN-03 round-trip.`
- **Status:** ALREADY READS `61/61`. No edit needed for D-07.

**Traceability table format (D-06):**
- **Column headers:** `| REQ-ID | Phase | Plan | Verified |` (4 columns, pipe-delimited)
- **Row format:** `| HARDEN-01 | Phase 14 | TBD  | Pending  |`
- **Phase 13 rows location:** lines 199-207 (HARDEN-01..07, SESS-CAP-01, JOBS-CAP-01). All 9 rows EXIST already. Currently `Phase = Phase 14` and `Plan = TBD` and `Verified = Pending`.
- **D-06 edits needed:**
  - Change `Phase` from `Phase 14` to `Phase 13` (since Phase 13 implemented them; Phase 14 only does traceability + UAT)
  - Change `Plan` from `TBD` to `13-01..13-04` (or per-requirement specifics: HARDEN-01/07/SESS-CAP-01 → `13-01`; HARDEN-02/07/JOBS-CAP-01 → `13-02`; HARDEN-03/04/05 → `13-03`; HARDEN-06 → `13-04`)
  - Change `Verified` from `Pending` to `[x]` (after live HARDEN-03 UAT recorded per D-13)
- The mapping is documented in 13-01/02/03/04-SUMMARY.md `requirements:` frontmatter.

**Existing REQUIREMENTS.md unchecked items (D-08 + D-05 checkbox flip):**

| Line | ID | Current | Phase 7 VERIFICATION verdict | D-action |
|------|----|---------|------------------------------|----------|
| 22 | SHELL-03 | `[ ]` | Satisfied (Phase 7 D-04 docstring confirmed) | D-08: flip to `[x]` |
| 39 | ARTIF-01 | `[ ]` | Satisfied (lazy subdir creation verified) | D-08: flip to `[x]` |
| 40 | ARTIF-02 | `[ ]` | Satisfied (write/append helpers) | D-08: flip to `[x]` |
| 41 | ARTIF-03 | `[ ]` | Satisfied (list/tree helpers) | D-08: flip to `[x]` |
| 42 | ARTIF-04 | `[ ]` | Satisfied (range-read get_tool_log) | D-08: flip to `[x]` |
| 94 | HARDEN-01 | `[ ]` | Phase 13 satisfied (code+test); needs Phase 14 UAT noted | D-05: flip to `[x]` |
| 95 | HARDEN-02 | `[ ]` | Phase 13 satisfied | D-05: flip to `[x]` |
| 96 | HARDEN-03 | `[ ]` | Code satisfied; live arm closed by D-13 UAT | D-05: flip to `[x]` after D-13 |
| 97 | HARDEN-04 | `[ ]` | Phase 13 satisfied | D-05: flip to `[x]` |
| 98 | HARDEN-05 | `[ ]` | Phase 13 satisfied | D-05: flip to `[x]` |
| 99 | HARDEN-06 | `[ ]` | Phase 13 satisfied | D-05: flip to `[x]` |
| 100 | HARDEN-07 | `[ ]` | Phase 13 satisfied | D-05: flip to `[x]` |
| 101 | SESS-CAP-01 | `[ ]` | Phase 13 satisfied | D-05: flip to `[x]` |
| 102 | JOBS-CAP-01 | `[ ]` | Phase 13 satisfied | D-05: flip to `[x]` |

**Total checkbox edits: 14.** Three additional table-cell edits per row × 9 rows = 27 cells in the traceability table (mostly `Pending` → `[x]` and `TBD` → plan IDs).

**Note for planner:** D-05 in CONTEXT.md says "Add Phase 13 requirement bodies" — interpret as "ensure the bodies are present AND checked"; they're already present, so the body work is `[ ]` → `[x]` only. Plan should call this out explicitly so the implementer doesn't waste time inserting duplicate text.

[VERIFIED: REQUIREMENTS.md line 22, 39-42, 94-102, 145-207, 209]

## Q5: STATE.md drift specifics (D-10)

**Stale phrases in body that disagree with `phases_complete: 9` frontmatter:**

| Line | Current text | Issue |
|------|--------------|-------|
| 25 | `**Current focus:** Phase 13 — harden-concurrency-caps-and-r2-sandboxing` | Phase 13 is complete; current focus should be Phase 14 |
| 30 | `Phase: 13 (harden-concurrency-caps-and-r2-sandboxing) — EXECUTING` | Should say `Phase: 14 (close-v1.1-gaps) — EXECUTING` (or `PLANNING` if not yet executing) |
| 31 | `Plan: 4 of 4` | Refers to Phase 13's 4 plans; should reflect Phase 14's plan count once known |
| 33 | `Last activity: 2026-05-21 - Completed quick task 260521-d6l: Phase 13 hot-fix r2 sandbox latching via stdin instead of argv` | OK as a historical note, but consider updating to reflect Phase 14 kickoff |
| 35 | `Progress: [          ] 0% (0/8 phases complete)` | Wrong on its face — frontmatter says 9/9. Should be `[**********] 100% (9/9 v1.1 phases complete before Phase 14)` |

**Recommended D-10 edit:** Rewrite lines 25-35 to honestly reflect post-Phase-13 state with Phase 14 in progress. Specifically:
```markdown
**Current focus:** Phase 14 — close-v1.1-gaps (milestone closure)

## Current Position

Milestone: v1.1 Remote RE Tool Expansion
Phase: 14 (close-v1.1-gaps) — EXECUTING
Plan: TBD (Phase 14 plans pending)
Status: 9/9 v1.1 implementation phases complete; closure phase in progress
Last activity: 2026-05-21 - Phase 13 verified PASS post-hot-fix; Phase 14 kicked off via /gsd-discuss-phase

Progress: [**********] 100% v1.1 implementation phases (9/9); milestone archive gated on Phase 14 closure
```

The Performance Metrics section (line 37-44) showing `v1.1 plans completed: 0` is also stale; the actual count is `0/(plan-count-of-phase-14) for Phase 14` + 44 completed before Phase 14. Suggest updating but it's not strictly required by D-10 (D-10 only mandates the "phases" body).

[VERIFIED: STATE.md lines 25-44]

## Q6: VALIDATION.md frontmatter format + per-phase readiness (D-11)

**Frontmatter key/value pattern (verified across files):**
- `nyquist_compliant: true` or `nyquist_compliant: false`
- `wave_0_complete: true` or `wave_0_complete: false`

Both are top-level YAML keys in the frontmatter block.

**Per-phase current state + flippability check:**

| Phase | VALIDATION.md current | VERIFICATION.md confirms nyquist? | Flip to `true`? |
|-------|------------------------|-----------------------------------|-----------------|
| 5 | `nyquist_compliant: false`, `wave_0_complete: false` | VERIFICATION says `status: passed`, score `4/4 must-haves verified`. Phase 5 is small (3 plans, 11 tests); the audit's nyquist-partial finding likely reflects the un-flipped flag, not a substantive gap. | **YES** — flip both flags to `true` (and tick the checkbox at `- [ ] nyquist_compliant: true set in frontmatter`) |
| 6 | `nyquist_compliant: false`, `wave_0_complete: false` | VERIFICATION says `status: passed`, score `5/5`. Wave-0 RED-stub TDD pattern was used (per STATE.md). | **YES** — flip both flags to `true` |
| 12 | `nyquist_compliant: false`, `wave_0_complete: false` | VERIFICATION says `status: passed` (12-05 gap-closure plan covered SKILL-03/04 final tests). | **YES** — flip both flags to `true` |
| 13 | `nyquist_compliant: false`, `wave_0_complete: false` | VERIFICATION says `status: PASS` with score `9/9 must-haves verified (automated)`. The single `HUMAN NEEDED` item is the live HARDEN-03 sandbox check, which Phase 14 D-13 records. | **YES — but ONLY AFTER the Phase 14 D-13 UAT records the live HARDEN-03 result.** Sequence: run UAT → record transcript → flip flag. Pre-condition is the UAT outcome, not just the existence of automated tests. |

**Risk flag for Phase 13:** If the Phase 14 D-13 UAT for HARDEN-03 fails (i.e., `e cfg.sandbox` returns `false` or errors), the flag stays `false` per D-11's "if VERIFICATION does not confirm, flag stays false" precondition. The plan should sequence this dependency explicitly.

**Phases 7, 8, 9, 10, 11 (already `nyquist_compliant: true`):** No edit needed for these.

[VERIFIED via `grep nyquist_compliant` across all VALIDATION.md files]

## Q7: ROADMAP.md progress table format (D-09)

Already covered in Code Example 4 above. Recap:

**Table structure (line 178):**
```markdown
| Phase                          | Milestone | Plans | Status      | Completed  |
|--------------------------------|-----------|-------|-------------|------------|
```

**Current stale rows (lines 184-188):** all five Phase 5/6/7/8/9 rows show `0/N`, `Not started`, `-`.

**Edits needed per D-09:** Update `Plans` column to actual count, `Status` to `Complete`, `Completed` to date from §Q3 table.

**Plan-count truth (from filesystem):**
- Phase 5: `0[1-3]-PLAN.md` → 3 plans
- Phase 6: `0[1-3]-PLAN.md` → 3 plans
- Phase 7: `0[1-8]-PLAN.md` → 8 plans
- Phase 8: `0[1-5]-PLAN.md` → 5 plans
- Phase 9: `0[1-5]-PLAN.md` → 5 plans

## Q8: Container UAT recipe (D-12, D-13)

**Repo files (verified existence):**
- `compose.yaml` — local mode definition (5 services: only `kali`)
- `compose.remote.yaml` — remote-mode overlay (referenced by `run_docker.sh:349`)
- `Dockerfile` — single-stage Kali base image
- `run_docker.sh` — driver script
- `scripts/probe_extraction_tools.sh` — Phase 10 probe (3 tool blocks + apt policy)
- `scripts/probe_dynamic_tools.sh` — Phase 11 probe (9 capability checks, emits `=== Dynamic mode is READY ===` on exit 0)
- `mcp-gateway/probe_extraction_tools.sh` — **does NOT exist at this path** (the audit referenced this path; the actual file is at `scripts/probe_extraction_tools.sh`)
- `mcp-gateway/probe_dynamic_tools.sh` — **does NOT exist at this path** (actual: `scripts/probe_dynamic_tools.sh`)

**Drift correction for planner:** CONTEXT.md canonical_refs lists `mcp-gateway/probe_extraction_tools.sh` — this is a path error. Use `scripts/probe_extraction_tools.sh` and `scripts/probe_dynamic_tools.sh`. Both are mounted under `/agent/scripts/` inside the container per `compose.yaml:11` (`"${HOST_PWD:-.}:/agent"`).

**Exact rebuild command (verified):**
```bash
# From repo root:
# Step A: clear cached image so the next build is fresh (optional but robust)
docker image rm kali-re-tools:latest 2>/dev/null || true
# (run_docker.sh tags HASH_IMAGE plus an auxiliary :latest tag — line 287)

# Step B: rebuild + start container in remote mode
./run_docker.sh --remote
# (For Phase 11 dynamic-mode UAT, use ./run_docker.sh --remote --dynamic)

# Step C: confirm token + URL printed by run_docker.sh in the "MARE-MCP-Toolbox Gateway is ready" block.

# Step D: capture image SHA for transcript records
IMAGE_SHA=$(docker images --no-trunc --format '{{.ID}}' kali-re-tools:latest | head -1)
echo "Container image SHA: $IMAGE_SHA"

# Step E: interactive UAT — attach to the container
docker compose exec kali bash
# (Inside container: cd /agent/mcp-gateway && uv run pytest ...)
```

**Per-probe READY output to expect in UAT transcripts:**

`probe_extraction_tools.sh` (run as `docker compose exec kali bash /agent/scripts/probe_extraction_tools.sh`):
```
=== binwalk ===
/usr/bin/binwalk
Binwalk v3.x.x

=== binwalk --help (look for -d/--depth -- A2: should be ABSENT in binwalk3) ===
(no --depth flag found -- confirms binwalk3)

=== unblob ===
/usr/local/bin/unblob
unblob X.Y.Z

=== upx-ucl / upx ===
/usr/bin/upx
upx X.Y.Z

=== apt policy binwalk3 (A1 confirmation) ===
binwalk3:
  Installed: X.Y.Z
```

`probe_dynamic_tools.sh` (run with `--remote --dynamic`):
```
=== MARE Dynamic-Mode Capability Probe ===

[OK]   unshare: /usr/bin/unshare (...)
[OK]   unshare --net round-trip: passes (seccomp permits)
[OK]   ptrace_scope=0 (parent-child tracing permitted)
[OK]   gdb: /usr/bin/gdb (...)
[OK]   strace: /usr/bin/strace (...)
[OK]   ltrace: /usr/bin/ltrace
[OK]   /proc/sys/fs/binfmt_misc is mounted
[OK]   qemu-*-static binaries available: N arches
[OK]   PTRACE_TRACEME smoke test: passes (SYS_PTRACE granted)

=== Dynamic mode is READY ===
```

[VERIFIED: scripts/probe_extraction_tools.sh, scripts/probe_dynamic_tools.sh, compose.yaml, run_docker.sh:264-287]

## Q9: Phase 13 requirement body drafts (D-05)

**Critical correction:** Per Q4 above, REQUIREMENTS.md ALREADY contains these bodies at lines 94-102. **No body drafting is needed.** Verbatim current contents:

```markdown
### Hardening (HARDEN, SESS-CAP, JOBS-CAP)

Added 2026-05-21 by Phase 13 implementation; brought into REQUIREMENTS.md by Phase 14 traceability sync.

- [ ] **HARDEN-01**: SessionRegistry cap is enforced atomically — N+1 concurrent `open_r2_session` / `open_gdb_session` callers against cap=N never both proceed past it, and any spawn-time failure (Cancel/OSError/RuntimeError) releases the acquired slot
- [ ] **HARDEN-02**: BackgroundJobRegistry cap is enforced atomically — N+1 concurrent `submit()` calls against cap=N produce exactly one `JobCapReached`, and all reachable terminal-state paths release the slot exactly once via `_mark_terminal`
- [ ] **HARDEN-03**: r2 sessions are spawned with `[-e, cfg.sandbox=true]` BEFORE the positional sample path when `sandbox=True`, and a live `e cfg.sandbox` query inside the open session returns `true` at runtime
- [ ] **HARDEN-04**: No `cfg.sandbox.grain` argv flag is emitted by the r2 session builder — the default `grain=all` posture is preserved across both `sandbox=True` and `sandbox=False` paths
- [ ] **HARDEN-05**: The `_DANGEROUS_R2_CMD_RE` pattern remains byte-identical to Phase 8 and its docstring is reframed as a defence-in-depth marker with `DO NOT EXTEND` + `PHASE 13 SECURITY BOUNDARY DELINEATION` language (security boundary lives on `cfg.sandbox`, not the regex)
- [ ] **HARDEN-06**: `open_r2_session_unsafe` is registered iff `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`; it is absent from `tools/list` when the env var is unset; opens emit a WARN-level audit log
- [ ] **HARDEN-07**: `SessionCapReached.to_dict()` and `JobCapReached.to_dict()` are byte-identical to their pre-Phase-13 shapes (4-key dicts, frozen via snapshot tests)
- [ ] **SESS-CAP-01**: Session slot lifecycle holds end-to-end — acquire-before-spawn, release-on-close, release-on-spawn-failure, release-on-reaper-idle-close, release-on-shutdown-active-close — without raising semaphore `ValueError`
- [ ] **JOBS-CAP-01**: Job slot lifecycle holds end-to-end — acquire-before-submit, single release via `_mark_terminal` across all 7 terminal-state paths, release-on-pre-spawn-failure (e.g., `ensure_subdir` raises)
```

**Plan task should specify:** "For lines 94, 95, 96, 97, 98, 99, 100, 101, 102 in REQUIREMENTS.md, change `- [ ]` to `- [x]` (and verify the rest of the line is unchanged — bodies are already correct per Phase 13 VERIFICATION.md)." A `sed -i 's/^- \[ \] \*\*HARDEN-/- [x] **HARDEN-/'` style edit is grep-verifiable.

**Caveat for HARDEN-03:** Flip to `[x]` ONLY AFTER the Phase 14 D-13 live UAT records `e cfg.sandbox` returning `true` (per CONTEXT.md D-05: "...live HARDEN-03 sandbox check is closed in D-13"). Sequence in the plan.

## Q10: SHELL-03 + ARTIF-01..04 stale checkboxes (D-08)

**Phase 7 VERIFICATION.md confirms all 5 satisfied** [VERIFIED: 07-VERIFICATION.md shows `score: 6/6 must-haves verified` and the 3 human_needed items are NOT about SHELL-03 or ARTIF-*].

**Exact REQUIREMENTS.md lines and current state:**

| Line | Current | Target |
|------|---------|--------|
| 22 | `- [ ] **SHELL-03**: \`run_shell\` docstring explicitly documents that confinement is structural posture (cwd + UID + timeout + capture), not OS-level isolation, so agents and operators know what \`run_shell\` is and is not` | Change `- [ ]` to `- [x]` |
| 39 | `- [ ] **ARTIF-01**: Each case directory supports lazily-created subdirs: \`tool-logs/\`, \`extracted/\`, \`hex/\`, \`rop/\`, \`dynamic/\`, \`qemu/\`, \`disassembly/\`, \`decompilation/\`, \`xrefs/\`` | Change `- [ ]` to `- [x]` |
| 40 | `- [ ] **ARTIF-02**: Agent can write/append artifacts via \`write_artifact(case_dir, relpath, content)\` and \`append_artifact(case_dir, relpath, content)\`, with \`confine_to\` enforced` | Change `- [ ]` to `- [x]` |
| 41 | `- [ ] **ARTIF-03**: Agent can enumerate artifacts via \`list_artifacts(case_dir, subdir)\` and \`get_artifact_tree(case_dir)\`` | Change `- [ ]` to `- [x]` |
| 42 | `- [ ] **ARTIF-04**: Agent can range-read large tool logs via \`get_tool_log(case_dir, log_name, offset, length)\` so multi-megabyte logs don't blow the MCP response cap` | Change `- [ ]` to `- [x]` |

**Traceability rows for these (lines 153, 164-167):** currently `Pending`. Flip to `[x]` per D-08.

[VERIFIED: REQUIREMENTS.md:22, 39-42, 153, 164-167; 07-VERIFICATION.md content]

## Q11: 15 outstanding UAT items — exact wording from VERIFICATION.md

These are the strings to use verbatim when constructing the `## Live UAT Results` block headings (D-13).

### Phase 7 (3 items)
1. `Dockerfile rebuild produces mare-shell UID=700, /usr/sbin/nologin, /nonexistent home, and ACL revocations on /agent/uploads`
   - Expected: `docker compose run --rm gateway-agent id mare-shell` returns `uid=700(mare-shell) gid=700(mare-shell)`; `getfacl /agent/uploads` shows `user:mare-shell:r-x` access AND default ACL
   - Why human: setfacl + mare-shell missing on host
2. `D-35 100 MB /dev/urandom slow test passes inside the container`
   - Expected: `docker compose run --rm gateway-agent uv run pytest -m slow tests/test_run_shell.py::test_run_shell_100mb_urandom` exits 0 in <60s
3. `MCP Resources actually visible to a remote MCP client (Claude Code / mastra) with mare://cases/<case>/tool-logs/<file> URIs`

### Phase 8 (2 items)
1. `Run the full Phase 8 test suite inside the Kali container (r2 present)`
   - Expected: 12 r2-gated tests + 3 sessions-test r2-gated tests flip from SKIP to PASS
2. `Manually verify lifespan zombie-free shutdown inside the container`
   - Expected: Open 2 r2 sessions, SIGTERM gateway, no r2 PIDs left in `ps -ef`

### Phase 10 (4 items)
1. `End-to-end recursive triage via Claude Code MCP client`
   - Expected: external client calls `run_binwalk(mode='extract')` → `list_extracted_files` → `promote_extracted_sample` → analysis tools on the new case
2. `Archive-bomb cap aborts mid-extraction in a live container`
   - Expected: `MCP_GATEWAY_MAX_EXTRACT_MB=64`, run extraction on zip-bomb → `.MARE_EXTRACT_CAP_EXCEEDED` marker, meta `status=cap_exceeded`, job cancelled within one EXTRACT_MONITOR_INTERVAL_S poll
3. `Probe script in-container output confirms binwalk3 / unblob / upx version + flag shapes`
4. `Three slow extraction integration tests pass in container` (slow JOBS integration tests)

### Phase 11 (5 items)
1. `Run ./run_docker.sh --remote --dynamic against rebuilt container, then call tools/list over MCP`
   - Expected: 61 tools (54 baseline + 7 dynamic)
2. `Run ./run_docker.sh --remote --dynamic, then call get_dynamic_capabilities() and run_strace on a sample`
3. `Run slow integration tests inside the rebuilt container`
   - Expected: test_strace_via_jobs_roundtrip (ENETUNREACH), test_setsid_grandchild_reaped, test_qemu_user_arm_roundtrip pass
4. `Open gdb session via open_gdb_session MCP tool, run gdb_exec with a blocked command like 'python print(1)', then run a safe command like '-info-functions'`
   - Expected: blocked → `gdb-MI command refused`; safe → MI output
5. `probe_dynamic_tools.sh READY verdict` (the script's `=== Dynamic mode is READY ===` exit-0 print)

### Phase 13 (1 item)
1. `r2 cfg.sandbox active at runtime (HARDEN-03 in-container positive control)`
   - Expected: `pytest tests/test_r2_sandbox_integration.py -v` PASSES; `test_sandbox_active_when_open_r2` confirms `e cfg.sandbox` returns `true`
   - Also: `pytest tests/test_r2_version.py -v`, `pytest tests/test_r2_sessions.py::test_unsafe_open_warn_log -v`

[VERIFIED: human_verification frontmatter blocks in 07/08/10/11/13-VERIFICATION.md]

**Cross-reference shape for the appended `## Live UAT Results` section:** copy each `test:` string verbatim as a subsection heading. Use `expected:` as the truth statement to match against the recorded output.

## Q12: Test-fix dependency on UAT (workstream ordering)

**Decision:** test fixes MUST land BEFORE the UAT-container rebuild. Reasoning:

1. The container UAT image is built from `mcp-gateway/src/` (verified: Dockerfile `COPY` + Phase 5 FOUND-01 image-hash includes `mcp-gateway/src/`).
2. If UAT runs against a container built from PRE-fix code, the Phase 8 UAT item "Run full Phase 8 test suite inside Kali container" will inherit the same test-pollution failures the dev host sees today — making the recorded transcripts captures of BUGGY behaviour and the audit re-run useless.
3. The 15 UAT items themselves (with the exception of the Phase 13 sandbox check) are mostly about runtime behaviour that is independent of the D-01/D-02 test fixes. So running them against a pre-fix image MAY pass on the runtime-behaviour side but FAIL on the "test suite green in container" side (Phase 8 UAT item #1).

**Recommended wave structure** (planner discretion, but this is the safe ordering):

| Wave | Workstream | Depends on | Parallelizable within wave? |
|------|------------|-----------|---------------------------|
| W1 | Test-suite fixes (D-01, D-02, D-04) + commit | nothing | D-01 and D-02 are in different files; D-04 is a third file. All parallel. |
| W2 | Acceptance gate: `uv run pytest -m 'not slow'` exits 0 (D-03) | W1 | sequential check |
| W3a | REQUIREMENTS.md checkbox flips (D-05, D-06, D-08) | nothing — can run alongside W1 | yes (planning files only) |
| W3b | ROADMAP.md progress table edit (D-09) | nothing | yes |
| W3c | STATE.md body sync (D-10) | nothing | yes |
| W3d | VALIDATION.md frontmatter flips for phases 5, 6, 12 (D-11 partial) | nothing | yes (these 3 have no UAT precondition) |
| W4 | Container rebuild + image SHA capture | W1+W2 (committed) | sequential |
| W5 | 15 UAT items: Phase 7×3, Phase 8×2, Phase 10×4, Phase 11×5, Phase 13×1 (D-12, D-13) | W4 | yes (different phases) BUT a single shared container runs them — coordinate so transcripts are kept distinct |
| W6 | Phase 13 VALIDATION frontmatter flip (D-11 Phase 13 row) + HARDEN-03 REQUIREMENTS checkbox flip (D-05 HARDEN-03) | W5 (specifically the Phase 13 UAT item) | sequential |
| W7 | Re-run `/gsd-audit-milestone v1.1` (D-14) | W2 + W3a-d + W6 | sequential — terminal step |

**Validation strategy section for plan-checker (Nyquist Dimension 8):**
- The "phase requirements" for Phase 14 are zero new REQs. The success oracle is `/gsd-audit-milestone v1.1` returning `passed`.
- Every Phase 14 task SHOULD include a `<verify>` block referencing one of these grep-able artifacts:
  - For test fixes: `cd mcp-gateway && uv run pytest -m 'not slow'` exits 0
  - For checkbox flips: `grep "^- \[x\] \*\*HARDEN-01" .planning/REQUIREMENTS.md` returns 1 line
  - For ROADMAP: `grep "5. F-1 Image-Hash Fix.*Complete.*2026-05-12" .planning/ROADMAP.md`
  - For STATE.md: `grep "current focus.*Phase 14" .planning/STATE.md` (case-insensitive)
  - For VALIDATION.md flips: `grep "nyquist_compliant: true" .planning/phases/05-*/05-VALIDATION.md`
  - For UAT: `grep "## Live UAT Results (Phase 14 closure)" .planning/phases/07-*/07-VERIFICATION.md`
  - For audit: `/gsd-audit-milestone v1.1` returns `status: passed`
- Wave 0 gaps: NONE. The Phase 14 acceptance gate is `pytest -m 'not slow'` which already exists; the audit oracle is the GSD harness command which already exists. No new test framework / fixtures needed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (versions pinned in mcp-gateway/pyproject.toml and uv.lock) |
| Config file | `mcp-gateway/pyproject.toml` (tool.pytest.ini_options section) |
| Quick run command | `cd mcp-gateway && uv run pytest -m 'not slow' -x` |
| Full suite command | `cd mcp-gateway && uv run pytest -m 'not slow'` (D-03 acceptance gate) |

### Phase Requirements → Test Map

**Phase 14 introduces no new REQ-IDs.** Instead, the validation map covers the work items.

| Work item | Behavior | Test type | Automated command | Pre-existing? |
|-----------|----------|-----------|-------------------|---------------|
| D-01 r2_sessions.py fix | `tools/r2_sessions.py` catches SessionCapReached after `importlib.reload(sessions)` | integration (test-order) | `cd mcp-gateway && uv run pytest tests/test_gdb_session.py::test_gdb_env_validates_bad_values tests/test_r2_sessions.py::test_unsafe_shares_combined_cap -q` | ✅ exists |
| D-02 sessions/__init__.py fix | Submodules `r2` + `gdb` reachable as package attributes after pop+re-import | integration | `cd mcp-gateway && uv run pytest tests/test_gdb_session.py::test_gdb_env_validates_bad_values tests/test_sessions_concurrency.py -q` | ✅ exists |
| D-03 acceptance gate | Full non-slow suite green | suite | `cd mcp-gateway && uv run pytest -m 'not slow'` | ✅ exists |
| D-04 ACL test contract | test_setfacl_on_path skips on host, runs in container | unit | `cd mcp-gateway && uv run pytest tests/test_acl_available.py -v` (host: SKIPPED; container: PASSED) | ✅ exists (currently fails on host) |
| D-05/06/07/08 REQUIREMENTS.md flips | grep-verifiable checkbox state | docs | `grep "^- \[x\] \*\*HARDEN-01" .planning/REQUIREMENTS.md` returns 1 | ✅ grep is the test |
| D-09 ROADMAP progress | Phases 5-9 marked Complete with real dates | docs | `awk '/5\. F-1 Image-Hash Fix/{print}' .planning/ROADMAP.md` shows `Complete | 2026-05-12` | ✅ grep is the test |
| D-10 STATE.md body | Body says Phase 14 in progress | docs | `grep -i "phase 14" .planning/STATE.md` returns ≥1 | ✅ grep is the test |
| D-11 VALIDATION flips | Each of 4 files shows `nyquist_compliant: true` | docs | `grep "^nyquist_compliant: true" .planning/phases/{05,06,12,13}-*/{05,06,12,13}-VALIDATION.md` | ✅ grep is the test |
| D-12/13 UAT records | Each affected VERIFICATION.md gets a `## Live UAT Results` section | docs | `grep -c "## Live UAT Results (Phase 14 closure)" .planning/phases/{07,08,10,11,13}-*/*-VERIFICATION.md` returns 5 | ⚙️ Wave 0: ensure section heading is identical across the 5 files |
| D-14 audit oracle | `/gsd-audit-milestone v1.1` returns `status: passed` | GSD command | `gsd-audit-milestone v1.1` (terminal step) | ✅ GSD harness |

### Sampling Rate
- **Per task commit:** `cd mcp-gateway && uv run pytest -m 'not slow' -x` (the acceptance gate, fast on dev host)
- **Per wave merge:** Same command (Phase 14 has no slow tests it newly introduces)
- **Phase gate:** Same command + `/gsd-audit-milestone v1.1` re-run

### Wave 0 Gaps
- None — existing test infrastructure covers all Phase 14 work items. No new test files or framework changes needed. The optional regression test for `importlib.reload` class-identity (Deferred Idea) is OUT OF SCOPE.

## Security Domain

Phase 14 makes no changes to the security boundary. The security-relevant code paths (r2 cfg.sandbox, BoundedSemaphore caps, env-var gating) are touched ONLY by Phase 14's import-resolution fix in `tools/r2_sessions.py`, which is purely syntactic. No `[ASSUMED]` security claims; the existing Phase 13 controls remain in effect.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | (Phase 14 makes no auth changes; existing bearer-token model unchanged) |
| V3 Session Management | no | (Phase 14 surfaces no new session paths; only fixes test-order pollution affecting existing session tests) |
| V4 Access Control | no | (env-gated unsafe-r2 tool unchanged) |
| V5 Input Validation | yes (regression scope only) | check_dangerous_cmd regex is frozen by Phase 13 D-09; Phase 14 does NOT modify it |
| V6 Cryptography | no | No crypto in scope |
| V14 Configuration | yes | VALIDATION.md frontmatter flips are config; D-11 mandates VERIFICATION precondition to prevent false-positive flips |

### Known Threat Patterns for the test-isolation fix

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Test-order side effect silently swallows a security check | Tampering | The D-01/D-02 fixes ARE the mitigation. After fix, every `SessionCapReached` raised by reloaded modules is correctly caught and surfaced as a structured error dict (preserving the contract that tools NEVER raise) |
| Container rebuild without security baseline | Tampering | UAT recipe requires explicit image SHA capture in transcripts (D-13). Operator can audit transcripts to verify the image carried the fix |
| UAT transcript spoofing (recording fake green output) | Tampering | Audit oracle (`/gsd-audit-milestone`) is automated; cannot be spoofed by transcript wording alone — the underlying pytest run + grep checks are mechanical |

## Assumptions Log

All factual claims in this RESEARCH.md were verified against the working tree, except:

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `tests/jobs/conftest.py` does `importlib.reload(jobs)` (Pitfall 1 latent bug) | Pitfall 1 | If wrong: the "latent" risk in tools/jobs.py is even lower (no reload happens today). Either way, Phase 14 does not need to address it — the recommendation is conservative. Verified later by reading `tests/jobs/conftest.py` in the planning phase. |
| A2 | The Phase 8 UAT item "Run full Phase 8 test suite inside the Kali container" will fail if the image carries pre-D-01/D-02 code | Q12 | If wrong: UAT could be parallelized with test fixes. Conservative ordering loses nothing; relaxing requires a real test. |
| A3 | The Phase 13 ROADMAP completion date `2026-05-20` is stale and should be `2026-05-21` (post-hot-fix) | Q3 drift note | If wrong: minor doc inconsistency, no audit impact. |

**No `[ASSUMED]` claims affect locked decisions.** The plan can proceed without further user confirmation.

## Open Questions (RESOLVED)

1. **Should the planner ALSO fix `tools/jobs.py` value-bindings for `JobCapReached` etc.?** RESOLVED: out of scope — Plan 01 does not bundle. Audit gap set is the closure scope; the latent jobs.py pattern is correct-but-fragile, not currently failing. Track as v1.2 hardening idea (already noted in CONTEXT.md `<deferred>`).
2. **Is Docker installed on the executor host that will run Phase 14?** RESOLVED: Plan 04 is `autonomous: false` with `checkpoint:human-action` for the rebuild step, so Docker availability is handled at execute-time via human checkpoint rather than at plan-time via conditional branches.
3. **Is the Phase 13 ROADMAP completion date drift worth fixing in D-09?** RESOLVED: leave alone — D-09 explicitly names phases 5-9 only. Phase 13's 2026-05-20 vs 2026-05-21 single-character drift is not in the audit gap list; out of scope. Re-audit will not flag it.
4. **HARDEN-03 traceability `Verified` flip ordering — pre- or post-UAT?** RESOLVED (SUPERSEDED BY D-05): the user-locked decision D-05 explicitly states "Each gets a checked `[x]` checkbox since `13-VERIFICATION.md` already marks them satisfied at the automated/code level (live HARDEN-03 sandbox check is closed in D-13 below)". This means Wave 1 (Plan 02) flips the box based on automated-level satisfaction; Wave 2 (Plan 04) closes the live arm by appending transcript evidence to `13-VERIFICATION.md` under the new `## Live UAT Results (Phase 14 closure)` section. If the live UAT fails, the unwind path is: revert the HARDEN-03 checkbox in Plan 02's commit + record the failure in `14-VERIFICATION.md`. User accepted this ordering at PRD-express-path lock-in.

## Sources

### Primary (HIGH confidence)
- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` (lines 28-41, 173, 183, 254, 384, 434, 453, 464) — actual file content
- `mcp-gateway/src/mcp_gateway/sessions/__init__.py` (lines 11-72) — actual file content
- `mcp-gateway/src/mcp_gateway/sessions/_base.py` (lines 144-160) — `SessionCapReached` class definition
- `mcp-gateway/src/mcp_gateway/sessions/r2.py` (lines 32, 64-66, 136-312) — driver + spawn-failure release
- `mcp-gateway/tests/test_gdb_session.py:200-214` — the reload pollution trigger
- `mcp-gateway/tests/test_r2_sessions.py:463-545` — `test_unsafe_shares_combined_cap`
- `mcp-gateway/tests/test_sessions_concurrency.py:1-380` — 6 affected tests; all use `monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", ...)`
- `mcp-gateway/tests/test_acl_available.py` — current file (16 lines)
- `.planning/REQUIREMENTS.md` (lines 22, 39-42, 94-102, 145-209) — verified ALREADY contains 9 Phase 13 bodies + traceability rows + 61/61 coverage line
- `.planning/ROADMAP.md` (lines 5-6, 22-33, 178-194, 208-225) — v1.1 phase list + progress table + Phase 14 entry
- `.planning/STATE.md` (lines 1-15 frontmatter, 25-35 body) — drift confirmed
- All 9 phase `*-VERIFICATION.md` files — date and status extraction
- All 9 phase `*-VALIDATION.md` files — current nyquist_compliant state
- `.planning/v1.1-MILESTONE-AUDIT.md` (full file) — the PRD
- `.planning/phases/14-close-v1.1-gaps/14-CONTEXT.md` (full file) — user-locked decisions
- `compose.yaml`, `compose.remote.yaml`, `run_docker.sh`, `Dockerfile` — repo container infrastructure
- `scripts/probe_extraction_tools.sh`, `scripts/probe_dynamic_tools.sh` — probe scripts (canonical paths)
- `.planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/13-0[1-4]-SUMMARY.md` — Plan 13-X requirement mappings

### Secondary (MEDIUM confidence)
- `STATE.md` Accumulated Context section (lines 76-174) — phase-by-phase development notes used to cross-reference dates and patterns.

### Tertiary (LOW confidence)
- None. All claims in this research are backed by file reads of the working tree.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new technology; existing pinned versions
- Architecture patterns (D-01/D-02 fixes): HIGH — patterns verified against the actual buggy code AND the existing correct pattern at line 173/254/384 of the same file
- Pitfalls: HIGH — every listed pitfall references a specific line in the working tree
- UAT recipe: HIGH — verified against compose.yaml, run_docker.sh, probe scripts
- REQUIREMENTS.md state (Q4 — critical finding that bodies already exist): HIGH — direct file read
- Phase completion dates (Q3): HIGH — direct frontmatter extraction
- Q9 requirement body drafts: HIGH — bodies copied verbatim from current REQUIREMENTS.md

**Research date:** 2026-05-21
**Valid until:** 2026-06-21 (Phase 14 is closure work; the codebase rarely changes around closure phases. Valid until the next mcp-gateway src/ edit or `/gsd-audit-milestone` re-run.)
