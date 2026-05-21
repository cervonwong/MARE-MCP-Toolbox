# Phase 14: Close v1.1 Milestone Gaps - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning
**Source:** PRD Express Path (.planning/v1.1-MILESTONE-AUDIT.md)

<domain>
## Phase Boundary

This phase brings v1.1 ("Remote RE Tool Expansion") to archive-ready state. Implementation work for v1.1 is already done across Phases 5–13. Phase 14 closes the **gaps** identified by `/gsd-audit-milestone` (recorded in `.planning/v1.1-MILESTONE-AUDIT.md`):

1. **Test-suite cleanliness** — the full non-slow pytest suite (`cd mcp-gateway && uv run pytest -m 'not slow'`) must exit 0 in a single non-isolated invocation. Currently 8 tests fail due to test-order pollution after `importlib.reload`, plus one host-environmental ACL test.
2. **Planning state sync** — `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, and per-phase `VALIDATION.md` frontmatter must honestly reflect that 9 phases are complete and 9 new Phase 13 requirements exist.
3. **Live container/live-client UAT** — 15 outstanding human-verification items (across Phases 7, 8, 10, 11, 13) must be executed in a rebuilt container and recorded with transcripts in each phase's `VERIFICATION.md`.

**Out of scope:** any new feature work, additional hardening, new phases, or refactoring outside what is required to close audit gaps. **Re-running `/gsd-audit-milestone` and seeing `status: passed` is the success oracle.**

</domain>

<decisions>
## Implementation Decisions

### Test-Order Failures (Phase 13 regression) — LOCKED

- **D-01.** `src/mcp_gateway/tools/r2_sessions.py` MUST catch `SessionCapReached` by **module attribute** (`sessions.SessionCapReached` — or equivalent `mcp_gateway.sessions._base.SessionCapReached` resolved at raise time), NOT a stale imported class. The current `from X import SessionCapReached` binding survives module load but escapes the `except` block after `mcp_gateway.sessions._base` is reloaded, because the raised exception class becomes a new object. The fix MUST survive `importlib.reload` of `mcp_gateway.sessions._base`.
  - **Reproducer that MUST go green after fix:**
    ```
    cd mcp-gateway && uv run pytest \
      tests/test_gdb_session.py::test_gdb_env_validates_bad_values \
      tests/test_r2_sessions.py::test_unsafe_shares_combined_cap -q
    ```

- **D-02.** `src/mcp_gateway/sessions/__init__.py` MUST expose `r2` and `gdb` as **package attributes** that survive the gdb-env reload cleanup path. The 6 `tests/test_sessions_concurrency.py` failures are caused by `monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", ...)` failing after the package was popped/re-imported. Acceptable alternative: change the affected tests to import the submodule directly (`from mcp_gateway.sessions import r2 as r2_mod`) AND document the justification in a code comment. **Preferred:** fix the package so existing tests continue to work — fewer test rewrites, future-proof.
  - **Reproducer that MUST go green after fix:**
    ```
    cd mcp-gateway && uv run pytest \
      tests/test_gdb_session.py::test_gdb_env_validates_bad_values \
      tests/test_sessions_concurrency.py -q
    ```

- **D-03.** Final acceptance gate for test fixes:
    ```
    cd mcp-gateway && uv run pytest -m 'not slow'
    ```
  MUST exit 0 with `0 failed` in a **single non-isolated invocation** (no `--forked`, no per-file invocation chaining).

### Host ACL Test Contract — LOCKED

- **D-04.** `tests/test_acl_available.py::test_setfacl_on_path` MUST have an explicit host/container contract. Choose ONE of:
  - **Option A (preferred):** mark the test container-only via `@pytest.mark.skipif(shutil.which("setfacl") is None, reason="setfacl host-binary missing; container-only contract")`. Add a one-line module docstring explaining the contract.
  - **Option B:** require `setfacl` on the host, document the install command (`sudo apt-get install acl` on Debian/Ubuntu / `brew install acl` if applicable) in the test docstring AND in `README.md` or `CONTRIBUTING.md` under a "Host test prerequisites" heading.
  - **Picked:** Option A — the project's reference run environment is the Kali Linux Docker container; host-bare runs should not fail loudly on environmental ACL absence. Container builds already install `acl` via the Dockerfile.

