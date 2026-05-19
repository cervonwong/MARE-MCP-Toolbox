#!/usr/bin/env bash
# Phase 10 Wave 0 probe -- resolves Assumptions A1/A2/A3 from 10-RESEARCH.md.
# Run INSIDE the container after `./run_docker.sh` rebuild:
#   docker exec -it <container> bash /agent/scripts/probe_extraction_tools.sh
set -u
echo "=== binwalk ==="
command -v binwalk && binwalk --version 2>&1 | head -3
echo
echo "=== binwalk --help (look for -d/--depth -- A2: should be ABSENT in binwalk3) ==="
binwalk --help 2>&1 | grep -E -- '(--depth|^[[:space:]]*-d,)' || echo "(no --depth flag found -- confirms binwalk3)"
echo
echo "=== unblob ==="
command -v unblob && unblob --version 2>&1 | head -3
echo
echo "=== upx-ucl / upx ==="
command -v upx && upx --version 2>&1 | head -3
echo
echo "=== apt policy binwalk3 (A1 confirmation) ==="
apt-cache policy binwalk3 2>&1 | head -5
