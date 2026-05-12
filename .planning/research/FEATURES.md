# Feature Research — Remote RE Tool Expansion (v1.1)

**Domain:** Reverse-engineering / malware-analysis MCP tooling (Kali-side primitives exposed to remote agents)
**Researched:** 2026-05-12
**Confidence:** HIGH for analyst-workflow patterns and tool semantics (long-stable CLIs, multiple corroborating sources); HIGH for wrapper shape recommendations (derived from existing v1.0 gateway conventions in `mcp-gateway/`).

This document answers the v1.1 milestone question: **how do RE analysts ACTUALLY use these tools, and what does a good MCP wrapper look like for each?** The downstream consumer (requirements/roadmapper) gets: per-tool table-stakes parameters, session vs one-shot classification, JSON-vs-raw output guidance, and composite workflows that justify orchestrator-skill checklists.

## Anchor Definitions

- **One-shot wrapper** — pure function: argv in, stdout/stderr + JSON result + auto-captured artifact out. Stateless. The default shape, modeled on v1.0 `run_capa` / `run_yara`.
- **Argv-profile wrapper** — one-shot but with a curated set of "mode" presets (e.g., `binwalk` has `signature`, `entropy`, `extract` modes). The wrapper translates a typed mode parameter to argv. Better discoverability than `run_shell`.
- **Session-managed wrapper** — `open_X_session` → `X_cmd` × N → `close_X_session`. Process persists between calls; analyzer state survives. r2 and gdb need this.
- **Job-required wrapper** — wraps a tool whose realistic runtime exceeds the MCP request timeout (≥ ~60 s). Returns a `job_id` immediately; result streamed to artifact. Same pattern v1.0 uses for `capa` deep analyses.
- **Shell-only** — no typed wrapper; analyst calls `run_shell` with cwd-confined argv. Used for the long tail (e.g., `file`, `strings`, `xxd | grep`, `find`, `awk`, `cut`).

All tools assume v1.0 gateway invariants: case-dir confinement (`case_dir`), sha256 sample resolution via `resolve_sample(sha256)`, automatic output capture under `case_dir/<artifact-bucket>/`, argv-only subprocess (no shell expansion except in the explicit `run_shell` tool), timeout + output-truncation, and structured JSON return shape `{stdout, stderr, returncode, artifact_path, truncated, duration_ms}`.

---

## Feature Landscape

### Category 1 — Static Inspection (One-shot or Argv-profile)

Things an analyst types at a Kali prompt to *describe* a binary without executing it. Iteration pattern: dozens of quick reads, each independent. JSON output where the tool supports it; raw text where the analyst's eye is the parser.

| Feature | Why Expected | Complexity | Wrapper Shape | Notes |
|---------|--------------|------------|---------------|-------|
| `run_file` | Every triage starts with `file <sample>`; identifies format, arch, link type, stripped/not | LOW | one-shot | argv = `file -k -b <path>`. Output is small (single line). Raw text fine. Capture to `case_dir/static/file.txt`. |
| `run_die` (Detect-It-Easy) | Packer/protector ID — UPX, ASPack, VMProtect, Themida, Enigma, .NET Native; far more accurate than `file` for packed PE | LOW | one-shot with optional `deep` flag | argv = `diec -j <path>` for JSON (DIE supports `-j`). Capture to `case_dir/static/die.json`. JSON parsing matters here — packer name drives the orchestrator's next move. |
| `run_xxd` | Hexdump a window around an offset — analysts use this to verify a magic number, inspect an embedded blob header, read a string table | LOW | one-shot with `offset` + `length` (+ optional `cols`) | argv = `xxd -s <offset> -l <length> -c <cols> <path>`. **Raw text** — never JSON. Capture to `case_dir/hex/<offset>-<length>.txt`. The `-s` and `-l` constraint is what makes it safe (full-file xxd of a 1 GB sample is a footgun). |
| `run_readelf` | ELF anatomy — sections (`-S`), program headers (`-l`), dynamic (`-d`), notes (`-n`), relocations (`-r`), symbols (`-s`), version info (`-V`), arch (`-A`) | LOW | argv-profile (mode = `headers \| sections \| dynamic \| symbols \| relocations \| notes \| arch \| all`) | argv = `readelf -W -<flag> <path>`. **Raw text** — readelf has no native JSON. `-W` (wide) is mandatory for parseable output. Capture per mode to `case_dir/static/readelf-<mode>.txt`. |
| `run_objdump` | Disassembly (`-d`), section-content dumps (`-s`), reloc tables, DWARF (`--dwarf`), demangled symbols (`-C`) | LOW | argv-profile (mode = `disasm \| sections \| relocs \| dwarf \| headers`) + optional `section=` filter | argv = `objdump -wC -<flag> <path>`. **Raw text**. For full-binary disasm, fall through to capstone or r2; `objdump -d` is the "quick look" path. Capture to `case_dir/disassembly/objdump-<mode>.txt`. |
| `run_nm` | Symbol table with type chars — analysts grep for `T <name>` (exported text), `U <name>` (undefined / will be resolved at runtime), and `W` (weak). Tells you what the binary *exports* and what it *needs*. | LOW | one-shot with `mode` (`defined \| undefined \| all`) + `demangle` bool | argv = `nm -C [--defined-only \| --undefined-only] <path>`. Raw text. |
| `run_rabin2` | Multi-format counterpart to readelf+nm — works on ELF/PE/Mach-O uniformly. `-I` (info), `-i` (imports), `-E` (exports), `-l` (libs), `-z` (strings in data sections), `-zzz` (all strings), `-H` (header) | LOW | argv-profile (mode = `info \| imports \| exports \| libs \| strings \| sections \| header \| all`) + `format=json\|text` | argv = `rabin2 -j -<flag> <path>` when JSON requested. **rabin2 `-j` produces real JSON** — parsing it matters because the orchestrator reads imports to drive YARA/capa hypotheses. This is the most important typed wrapper of the inspection tier. Capture to `case_dir/static/rabin2-<mode>.json`. |
| `run_capstone_disasm` | Disassemble an arbitrary buffer — given `(arch, mode, bytes, base_addr)`, return instruction list. Used when an analyst extracts shellcode from a string blob, an injected region, or a packer stub and needs to read it. | MEDIUM | one-shot, typed | Inputs: `arch` (`x86 \| arm \| arm64 \| mips \| ppc \| sparc`), `mode` (`32 \| 64 \| arm \| thumb \| little \| big`), `bytes` (hex string OR `sha256+offset+length` reference into a sample), `base_addr` (default 0). Output: **typed JSON** `[{addr, bytes, mnemonic, op_str}]`. This is one of the few places JSON pays off enormously — agent can iterate over instructions structurally. Backed by `capstone` Python module, not shelled out. |
| `run_ropper` | ROP gadget search — given a binary, find `pop rdi; ret` etc. Used by exploit-dev and by analysts reading malware that uses ROP for evasion (process hollowing, COP chains) | MEDIUM | one-shot with `search` (filter string), `arch` override, `badbytes` (hex), `quality` (1–5), `type` (`rop \| jop \| sys \| all`) | argv = `ropper --file <path> --nocolor --search '<filter>' --badbytes <hex> [-a <arch>]`. ropper supports semantic search (`--semantic`) and chain templates. **JSON pays off** — ropper's text output is paginated and noisy; structured gadget list (addr, instr-sequence, bytes) is much more useful. The wrapper should bound result count (`--len`, default 200) so a single call doesn't return 200 k gadgets. |
| `run_jq` | Query the JSON artifacts the rest of the toolchain produces — capa output, rabin2 `-j`, YARA `-j`, MCP Resources | LOW | one-shot | argv = `jq -c <filter> <path>`. Operates over `case_dir/**/*.json`. Raw text out (jq output is itself JSON). |
| `run_yq` | Same for YAML (capa rules, signature configs, container manifests in extracted firmware) | LOW | one-shot | argv = `yq -o=json <filter> <path>`. |