### REQUIREMENTS.md Sync — LOCKED

- **D-05.** Add Phase 13 requirement **bodies** to `.planning/REQUIREMENTS.md`: `HARDEN-01`, `HARDEN-02`, `HARDEN-03`, `HARDEN-04`, `HARDEN-05`, `HARDEN-06`, `HARDEN-07`, `SESS-CAP-01`, `JOBS-CAP-01`. Copy/refine wording from `ROADMAP.md` Phase 13 section and `13-VERIFICATION.md`. Each gets a checked `[x]` checkbox since `13-VERIFICATION.md` already marks them satisfied at the automated/code level (live HARDEN-03 sandbox check is closed in D-13 below).

- **D-06.** Add 9 corresponding **traceability rows** to the REQUIREMENTS.md traceability table — one per Phase 13 requirement, pointing at the relevant phase plan(s) and `13-VERIFICATION.md`. Mark `Verified` as `[x]` for all 9 after the live HARDEN-03 sandbox check (D-13) is recorded.

- **D-07.** The coverage line in `REQUIREMENTS.md` MUST read **`61/61`** after the additions (52 original + 9 Phase 13).

- **D-08.** Re-check (`[x]`) the stale unchecked items reflecting Phase 7 verification: `SHELL-03`, `ARTIF-01`, `ARTIF-02`, `ARTIF-03`, `ARTIF-04`. Read `07-VERIFICATION.md` to confirm before flipping. Update their traceability `Verified` columns to match.

### ROADMAP.md Progress Sync — LOCKED

- **D-09.** Mark Phases **5, 6, 7, 8, 9** as `Complete` in the v1.1 ROADMAP progress table with their actual completion dates. Pull the actual completion dates from each phase's `*-VERIFICATION.md` frontmatter (or `git log` of the verification commit if frontmatter is missing). Do NOT use `2026-05-21` as a placeholder.

### STATE.md Body Sync — LOCKED

- **D-10.** Update the body text in `.planning/STATE.md` so it matches its frontmatter (which already says 9/9 phases complete pre-Phase-14). Specifically, remove any "Next phase" / "in progress" stale text that disagrees with `phases_complete: 9` in frontmatter.

### VALIDATION.md Frontmatter Sync — LOCKED

- **D-11.** Set `nyquist_compliant: true` in the frontmatter of each of:
  - `.planning/phases/05-*/05-VALIDATION.md`
  - `.planning/phases/06-*/06-VALIDATION.md`
  - `.planning/phases/12-*/12-VALIDATION.md`
  - `.planning/phases/13-*/13-VALIDATION.md`

  **Precondition:** before flipping a flag to `true`, the corresponding `*-VERIFICATION.md` MUST contain a `nyquist_status: compliant` (or equivalent passed verdict). If any of the 4 phase VERIFICATIONs do not confirm compliance, that phase's VALIDATION frontmatter stays `false` and the gap is recorded in `14-VERIFICATION.md` (do NOT force `true`).

### Live Container UAT — LOCKED

- **D-12.** All 15 outstanding human-verification items MUST be executed in a freshly **rebuilt container** (`docker compose build --no-cache && docker compose up -d`, exact recipe to be confirmed against `docker-compose.yml`). Each item gets a timestamp + transcript snippet recorded against its phase's `VERIFICATION.md`. Items by phase:
  - **Phase 7 ×3:** mare-shell UID + ACL revocations; 100 MB run_shell /dev/urandom slow test; MCP Resources visible to a remote MCP client.
  - **Phase 8 ×2:** r2-gated test suite in container; gateway shutdown leaves no zombie r2 processes.
  - **Phase 10 ×4:** remote-client recursive triage (run_binwalk extract → list_extracted_files → promote_extracted_sample); archive-bomb cap aborts mid-extraction; `probe_extraction_tools.sh` READY verdict; three slow extraction integration tests pass.
  - **Phase 11 ×5:** `tools/list` returns 61 under `--remote --dynamic`; `get_dynamic_capabilities` + `run_strace` end-to-end; strace/ltrace/qemu slow JOBS integration tests; gdb MI allowlist runtime enforcement; `probe_dynamic_tools.sh` READY verdict.
  - **Phase 13 ×1:** Live r2 session reports `cfg.sandbox=true` (closes HARDEN-03 live arm).

