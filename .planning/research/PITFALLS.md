# Pitfalls Research — v1.1 Remote RE Tool Expansion

**Domain:** Containerized FastMCP gateway adding `run_shell` + typed RE wrappers + session-scoped r2/gdb + dynamic-mode (strace/ltrace/qemu-user/gdb) + background job system
**Researched:** 2026-05-12
**Confidence:** HIGH (existing gateway code reviewed directly; pitfalls grounded in current `subprocess_runner.py` / `app.py` / `uploads.py` patterns + verified MCP/asyncio docs)

**Phase shorthand used below** (mirrors `.planning/PROJECT.md` v1.1 target features):
- **F-1**: `run_docker.sh` content-hash extension to `mcp-gateway/` (lands first)
- **Runner**: Internal `ReToolRunner` (argv-only subprocess primitive + capture + cap + pgroup cleanup)
- **Shell**: `run_shell` tool
- **Typed**: Typed static wrappers (`run_binwalk`, `run_capstone_disasm`, …)
- **R2**: Session-scoped `open_r2_session` / `r2_cmd` / `close_r2_session`
- **Extract**: Extraction tier (`run_unblob`, `binwalk -e`, UPX, `extract_embedded_files`, `promote_extracted_sample`)
- **Dynamic**: Dynamic Lab Mode (strace/ltrace/qemu-user + gdb session)
- **Jobs**: Background job system (`start_tool_job` / `get_tool_job` / `cancel_tool_job`)
- **Artifacts**: Artifact / control helpers (`write_artifact`, `get_tool_log`, …)
- **Skill**: Orchestrator skill update

---

## Critical Pitfalls

### Pitfall 1: stdout/stderr PIPE deadlock on large subprocess output

**What goes wrong:**
The current `subprocess_runner.run_script` uses `asyncio.create_subprocess_exec(... stdout=PIPE, stderr=PIPE)` + `proc.communicate()` with a 600 s timeout. That works for the 10 atomic scripts (small JSON/markdown output). The v1.1 surface explodes the output domain — `strings`, `xxd`, `objdump -d`, `capa`, `strace`, `qemu-user -d in_asm,exec` can each emit hundreds of MB to GB of stdout. If the runner naively keeps using `communicate()` without a write-side cap, the OS pipe buffer (~64 KB on Linux) fills, the child blocks on `write()`, but the reader is reading the *whole* output into memory before returning. Result: gateway OOM, or for "small" outputs the gateway returns a 200 MB JSON blob over MCP and blows out the 25k-token MCP result cap.

**Why it happens:**
- The existing pattern works for small bounded outputs and gets cargo-culted to large ones.
- Devs reach for `communicate()` because the docs say "use this to avoid deadlocks" — true for *correctness* (concurrent stdout/stderr drain), but it buffers everything in memory. The deadlock-safe alternative for capped output is concurrent draining of two `StreamReader`s with a running byte counter.
- MCP tool results have an effective ~25k-token client-side cap; a 5 MB string is already over budget even if the gateway survives.

**How to avoid:**
- `ReToolRunner` MUST stream stdout/stderr through `anyio.create_task_group()` (or `asyncio.gather`) reading both pipes concurrently. Maintain a running byte counter; on first `> max_inline_bytes` (suggest 256 KB stdout / 64 KB stderr default), STOP appending to the in-memory buffer but KEEP draining the pipes (otherwise the child still deadlocks). Drained-but-discarded bytes still go to `tool-logs/<ts>-<slug>.txt` via an `aiofiles` writer.
- Return shape: `{exit_code, stdout_head, stdout_truncated: bool, stdout_bytes_total, stderr_head, stderr_truncated, log_path}`.
- Never return raw `stdout` as a `bytes`-derived field from MCP; always UTF-8-decode with `errors="replace"` only over the head slice. Truncate on a UTF-8 character boundary (not mid-codepoint) — slice on the buffer, then `b.decode("utf-8", errors="replace")` is safe enough; document this.
- For binary tools (`xxd` raw, `objdump --no-show-raw-insn` disabled, etc.), redirect stdout straight to a file (not PIPE) and return only the path — no need to drain into the gateway at all.

**Warning signs:**
- Unit test with a 100 MB-of-`/dev/urandom` stdout that asserts the runner completes in bounded time and bounded RSS.
- A wrapper that hands `stdout=PIPE` and `communicate()` to a known-large tool (objdump full disasm).
- `tool-logs/` files smaller than `stdout_bytes_total` minus the head — means pipe drain is dropping bytes silently.

**Phase to address:** **Runner** (foundation — every other phase calls it). Tests must assert OOM-safety before any wrapper merges.

---

### Pitfall 2: `run_shell` cwd-escape via the agent's own `cd`/`pushd`/relative-path

**What goes wrong:**
Naive implementation: `run_shell("strings ../uploads/abc/foo | head")` runs `bash -c <cmd>` with `cwd=case_dir`. The shell is happy to `cd ..`, follow `../../../etc/`, or accept absolute paths and write to `/root`. The "case-dir confinement" claim in `.planning/PROJECT.md` becomes a comforting fiction — confinement was only on the *initial* working directory, not on what the shell can reach.

**Why it happens:**
- `cwd=` is *where the process starts*, not a sandbox boundary.
- Bash one-liners are user-authored; the agent can (intentionally or accidentally) emit `cd /tmp && …`, `find / -name secret`, etc.
- The current threat model (T-02-PATHTRAVERSAL) only addresses *parameter* path traversal in tool args — `run_shell` shifts the surface from "argv validation" to "the entire shell language".

