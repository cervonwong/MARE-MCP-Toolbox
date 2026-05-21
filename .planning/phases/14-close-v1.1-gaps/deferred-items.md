# Phase 14 — Deferred Items

Out-of-scope discoveries logged during plan execution. Each entry should record the discovering plan, the issue, and the suggested follow-up.

## From Plan 14-02

### 47 already-satisfied v1.1 traceability rows still marked "Pending"

- **Discovered during:** Plan 14-02, Task 3 (final cross-file consistency check)
- **What:** REQUIREMENTS.md traceability table still shows 47 rows with `TBD | Pending` for requirements whose body checkboxes are `[x]` and whose phase VERIFICATION.md marks them satisfied. Affected ID families: FOUND-01..04, SHELL-01/02, STATIC-01..10, ARTIF-05, SESS-01..06, JOBS-01..07, EXTR-01..06, DYN-01..07, SKILL-01..04.
- **Why deferred:** Out of scope for Plan 14-02. The plan's narrative bounds the diff to 14 rows / ≤50 changed lines; flipping 47 more rows would be a much larger, separate sweep. Task 3 acceptance criterion 4 (Pending count == 0) is internally inconsistent with that scope bound.
- **Severity:** medium — `/gsd-audit-milestone v1.1` (planned in Plan 14-05) may flag these as a traceability gap and demand a follow-up sweep before milestone close.
- **Suggested follow-up:** Either (a) add a dedicated wave-1 sister plan to 14-02 that performs the 47-row sweep, or (b) handle inline during Plan 14-05 audit-re-run if the auditor reports them. Source-of-truth for each row's Plan and Verified columns is the corresponding phase's `*-VERIFICATION.md` file.
- **Status:** open.