- **D-13.** Recording format per item: append to the relevant `*-VERIFICATION.md` under a new `## Live UAT Results (Phase 14 closure)` section. Each entry includes: item description, command run, ISO-8601 UTC timestamp, container image SHA or build date, and ≥10 lines of transcript (truncated with `…` only when output exceeds 200 lines).

### Audit Re-run Gate — LOCKED

- **D-14.** The phase is NOT complete until `/gsd-audit-milestone` re-run returns `status: passed` with **no gaps**. This is the success oracle. Re-running is the final task in the phase.

### Claude's Discretion

- Plan wave structure and parallelization across the 5 work-streams (test fixes / REQUIREMENTS.md sync / ROADMAP.md sync / STATE.md sync / VALIDATION.md sync) provided dependencies are honored. Live UAT (D-12/D-13) must follow test fixes (D-01/D-02/D-03) because UAT runs in a rebuilt container whose image MUST include the test fixes — otherwise UAT-recorded behaviour is stale.
- Whether to add new tests guarding against the `importlib.reload` regression — recommended but not strictly required for the audit to pass. If added, place them where they will be picked up by `pytest -m 'not slow'`.
- Exact wording of `REQUIREMENTS.md` Phase 13 entries (must be faithful to ROADMAP + VERIFICATION but copy/edit is at planner discretion).
- Exact section formatting of the appended `## Live UAT Results` blocks in each phase's `VERIFICATION.md`, provided D-13's required fields are present.
- Whether to commit per-fix atomically vs. per-workstream, provided commits are scoped (no mixing of test fix + planning state in the same commit).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit & Milestone Scope
- `.planning/v1.1-MILESTONE-AUDIT.md` — the PRD for this phase. Every gap listed here MUST be addressed.
- `.planning/ROADMAP.md` (lines 33, 208 onward) — Phase 14 entry with the 10 numbered success criteria; v1.1 progress table that needs updating.
- `.planning/REQUIREMENTS.md` — destination for HARDEN-01..07, SESS-CAP-01, JOBS-CAP-01 bodies + traceability; also has the stale SHELL-03 / ARTIF-01..04 checkboxes.
- `.planning/STATE.md` — frontmatter (correct) vs body (stale).

### Test-Order Regression (D-01, D-02)
- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — the file that imports `SessionCapReached` by value; D-01 patch target.
- `mcp-gateway/src/mcp_gateway/sessions/__init__.py` — gdb-env reload cleanup path; D-02 patch target.
- `mcp-gateway/src/mcp_gateway/sessions/_base.py` — defines `SessionCapReached`; the class that gets reloaded.
- `mcp-gateway/tests/test_r2_sessions.py` — contains `test_unsafe_shares_combined_cap` (1 failure under suite order).
- `mcp-gateway/tests/test_sessions_concurrency.py` — 6 failures under suite order.
- `mcp-gateway/tests/test_gdb_session.py::test_gdb_env_validates_bad_values` — the trigger that pollutes state (runs `importlib.reload`).

### Host ACL Contract (D-04)
- `mcp-gateway/tests/test_acl_available.py` — the test to mark container-only.
- `Dockerfile` — installs `acl` package and re-applies ACLs at container start (the contract baseline).

### Phase Verification Source-of-Truth (for completion dates D-09, traceability D-06, sync D-08/D-11)
- `.planning/phases/05-*/05-VERIFICATION.md`
- `.planning/phases/06-*/06-VERIFICATION.md`
- `.planning/phases/07-*/07-VERIFICATION.md` — confirms SHELL-03 + ARTIF-01..04 are satisfied (D-08 source).
- `.planning/phases/08-*/08-VERIFICATION.md`
- `.planning/phases/09-*/09-VERIFICATION.md`
- `.planning/phases/10-*/10-VERIFICATION.md`
- `.planning/phases/11-*/11-VERIFICATION.md`
- `.planning/phases/12-*/12-VERIFICATION.md`
- `.planning/phases/13-*/13-VERIFICATION.md` — source for HARDEN/SESS-CAP/JOBS-CAP bodies (D-05).