**How to avoid:**
- `run_shell` is an **agent-trust** tool, not an isolation tool. Document that explicitly. Confinement is achieved by *posture*, not by parsing bash.
- Concrete posture steps:
  1. **Drop root inside the shell.** Run `bash -c` as a dedicated `mare-shell` UID (created at image build) with primary group ACL on `case_dir` and `/agent/uploads/` (RO). Read-only bind mount of `/agent/scripts/`, `/agent/mcp/`, the disassembler installs. `/etc`, `/root`, `/agent/.mcp-gateway-token` not group-readable.
  2. **Mount-namespace per shell call** (preferred, see Pitfall 14) — `unshare --mount` + `mount --bind case_dir /work` + `chdir /work` + RO remount of `/agent` except `/agent/uploads` and `case_dir`.
  3. Even without (2), **canonicalize `case_dir` once via `os.path.realpath` and reject if not under `STATUS_ROOT`** (already done by `case_dirs.resolve_case_dir`).
  4. Forbid `MCP_GATEWAY_TOKEN`/`MCP_GATEWAY_TOKEN_FILE`/`AWS_*`/`*_API_KEY` from the inherited env passed to the shell (whitelist env, don't blacklist).
  5. Auto-capture exits the conversation about "did the agent escape": every call writes `tool-logs/<ts>-<slug>.txt` and the agent must reason from that artifact.
- Document in `run_shell` docstring: "This is not a sandbox. Confinement = mare-shell UID + case_dir bind mount + env scrub + timeout + output cap + auto-capture. A determined attacker controlling the agent CAN read the container's user-readable filesystem. Do not bind the gateway to public networks."

**Warning signs:**
- A `run_shell("pwd; ls /root; cat /agent/.mcp-gateway-token")` test that does NOT return the token but does return `case_dir` for pwd.
- Process accounting (`/proc/<pid>/status` `Uid:` field) shows the shell running as `root`/`agent` instead of `mare-shell`.
- `case_dir` resolved path differs from input — log the canonicalization.

**Phase to address:** **Shell** (primary), with the `mare-shell` UID landing in the Dockerfile as part of the **F-1** rebuild trigger plan so the rebuild proves the new user image works.

---

### Pitfall 3: `run_shell` output bombs + ANSI escapes + slow-loris hang

**What goes wrong:**
Three sub-pitfalls that compound:
1. **Output bomb:** `run_shell("yes | head -c 50G")` — caught by the runner's cap (Pitfall 1) IF the cap is applied; if not, OOM.
2. **ANSI escapes saved to artifacts:** `run_shell("ls --color=always")` writes ESC-sequences into `tool-logs/<ts>-<slug>.txt`. When the agent reads the artifact, it sees garbled hex bytes. When a human cats it, the terminal interprets the escape — including malicious ones (e.g., a sample's filename that contains `\e]0;owned\a`).
3. **Slow loris:** `run_shell("sleep 1; while true; do echo .; sleep 1; done")` keeps producing output below the rate that triggers the byte cap but past the timeout. Less obviously: `run_shell("python3 -c 'import time; time.sleep(599)'")` produces no output and exits a millisecond before the timeout — totally legal, just useless.

**Why it happens:**
- Easy to add a byte cap, easy to add a timeout, easy to forget that they interact (the timeout must include "stuck draining" time).
- ANSI scrubbing is a known-unknown; tools defensively emit color even when not on a TTY (some use `--color=auto` which detects PTY, but `LESS=R` and other env can re-enable).
- `bash -c` inherits TTY-detection from the parent; running with no PTY usually disables color, but tool authors increasingly use `FORCE_COLOR=1`-style env.

**How to avoid:**
- Strip ANSI before write: a single regex pass `re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")` over each pipe chunk before append (or use a small library; do not rely on tool flags).
- Set `TERM=dumb`, `NO_COLOR=1`, `COLUMNS=120`, unset `FORCE_COLOR`/`CLICOLOR_FORCE` in the env handed to bash. Belt + suspenders.
- Timeout is **wallclock to-completion**, not idle. Drain task group has a hard `move_on_after(timeout)` and cleanup (Pitfall 4) runs unconditionally.
- Add an idle-output watchdog only as a separate optional flag (`idle_timeout: float | None = None`) — don't make it the default, some legitimate tools (Ghidra import) are silent for minutes.

**Warning signs:**
- `tool-logs/*.txt` contain `\x1b[` byte sequences when read raw.
- A test running `run_shell("printf '\\x1b[31mhi\\x1b[0m'")` does not produce the escape bytes in the captured log.
- A test with a `sleep 700; echo hi` command does not return within `timeout + cleanup_grace` seconds.

**Phase to address:** **Runner** (ANSI strip, env scrub, hard timeout) + **Shell** (regression tests).

---

### Pitfall 4: Process-group cleanup leaks grandchildren / signal-handler escape

**What goes wrong:**
The existing `subprocess_runner` correctly does `start_new_session=True` + `os.killpg(proc.pid, SIGKILL)` on timeout. v1.1 adds:
- Long-running pipelines (`run_shell("strings huge.bin | grep -i password | sort -u | head")` — 4 processes in the pgroup).
- Samples that **fork/exec** under strace/ltrace (the sample is itself a process tree; strace's `-f` follows but if a child `setsid()`'s itself out, it leaves the pgroup).
- Samples that **mask SIGTERM** (typical malware behavior). `SIGKILL` cannot be masked, but the existing code goes straight to SIGKILL on timeout — good. Less-good: developers will be tempted to "be nice" and try SIGTERM first.
- Background jobs whose `asyncio.Task` is cancelled while the pgroup is mid-spawn (race: pgroup not yet established when cancel arrives).

**Why it happens:**
- Linux pgroups are per-process; `setsid()` creates a new session, escaping the pgroup. The kernel does not track "grandchildren of pgroup leader" once they `setsid`.
- `asyncio` cancellation cancels the Python task, not the child process. The subprocess survives until something kills it.

**How to avoid:**
- Keep `start_new_session=True` + `killpg(SIGKILL)` as the **only** termination path on timeout/cancel. Do NOT add a "polite SIGTERM first" mode for samples (legitimate tools that need graceful shutdown can ignore signals from killpg too, but RE samples don't deserve grace).
- Wrap the kill in `try/except ProcessLookupError` (already done) AND `try/except PermissionError` (uncommon but possible if uid changed mid-flight via setuid binary).
- For `-f`-following dynamic tools (`strace -f`, `ltrace -f`, `gdb` with `set follow-fork-mode child`), **also** kill the *strace pid's own pgroup* and, as belt-and-suspenders, scan `/proc/<runner_pid>/task/*/children` for grandchildren that escaped via `setsid` and SIGKILL them too. Build this into `ReToolRunner._cleanup()`.
- On `asyncio.CancelledError`, the cleanup path MUST run with a shielded `await proc.wait()` in `finally` — otherwise the gateway returns to the caller while the subprocess is still alive, and the next `init_case` for the same sample races with a half-dead grandchild holding the case-dir open.
- Background jobs (Jobs phase): store `pgid = os.getpgid(proc.pid)` in the Job record at spawn time, not derived from `proc.pid` later (the proc may already be dead and pid reused).

**Warning signs:**
- After a cancelled job, `ps -ef` inside the container shows orphan `<defunct>` or live grandchildren parented to PID 1.
- `pgrep -g <pgid>` after cleanup returns rows.
- Container shutdown takes > 10 s because PID 1 is reaping zombies.

**Phase to address:** **Runner** (base implementation) + **Dynamic** (strace `-f` follow-fork tests) + **Jobs** (cancellation race tests).

---

### Pitfall 5: Session-scoped r2/gdb — idle session leaks, zombie subprocesses, no reaping

**What goes wrong:**
`open_r2_session(sample)` spawns `r2 -q0` (or similar) as a long-lived subprocess, stuffs it into a `dict[session_id, Proc]`. The agent crashes / disconnects / forgets the `session_id`. The r2 process sits at the r2 prompt forever holding the sample mmap'd. Over a multi-hour analyst session: 50 stale r2's, multi-GB resident, FDs exhausted.

Worse: `gdb` opened on a sample run with `target exec` — gdb has the target child as well, so each leaked gdb is 2 processes. Worse still: gdb dropping into an interactive prompt waiting on `(gdb) ` and the dev's `gdb_exec` doing a `proc.stdin.write(b"info reg\n")` — but gdb pages output through `less` by default for long lists, deadlocking on the pager.

**Why it happens:**
- Single-session module state (`session_state.py`) was fine for v1.0 (one client, no per-tool sessions). v1.1 adds multi-instance sessions inside that single client session — no reaper.
- r2 and gdb both have pager-on-by-default for long output (`SCR_INTERACTIVE`/`set pagination on`).
- gdb's prompt is " (gdb) "; r2's is "[0x...]>". Neither emits a clear "end of output" marker — naive `readuntil(prompt)` works until a tool inside (e.g., `r2.cmd("aaaa")`) prints a line that contains the prompt-like string.

**How to avoid:**
- Session registry: `dict[str, Session]` with `created_at`, `last_used_at`, `pgid`, `case_dir`, `sample_path`. A background `asyncio.create_task(reaper())` runs every 60 s, kills sessions idle > `MCP_GATEWAY_SESSION_IDLE_S` (default 1800 s = 30 min), bounded by `MCP_GATEWAY_MAX_SESSIONS` (default 8) — refuse `open_*_session` when at cap, return `{error: "session cap reached", existing: [...]}`.
- session_id = `secrets.token_urlsafe(12)` (not user-chosen) to avoid collisions across MCP clients.
- For r2: launch with `-2` (silent), `-q0` (no init), and at session start `proc.stdin.write(b"e scr.interactive=false\ne scr.color=0\ne scr.html=0\n")`. Use r2's `\n\n` synchronous-output trick or the JSON output mode (`r2.cmd("?j")`) and parse JSON, sidestepping prompt-detection entirely. Better still: use r2's R2Pipe or local pipe protocol if available.
- For gdb: `--batch-silent` for one-shot calls; for sessions, use `gdb-mi` (machine interface) — emits `(gdb) ` followed by `^done`/`^error`/`*stopped` records with explicit end markers. Set `set pagination off`, `set confirm off`, `set print pretty off` at session open. Never let gdb's CLI mode through to MCP — too prompt-ambiguous.
- Track FDs: `len(os.listdir(f"/proc/{proc.pid}/fd"))` reported in `list_sessions()` so leaks are visible.
- On gateway shutdown (lifespan exit), iterate registry and `killpg(SIGKILL)` every session. Match the existing `app.py` lifespan pattern.

**Warning signs:**
- `list_sessions()` shows entries with `last_used_at` > 30 min ago — reaper isn't running.
- `ls /proc/<gateway_pid>/fd | wc -l` climbs across a soak test.
- Tests with two `open_r2_session()` calls in a row do NOT show different `session_id`s — registry collision or stale-reuse bug.
- A `gdb_exec("info threads")` on a multithreaded sample times out — pager is on.

**Phase to address:** **R2** (registry, reaper, pager-off, session-id collision tests), **Dynamic** for gdb (MI mode), plus a shared `sessions.py` module that both reuse.

---

### Pitfall 6: r2/gdb interactive prompts blocking on stdin

**What goes wrong:**
Some r2 commands (e.g., `Vp` visual mode, `?I` interactive input) and gdb commands (`run`, `attach` with a not-permitted target, `quit` when a process is running) print a prompt and wait for `y/n`. The session reader's `readuntil(b"]> ")` never returns because the prompt is `Quit anyway? (y or n) `. Gateway hangs that session forever (until reaper, Pitfall 5, kicks in).

**Why it happens:**
- Devs test with safe commands (`afl`, `pdf`); confirmation prompts surface only on edge cases.
- gdb's `set confirm off` covers most but not all (target exec prompts, signal prompts).

**How to avoid:**
- r2 session init: `e cfg.user=mare`, `e scr.interactive=false`. Also: do NOT expose `Vp` / `?I` / `!` / `#!` (shell shellout) via `r2_cmd` — allowlist the *categories* of commands at the wrapper level. Or, simpler: prepend every command with `e scr.interactive=false;` (idempotent, cheap).
- gdb session init: `set confirm off`, `set pagination off`, `set print pretty off`, `set verbose off`, `set debuginfod enabled off`, `set auto-solib-add off` (avoid net or libstdc++ download stalls).
- Per-command wallclock timeout INSIDE the session (not just the open-session lifetime). `r2_cmd(cmd, timeout=30.0)` — if the read doesn't see a prompt-end within timeout, kill the whole session (the r2 state is unrecoverable) and return `{error: "session killed: command timed out", session_invalidated: true}`.
- Sentinel-marker pattern: after each command, send `?e __MARE_END__\n` (r2) or `printf "__MARE_END__\\n"` (gdb), read until that sentinel. Sidesteps prompt-parsing entirely.

**Warning signs:**
- A test calling `r2_cmd(session_id, "?I prompt")` does NOT return within 5 s and DOES result in `session_invalidated: true`.
- The gateway log shows session-reaper waking up to kill a session that's only 90 s old — means a command hung.

**Phase to address:** **R2** + **Dynamic** (gdb).

---

### Pitfall 7: Symlinks / archive bombs / extracted files escaping `case_dir`

**What goes wrong:**
`run_unblob` and `binwalk -e` on a malicious sample extract:
- A tar member with absolute path `/etc/passwd` (slipstream, mitigated by modern tar but not all callers).
- A zip slip: `../../../../../tmp/owned`.
- A 100 MB file that decompresses to 100 GB (zip bomb).
- A symlink `extracted/foo -> /agent/.mcp-gateway-token`. `get_artifact(case_dir, "foo")` then `realpath`'s through it. Current `artifacts.get_artifact` uses `os.path.realpath` + `startswith(real_case + os.sep)` — good — but the **artifact tools added in v1.1** (`list_artifacts`, `get_artifact_tree`, `write_artifact`, `append_artifact`, `get_tool_log`) must replicate that pattern with no slip.
- `promote_extracted_sample` copying a 50 GB extracted file into `/agent/uploads/<new_sha>/` — fills the disk.

**Why it happens:**
- Decompression tools defer path-safety to the caller (unblob is good about it, but binwalk's `-e` historically had absolute-path bugs).
- Devs replicate the safe-path helper inline 12 times across 12 tools, miss it in one.
- Compressed archives have lying metadata about their uncompressed size.

**How to avoid:**
- One canonical helper: `confine_to(case_dir: Path, candidate: Path) -> Path` raising `ValueError` on escape. **Every** new path-accepting tool calls it. Add a `test_path_confinement_helper.py` that fuzzes with symlinks, traversal, NUL bytes, control chars (reuse `uploads._is_invalid_filename` predicate where applicable).
- Extraction runs **inside** `case_dir/extracted/<tool>-<ts>/`, never `/tmp`. After extraction, walk the tree with `Path.rglob`, refuse to `list_extracted_files` any path whose `realpath` is outside the extraction dir. Quarantine these as `.unsafe-symlink` filenames.
- Pre-decompress size check: for known formats (zip, tar.gz) read the central directory / header and refuse extraction if declared-uncompressed > `MCP_GATEWAY_MAX_EXTRACT_MB` (default 4 GB). For unknown / stream formats, monitor extraction-output dir size every 5 s during extraction, kill the pgroup on overshoot.
- `promote_extracted_sample` recomputes sha256 from the bytes (don't trust filename), enforces the same `_max_bytes()` cap as `/upload`, copies to `/agent/uploads/<sha>/` atomically via tempfile+rename. Disk-space check (`shutil.disk_usage`) before copy.
- Symlinks in extraction output: replace with `.symlink-target.txt` files containing the target string (preserved for analysis, not followed).

**Warning signs:**
- `find <case_dir>/extracted -type l` returns symlinks after a `binwalk -e` call.
- Test extraction of a crafted zip with `../foo` in it does NOT escape but DOES leave a `.unsafe-symlink-foo` quarantine marker.
- `df` inside the container drops by GBs after a single `run_unblob`.
- `list_artifacts(case_dir)` returns a path containing `..` or starting with `/`.

**Phase to address:** **Extract** (primary), **Artifacts** (path-helper replication).

---

### Pitfall 8: Background jobs orphaned by gateway restart / log artifact growth

**What goes wrong:**
`start_tool_job(argv=...)` launches a subprocess and stores a Job record. The gateway is restarted (image rebuild, F-1 trigger, container redeploy). On startup:
- The old subprocess is killed by docker (good), OR
- The subprocess was double-fork-daemonized (some tools do this) and survives, but the gateway has no Job record for it — orphan with no way to query/cancel through MCP.
- The `jobs.json` registry on disk still references the dead pid. Next start, `get_tool_job(old_id)` returns "running" status when the pid is recycled and now points to an unrelated process.
- The job log file (`tool-logs/jobs/<job_id>.log`) was being streamed by an `asyncio.Task` that's gone — the log is half-written, no terminating record.
- Logs grow without bound: a `start_tool_job(["yes"])` runs forever, log file fills disk.

**Why it happens:**
- Persisting jobs to disk seems prudent for "let an analyst come back tomorrow"; the resurrection logic is harder than it looks.
- Pids are reused by the kernel. A pid stored Tuesday means nothing Wednesday.
- "Streaming the log" is usually a one-shot pipe-drain; if the gateway dies, the drain task dies, the pipe goes to PID 1.

**How to avoid:**
- **Default scope: in-memory only.** `Jobs` registry is a `dict[str, Job]` in process memory. On gateway exit, kill all jobs (lifespan teardown). Document: "Restart cancels in-flight jobs by design."
- If persistence is needed later, use a **pid+start-time tuple** as identity (`/proc/<pid>/stat` field 22 boot-relative-jiffies) — survives pid reuse. Don't ship this in v1.1.
- Job log files: every job has a `tool-logs/jobs/<job_id>.log` with a hard size cap (`MCP_GATEWAY_MAX_JOB_LOG_MB` default 256 MB). On cap, kill the job, append `[truncated: log exceeded N MB]\n` and mark `status="killed_log_cap"`. Same UTF-8-safe truncation as Pitfall 1.
- Total disk usage cap: count of `jobs/` files * cap should not exceed a budget; old completed jobs' logs garbage-collected after N hours or M completed jobs (LRU). Expose `cleanup_completed_jobs()` tool.
- `get_tool_job` returns `{job_id, status, exit_code, started_at, ended_at, log_path, log_bytes, runner_alive}`; agent uses `log_path` as an MCP Resource URI for streaming reads.
- Cancellation: `cancel_tool_job(id)` does `killpg(SIGKILL)` on the stored pgid, awaits the worker task with `asyncio.wait_for(task, timeout=5)`, then forcibly removes from registry even if the task hangs. The worker task itself wraps the subprocess wait in `try/finally` so cleanup runs on `CancelledError`.
- `Mcp-Session-Id` (when v2 of the gateway adds per-session state — out of scope for v1.1) eventually scopes jobs per client; v1.1 stays single-session (`session_state` module pattern).

**Warning signs:**
- `pgrep -P 1 | wc -l` (orphans reparented to init) climbs.
- `ls tool-logs/jobs/ | wc -l` keeps growing across days, never shrinks.
- `cancel_tool_job(id)` returns success but `pgrep -g <pgid>` still shows children.

**Phase to address:** **Jobs** (primary), **Runner** (shared pgid-and-cleanup primitive).

---

### Pitfall 9: Dynamic mode — egress when no-net was intended

**What goes wrong:**
`run_strace`, `run_qemu_user`, `gdb_exec("run")` execute the sample. The sample makes outbound network calls — C2 connect, DNS exfil, telemetry, license check. "No-net by default" means the *container's* network is offline OR network namespaces are unshared per call. If only the former: the rest of the container loses MCP connectivity. If only the latter: forgetting to actually unshare leaks. If neither: the sample phones home from the analyst's network.

The current container runs with `seccomp=unconfined` + `SYS_PTRACE` (PROJECT.md "Constraints"); it does NOT default to a no-net stance.

**Why it happens:**
- "Dynamic analysis without sandbox VM" is the explicit scope (PROJECT.md "Out of Scope: Full-VM / kernel-mode dynamic"). Network isolation is the *minimum* sandbox.
- Devs reach for `iptables -P OUTPUT DROP` and break the rest of the container.
- `--network=none` on a docker run flag is a per-container setting, not per-sample.

**How to avoid:**
- Per-sample-execution **network namespace** via `unshare --net` for each dynamic invocation. The unshared namespace has no interfaces by default, no loopback unless explicitly created — perfect for no-net.
- For the **`--net` opt-in** variant (`run_strace(..., allow_net=True)` etc., off by default): set up a netns with only `lo` (loopback), or with a veth pair to a `mare-dynamic-egress` bridge that has explicit firewall rules — out of scope for v1.1 unless requested; v1.1 just enforces no-net.
- The unshare also covers IPC / UTS / mount (see Pitfall 14) — one `unshare --net --ipc --uts --mount` per call.
- Sanity test: `run_strace(sample=<helper that does getaddrinfo("example.com")>)` must return ENETUNREACH/EAI_AGAIN (or equivalent), not a real DNS resolution.
- Document: dynamic mode is `--dynamic` opt-in (env-gated tool registration), AND no-net is enforced regardless of the `--dynamic` flag. Don't conflate "tools registered" with "network policy".

**Warning signs:**
- A test sample that calls `gethostbyname` returns a real IP under `run_strace` — netns leak.
- The gateway loses connectivity to IDA Pro (127.0.0.1:8745) during a dynamic call — netns unshared too much (loopback dropped). Fix: `ip link set lo up` inside the netns OR don't unshare net for the GATEWAY, only for the spawned subprocess.

**Phase to address:** **Dynamic** (primary). Cross-link to F-1 (Dockerfile gets `unshare` from `util-linux`, which Kali has).

---

### Pitfall 10: qemu-user binfmt_misc not registered or registration drift

**What goes wrong:**
`run_qemu_user(sample=<mips_binary>, argv=[...])` runs `qemu-mips-static` directly — works. But agents will (and should) also `run_shell("./mips_sample arg")` from inside a case_dir, expecting binfmt to dispatch to qemu transparently. binfmt_misc requires:
- Kernel `CONFIG_BINFMT_MISC=y` (Kali yes).
- `/proc/sys/fs/binfmt_misc` mounted (host typically yes, container may not be).
- Registrations present (typically populated by `multiarch/qemu-user-static --reset --persistent yes` on the host).
- For containers using interpreters: the `F` (fix-binary) flag at registration time, so the kernel opens the interpreter once and the registration survives across mount namespaces.

If the container starts in `--privileged` it can write to binfmt_misc; without privileged, it cannot — but it *can* use already-registered handlers if `F` flag was set on registration on the host. So success depends on the host's binfmt state, which the container can't fully control.

**Why it happens:**
- binfmt is a host-system thing leaking into container UX.
- Without `F`, the registration points at an interpreter path inside the host's mount namespace — invisible inside the container.
- Many devs don't know `F` exists.

**How to avoid:**
- `run_qemu_user` is the **primary** path — always explicit (`qemu-<arch>-static <sample>`), never relies on binfmt. Document this in the tool's docstring.
- `run_shell` execs of non-host-arch binaries are **best effort**. Detect at container start: probe `/proc/sys/fs/binfmt_misc/qemu-mips` etc., set a runtime flag exposed by `get_active_backend()`-equivalent (`get_dynamic_capabilities()`) so the orchestrator skill can warn.
- Provide a one-time `setup_binfmt.sh` helper (host-side) in the v1.1 docs (`templates/`) using `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes` with `F`-flag persistence. Cite the F-flag requirement.
- If detection shows binfmt absent, `run_shell` exec of foreign-arch binaries returns the kernel's `exec format error` cleanly — don't try to be clever.

**Warning signs:**
- `ls /proc/sys/fs/binfmt_misc/` is empty inside the container.
- `cat /proc/sys/fs/binfmt_misc/qemu-arm` shows `interpreter /usr/bin/qemu-arm-static` but no `F` flag in `flags:`.
- `run_shell("./mips_binary")` returns "Exec format error" instead of qemu output.

**Phase to address:** **Dynamic** (detection + docs); installer helper to **Skill** docs.

---

### Pitfall 11: ptrace/strace permission gotchas in container

**What goes wrong:**
`run_strace(sample)` fails with `Operation not permitted` despite the container having `SYS_PTRACE` because:
- **Yama** (`/proc/sys/kernel/yama/ptrace_scope`) is host-controlled. Docker's default seccomp denies `ptrace`, but PROJECT.md says `seccomp=unconfined`, so seccomp is not the blocker. Yama might still set `ptrace_scope=1` (only parent can ptrace child) — works for strace (strace forks/execs the child, so it IS the parent). Setting `ptrace_scope=2/3` would break this. Verify at container start.
- **AppArmor / SELinux** profiles on the host can deny ptrace even with CAP_SYS_PTRACE in the container.
- A sample that calls `prctl(PR_SET_DUMPABLE, 0)` becomes non-attachable, even to its parent strace, after the prctl. Strace started before the prctl works; strace `-p` after, fails.
- gdb attaching to a setuid binary: yama `ptrace_scope=1` allows parent-child; `gdb --args /path/setuid_bin` execs it as the unprivileged user (setuid dropped because gdb's `exec` of a ptraced child doesn't get setuid privileges) — usually works for analysis purposes, but the analyst will be surprised when the binary "behaves differently from when run normally". Document.

**Why it happens:**
- "I have SYS_PTRACE so I can ptrace anything" — false. Yama, AppArmor, prctl, and "process not in my session" all gate it.
- The container's view of `/proc/sys/kernel/yama/*` is the **host's** value (it's a sysctl namespace not in user-namespace control unless user-ns is unshared).

**How to avoid:**
- At gateway startup (or first dynamic-tool call), probe `ptrace_scope` and the actual ability (try `ptrace(PTRACE_TRACEME)` from a child). Surface result via `get_dynamic_capabilities()`. If denied, `run_strace`/`run_ltrace`/`open_gdb_session` return `{error: "ptrace_scope=<n> denies tracing; ask host operator to set to 0 or use --cap-add=SYS_PTRACE --security-opt apparmor=unconfined"}`.
- Document the host-side prerequisites in the **Dynamic** phase README.
- Note: `seccomp=unconfined` is already in PROJECT.md "Constraints" — keep it.

**Warning signs:**
- `strace ls` from inside the container fails — broken environment, fail-fast at startup.
- `gdb_exec` shows "ptrace: Operation not permitted" — capabilities check failed.

**Phase to address:** **Dynamic** (capability probe + helpful error messages).

---

### Pitfall 12: MCP tool result size limit (25k tokens) — silent client-side truncation

**What goes wrong:**
The gateway happily returns 200 KB of strings output. The MCP client (Claude Code, mastra.ai) silently truncates at the 25k-token ceiling. The agent reads "...truncated..." or worse, doesn't notice and acts on partial data. The gateway is correct; the agent is misled.

The current 22 tools return mostly small dicts (e.g., `init_case` returns a small JSON). v1.1's `run_shell`, `run_objdump -d`, `run_strings`, etc. routinely produce > 25k tokens of text.

**Why it happens:**
- The client-side cap is opaque to the server; FastMCP does not enforce it at the server unless `ResponseLimitingMiddleware` is wired (verified 2026-05 docs).
- Devs test with small samples; production samples are larger.

**How to avoid:**
- **Default contract for `ReToolRunner`-driven tools:** return the **head** of the output (e.g., first 8 KB stdout, 2 KB stderr — well under the 25k-token client cap), `truncated: bool`, `bytes_total: int`, and the `log_path` for the full content. Agent reads the full output via `get_tool_log(case_dir, log_relpath)` or an `mare://cases/<case>/tool-logs/<file>` MCP Resource (already prefigured in v1.0's resources.py).
- Add response-side `ResponseLimitingMiddleware` (FastMCP-native, verified Beta 2 docs) as a backstop with a conservative cap (e.g., 80 KB serialized JSON) so a buggy tool can't bypass the head-truncation policy.
- For tools that NATURALLY produce structured small output (`run_capstone_disasm` for 50 instructions, `r2_cmd("afl")` for 30 functions), return the full result — they're inherently small. Reserve head-truncation for *unbounded* output.
- Document the convention in tool docstrings: "Returns the first 8 KB of stdout; full output at `log_path`."

**Warning signs:**
- An agent reasons about "the strings output" and the conclusion contradicts what `cat tool-logs/<file>` shows — silent truncation.
- A tool returns a `stdout` field > 30 KB in a unit test.
- `ResponseLimitingMiddleware` logs no truncations even on huge-sample tests — middleware not actually wired.

**Phase to address:** **Runner** (head+log_path pattern), **Artifacts** (`get_tool_log` tool + MCP Resource exposure), **Shell** + **Typed** + **Dynamic** (each tool's return shape contract).

---

### Pitfall 13: `Mcp-Session-Id` collisions / single-session state leaking across clients

**What goes wrong:**
`session_state.py` is module-level (`PINNED_BACKEND`, `ACTIVE_CASE`). With v1.1 adding r2/gdb sessions, the temptation is to add `R2_SESSIONS: dict[str, ...]` next to it. As soon as a second MCP client connects (Claude Code + mastra.ai concurrently, both authorized with the same token), client A's `set_active_case("001-foo")` overwrites client B's. r2 sessions are shared by id — client A can `r2_cmd(client_B_session_id, "dc")` if the id is guessable or logged.

**Why it happens:**
- v1.0 was designed for "one external client at a time" implicitly. v1.1's surface (long-running sessions, jobs, dynamic) makes multi-client concurrency more realistic.
- `session_state.py` comment notes: "v2 (GW-V2-03) will replace this with per-client-session state keyed off Mcp-Session-Id" — that's flagged for *v2*, not v1.1. But v1.1 IS adding much state.

**How to avoid:**
- For v1.1, **acknowledge the limitation explicitly**. Keep the single-session model. Document in `run_shell`, `open_r2_session`, etc., docstrings: "Sessions and jobs are shared across all MCP clients connected with the same bearer token. This gateway is single-user."
- Session ids from `secrets.token_urlsafe(12)` make guessing infeasible, but operationally clients with the same token are trusted.
- Plan v1.2/v2 to thread `ctx.session_id` (from FastMCP `Context`) into the sessions/jobs registries — register tools with `def open_r2_session(sample: str, ctx: Context)` and key the registry by `ctx.session_id`. Don't do it in v1.1; it's a roadmap-flagged delta.
- Bearer token rotation guidance: rotate token if a second client should not see existing sessions.

**Warning signs:**
- Two test clients with the same token can `list_sessions()` and see each other's sessions.
- Race tests showing `set_active_case` interleaving — last-writer-wins (expected for single-session; document).

**Phase to address:** **R2** and **Jobs** docstrings + a note in **Skill** ("the orchestrator running on a remote client should not assume sole ownership of the gateway").

---

### Pitfall 14: Mount-namespace tricks for case-dir confinement misapplied

**What goes wrong:**
Pitfall 2 recommends `unshare --mount` + bind-mount `case_dir` to `/work` for `run_shell`. Naive impl: `unshare -m bash -c "mount --bind <case_dir> /work && cd /work && <user_cmd>"`. Problems:
- `unshare -m` requires CAP_SYS_ADMIN inside the container. v1.0 has CAP_SYS_PTRACE explicit; CAP_SYS_ADMIN is not. Adding it broadens the attack surface dramatically.
- The mount inside the namespace is invisible to the gateway, fine — but cleanup of any *files* the shell wrote OUTSIDE the bind (it can't, if the bind is the only writable spot) — also fine. But `/tmp` is shared by default unless re-bound; samples writing to `/tmp/.X11-unix/...` survive the call. Re-bind `/tmp` to a per-call tmpfs.
- `pivot_root` for "real" jailing requires more privileges than the threat model allows.

**Why it happens:**
- Devs over-engineer the sandbox after Pitfall 2 awareness, then under-deliver privileges.
- Cleanup races: namespace exits when the last process in it exits — if the shell command background-spawned anything (`& disown`), the namespace lives until that exits too.

**How to avoid:**
- **Minimum viable** posture: UID + env scrub + cwd + chmod ACL (Pitfall 2). Skip mount namespaces for v1.1 unless CAP_SYS_ADMIN is acceptable.
- If mount-ns is in scope: ensure the container's `--cap-add=SYS_ADMIN` is documented and gated behind `--dynamic` mode (the same env-gate as dynamic tools — accept the broader cap surface only when the user opts into dynamic mode).
- Per-call **tmpfs `/tmp` bind** mount (small, e.g., `tmpfs size=256m`) so `/tmp` is per-call and disappears on namespace exit.
- Avoid `pivot_root`; bind-mount + `chdir` + `chroot` (CAP_SYS_CHROOT) is sufficient for the cwd-confinement narrative and matches available caps.

**Warning signs:**
- Container `docker inspect` shows CAP_SYS_ADMIN added without a Dockerfile/compose comment explaining why.
- Tests show `/tmp/sample-leftover.bin` from one `run_shell` visible to the next.
- `unshare -m` inside the container returns `Operation not permitted` — capability missing.

**Phase to address:** Decision deferred to **Shell** phase; if accepted, lands with **Dynamic** (both need the cap). v1.1 default: skip mount-ns, document the limitation.

---

### Pitfall 15: F-1 carryover — gateway-package edits don't trigger rebuild

**What goes wrong:**
Already documented in `.planning/PROJECT.md` (F-1) and `MILESTONES.md`. `run_docker.sh:209-222` `DOCKERFILE_SHA` covers `Dockerfile` + `docker-bin/` + disassembler zips, NOT `mcp-gateway/src/`. v1.1 edits 12+ files in `mcp-gateway/src/`; without the fix, the running container keeps the v1.0 gateway code and:
- New tools (`run_shell`, `run_*` wrappers, `open_r2_session`, `start_tool_job`) don't appear in `mcp/list`.
- Tests pass (they import source directly), e2e tests against the container fail mysteriously, half-fixed.
- The agent gets confused — orchestrator skill expects new tools, gets `tool_not_found` from the gateway.

**Why it happens:**
- The cache is a real performance win; turning it off is unacceptable. Extending the hash is straightforward but easy to forget.
- 2026-05-11 UAT caught it once; institutional memory might not.

**How to avoid:**
- **Land F-1 first.** Single small commit: extend the `find ... -print0 | sort -z | xargs -0 sha256sum` (or equivalent) inclusion list to add `-path "./mcp-gateway/src"` and `-path "./mcp-gateway/pyproject.toml"`. Exclude `__pycache__`, `.venv`, `*.egg-info`, `.pytest_cache`.
- Add a CI / test that creates a no-op edit in `mcp-gateway/src/` and asserts the resulting `DOCKERFILE_SHA` *changed* (regression test for the regression test).
- Bonus: bake the gateway `_version.py` (already exists at `mcp_gateway/_version.py`) into the runtime, return it from a `get_gateway_version()` tool, and assert it bumped after every milestone — gives a runtime signal if a stale image is connected.

**Warning signs:**
- A new tool appears in `tests/test_tool_list.py` but not in `claude --mcp-config ... mcp list`.
- `docker inspect <image> --format '{{.Created}}'` is older than the most recent `mcp-gateway/src/` git commit.
- An MCP client's `tools/list` count != the count asserted by `test_tool_list.py`.

**Phase to address:** **F-1** (first, blocks everything else).

---

### Pitfall 16: Orchestrator skill breaks the inside-container agent flow

**What goes wrong:**
The skill update redirects steps from "run `scripts/scan_yara.sh` directly" to "call MCP tool `scan_yara`". For remote agents (Claude Code on host, mastra.ai), perfect — that's the only path. For the **inside-container agent** (the existing v1.0 mode invoked by `./run_docker.sh` without `--remote`), the MCP gateway is NOT running (`MCP_GATEWAY_ENABLED` guard). Skill steps that depend on `mcp__mare__scan_yara` fail; the inside-container agent has no MCP target.

PROJECT.md "Backward compatibility: Existing 'agent inside container' mode must continue working unchanged" — this constraint is exactly what gets violated.

**Why it happens:**
- "Update the skill" reads as "rewrite for the new mode". Easy to forget the dual-mode reality from Phase 3.
- Skill tests typically run in one mode; the other mode regresses silently.

**How to avoid:**
- Skill steps must work in BOTH modes. Pattern:
  - Step describes the **goal** ("collect strings into 01_strings_raw.txt").
  - Step provides **two implementations** with a decision rule: "If the `mare-gateway` MCP server is connected (check `tools/list` for `collect_strings`), call `mcp__mare__collect_strings(sample)`. Otherwise, run `bash workspace/.claude/skills/malware-analysis-orchestrator/scripts/collect_strings.sh <sample>`."
  - Inside-container Claude Code does not see the gateway tools → falls through to scripts. Host Claude Code sees the gateway → uses MCP. Same skill, both modes.
- Add a skill-mode test: snapshot the skill text, grep for unconditional MCP-only references (e.g., a step that says "call X" with no fallback) — fail CI.
- Backend priority documentation update (`IDA > BN > Ghidra`) — same in both modes (`configure-agent-mcp.sh` handles it). Mark dynamic mode in `CURRENT_STATE.json`, but only if the per-case `CURRENT_STATE.json` exists (it always does post-init_case).

**Warning signs:**
- `./run_docker.sh` (no `--remote`) + invoke the orchestrator → it errors with "tool not found".
- Skill SKILL.md contains `mcp__mare__*` references with no `OR` fallback path.

**Phase to address:** **Skill** — dual-mode test before merge.

---

### Pitfall 17: Per-tool MCP tool_name collisions with backend-passthrough

**What goes wrong:**
v1.0's `D-07` design exposes backend-native tool names as-is via PinnedBackend (e.g., IDA's `decompile`, `list_funcs` come through under those names). v1.1 adds `run_capstone_disasm`, `r2_cmd`, etc. If a future backend (or a current backend update — IDA's mrexodia repo has 50+ tools and grows) adds a tool named `r2_cmd` or `run_strace`, the gateway-native registration collides with the backend pass-through registration. FastMCP raises on duplicate tool registration, gateway fails to start.

**Why it happens:**
- D-07 is dynamic pass-through; gateway-native names are static. They evolve independently.
- Backend authors don't coordinate with the gateway's naming.

**How to avoid:**
- Prefix discipline: all gateway-native tools added in v1.1 use a stable prefix scheme. Existing tools (`run_triage`, `collect_strings`) lack a prefix — fine, grandfathered. **New** v1.1 tools: `run_*` (subprocess-driven static), `dynamic_*` (Dynamic mode — alt naming for `run_strace` could be `dynamic_strace`; pick one and stick to it), `session_*` for r2/gdb (`session_r2_open` / `session_r2_cmd` / `session_r2_close`), `job_*` for jobs.
- Decision: keep `run_*` prefix (matches `.planning/PROJECT.md` listing), but **at registration time**, check for collision with the pinned backend's tool list — log a loud warning and rename the gateway tool to `mare_run_<name>` as a fallback. Better: hard-fail at startup so the collision is fixed in code.
- Tests: `test_no_tool_name_collision_with_backend` — for each known backend, fetch `list_tools()` and assert no overlap with the gateway-native names.

**Warning signs:**
- Gateway startup logs include "duplicate tool name" or FastMCP raises.
- A backend update bumps tool count; gateway integration test fails.
- A `tools/list` shows the same name twice (would be a bug in FastMCP, but defensive).

**Phase to address:** **Runner**/**Shell** (naming convention adopted at first new tool), **Typed** / **R2** / **Dynamic** / **Jobs** (all follow). Test added at **Typed** phase (when collision likelihood becomes real).

---

### Pitfall 18: FastMCP request cancellation does not cancel the in-flight subprocess

**What goes wrong:**
An MCP client cancels a tool call (network drop, user-cancel in Claude Code, mastra.ai task aborted). FastMCP raises `asyncio.CancelledError` in the tool handler. If the tool was `await run_script(...)`, the cancellation does NOT propagate to the subprocess by default — the `asyncio.create_subprocess_exec` task gets cancelled, but the OS-level child process keeps running until its own timeout or completion. The gateway returns control to the next request, but a 600 s `scan_capa` keeps eating CPU.

**Why it happens:**
- `asyncio` cancellation cancels Python tasks, not OS processes.
- The current `run_script` correctly handles `asyncio.TimeoutError` (killpg) but doesn't have a `finally` that runs on `CancelledError`.

**How to avoid:**
- Restructure `ReToolRunner` to use:
  ```python
  proc = await asyncio.create_subprocess_exec(..., start_new_session=True)
  try:
      ... drain logic ...
  except (asyncio.TimeoutError, asyncio.CancelledError):
      try:
          os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
      except (ProcessLookupError, PermissionError):
          pass
      # Shielded wait so cleanup completes even if our task is being cancelled
      await asyncio.shield(proc.wait())
      raise
  ```
- Same pattern for `r2_cmd`, `gdb_exec` per-call timeouts and for `start_tool_job` worker tasks.
- Test: tool handler raises `CancelledError` mid-run; subprocess is dead within 100 ms; no zombies.

**Warning signs:**
- After an MCP-client disconnect, `ps -ef` shows the spawned process still running for the full nominal timeout.
- `pgrep -g <pgid_from_log>` after a cancelled call returns rows.

**Phase to address:** **Runner** (primary fix), **R2** + **Dynamic** + **Jobs** (apply the pattern).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip mount-namespace, rely on UID + cwd + env scrub for `run_shell` confinement | No CAP_SYS_ADMIN needed; faster to ship | Confinement is posture, not isolation; bind only to localhost or VPN; document loudly | v1.1 default (small team, trusted network) |
| Single-session state for r2/gdb/jobs (no per-`Mcp-Session-Id` keying) | Reuses existing `session_state.py` pattern | Two MCP clients with same token will see each other's sessions; needs rework when multi-client common | v1.1 (matches existing module shape; flag for v2 GW-V2-03) |
| In-memory-only job registry (no disk persistence) | Avoids pid-reuse and resurrection complexity | Restart kills all jobs; analyst can't "come back tomorrow" | v1.1 (acceptable; document) |
| Inline `confine_to(case_dir, path)` helper duplicated to each tool initially | Fast to add tools | Bug in one copy means inconsistent confinement | Never — extract helper from day 1 in **Runner** phase |
| Return `stdout` raw from `run_*` tools (no head/log_path) | Trivial implementation | 25k-token client cap silently truncates; agent reads partial data | Never — head+log_path is non-negotiable for unbounded-output tools |
| Use `bash -c` without env scrub | Simpler subprocess call | Token / API-key leak through the shell | Never |
| Try SIGTERM before SIGKILL on timeout/cancel | "Polite" cleanup | Sample's signal handler eats SIGTERM, gateway waits the grace period for nothing | Never for sample-running tools; OK for our own scripts only |
| Single-pass `decode("utf-8", errors="replace")` on full unbounded output | Trivial | Mid-codepoint truncation produces `�` everywhere; ANSI escapes stick around | Acceptable on already-bounded head slice, NOT on the streamed log |
| Skip F-1 fix, manually rebuild image before each test | Avoids the script-edit | Forgotten rebuild → stale gateway → tests pass + e2e fails (the 2026-05-11 UAT failure mode) | Never — F-1 lands first |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| FastMCP server | Returning `bytes` or non-JSON-serializable objects | Always return `dict`/`list`/`str`/`int`; for binary, return path string + serve via `mare://` MCP Resource |
| FastMCP tool handler | No `try/finally` around long subprocess | `asyncio.shield(proc.wait())` in cleanup; killpg on CancelledError + TimeoutError |
| `PinnedBackend` ClientSession (existing) | New tool calls `pinned.call()` without the `asyncio.Lock` | Always go through `pinned.call_unified` or `pinned.call` which take the lock |
| `mcp` Python SDK | Manual `ClientSession.initialize()` outside the `async with` | Use `AsyncExitStack` pattern matching `PinnedBackend` |
| `idalib-mcp` HTTP backend | Resolving `localhost` via DNS in container (IPv6 hang noted in `client.py` comment) | Hardcode `127.0.0.1` (already done — preserve in v1.1) |
| r2 / rabin2 stdout | Parsing the textual output | Use JSON output mode (`r2.cmd("?j")`, `rabin2 -j`) — sidesteps prompt-parsing |
| gdb output | Parsing the CLI `(gdb)` prompt | Use `gdb --interpreter=mi` (Machine Interface) with `^done` / `^error` end markers |
| qemu-user | Assuming binfmt_misc registration | Always invoke `qemu-<arch>-static` directly; binfmt is opportunistic |
| strace `-f` follow-fork | Single-pgroup cleanup misses grandchildren after `setsid()` | Kill pgroup AND scan `/proc/<runner>/task/*/children` for stragglers |
| `asyncio.create_subprocess_exec` + `PIPE` | `proc.communicate()` for unbounded output | Concurrent stream drain via task group; head buffer + file sink |
| Streaming `/upload` | Reusing the pattern verbatim for "shell-side upload from inside container" | Not needed in v1.1; upload stays HTTP-only; case-dir writes go through `write_artifact` / `append_artifact` |
| `run_docker.sh --remote` content-hash | Forgetting `mcp-gateway/src` in the SHA inputs | F-1 fix — extend hash; add regression test |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Reading full subprocess output into Python memory | Gateway RSS climbs to multi-GB on `objdump -d` of a 50 MB binary | Stream + cap + file sink (Pitfall 1) | First call on a real malware sample (typical 5-50 MB) |
| Unbounded session registry growth | FD count climbs, `ulimit -n` (1024 default) hit after ~200 leaked sessions | Idle reaper + session cap (Pitfall 5) | Long analyst session (4+ hours) |
| Per-call full-r2-analysis (`aaaa`) | First-call latency 30-120 s on stripped 50 MB binary | Sessions exist precisely to avoid this; do `aaa` once at open, persist | Every iterative analysis session |
| Unbounded job log files | Disk fills, container OOM-kills on log writes failing | Per-job size cap + LRU cleanup (Pitfall 8) | Long-running `qemu-user` or `strace -f` job |
| Recompute sha256 of every upload-resolve | sha256 of 1 GB sample = ~3 s; repeated per `get_sample_info` call | Cache by path + mtime; OR trust the existing `<sha256>/` directory layout for content-addressed | When 100+ samples in `/agent/uploads/` |
| Synchronous `os.path.realpath` inside the event loop on every path-confinement check | Event-loop stalls on slow filesystems (network mount, FUSE) | Cache resolved `case_dir`; for hot paths use `pathlib.PurePath` checks where symlinks are not expected | Network-mounted `/agent/status` (uncommon but possible) |
| `binwalk -e` extracting deep-nested recursive archives | Hours of extraction, GB of disk, before any analysis | Hard `--depth` limit on binwalk; size budget; timeout | Recursive archive bombs (e.g., rzip-inside-zip nesting) |
| Spawning a fresh r2 per `r2_cmd` (defeating the session abstraction) | Latency stays high even with sessions; bug | Test: 100 `r2_cmd` calls in a single session should take < 5 s of overhead | Whenever a developer accidentally writes `r2_cmd` to re-spawn |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Binding gateway port to `0.0.0.0` by default | Anyone on the network with the token (or before token-check, the auth bypass surface) reaches `run_shell` | Default `MCP_GATEWAY_HOST_BIND=127.0.0.1`; explicit opt-in to network exposure; require Origin check (already present) |
| Putting the bearer token in shell-visible env (`echo $MCP_GATEWAY_TOKEN`) | `run_shell("env")` exfiltrates the token | Whitelist env handed to `bash -c` — exclude `MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_TOKEN_FILE`, `AWS_*`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` |
| Allowing the agent to upload AND immediately exec | Crafted ELF → `chmod +x` (filesystem permissions allow it) → exec via `run_shell` → arbitrary code in container | Dynamic execution gated behind `--dynamic` flag; static analysis tools never `exec` the sample (they only read it) |
| Trusting filename in `promote_extracted_sample` | Sample's archive metadata lies about size; promoted file may be HTML named `.exe` | Recompute sha256; recompute size from disk; reject if exceeds upload cap |
| Reusing v1.0 path-traversal predicate inconsistently across new tools | One tool misses the check, sample writes outside case_dir | Single helper, reused; test fuzz |
| Logging tool args verbatim including sample paths | Logs leak `/agent/uploads/<sha>/<malicious_name_with_xss>.bin` to log viewers | Use placeholders `<sha256_short>` in logs; sanitize ANSI / control chars before any log emit |
| Allowing gdb's `python <code>` / r2's `#!` shellout | Sandbox escape: gdb embeds Python with full access | r2: refuse commands starting with `#!`, `R!`, `!`. gdb: do not expose `gdb_exec("python ...")`; allowlist subcommand prefixes (`info`, `print`, `x`, `disas`, `bt`, `continue`, `step`, `next`, `break`, …) at the wrapper level |
| Container starts with `--privileged` | All caps, all devices — massive blast radius | Document needed caps explicitly (`SYS_PTRACE`, optionally `SYS_ADMIN` for mount-ns, `SYS_CHROOT`); never recommend `--privileged` |
| `seccomp=unconfined` taken as "any syscall is fine" | Sample runs `keyctl`, `bpf`, `userfaultfd` to attack kernel | Out of scope to fully mitigate without a VM; document the residual risk; recommend dedicated VM/host for dynamic mode |
| Static and dynamic tools coexist on the same gateway with same auth | Compromised auth = ability to RCE samples | Dynamic env-gated default-off (already planned); consider separate token namespace for `--dynamic` mode |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Return shapes differ across `run_*` tools (some `{out, err, rc}`, others `{stdout, stderr, exit_code}`) | Agent has to switch parsing per tool; LLM hallucinates field names | Single `RunResult` schema for every subprocess-backed tool, generated from a TypedDict in the codebase |
| `run_shell` docstring doesn't say "case-dir confined, not sandboxed" | Agent (and users) over-trust confinement; build sensitive flows on a false premise | Explicit docstring (Pitfall 2 text); link to security model doc |
| `truncated: true` shown only in a nested field | Agent doesn't notice, reasons on partial output | Top-level field; encode in the tool's *content* text too (`"...[truncated; full at <log_path>]"`) |
| `run_strace` produces hundreds of MB; agent gets the head, doesn't know to use `get_tool_log` | Agent quits the analysis at "I have enough" | Tool docstring: "Returns first N KB. For full trace, call `get_tool_log(case_dir, log_path)`." Make the log_path a clickable `mare://` URI |
| Session id collisions / opaque ids | Agent confuses two open r2 sessions | `list_sessions()` tool returning `{id, sample, opened_at, idle_for_s, fd_count}` — give the agent something to introspect |
| No `dry_run` for `run_shell` | Agent runs a destructive (write-heavy) command before checking | `run_shell(cmd, dry_run=True)` returns the planned cwd, env, timeout, output path without executing |
| Timeouts hard-coded, no per-call override | Agent must fail-then-retry-with-knowledge | `timeout: float | None = None` (default per-tool sensible) on every `run_*` tool; cap the override at a safety ceiling (e.g., `min(user, 3600)`) |
| Jobs return `status: "running"` with no progress | Agent polls blindly, wastes turns | Include `log_bytes`, `last_log_line` (head of last N bytes from log) so agent has signal between polls |

---

## "Looks Done But Isn't" Checklist

- [ ] **`run_shell`:** Often missing **env scrub** — verify `MCP_GATEWAY_TOKEN`, `*_API_KEY`, `AWS_*` are NOT in the env that reaches `bash -c`. Test: `run_shell("env | grep -E 'TOKEN|API_KEY|AWS_'")` returns empty.
- [ ] **`run_shell`:** Often missing **non-root UID** — verify `id` inside the shell returns `uid=<mare-shell>`, not root or agent. Test: `run_shell("id -u")` returns the mare-shell UID.
- [ ] **`ReToolRunner`:** Often missing **CancelledError handling** — verify killpg runs on client disconnect (Pitfall 18). Test: launch a 60 s sleep, cancel after 1 s, assert process dead in < 200 ms.
- [ ] **`ReToolRunner`:** Often missing **head+log_path return shape** — verify a `run_shell("yes | head -c 100M")` returns `stdout_truncated: true`, `stdout_bytes_total: 100*1024*1024`, and a `log_path` artifact exists with the full content.
- [ ] **`open_r2_session`:** Often missing **idle reaper** — verify a session unused for `MCP_GATEWAY_SESSION_IDLE_S` is killed and removed from `list_sessions()`. Test with a low (10 s) idle env override.
- [ ] **`open_r2_session`/`open_gdb_session`:** Often missing **pager-off init** — verify a long-output command returns within timeout (no `(less)` pager hang).
- [ ] **`open_gdb_session`:** Often missing **MI interpreter** — verify the session is launched with `--interpreter=mi` and parsing uses `^done`/`^error`/`*stopped` markers, not the `(gdb)` prompt.
- [ ] **Extraction (`run_unblob`, `binwalk -e`):** Often missing **symlink quarantine** — verify a crafted archive with symlinks to `/etc/passwd` produces no usable symlinks in the case_dir; instead a `.unsafe-symlink-foo.txt` describing the target.
- [ ] **`promote_extracted_sample`:** Often missing **size-cap check** — verify promoting a 2 GB file is rejected (or accepted only if cap raised) with a clear error.
- [ ] **Dynamic mode:** Often missing **netns enforcement** — verify a sample that calls `getaddrinfo` returns ENETUNREACH under `run_strace`, not a real DNS resolution.
- [ ] **Dynamic mode:** Often missing **ptrace capability probe** — verify `get_dynamic_capabilities()` reports `ptrace_ok: true/false` and the dynamic tools return a helpful error (not opaque EPERM) when `false`.
- [ ] **`start_tool_job`:** Often missing **shutdown cleanup** — verify gateway lifespan teardown kills all running jobs; verify no PID-1 reparented orphans 5 s after gateway exit.
- [ ] **`start_tool_job`:** Often missing **log size cap** — verify a `start_tool_job(["yes"])` is auto-killed when the log exceeds `MCP_GATEWAY_MAX_JOB_LOG_MB`.
- [ ] **F-1 fix:** Often missing **regression test** — verify a no-op touch to `mcp-gateway/src/some_file.py` changes `DOCKERFILE_SHA`.
- [ ] **Orchestrator skill:** Often missing **dual-mode fallback** — verify the skill works both `./run_docker.sh` (local, no gateway) and `--remote` modes. Grep for `mcp__mare__` references that lack a scripts/ fallback.
- [ ] **Tool-name collisions:** Often missing **collision test** — verify no v1.1 gateway-native tool name is in any backend's `list_tools()`.
- [ ] **MCP result size cap:** Often missing **ResponseLimitingMiddleware** — verify a deliberately huge tool return is truncated server-side before reaching the client.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| OOM from unbounded output (Pitfall 1) | LOW | Container restart; add the head+log_path pattern; ship hotfix |
| Orphan grandchildren (Pitfall 4) | LOW | `pkill -KILL -P 1` inside container for the offending image of zombies; root cause is the cleanup-not-shielded bug — fix in Runner |
| Stale r2/gdb sessions (Pitfall 5) | LOW | `list_sessions()` then `close_*_session` each; or container restart |
| Symlink escape into `/agent/.mcp-gateway-token` (Pitfall 7) | HIGH | Rotate token, audit access logs, force gateway restart with new token, audit any `tool-logs/` produced before fix |
| Token leak via `run_shell` env (Security Mistakes) | HIGH | Rotate token immediately, audit any `tool-logs/` from `run_shell` calls for token strings, redeploy gateway |
| Network egress during "no-net" dynamic call (Pitfall 9) | HIGH | Identify what egressed (audit `tool-logs/dynamic/`), determine if any C2 was reached, treat as incident; fix netns enforcement; re-test |
| Stale gateway code (Pitfall 15 F-1) | LOW | `./run_docker.sh --rebuild` or manual `docker rmi` + rerun; apply the F-1 fix to prevent recurrence |
| Job log disk fill (Pitfall 8) | LOW | Manually `rm tool-logs/jobs/*.log` for completed jobs; cap recovers automatically; add LRU cleanup |
| Skill regression (Pitfall 16) | LOW | Revert skill commit; re-test both modes; add dual-mode test before re-merge |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Output deadlock / huge output | **Runner** | Unit test: 100 MB-of-`/dev/urandom` stdout completes < 2× nominal time, RSS < 200 MB |
| 2. `run_shell` cwd-escape | **Shell** (+ Dockerfile via **F-1**) | Test: `run_shell("id -u")` = mare-shell UID; `run_shell("cat /agent/.mcp-gateway-token")` fails |
| 3. Output bombs + ANSI + slow loris | **Runner** (+ **Shell** tests) | Test: ANSI escape in input → not in log; `sleep 700` killed at timeout + cleanup_grace |
| 4. Pgroup cleanup / fork escape | **Runner** + **Dynamic** + **Jobs** | Test: `strace -f` of a fork-bomb → no zombies after cancel; `setsid` grandchild scanned and killed |
| 5. Session leaks / zombie sessions | **R2** (+ shared `sessions.py`) | Test: open 10 sessions, sleep past idle, reaper reduces to 0; cap=8 → 9th open is rejected |
| 6. Interactive prompt hangs | **R2** + **Dynamic (gdb)** | Test: `r2_cmd("?I")` returns within timeout with `session_invalidated: true` |
| 7. Symlink / archive bombs | **Extract** + **Artifacts** | Test: zip-slip archive → no escaped files; bomb archive → halted at size cap |
| 8. Orphan jobs / log growth | **Jobs** | Test: gateway restart kills all jobs; log cap auto-kills runaway |
| 9. Dynamic netns leak | **Dynamic** | Test: sample DNS lookup returns ENETUNREACH under `run_strace` |
| 10. qemu binfmt drift | **Dynamic** + **Skill** docs | Test: `get_dynamic_capabilities()` reports binfmt status accurately |
| 11. ptrace permission gotchas | **Dynamic** | Test: dynamic tools surface ptrace_scope errors with actionable message |
| 12. 25k-token MCP cap silent trunc | **Runner** + every `run_*` tool | Test: deliberately huge output → server-side truncation before client; head+log_path always present |
| 13. Cross-client state collisions | **R2** + **Jobs** docstrings + **Skill** note | Documentation review; defer per-session keying to v2 |
| 14. Mount-ns over/under-priv | **Shell** decision; **Dynamic** if accepted | Decision logged; default v1.1: skip mount-ns |
| 15. F-1 stale gateway | **F-1** (lands first) | Test: touch `mcp-gateway/src/x.py` → `DOCKERFILE_SHA` changes |
| 16. Skill breaks inside-container mode | **Skill** | Test: orchestrator works in both `./run_docker.sh` and `--remote` modes |
| 17. Tool-name collision with backend | **Runner**/**Shell** (convention) + **Typed** (test) | Test: gateway-native names ∩ backend `list_tools()` = ∅ |
| 18. FastMCP cancel doesn't kill subprocess | **Runner** + every async tool | Test: client disconnect → subprocess dead < 200 ms |

**Suggested phase ordering** (derived from dependencies):

1. **F-1** (Pitfall 15) — unblocks everything; trivial fix; ships first.
2. **Runner** (Pitfalls 1, 3, 4, 12, 17, 18) — the foundation primitive every other phase depends on. No new tools merge before the runner's test suite is green.
3. **Artifacts** (Pitfalls 7 partial, 12 partial) — `write_artifact` / `get_tool_log` / `get_artifact_tree` are dependencies of every other tool's return shape (`log_path` resolves via MCP Resource).
4. **Shell** (Pitfalls 2, 3, 14, security row "token in env") — first real consumer of Runner + Artifacts; also lands the `mare-shell` UID changes that ride along with F-1's rebuild.
5. **Typed** (Pitfalls 12, 17) — pure wrappers; safest to add once Runner contract is stable.
6. **R2** (Pitfalls 5, 6, 13) — adds shared `sessions.py` module.
7. **Extract** (Pitfall 7) — depends on Runner, Artifacts; introduces extraction-output confinement.
8. **Dynamic** (Pitfalls 4, 6 gdb, 9, 10, 11, 14 if mount-ns) — env-gated default-off; depends on Runner + sessions; can ride with **Jobs** since strace/qemu are typically backgrounded.
9. **Jobs** (Pitfalls 4, 8, 18) — depends on Runner + Artifacts; comes near the end because it builds on everything.
10. **Skill** (Pitfall 16) — last, because it documents the new tools as they exist. Add the dual-mode test in this phase.

---

## Sources

- **Existing code reviewed (HIGH confidence — authoritative for the project):**
  - `/home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway/src/mcp_gateway/subprocess_runner.py` — current argv-only `run_script` with `start_new_session=True` + `killpg(SIGKILL)` on timeout
  - `/home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway/src/mcp_gateway/app.py` — FastMCP wiring, lifespan, middleware order, `streamable_http_path="/"` quirk
  - `/home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway/src/mcp_gateway/uploads.py` — streaming upload pattern, `_is_invalid_filename` predicate, atomic move
  - `/home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway/src/mcp_gateway/tools/artifacts.py` — existing path-confinement (`os.path.realpath` + `startswith(real_case + os.sep)`)
  - `/home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway/src/mcp_gateway/tools/case_dirs.py` — `resolve_case_dir` STATUS_ROOT constraint
  - `/home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway/src/mcp_gateway/backend/client.py` — `PinnedBackend` async lock, AsyncExitStack pattern, 127.0.0.1 literal note
  - `/home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway/src/mcp_gateway/session_state.py` — module-level state model with v2 flag for per-session keying
  - `/home/cervon/Code/MARE-MCP-Toolbox/.planning/PROJECT.md` — v1.1 target features, F-1 carryover, dual-mode constraint
  - `/home/cervon/Code/MARE-MCP-Toolbox/.planning/MILESTONES.md` — F-1 root-cause description from 2026-05-11 UAT
- **Asyncio subprocess PIPE deadlock** (HIGH — Python docs):
  - [Python 3 asyncio-subprocess docs](https://docs.python.org/3/library/asyncio-subprocess.html) — `communicate()` deadlock notes
  - [Asynchronous subprocess pipe reading (Stefaan Lippens)](https://www.stefaanlippens.net/python-asynchronous-subprocess-pipe-reading/) — concurrent drain pattern
- **qemu-user binfmt_misc** (HIGH — kernel + multiarch docs):
  - [multiarch/qemu-user-static (GitHub)](https://github.com/multiarch/qemu-user-static) — F-flag persistence requirement
  - [binfmt_misc (Wikipedia)](https://en.wikipedia.org/wiki/Binfmt_misc) — F-flag semantics (open at registration time)
  - [Architecture emulation containers with binfmt_misc (LWN)](https://lwn.net/Articles/679308/) — F-flag introduction context
- **MCP tool result size limits** (HIGH — official MCP + FastMCP):
  - [Response size limit for MCP responses (modelcontextprotocol discussion #2211)](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2211) — 25k-token cap discussion
  - [FastMCP Updates](https://gofastmcp.com/updates) — `ResponseLimitingMiddleware` (Beta 2) UTF-8-safe truncation
  - [Truncated MCP Tool Responses (anthropics/claude-code #2638)](https://github.com/anthropics/claude-code/issues/2638) — client-side truncation behavior
- **Container ptrace / Yama / SYS_PTRACE** (MEDIUM — kernel docs + general SRE knowledge):
  - Linux kernel `Documentation/admin-guide/LSM/Yama.rst` (`ptrace_scope`)
  - PROJECT.md "Constraints" section (`seccomp=unconfined`, SYS_PTRACE already documented)
- **Process group cleanup semantics** (HIGH — POSIX + Python):
  - POSIX `setpgid(2)` / `killpg(3)` man pages
  - Existing `subprocess_runner.py` already implements the canonical pattern

---
*Pitfalls research for: v1.1 Remote RE Tool Expansion — adding shell + typed RE + session-scoped r2/gdb + dynamic mode + background jobs to the FastMCP gateway*
*Researched: 2026-05-12*
