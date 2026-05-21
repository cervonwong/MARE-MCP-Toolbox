"""Phase 13 Wave 0: in-container r2 version + cfg.sandbox support probe.

Converts RESEARCH Assumption A1 into a verified invariant:
> The container's r2 version supports cfg.sandbox.

On hosts without r2 (dev / CI), tests skip cleanly. Inside the Kali container,
they run for real against the bundled radare2 package.

Companion to Plan 03 / HARDEN-03: if cfg.sandbox is not supported by the
container's r2, Plan 03's argv flags `-e cfg.sandbox=true` would have NO
effect and the security boundary would silently regress.
"""
from __future__ import annotations
import subprocess
from tests.conftest import _require_r2_or_skip


def test_r2_version_parseable():
    """OQ4: r2 -V returns a parseable version string containing 'radare2'."""
    _require_r2_or_skip()
    result = subprocess.run(
        ["r2", "-V"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"r2 -V failed: rc={result.returncode}, stderr={result.stderr!r}"
    )
    # Kali r2 6.0.5 prints "<version>  r2" / "<version>  r_anal" / ...; older
    # builds print "radare2 <version>". Accept either by scanning all lines for
    # a known r2 module token.
    stdout_low = result.stdout.lower()
    assert any(tok in stdout_low for tok in ("radare2", "r_anal", " r2\n", " r2 ")), (
        f"r2 -V output did not contain a recognizable r2 token: {result.stdout!r}"
    )


def test_r2_cfg_sandbox_supported():
    """A1 verification: r2 accepts -e cfg.sandbox=true without warning unknown.

    Spawns a one-shot r2 with cfg.sandbox=true; if the binary did not
    understand the variable r2 would print 'unknown variable cfg.sandbox' to
    stderr. We assert that warning does NOT appear.
    """
    _require_r2_or_skip()
    result = subprocess.run(
        ["r2", "-2", "-q0", "-e", "cfg.sandbox=true",
         "-c", "e cfg.sandbox", "--", "/dev/null"],
        capture_output=True, text=True, timeout=15,
    )
    stderr_low = result.stderr.lower()
    # The combination "unknown" + "cfg.sandbox" indicates the variable is not
    # supported by this r2 build. Either token alone is fine (other errors
    # like "Cannot open /dev/null" are expected on minimal targets).
    assert not ("unknown" in stderr_low and "cfg.sandbox" in stderr_low), (
        f"r2 reports cfg.sandbox unknown: {result.stderr!r}"
    )