### Phase 13 Plan Artifacts (for traceability rows D-06)
- `.planning/phases/13-*/13-01-SUMMARY.md`
- `.planning/phases/13-*/13-02-SUMMARY.md`
- `.planning/phases/13-*/13-03-SUMMARY.md`
- `.planning/phases/13-*/13-04-SUMMARY.md`

### Container UAT Probes (D-12)
- `mcp-gateway/probe_extraction_tools.sh` — Phase 10 probe.
- `mcp-gateway/probe_dynamic_tools.sh` — Phase 11 probe.
- `docker-compose.yml` — rebuild recipe target.

### Project Guidance
- `./CLAUDE.md` (root) — project conventions; especially GSD workflow enforcement section. NB: planning/execution must go through GSD commands per project policy.

</canonical_refs>

<specifics>
## Specific Ideas

### Exact reproducer chains (from D-01, D-02, D-03)
```
# Failure reproducer — must pass post-fix:
cd mcp-gateway && uv run pytest \
  tests/test_gdb_session.py::test_gdb_env_validates_bad_values \
  tests/test_r2_sessions.py::test_unsafe_shares_combined_cap \
  tests/test_sessions_concurrency.py -q

# Final gate — must show 0 failed:
cd mcp-gateway && uv run pytest -m 'not slow'
```

### `r2_sessions.py` fix pattern (D-01)
Replace any `from mcp_gateway.sessions._base import SessionCapReached` value-binding usage in `except`-blocks with module-attribute access:
```python
from mcp_gateway import sessions as _sessions_pkg
# ...
try:
    ...
except _sessions_pkg._base.SessionCapReached as exc:
    ...
```
Or import the module and access at exception-catch time so the class object is resolved freshly on each call (survives `importlib.reload`).

### `sessions/__init__.py` fix pattern (D-02)
After reloads in the cleanup path, re-bind `r2` and `gdb` to the current `sys.modules["mcp_gateway.sessions.r2"]` and `sys.modules["mcp_gateway.sessions.gdb"]`:
```python
import sys, importlib
# after reload:
sys.modules[__name__].r2 = sys.modules["mcp_gateway.sessions.r2"]
sys.modules[__name__].gdb = sys.modules["mcp_gateway.sessions.gdb"]
```
Validate by running the reproducer above.

### REQUIREMENTS.md additions skeleton (D-05, D-06, D-07)
Add a `## Phase 13 Hardening Requirements` (or fold into existing section structure) with bodies and `[x]` checkboxes. Add 9 rows to the traceability table with columns: `ID | Description | Phase | Plan(s) | Verified`. Update the header coverage line from `52/52` to `61/61`.

### Per-phase live-UAT block skeleton (D-13)
```markdown
## Live UAT Results (Phase 14 closure)

### [Item description]
- **Date:** 2026-05-21T14:32:00Z
- **Container build:** mare-toolbox:sha-deadbeef (built 2026-05-21)
- **Command:** `…`
- **Outcome:** passed
- **Transcript (10 lines):**
  ```
  …
  ```
```

### Audit re-run command (D-14)
```
/gsd-audit-milestone v1.1
```
Acceptance: top-of-output `status: passed`, `gaps: []` block empty.

</specifics>

<deferred>
## Deferred Ideas

- **New regression tests for the `importlib.reload` class-identity pitfall** — recommended but not blocking. May be deferred to v1.2 unless the planner judges it cheap enough to bundle.
- **Refactoring `mcp_gateway.sessions` package layout** beyond the minimal D-02 fix — explicitly out of scope; v1.1 archive gate is the priority.
- **Adding new HARDEN requirements** — none. Only the 9 from Phase 13 (HARDEN-01..07, SESS-CAP-01, JOBS-CAP-01) are in scope.
- **Re-running `/gsd-secure-phase` for any phase** — not required by the audit.
- **CI workflow updates** to enforce host-vs-container test contract — defer; D-04 is the in-scope contract decision (test-side skipif).

</deferred>

---

*Phase: 14-close-v1-1-gaps*
*Context gathered: 2026-05-21 via PRD Express Path (.planning/v1.1-MILESTONE-AUDIT.md)*
