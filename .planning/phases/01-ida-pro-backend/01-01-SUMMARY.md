---
phase: 01-ida-pro-backend
plan: 01
subsystem: infra
tags: [ida-pro, docker, multi-stage-build, idalib, ida-pro-mcp]

# Dependency graph
requires: []
provides:
  - IDA Pro conditional Docker install via multi-stage build
  - ida-pro-mcp (mrexodia) installed from GitHub in container
  - idapro idalib Python package activation
  - IDA Pro zip detection and build context in run_docker.sh
  - IDA license persistence via host bind mount (~/.idapro-docker/)
  - License seeding for ida.key and ida.hexlic
  - Updated Ghidra condition (only installs when no commercial disassembler enabled)
affects: [01-02, configure-agent-mcp, remote-mcp-gateway]

# Tech tracking
tech-stack:
  added: [ida-pro-mcp (mrexodia), idapro (bundled idalib)]
  patterns: [multi-stage Docker build for license security, conditional install via build args, named build context for large archives]

key-files:
  created: []
  modified: [Dockerfile, run_docker.sh, compose.yaml]

key-decisions:
  - "Used ida-pro-mcp from mrexodia GitHub (not ida-mcp from PyPI) per CONTEXT.md locked decision"
  - "Install idapro from IDA bundled idalib/python directory, not from PyPI"
  - "Support both .run installer and pre-installed directory in IDA zip"
  - "Seed both ida.key and ida.hexlic license formats"
  - "Added .idapro directory to agent user home for container-side persistence"

patterns-established:
  - "IDA Pro provisioning mirrors Binary Ninja pattern exactly (zip detection, named build context, license seeding)"
  - "Multi-stage ida-builder stage creates empty /opt/ida-pro when disabled so COPY --from never fails"
  - "Combined cleanup_stages function handles both binja and ida temp dirs"

requirements-completed: [IDA-01, IDA-02, IDA-03, IDA-05, IDA-06, INF-03, INF-04]

# Metrics
duration: 3min
completed: 2026-04-14
---

# Phase 1 Plan 01: IDA Pro Docker Install Summary

**IDA Pro multi-stage Docker build with conditional install, ida-pro-mcp from mrexodia, idalib activation, and run_docker.sh provisioning mirroring the Binary Ninja pattern**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-14T05:23:06Z
- **Completed:** 2026-04-14T05:26:17Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- IDA Pro installs conditionally via multi-stage Docker build that never leaks license artifacts into final image layers
- run_docker.sh detects idapro.zip, creates ida-stage build context, seeds IDA licenses, and includes IDA in checksum calculation
- compose.yaml mounts IDA user directory and passes IDADIR env var into container
- Ghidra now only installs when neither Binary Ninja nor IDA Pro is enabled

## Task Commits

Each task was committed atomically:

1. **Task 1: Add IDA Pro multi-stage build and conditional install to Dockerfile** - `30e243d` (feat)
2. **Task 2: Update run_docker.sh with IDA zip detection, license seeding, and build context** - `9159564` (feat)

## Files Created/Modified
- `Dockerfile` - Added ida-builder multi-stage build, INSTALL_IDA_PRO arg, IDADIR env, idapro/idalib setup, ida-pro-mcp install, updated Ghidra condition, Python version check, .idapro agent dir
- `run_docker.sh` - Added IDA zip detection, IDA_USER_DIR persistence, ida.key/ida.hexlic license seeding, IDA checksum inclusion, IDA_STAGE_DIR temp dir, ida-stage build context, IDA build args, IDA_USER_DIR compose env passthrough
- `compose.yaml` - Added IDA user directory volume mount and IDADIR environment variable

## Decisions Made
- Used ida-pro-mcp from mrexodia's GitHub repo (installed via pip from archive URL) instead of ida-mcp from PyPI, per CONTEXT.md locked decision that explicitly states "Do NOT use ida-mcp from PyPI (wrong package -- that's jtsylve's version)"
- Install idapro Python package from IDA's bundled idalib/python directory rather than PyPI, per CONTEXT.md
- Added .idapro directory creation in agent user setup (Rule 2 - ensures bind mount target exists)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Used ida-pro-mcp instead of ida-mcp**
- **Found during:** Task 1 (Dockerfile IDA Pro install)
- **Issue:** Plan action says `pip install ida-mcp` but CONTEXT.md explicitly states to use mrexodia/ida-pro-mcp and "Do NOT use ida-mcp from PyPI"
- **Fix:** Installed from `https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip` instead
- **Files modified:** Dockerfile
- **Verification:** grep confirms correct install URL
- **Committed in:** 30e243d (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added .idapro directory for agent user**
- **Found during:** Task 1 (Dockerfile agent user setup)
- **Issue:** The bind mount target /home/agent/.idapro needs to exist in the image
- **Fix:** Added .idapro to the mkdir and chown commands for agent user home directories
- **Files modified:** Dockerfile
- **Verification:** Directory creation visible in Dockerfile
- **Committed in:** 30e243d (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 missing critical)
**Impact on plan:** Both fixes essential for correctness. The ida-pro-mcp switch follows locked CONTEXT.md decisions. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- IDA Pro Docker infrastructure is in place, ready for Plan 02 (configure-agent-mcp.sh backend detection and MCP config)
- The ida-pro-mcp package provides the `idalib-mcp` command for headless SSE server mode
- License persistence and seeding infrastructure matches Binary Ninja pattern

## Self-Check: PASSED

All files verified present. All commit hashes verified in git log.

---
*Phase: 01-ida-pro-backend*
*Completed: 2026-04-14*