**Rationale notes:**

- **Why argv-profile for readelf/objdump/rabin2 and not just `run_shell`?** Three reasons: (1) discoverability — an agent sees the mode names in the tool schema and picks one; (2) consistent capture paths (the wrapper knows mode = `dynamic` → `case_dir/static/readelf-dynamic.txt`); (3) downstream orchestrator scripts can rely on the artifact existing at a known path. Without typed wrappers, every prompt would have to re-derive the path convention.
- **Why JSON for rabin2/capstone/ropper but raw for readelf/objdump/xxd?** rabin2 has native `-j`; capstone returns Python objects natively; ropper's text output is paginated and unfriendly to LLMs. readelf/objdump have no JSON mode and their text is dense but linear — the agent can read it. xxd is *visual* — its value is the side-by-side hex/ASCII view, which JSON would destroy.

### Category 2 — Extraction / Unpacking (One-shot, Job for unblob)

Pull child files out of a parent — embedded firmware blobs, packed PE sections, dropped resources. Once extracted, the analyst wants to *promote* a child to its own case and triage it.

| Feature | Why Expected | Complexity | Wrapper Shape | Notes |
|---------|--------------|------------|---------------|-------|
| `run_binwalk` | Signature-based scanner for embedded files inside a blob; works on firmware, packed PE, ISO/IMG dumps | LOW | argv-profile (mode = `signature \| entropy \| extract \| strings`) | argv = `binwalk <flag> <path>`. `-B` (signatures, default), `-E` (entropy graph data — text), `-Me <path>` (matryoshka recursive extract, **goes to extracted/**). Captures to `case_dir/extracted/binwalk-<mode>.txt` (and `_extracted/` subtree for `extract` mode). Time-bounded; `-Me` can be slow → fall through to job system if > 60 s. |
| `run_unblob` | Modern alternative to binwalk for firmware — faster, more formats including modern ones (CPIO variants, RomFS, modern squashfs), better path-traversal hardening, sandboxed extractor processes | MEDIUM | one-shot + **job-required** (default to job for binaries > 50 MB) | argv = `unblob --extract-dir <out> [--report <json>] <path>`. unblob produces a **structured `--report` JSON** mapping every chunk's offset/format/extracted-path. Capture report to `case_dir/extracted/unblob-report.json` and the tree to `case_dir/extracted/unblob/`. **JSON parsing matters** — the report is the *index* the orchestrator uses to decide what children to promote. |
| `run_upx_test` | `upx -t <path>` — verifies UPX-packed file is intact; cheap sanity check before unpacking | LOW | one-shot | argv = `upx -t <path>`. Returns boolean + version line. |
| `run_upx_list` | `upx -l <path>` — list compression ratio, format, version *without unpacking*; quick triage to confirm UPX vs UPX-modified | LOW | one-shot | argv = `upx -l <path>`. **JSON parsing matters lightly** — header line is regex-friendly. Optional `format=json` to parse "Format: linux/elf64.amd64, Version: 4.02"-style. |
| `run_upx_unpack` | `upx -d <path> -o <out>` — produces the unpacked binary; the single most common unpack path for commodity malware | LOW | one-shot | argv = `upx -d <in> -o <case_dir>/extracted/<sha>-unpacked`. Refuses to overwrite. After unpack, recommend calling `promote_extracted_sample`. |
| `extract_embedded_files` | Convenience: runs binwalk *or* unblob (engine = parameter) + returns list of extracted children with sizes/hashes. Hides the engine choice for the orchestrator's "default extraction step". | MEDIUM | one-shot wrapping `run_unblob` → `run_binwalk` fallback | Result: `{engine, children: [{path, sha256, size, format, parent_offset}]}`. This is the composable primitive the orchestrator calls; `run_binwalk`/`run_unblob` are still exposed for manual control. |
| `list_extracted_files` | Walk `case_dir/extracted/` and return a tree with sha256/size/format-detect for each leaf | LOW | one-shot | Pure FS operation. Result is the orchestrator's "what came out of this sample?" view. |
| `promote_extracted_sample` | Turn an extracted child into a first-class case (new sha256-addressed upload, new case_dir, link back to parent) | MEDIUM | one-shot, mutates case state | Inputs: `parent_case_id`, `extracted_path` (must be inside `parent_case_dir/extracted/`). Outputs: `{child_case_id, child_sha256, link: parent_case_id}`. **Path-traversal guard mandatory** — same logic v1.0 uses for `/upload`. |

**Rationale notes:**

- **Why both binwalk and unblob, not just one?** unblob beats binwalk on most modern firmware formats and is path-traversal-hardened by design, but binwalk has wider format coverage and is the analyst's reflex. EMBA (the embedded-firmware analyzer community standard) actually runs them complementarily as of 2025. Exposing both keeps the agent's options open; the `extract_embedded_files` convenience tool picks unblob by default and falls back to binwalk.
- **Why a typed `promote_extracted_sample`?** Promoting a child to a case is a structural change to the gateway state — uploading the child's bytes as a new sha256-addressed sample, creating a new case_dir, recording the parent-child link. Doing this via `run_shell` would bypass the case-system invariants. This *must* be a typed tool.

### Category 3 — Dynamic Tools (env-gated default-off)

Execute the sample under instrumentation. Default-off because the container has `SYS_PTRACE` + `seccomp=unconfined` and running unknown samples is qualitatively different from analyzing them. The `MCP_GATEWAY_DYNAMIC_TOOLS=1` env-gate (surfaced as `./run_docker.sh --dynamic`) is a deliberate UX speedbump.

| Feature | Why Expected | Complexity | Wrapper Shape | Notes |
|---------|--------------|------------|---------------|-------|
| `run_strace` | System-call trace — every malware analyst's first dynamic step on Linux samples. Shows `execve`, `open`, `connect`, `clone`, `ptrace` calls — i.e. C2 contact, persistence, anti-debug | MEDIUM | argv-profile + **job-required** by default | argv = `strace -f -t -e trace=<filter> -o <out> -- <sample> [args]`. Modes: `network` (`-e trace=network`), `file` (`-e trace=file`), `process` (`-e trace=process`), `all` (no filter). Outputs to `case_dir/dynamic/strace-<mode>.txt`. **Network disabled by default** — `--network=none` enforced at container level when dynamic mode is on (or hostile sample escapes). Time-cap mandatory. |
| `run_ltrace` | Library-call trace — complements strace by hooking dynamic-linker calls (`libc.so` etc). Shows `strcpy`, `malloc`, `getenv`, `system`. Especially valuable when the malware uses libc heavily and strace shows only the syscalls under it. | MEDIUM | argv-profile + **job-required** by default | argv = `ltrace -f -t -o <out> -- <sample>`. Same network-disabled-by-default policy. Output to `case_dir/dynamic/ltrace.txt`. |
| `run_qemu_user` | Run a non-host-arch binary via `qemu-<arch>-static` — analysts use this constantly on MIPS/ARM IoT malware on an x86_64 box. Combined with strace via `qemu-mipsel-static -strace`. | MEDIUM | argv-profile + **job-required** | argv = `qemu-<arch>-static [-strace] [-d <log-flags>] -- <sample>`. Arch param selects binary. `-d in_asm,cpu` mode for instruction tracing (great for unpacker analysis). Output to `case_dir/qemu/<arch>-<mode>.txt`. Network namespace isolation same as strace. |
| `open_gdb_session` | Persistent debugger — analysts iterate: break at `main`, run, inspect regs, step, set another bp, inspect heap, etc. One-shot gdb is rarely useful for non-trivial reversing because the session *is* the analysis state. | HIGH | **session-managed** | `open_gdb_session(sample_path, args=[], env={}) → session_id`. Launches `gdb --interpreter=mi3 <sample>` as a subprocess. Returns immediately at `(gdb)` prompt before `run`. |
| `gdb_exec` | Send a command to an existing gdb session and get the response | HIGH | session command | `gdb_exec(session_id, cmd, timeout=30) → {output, mi_records?, console_text}`. Wraps the MI3 protocol; returns both raw console and parsed MI records (typed JSON for `-stack-list-frames`, `-data-list-register-values`, `-data-read-memory`, etc.). Long-running commands (`continue`, `run`) need a hard timeout per call. |
| `close_gdb_session` | Tear down — kill process, release session slot | LOW | session lifecycle | `close_gdb_session(session_id) → {ok, exit_status?}`. Idempotent. Sessions auto-expire after configurable idle (default 30 min) to bound resource use. |

**Rationale notes:**

- **Why session-managed gdb but not session-managed strace?** strace is a *single trace* of one execution — re-running is cheap, no analysis state accumulates across calls. gdb is the opposite: every `b <addr>`, `set $rip = ...`, `watch *(int*)0x...` builds up state that's *expensive* to recreate. Treating gdb as one-shot would force the agent to re-script every interaction into a `gdb -batch -ex ...` blob, which is what analysts do in CI but not in interactive RE.
- **Why MI3 (machine interface) over console parsing?** gdb-mi gives typed structured responses for `-stack-list-frames`, `-thread-info`, `-data-read-memory-bytes`, etc. Far more reliable than scraping `(gdb) info regs` output. Fall through to console output for commands that have no MI equivalent.
- **Network-none default:** The single biggest dynamic-analysis footgun is "malware contacted real C2 because someone forgot to disable network." Bind this to the dynamic env-gate: turning on dynamic mode auto-applies `--network=none` to the spawned process group. Explicit opt-in (`allow_network=true`) for the legitimate cases (sandboxed honeynet, INetSim).

### Category 4 — Session-managed r2

| Feature | Why Expected | Complexity | Wrapper Shape | Notes |
|---------|--------------|------------|---------------|-------|
| `open_r2_session` | r2 with `aaa` analysis run once and kept in memory; analyst issues many follow-up commands (`pdf @ <fn>`, `axt @ <addr>`, `iz~http`, `/<pattern>`, `s sym.<name>`) without re-analyzing. The whole *point* of using r2 in malware analysis is the persistent analysis state. | HIGH | **session-managed** | `open_r2_session(sample_path, analysis_level="aaa") → session_id`. Launches `r2 -q0 <sample>` via r2pipe, runs analysis level. Returns when prompt is ready (`aaa` on a 5 MB stripped binary can take 30 s — should still complete inside one request, but big binaries should fall back to a job that loads + analyzes + then advertises session_id). |
| `r2_cmd` | Send any r2 command to a session; return output | MEDIUM | session command | `r2_cmd(session_id, cmd, format="text|json") → {output}`. r2 has uniform `j` suffix for JSON (`pdfj` for function disasm JSON, `izj` for strings JSON, `iij` for imports JSON, `aflj` for function list JSON). The wrapper appends/respects `j` based on `format`. **JSON output is excellent here** — r2's JSON is one of the more thoughtful in the RE world, and structured function/instruction/xref data lets the agent iterate. |
| `close_r2_session` | Release session | LOW | session lifecycle | Same shape as `close_gdb_session`. |

**Rationale notes:**

- **Why r2 not session-batched-into-one-call?** An analyst's r2 trace on a typical sample is 20–60 commands; re-running `aaa` for each costs 30 s × 60 = 30 min of pointless re-analysis. Sessions cut this to one `aaa` plus 60 fast commands.
- **Why expose raw `r2_cmd` rather than typed `r2_disasm_function`, `r2_list_strings`, etc.?** The r2 command space is huge (thousands of commands) and reverse engineers value the ability to compose them (`pdf @ sym.foo~call`). A typed surface would cover 5% of real use. The structured JSON return (when `format=json`) gives the agent typed data without constraining what it can ask for.

### Category 5 — Background Job System

The MCP request lifetime is bounded (default ~60 s; clients vary). Several v1.1 tools regularly exceed this: capa on big binaries, unblob on multi-GB firmware, IDA/Ghidra deep analysis, strace traces with a long run-time, qemu execution of a network-loop sample.

| Feature | Why Expected | Complexity | Wrapper Shape | Notes |
|---------|--------------|------------|---------------|-------|
| `start_tool_job` | Run any registered tool asynchronously; return job_id immediately | HIGH | factory wrapper | `start_tool_job(tool="run_strace", params={...}) → {job_id, status="queued", artifact_path}`. The artifact_path is *pre-allocated* so the agent can poll the partial output via MCP Resources while the job runs. |
| `get_tool_job` | Status + result | LOW | one-shot | `get_tool_job(job_id) → {status: "running\|done\|failed\|cancelled", returncode?, duration_ms, stdout_tail, artifact_path, exit_reason?}`. Idempotent. |
| `cancel_tool_job` | Kill the process group | LOW | one-shot | Sends SIGTERM, then SIGKILL after grace. Marks status as `cancelled`. |
| `list_tool_jobs` | What's running / what's done | LOW | one-shot | Filter by case_id, status. |

**Rationale notes:**

- **Why is artifact_path pre-allocated?** Lets the agent stream partial output via `mare://cases/<case>/tool-logs/<job>.txt` while the job runs — important for strace where the interesting events may show up in the first 10 s out of a 60 s run.
- **Process-group cleanup:** Critical for qemu and gdb — they often spawn children. Use `os.setsid` + `killpg(SIGTERM)` on cancel; otherwise zombies accumulate.

### Category 6 — Constrained Shell (`run_shell`)

| Feature | Why Expected | Complexity | Wrapper Shape | Notes |
|---------|--------------|------------|---------------|-------|
| `run_shell` | The long tail — `strings | grep -i http`, `find extracted/ -name '*.dll'`, `awk` over capa output, `cut`, `sort`, `uniq -c`. Analysts pipe constantly; without a shell tool the wrapper count balloons into the hundreds and many real workflows still don't fit. | MEDIUM | constrained one-shot | `run_shell(cmd: str, cwd_subpath?: str, timeout_s?: int, env?: dict) → standard wrapper return`. Cwd defaults to `case_dir`; `cwd_subpath` constrained to descendants (no `..`). Hard timeout, output cap (default 1 MiB tail), auto-capture to `case_dir/tool-logs/<timestamp>-<slug>.txt`. **No network egress unless dynamic mode opts in.** |

**Rationale notes:**

- **Security model:** The boundary moves from "argv-only" (v1.0) to "case-dir-confined + timeout + output-cap + capture + dynamic-env-gate" (v1.1). This is *the* big architectural shift of v1.1 — it accepts that allowlisting argv for every Kali tool is a losing battle and replaces it with structural confinement.
- **`run_shell` is not `run_shell_as_root`:** the gateway process and `run_shell` subprocesses are non-root (existing v1.0 invariant). Sample-execution capability is gated by the dynamic env-gate, not by `run_shell` itself. A `run_shell` that runs `strings | grep` is fine in default mode; a `run_shell` that runs `./sample` is blocked unless dynamic mode is on.

### Category 7 — Artifact / Control Helpers

| Feature | Why Expected | Complexity | Wrapper Shape | Notes |
|---------|--------------|------------|---------------|-------|
| `write_artifact` | Agent-produced notes, hypothesis docs, summary IOC lists — first-class structured artifacts, not shell-redirect side effects | LOW | one-shot | `write_artifact(case_id, relative_path, content, mode="overwrite\|append") → {path, sha256}`. Path-traversal guarded. |
| `append_artifact` | Logbook append (orchestrator notes during a run) | LOW | one-shot | Convenience over `write_artifact(..., mode="append")`. |
| `list_artifacts` | Enumerate everything under a case_dir (or under one bucket like `dynamic/`) | LOW | one-shot | Returns tree with sizes, mtimes, sha256, MCP resource URIs. |
| `get_artifact_tree` | Whole-case structured view (the 13 v1.0 artifacts + the 9 new buckets) | LOW | one-shot | Useful for the agent to recap state after a long session. |
| `get_tool_log` | Read a specific captured tool-log without going through MCP Resources (avoids URI round-trip for the agent's own outputs) | LOW | one-shot | `get_tool_log(case_id, log_name, offset=0, length=...) → {content, truncated, total_size}`. Range-read so the agent can sample a giant strace. |

---

## Differentiators (vs. raw "agent inside container")

What this tool surface gives a *remote* agent that the v1.0 surface didn't:

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Analyst-parity primitives over MCP | Remote agent can do every common Kali-prompt step without an in-container agent. This is the v1.1 north-star. | — | Realized by Categories 1–6 together. |
| Auto-capture under typed buckets | Every tool invocation produces an artifact at a known path (`case_dir/static/...`, `case_dir/extracted/...`, etc.). Orchestrator can rely on the path convention; agent doesn't have to plumb tee/redirects. | LOW | Implemented by the internal `ReToolRunner` (already a v1.1 requirement). |
| Session tooling (r2, gdb) | Enables the *interactive* analyst loop, not just batch reports. No competitor MCP server exposes this. | HIGH | r2 + gdb sessions. |
| Job system with live artifact streaming | Long-running analyses don't block the agent and partial output is queryable via MCP Resources. | HIGH | `start_tool_job` + `mare://cases/...` Resources. |
| Default-off dynamic lab mode | First-class but explicitly opt-in — meets the "first-class, not always-on" requirement; lets the same image be used for static-only triage *or* sandboxed dynamic, by flag. | MEDIUM | env-gate + `--dynamic` launcher flag + network-none default. |
| Typed JSON for capstone/rabin2/ropper/r2 | LLM agents iterate over structured data far better than over paginated text. The wrappers that return typed JSON dramatically reduce token churn. | LOW–MEDIUM | Per-tool, see categories above. |
| Promote-extracted-to-new-case | A canonical RE move (extract → promote child → triage child → recurse) is one MCP call instead of a fragile shell ritual. | MEDIUM | Required for any meaningful firmware workflow. |

---

## Anti-Features (Tempting but Wrong)

| Feature | Why Tempting | Why Problematic | Alternative |
|---------|--------------|-----------------|-------------|
| Composite "investigate_*" tools (e.g., `investigate_packer`, `auto_triage_pe`, `generate_detection_leads`) | Looks like a clean MCP surface; one tool call gets you a full report | These are agent prompts dressed as tools. They hard-code an analysis strategy at the gateway layer, which is the *agent's* job. They bloat the tool schema, drift faster than primitives, and are impossible to test deterministically. Already an explicit Out-of-Scope item in PROJECT.md. | Keep the gateway primitive. Express composite workflows as *orchestrator-skill checklists* (see Composite Workflows below). |
| Typed `r2_*` tool per r2 command (`r2_pdf`, `r2_aflj`, `r2_iz`, ...) | "Discoverability" via tool schema | r2 has thousands of commands and analysts compose them (`pdf @ sym.foo~call`). A typed-per-command surface covers ~5% of real use and bans the rest. Schema bloat is enormous. | Single `r2_cmd(session_id, cmd, format)` with `format="json"` exploiting r2's `j` suffix. Agent learns r2 commands the way humans do. |
| Allow-list-argv-everywhere (no `run_shell`) | Tighter security posture on paper | Loses the long tail (`strings | grep`, `find`, `awk` pipelines, `xargs`, `tee` to a side log). Analysts ad-lib constantly. Wrapper count balloons; gaps remain. | `run_shell` with cwd-confinement + timeout + output-cap + capture + dynamic-env-gate. Structural confinement, not argv allowlisting. |
| Always-on dynamic mode | "It's a first-class capability, why hide it?" | The default container is for static triage. Always-on dynamic widens the attack surface for an exploit-against-the-analyzer (CVE-in-strace, CVE-in-qemu) and creates accidental sample-execution incidents. | Env-gate + explicit `--dynamic` flag (already decided in PROJECT.md). |
| One-shot gdb-as-batch (`run_gdb_script(script)`) | Avoids session state management | Every interactive analysis becomes a script-generation problem. Agent can't *react* to what it sees between commands. Loses the iteration that's the whole point of gdb in malware analysis. | Session-managed gdb. |
| `run_strings` as a typed wrapper | strings is in every analyst's reflex | v1.0 already exposes strings via the existing case pipeline (`collect_strings`). Don't duplicate. If finer control is needed, `run_shell` covers it. | Skip — fold into existing v1.0 surface and `run_shell`. |
| `run_objdump_full_binary_disasm` as a default mode | One call, full disasm | A 50 MB stripped Linux binary disassembles to hundreds of MB of text. Output-cap will truncate it. Always-truncated results are misleading. | Force `--section` filter for objdump-disasm mode, or push the agent toward r2/capstone for full disasm with structured query. |
| Direct access to the host filesystem from `run_shell` | "Just expose `/`" | Defeats the whole confinement model. Crashes the security boundary that justifies enabling a shell at all. | Cwd-confine to `case_dir` (and its descendants). All cross-case work goes through typed tools (`promote_extracted_sample`, etc.). |

---

## Feature Dependencies

```
F-1 image-hash fix (mcp-gateway/ in DOCKERFILE_SHA)
    └──unblocks──> every other v1.1 wrapper (otherwise edits don't reach the container)

ReToolRunner (internal)
    ├──required-by──> all run_* one-shot wrappers
    ├──required-by──> run_shell
    └──required-by──> start_tool_job (which is a ReToolRunner + async harness)

Case-dir artifact tree expansion (tool-logs/, extracted/, hex/, rop/, dynamic/, qemu/, disassembly/, decompilation/, xrefs/)
    └──required-by──> auto-capture in every wrapper
                       └──required-by──> orchestrator-skill checklists that reference fixed paths

Background job system (start/get/cancel_tool_job)
    ├──required-by──> run_unblob (large firmware)
    ├──required-by──> run_strace / run_ltrace / run_qemu_user (long traces)
    └──required-by──> capa deep analyses, IDA/Ghidra reanalysis

Session lifecycle infra (open/close/cmd for r2 and gdb)
    ├──required-by──> r2_cmd
    └──required-by──> gdb_exec

Dynamic env-gate (MCP_GATEWAY_DYNAMIC_TOOLS, --dynamic flag, --network=none default)
    ├──required-by──> run_strace, run_ltrace, run_qemu_user, gdb session tools
    └──enhanced-by──> get_tool_job (long-trace observability)

Extraction tier (run_unblob, run_binwalk, run_upx_*)
    ├──feeds──> extract_embedded_files (composer)
    └──feeds──> promote_extracted_sample (which depends on v1.0 sha256 upload + case creation)

promote_extracted_sample
    └──depends-on──> v1.0 upload-by-sha256 + case-creation tools

run_shell
    └──enhances──> every typed wrapper (analyst always has an escape hatch for pipelines)

Orchestrator-skill update (deep RE checklist)
    └──depends-on──> the full typed surface above (otherwise the checklist refers to tools that don't exist)
```

### Dependency Notes

- **F-1 first, then everything.** Without the image-hash fix, edits to `mcp-gateway/` silently don't reach the running container. v1.0 UAT already burned us on this (Plan 04-03's `tools/resources.py` was in repo but not in image). F-1 is sequenced first in PROJECT.md for exactly this reason.
- **ReToolRunner is the chokepoint.** Every typed wrapper is a thin schema + argv-formatting layer over ReToolRunner; specifying its contract (argv, env, cwd, timeout, output-cap, process-group, capture-path) is what unblocks parallel wrapper authoring.
- **Sessions vs jobs are different infra.** A session is a long-lived subprocess the agent talks to repeatedly; a job is a single subprocess whose result the agent polls. Don't conflate them in the implementation — they have different lifecycles (sessions need keep-alive/idle-timeout; jobs need queue/cancel/result).
- **Dynamic env-gate fans out.** Turning on dynamic mode must atomically enable `run_strace`, `run_ltrace`, `run_qemu_user`, and gdb session tools, *and* apply the network-none default. A single env-gate read at gateway boot is cleaner than per-tool checks.

---

## Composite Analyst Workflows (Drive Orchestrator-Skill Checklist)

These are the workflows analysts run *repeatedly* and that the malware-analysis-orchestrator skill update should encode as deep-RE checklists. Each step lists the gateway tool to call. None of these become composite MCP tools — they're agent-side scripts of primitive calls.

### W-1: Packed-Binary Triage (PE or ELF)

Goal: identify packer → unpack → re-triage unpacked binary.

1. `run_file` → format, arch
2. `run_die` (deep=true) → packer ID (UPX, ASPack, VMProtect, .NET Native, etc.)
3. Branch on packer:
   - **UPX** → `run_upx_test` → `run_upx_list` → `run_upx_unpack` → `promote_extracted_sample` on output → recurse from step 1 on child
   - **Commercial protector (VMProtect, Themida, Enigma)** → log; skip auto-unpack; flag for manual analysis or dynamic dump
   - **Unknown packer** → `run_binwalk` signatures + entropy → `run_xxd` of high-entropy regions → if structure visible, attempt `run_unblob`
4. On unpacked child: standard static checklist (W-2 or W-3)

**Why this matters for v1.1:** drives the case for `run_die` with structured JSON output (orchestrator branches on packer field), `run_upx_*` triplet, and `promote_extracted_sample`.

### W-2: ELF Deep-Dive (Linux Malware Static)

1. `run_file` → arch confirm, dynamically linked vs static
2. `run_rabin2` mode=`all` (or `info`+`imports`+`libs`+`strings`) **format=json** → arch, entry, imports, NEEDED libs, strings → orchestrator parses imports → primes YARA/capa hypotheses
3. `run_readelf` mode=`sections` → confirm `.text/.data/.rodata` sizes vs unusual sections (`.upx0`, `.upx1`, `.MyPackedSection`)
4. `run_readelf` mode=`dynamic` → DT_NEEDED, DT_RPATH (LD_PRELOAD-style persistence), DT_INIT/DT_FINI
5. `run_readelf` mode=`notes` → build-id, GNU notes, GO buildinfo (Go-malware identification)
6. `run_nm` mode=`undefined` demangle=true → external API surface
7. v1.0 YARA + capa pipeline
8. `open_r2_session` → `r2_cmd(... pdfj @ entry0)` → main-flow walk; `r2_cmd(... aflj~malware-ish-name)` → suspicious functions; `r2_cmd(... izj~http://|.onion|/api/)` → C2 strings
9. Hypothesis writeup via `write_artifact`

**Why this matters for v1.1:** drives `run_rabin2` JSON-first design, `run_readelf` argv-profile modes, and r2 session as the deep-disasm loop.

### W-3: PE Deep-Dive (Windows Malware Static)

Same shape as W-2 but PE-flavored. `run_rabin2` works on PE (key for OS-agnostic flow); `run_readelf`/`run_nm` don't. Compensate with:

1. `run_file` / `run_die`
2. `run_rabin2` mode=`all` format=json → imports (Win32 API list — driver of capa/YARA), exports, sections
3. `run_xxd` of PE header at offset 0 → `.text` PointerToRawData → confirm overlay presence
4. v1.0 disasm pipeline (IDA > BN > Ghidra) → `decompile_function` on entry/TLS-callback/Wmain
5. `run_capstone_disasm` on extracted shellcode regions (TLS callbacks, packed sections)
6. capa / YARA
7. r2 session for xrefs and string walk
8. Writeup

### W-4: ROP Gadget Hunt (Exploit Dev or ROP-using-Malware Reading)

1. `run_file` → confirm arch
2. `run_rabin2` mode=`info` format=json → NX/PIE/RELRO/Canary status (sets the exploit-mitigation context)
3. `run_ropper` with `search="pop rdi; ret"`, `search="syscall"`, `search="mov [r??], r??"` patterns; `badbytes="00"` typical → structured gadget list
4. `run_ropper` with `--semantic` filters for specific primitives
5. `write_artifact` to `case_dir/rop/chain-hypothesis.md`

**Why this matters for v1.1:** the only justification for ropper-as-typed-wrapper (vs `run_shell ropper ...`) is the structured-JSON gadget list — that's the value-add.

### W-5: Dynamic API Trace (Linux user-mode malware behavior)

Requires `--dynamic`.

1. Static recap (W-2 abbreviated)
2. `start_tool_job(run_strace, mode=all, timeout=30s, no_network=true)` → job_id
3. Poll partial output via MCP Resource `mare://cases/<case>/dynamic/strace-all.txt` while job runs
4. `get_tool_job(job_id)` for completion + final exit_reason
5. `start_tool_job(run_ltrace, ...)` for libc-level view
6. `run_jq` over capa's behaviors JSON, cross-reference with strace events
7. (Optional) `open_gdb_session` → `gdb_exec("b open"; "run"; "bt"; ...)` to inspect the call site for an interesting `open()` from strace
8. Network-aware re-run if a sandbox is available: `run_strace` with `allow_network=true` against INetSim/FakeDNS (out of scope for v1.1 default — flag as future)

**Why this matters for v1.1:** drives the job-system requirement (strace traces routinely exceed 60 s), the live-artifact MCP-Resource streaming, and the gdb session as the targeted follow-up.

### W-6: Embedded Firmware Unpack

1. `run_file` → likely says "data" or specific firmware header
2. `run_binwalk` mode=`signature` → first-pass format ID
3. `run_binwalk` mode=`entropy` → reveal compressed/encrypted regions
4. `start_tool_job(run_unblob, ...)` (firmware is usually big) → job_id
5. `get_tool_job` → unblob `--report` JSON
6. `list_extracted_files` → children with sha256/format
7. For each interesting child (filesystem images, kernel modules, suspicious ELFs):
   - `promote_extracted_sample` → child_case_id
   - Recurse into W-2/W-3 on child
8. `run_jq` over unblob report to summarize extraction tree to the user

**Why this matters for v1.1:** strongest case for unblob with JSON `--report`, `extract_embedded_files` composer, `promote_extracted_sample`, and the job system together.

### W-7: Cross-Arch Triage (MIPS/ARM IoT Malware)

1. `run_file` → confirm e.g. `MIPS, MSB`
2. `run_rabin2` mode=`all` format=json
3. Static disasm via r2 (works for MIPS/ARM out of the box)
4. (Dynamic mode) `start_tool_job(run_qemu_user, arch=mipsel, strace=true)` → behavior trace on x86_64 host
5. Same triage flow from here

---

## MVP Definition

### Launch With (v1.1 — Must-Have for Analyst Parity)

- [x] **F-1 image-hash fix** — non-negotiable; nothing else lands reliably without it.
- [ ] **`ReToolRunner` (internal)** — argv-only subprocess + process-group + timeout + output-cap + JSON result + auto-capture. Foundation for every wrapper.
- [ ] **`run_shell`** — closes the long-tail gap; documented as the safety-by-confinement primary surface.
- [ ] **Expanded case-dir artifact tree** — `tool-logs/`, `extracted/`, `hex/`, `rop/`, `dynamic/`, `qemu/`, `disassembly/`, `decompilation/`, `xrefs/`. Just directory plumbing; cheap and unblocks everything.
- [ ] **Static one-shot wrappers (Category 1):** `run_file`, `run_die`, `run_xxd`, `run_readelf`, `run_objdump`, `run_nm`, `run_rabin2`, `run_capstone_disasm`, `run_ropper`, `run_jq`, `run_yq`. All ride on `ReToolRunner`. Schema-light, easy to land.
- [ ] **Extraction tier:** `run_binwalk`, `run_unblob`, `run_upx_test`, `run_upx_list`, `run_upx_unpack`, `extract_embedded_files`, `list_extracted_files`, `promote_extracted_sample`.
- [ ] **Background job system:** `start_tool_job` / `get_tool_job` / `cancel_tool_job` / `list_tool_jobs`. Without this, unblob and dynamic tools are essentially unusable.
- [ ] **Session-scoped r2:** `open_r2_session` / `r2_cmd` / `close_r2_session`. The single most impactful new capability for non-trivial RE.
- [ ] **Artifact / control helpers:** `write_artifact`, `append_artifact`, `list_artifacts`, `get_artifact_tree`, `get_tool_log`.
- [ ] **Orchestrator-skill update** — encode W-1..W-4 + W-6 as deep-RE checklists; fix the stale assumptions called out in PROJECT.md (backend priority, remote agents use gateway not local `scripts/`).

### Add When Dynamic Mode Lands (v1.1 second wave)

- [ ] **Dynamic env-gate** (`MCP_GATEWAY_DYNAMIC_TOOLS=1`, `--dynamic` flag, `--network=none` default).
- [ ] **`run_strace`, `run_ltrace`, `run_qemu_user`** — first-class dynamic tools.
- [ ] **Session-scoped gdb:** `open_gdb_session` / `gdb_exec` / `close_gdb_session`. Higher complexity than r2 (MI3 parsing).
- [ ] **Orchestrator-skill** picks up W-5 and W-7.

### Future Consideration (v1.2+)

- [ ] Sandboxed-network dynamic mode (INetSim/FakeDNS/cuckoo-style network simulation) — currently flagged with `allow_network=true` but no simulation layer.
- [ ] Coverage-guided dynamic (afl-style instrumentation hooks) — out of scope for "analyst parity"; this is fuzzing, not triage.
- [ ] Memory-snapshot tooling (Volatility integration) — separate workflow domain.
- [ ] Web UI for case browsing — already an Out-of-Scope per PROJECT.md; reaffirm.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| F-1 image-hash fix | HIGH (unblocks everything) | LOW | **P0** |
| `ReToolRunner` foundation | HIGH | MEDIUM | **P0** |
| `run_shell` | HIGH (covers long tail) | LOW (after ReToolRunner) | **P0** |
| Case-dir tree expansion | HIGH (orchestrator path conventions) | LOW | **P0** |
| `run_file`, `run_die`, `run_xxd`, `run_jq`, `run_yq` | MEDIUM (table-stakes triage; some duplicate `run_shell` but discoverable) | LOW | P1 |
| `run_rabin2` (JSON-first) | HIGH (drives downstream branches) | LOW | **P1** |
| `run_readelf`, `run_objdump`, `run_nm` | MEDIUM (raw-text, ergonomic over shell) | LOW | P1 |
| `run_capstone_disasm` | HIGH (typed JSON instructions for arbitrary buffers — unique capability) | MEDIUM | **P1** |
| `run_ropper` | MEDIUM (niche, but typed JSON is the differentiator) | MEDIUM | P2 |
| Extraction tier (binwalk, unblob, upx, promote) | HIGH (the firmware/packer workflow is core) | MEDIUM | **P1** |
| Job system | HIGH (gates unblob + all dynamic) | HIGH | **P1** |
| `open/close/r2_cmd` session | HIGH (the interactive RE loop) | HIGH | **P1** |
| Artifact helpers | MEDIUM | LOW | P1 |
| Orchestrator-skill update | HIGH (without it the wrappers exist but aren't used coherently) | MEDIUM | **P1** |
| Dynamic env-gate + `run_strace`/`run_ltrace`/`run_qemu_user` | HIGH (when dynamic needed) | MEDIUM | **P2** |
| gdb session | MEDIUM (heavy users only) | HIGH (MI3) | P2 |

**Priority key:**
- **P0** — Foundational; nothing else works until these land.
- **P1** — Core v1.1 deliverable; ship in the milestone.
- **P2** — Second wave / dynamic-mode bundle; same milestone but later phase.
- P3 — Defer to v1.2+.

---

## Competitor / Adjacent Tool Analysis

| Capability | Existing MCP Servers | Analyst CLI Tools | v1.1 Approach |
|------------|---------------------|--------------------|---------------|
| Disassembler over MCP | ida-pro-mcp (mrexodia, 50+ tools), Ghidra MCP, BN MCP | IDA/Ghidra/BN GUIs | v1.0 already pinned (IDA > BN > Ghidra via gateway pass-through). No change. |
| Static-inspection wrappers (readelf/objdump/nm/rabin2) | None known | Direct CLI | First MCP surface for these in this domain. Typed argv-profile + JSON-where-supported. |
| Extraction (binwalk/unblob/upx) | None as MCP tools | Direct CLI; EMBA orchestrates both | First MCP surface. unblob's `--report` JSON is the key integration point. |
| Dynamic (strace/ltrace/qemu/gdb) | None as MCP tools | Direct CLI; Cuckoo for sandbox VMs | First MCP surface for user-mode dynamic in container. Env-gated; jobs for long traces. |
| Session-managed RE (r2, gdb over MCP) | None known | r2pipe (Python/Node bindings), gdb-MI clients | r2pipe and gdb-MI under the hood, exposed as MCP session lifecycle tools. Novel. |
| Constrained shell over MCP | Some general-purpose MCP servers (filesystem, shell) | bash | Constrained `run_shell` cwd-confined to case_dir + timeout + capture. Domain-specific; tighter than general shell MCPs. |
| Composite "investigate" tools | Some MCP servers do this | n/a | Explicitly Anti-Feature here. Composition stays in the agent (orchestrator skill). |

---

## Confidence Notes & Gaps

**HIGH confidence:**
- Analyst workflows W-1..W-7 (long-stable RE practice; corroborated by SentinelOne, EMBA project docs, radare2 book, Hex-Rays docs, multiple practitioner blogs).
- Tool-specific argv conventions (readelf, objdump, rabin2, binwalk, upx, strace, ltrace are decades-stable CLIs).
- JSON-output flags: rabin2 `-j` (confirmed via radare2 book + man page), DIE `-j`, jq/yq native, capstone Python returns objects, r2 `j`-suffix (confirmed via radare2 book).
- Session-vs-one-shot classification for r2 and gdb (both are universally used as session tools in real RE work).

**MEDIUM confidence:**
- ropper JSON output details — ropper has structured Python API but the gateway implementation may use direct ropper Python module rather than `--output json` parsing; either path yields typed JSON, but the exact integration shape is a Phase-7 decision.
- unblob `--report` schema stability — unblob's report JSON shape evolves (per ONEKEY 2025 changelog); the wrapper should tolerate version drift (parse defensively, surface unknown fields raw).
- MI3 (gdb machine interface v3) parsing complexity — well-documented but a real implementation surface; estimate "HIGH" cost reflects this.

**Gaps to address in phase-level planning:**
- **Session resource limits.** How many concurrent r2/gdb sessions per container? Memory cost of r2 `aaa`'d on a 100 MB binary is non-trivial. Phase-7-or-similar should set caps and an eviction policy.
- **`run_shell` argv-sanitization.** "cwd-confined" is structural; quoting/expansion (`$(...)`, backticks) is a separate concern. The current PROJECT.md decision says full bash one-liner per call — confirm the threat model accepts that.
- **Dynamic-mode network namespace mechanics.** "`--network=none` enforced" — exact mechanism (per-process via `unshare`? per-container? per-subprocess via `ip netns`?) needs concrete spec. Worth a feasibility note in PITFALLS / ARCHITECTURE research.
- **Job persistence across gateway restart.** If the gateway process restarts, do in-flight jobs survive? PROJECT.md doesn't commit; phase decision needed (recommendation: jobs are in-memory, restart kills them, agent can re-issue from artifact path).

---

## Sources

- [unblob homepage](https://unblob.org/) — modern extractor, `--report` JSON, sandboxed extractor processes
- [Unblob updates since 2025-11](https://www.onekey.com/resource/latest-developments-in-unblob-new-formats-smarter-extraction-and-a-more-hardened-release-pipeline) — ONEKEY 2025 changelog, format coverage, security hardening
- [EMBA firmware extraction layer (wiki)](https://github.com/e-m-b-a/emba/wiki/The-EMBA-book-%E2%80%90-Chapter-1:-Firmware-Extraction-Layer) — binwalk + unblob complementary use in practice
- [ReFirmLabs/binwalk](https://github.com/ReFirmLabs/binwalk) — current binwalk capabilities
- [Ropper on GitHub (sashs/Ropper)](https://github.com/sashs/Ropper) — multi-arch gadget search, semantic search, Capstone-backed disasm
- [Ropper PyPI](https://pypi.org/project/ropper/) — Python module for typed JSON gadget access
- [The Official Radare2 Book — rabin2](https://book.rada.re/tools/rabin2/intro.html) — `-j` JSON output, imports/exports/sections/strings
- [rabin2 man page](https://github.com/radareorg/radare2/blob/master/man/rabin2.1) — argv reference
- [Radare2 Book — Code Analysis](https://book.rada.re/analysis/code_analysis.html) — `aa`/`aaa`/`aaaa` analysis levels
- [SentinelOne — Radare2 power-ups for macOS malware](https://www.sentinelone.com/labs/radare2-power-ups-delivering-faster-macos-malware-analysis-with-r2-customization/) — r2 session patterns for malware
- [Retrieving RAT config statically with radare2](https://radareorg.github.io/blog/posts/malware-static-analysis/) — concrete malware r2 session workflow
- [idapro PyPI](https://pypi.org/project/idapro/) — idalib for headless IDA (already in STACK)
- [Capstone Engine docs](https://www.capstone-engine.org/) — Python bindings, typed instruction objects
- v1.0 internal: `mcp-gateway/src/` — existing wrapper conventions (`run_capa`, `run_yara`, sha256 sample resolution, `case_dir` confinement), the template for v1.1 wrappers
- PROJECT.md v1.1 milestone scope (this repo) — wrapper list and security-model shift to confinement-based

---
*Feature research for: MARE-MCP-Toolbox v1.1 Remote RE Tool Expansion*
*Researched: 2026-05-12*
