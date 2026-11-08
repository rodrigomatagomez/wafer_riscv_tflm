# Animas / Zenith: discovered capabilities and exact interfaces used

This project uses Animas's MCP tool server (an `animas` MCP server defined in
`.mcp.json`, SSE transport at `http://localhost:27500/mcp/sse`) as the actual
RTL compilation/simulation route, per claude_implementation_prompt.txt
Section 2. See docs/issues.md ISS-002 for the connectivity history (the
bridge was initially broken, then resolved externally by the user).

## Project model

- Animas projects are described by a `project.apf` JSON file at the project
  root (`apf_version`, `project` metadata, `sources: [{path, role, library}]`,
  `settings: {top_module, sim_top, sim_tool, synth_tool, elab_mode, ...}`).
- `mcp__animas__list_projects()` returns `{projects: [...], active_project}`.
  `active_project.id` (a UUID) is required as `project_id` for every other
  call. The GUI app exposes the project root through an xdg-document-portal
  FUSE mount (`/run/flatpak/doc/<hash>/<project-name>`), not the literal host
  path — tools report paths relative to that mount, which is transparent to
  the caller.
- `mcp__animas__get_project_info(project_id)` returns the current
  `top_module`, `sim_top`, `sim_tool` ("zenith"), `synth_tool` ("yosys"),
  `elab_mode`, and `latest_zwdb` (null until a simulation has produced a
  waveform database).

## File management

- `add_source_file(project_id, rel_path, content, role, set_as_top=False)`
  creates a new file on disk AND registers it in one call. `role` is one of
  `rtl` / `simulation` / `mem` / `listf`.
- `overwrite_source_file(project_id, path, content)` replaces an existing
  registered file's full content (note the parameter is `path`, not
  `rel_path`, unlike `add_source_file`).
- `read_source_file(project_id, path)` / `read_source_file_lines(...)` read
  back the current on-disk content (warns if the Animas editor has unsaved
  changes diverging from disk).
- `register_existing_file(project_id, rel_path, role)` registers a file that
  already exists on disk but isn't yet in the APF (role auto-suggested by
  extension if omitted).
- `set_file_role(project_id, path, role)` corrects a file's role after the
  fact.
- `check_project_paths(project_id)` reports `missing` (APF entries with no
  file on disk), `untracked` (files on disk not in the APF — this naturally
  includes build artifacts like a Python venv or Keras checkpoints that were
  never meant to be Animas sources; it is informational, not an instruction
  to delete anything), and `bad_incdirs`.

## Top-module / elaboration control

- `set_rtl_top(project_id, module_name)` sets the synthesis/schematic top
  and switches the project to `manual_top` mode. `module_name` is the bare
  SystemVerilog module name, not a file path.
- `set_sim_top(project_id, rel_path)` sets the testbench entry point (a file
  path this time). In `manual_top` mode this is the file elaborated as the
  simulation top.
- Both tools should be (re-)asserted before `run_simulation` if there is any
  chance the user changed something in the UI concurrently — `get_project_info`
  is the way to check current tops first.

## Running simulations

- `run_simulation(project_id, timeout_seconds=1800, extra_flags=None)` acts
  as a remote control for the Animas UI's own Run button when the app is
  open (`mode: "ui_remote_control"` in the response) — this makes the UI's
  live log and waveform view update exactly as if a human clicked Run. If no
  Animas backend is reachable it falls back to invoking Zenith directly as a
  headless subprocess instead (`mode` would differ; not exercised in this
  project since the UI route was available throughout real use).
- The response includes `status`, `elapsed_s`, `zwdb_path`, `log_path`, and
  an `output_tail` convenience field. **`output_tail` can be a stale
  snapshot** immediately after a source edit (see docs/issues.md ISS-002) —
  always confirm with `read_simulation_log` / `get_last_sim_result` rather
  than trusting `output_tail` alone.
- `get_zenith_help()` runs the real installed `zenith --help` as a direct
  subprocess (works regardless of daemon state) and is the authoritative
  source of supported CLI flags. Useful flags observed: `--vcd`, `--zwdb`,
  `--end <time>`, `-f <filelist>`, `-top <module>`, `+define+NAME[=VAL]`,
  `+incdir+<path>`, `--seed <N>` (deterministic `$random`/`$urandom`),
  `--stats`. **Important translation caveat documented by the tool itself**:
  when running through the daemon (as `run_simulation` does), only a small
  allow-list of cflags survive translation to the daemon's job protocol
  (`+...` plusargs, `--verbose`, `--stats`, `--dump-ast`, `--hir-summary`,
  `--preprocess-only`, `--dump-hir`, `--dump-scheduler`, `--dump-all`) — flags
  like `--end`, `-G`, `--verbose-time` are silently dropped in daemon mode
  and must instead be passed via a headless/standalone Zenith invocation if
  truly needed (not required for this project's tests, which used
  `$finish`-driven termination rather than a fixed `--end`).
- Transient condition observed once: "Zenith server connection lost —
  attempting restart…" followed by an `ERROR:` with no useful log — simply
  re-invoking `run_simulation` succeeded immediately after. Treat this as a
  retry-once condition, not a hard failure.
- **`run_simulation`'s actual execution mode (`ui_remote_control` vs.
  `headless`) is not caller-controlled and was observed to vary between
  consecutive calls with identical arguments**, apparently depending on
  whether the Animas desktop UI happened to be running/responsive at the
  moment of the call. This matters beyond just the `output_tail`-staleness
  caveat above: **`--seed <N>` (not a `+`-prefixed plusarg) was observed to
  be silently dropped in `ui_remote_control` mode** (consistent with the
  documented cflag allow-list above, which does not include `--seed`),
  while it was correctly passed through verbatim in `headless` mode (visible
  in that response's own `command` field). Two runs intended to share a
  fixed seed therefore do NOT reliably share one unless both are confirmed
  `headless` (check the `mode` field in each `run_simulation` response) —
  see `docs/decisions.md` D-007 for a concrete case where this produced a
  spurious-looking divergence between two otherwise-identical simulations.
- **`set_sim_options`'s structured `defines` parameter was also observed to
  be unreliable in roughly the same way**, in at least one case failing to
  take effect for a `headless`-mode run despite being correctly echoed back
  in the tool's own response. The reliable alternative found: pass
  `+define+NAME` as a plain string inside `cflags` (which IS in the
  documented `+`-prefixed allow-list) instead of using the dedicated
  `defines` parameter, and always confirm the intended define actually took
  effect by checking the resulting simulation log's own banner/behavior
  (e.g. this project's `tb/soc_tb.sv` prints `ram=lite` vs `ram=full`) rather
  than trusting either input mechanism blindly.

## Reading results

- `get_last_sim_result(project_id)` parses `zsim.log` (and the ZWDB, if
  present) into structured fields: `passed` (true/false/null —
  indeterminate if no recognized pass/fail marker text is present; this
  project's testbenches print distinctive strings and check them directly
  rather than relying on this heuristic field), `finished`, `finish_time`,
  `error_count`, `warning_count`, `fatal_count`, `end_time`, `timescale`.
- `read_simulation_log(project_id, last_n_lines=200)` /
  `read_simulation_log_lines(...)` return raw `zsim.log` content.
- `search_simulation_log`, `summarize_assertion_failures` were registered
  but not yet needed for the directed-test scale used here.

## Waveform / signal inspection (for debugging, not required for the basic
## pass/fail test-suite evidence captured via log text)

- `get_hierarchy(project_id)` returns the signal hierarchy from the most
  recent ZWDB.
- `list_signals`, `query_signals_at_time`, `query_signals_window`,
  `query_signals_at_clock_edge`, `find_signal_transitions`,
  `find_signals_changed_between`, `find_signals_with_value`,
  `find_value_in_packed_bus`, `get_signal_stats`, `get_clock_info`,
  `get_timescale` all require a ZWDB to already exist (`get_project_info
  .latest_zwdb` is the authoritative existence check).
- `load_signals_to_waveform`, `set_waveform_view`, `add_waveform_marker`,
  `setup_debug_view`, `screenshot_waveform`, `screenshot_schematic` support
  interactive debugging via the UI; used selectively for this project's
  bounded diagnostic waveform windows (Section 7 of the prompt explicitly
  discourages dumping every signal across millions of cycles).

## Verified end-to-end (sanity check before investing in the real core)

A throwaway `sanity_counter` / `sanity_counter_tb` pair was added, elaborated,
and simulated through this exact tool sequence (`add_source_file` x2 →
`set_rtl_top` → `set_sim_top` → `run_simulation` → `read_simulation_log`),
confirming the full chain works. See docs/development_log.jsonl and
docs/issues.md ISS-002 for the full trace, including one caught self-check
bug in the throwaway testbench (an arithmetic mistake in the author's own
expected value, not a simulator or DUT defect) that was found and fixed
using exactly this loop.

## Wall-clock limits: no Zenith-level flag exists; `run_simulation`'s `timeout_seconds` is backend-only

Investigated directly via `flatpak run --branch=1.0.2 --command=zenith com.mifraltech.animaseda --help`
(the exact binary/version the running daemons use) to settle, with authoritative evidence, which
setting controls which limit:

- **Zenith itself has no wall-clock-seconds option at all.** Its only time/iteration-bounding flags
  are `--end <time>` (a *simulated*-time end point, not wall-clock; unused by this project, which
  relies on `$finish` via our own `+MAXCYCLES=` testbench plusarg instead), `--max-delta <n>`
  (zero-delay loop guard per simulated-time step, default 50000), and `--max-handoffs <n>` (delta-cycle
  cap across all simulated-time steps, default 10,000,000) -- neither of the latter two is a per-real-second
  limiter; they guard against non-terminating combinational/zero-delay loops, not normal clocked advancement.
- **`mcp__animas__run_simulation`'s `timeout_seconds` parameter (default 1800) is therefore the only
  documented, per-run-configurable wall-clock-affecting setting in this whole stack** -- it is purely an
  Animas-backend-level orchestration value, with no Zenith-side counterpart. Passing a larger value
  (e.g. `7200`) is the correct, supported way to ask for a longer wall-clock allowance for one job.
- **This is a different thing from the harness's own MCP tool-call idle timeout** (observed to abort
  silently at 300s with "sent no response or progress for 300s"). That 300s figure is this agent
  session's own client-side limit on how long it will wait for *any* tool response; it has no bearing
  on whether the underlying Animas/Zenith job keeps running, and is not configurable from inside this
  project. A `run_simulation` call can (and routinely does) hit this 300s client-side abort while the
  actual simulation keeps computing for much longer server-side -- always verify via `animas.log`
  (`"Simulation started"` with no matching `"done"`) and direct process/log inspection, never assume
  a client-side abort means the job stopped, and never assume it means the job *kept* going either --
  check.
- **Observed twice in this project: a job that was confirmed via `get_last_sim_result`/`animas.log` to
  still be `finished: false`, after measurably real CPU consumption for over an hour, later went
  genuinely idle (zero `/proc/<pid>/stat` CPU-time delta across multiple separate measurements, single
  sleeping thread, no terminal marker ever written) with no logged cause.** No Zenith-level or
  Animas-level mechanism was found that explains this (no wall-clock flag exists to have triggered it;
  `get_sim_diagnostics` showed zero errors/fatals). The practical lesson: `finished: false` plus zero
  CPU-time delta across two or more independent measurements a few seconds apart is the correct signal
  to treat a job as stopped-with-unknown-cause, not a single log-silence observation alone (which can
  reflect buffering) and not sustained CPU usage alone (which was observed to persist for a time after
  the job had, in at least one case, already gone idle by the time it was actually re-checked). Both
  stalled/idle jobs in this project were resolved the same way: narrowly-targeted `SIGTERM` to the
  freshly-re-verified daemon PID (never a cached one), after confirming via `/proc/<pid>/cwd` and parent
  process identity that it belonged exclusively to this project's Animas backend instance, not any other
  user's or project's job on the (observed to be shared, multi-user) host. A subsequent `run_simulation`
  call then transparently respawned a fresh daemon and completed the retried case successfully.

## `waveform_mode: "off"` does not reliably prevent ZWDB generation

Observed directly: two separate runs launched with `set_sim_options(waveform_mode="off")` (confirmed via
`get_project_info` to actually be `"off"` at launch time) each nonetheless produced a full-size ZWDB file
in `output/` -- one reached **5.5 GB** (for a run that was later found idle and terminated) and another
reached **2.7 GB** (for a run that completed normally and produced a correct, verified result). Neither
was a small/placeholder file. This is a real capability gap, not a one-off: `waveform_mode="off"` should
not be relied upon as a hard guarantee against large waveform output for a long functional run (per
claude_implementation_prompt.txt Section 7's explicit "avoid dumping every signal across millions of
cycles" guidance) -- it reduces risk but does not eliminate it. **Practical mitigation adopted**: treat
`output/*.zwdb` as disposable, regenerable scratch output; delete completed/abandoned runs' ZWDB files
promptly after extracting the needed text-log evidence into a durable `results/` location, rather than
assuming "off" means no cleanup is ever needed. This project's home-directory quota was exhausted once
by the accumulation of several such files (one single-digit-GB file left over from a terminated run, plus
smaller ones from earlier sessions), which in turn caused a `docs/` text file to be silently truncated
mid-write (`cat: write error: Disk quota exceeded`) -- recovered by hand once the stale `.zwdb` files were
identified (via `ls -la --time-style=full-iso`, cross-checked against each run's own timeline) and removed.
  to treat a job as stopped-with-unknown-cause, not a single log-silence observation alone (
## `run_simulation` calls can queue with significant delay; a fast "success" response can be a cached prior result, not fresh work

Observed directly across cases 3 and 4 of the 20-case sweep: after a case finished, the *next*
`run_simulation` call for the following case would sometimes hit the harness's 300s client-side idle
timeout with **no corresponding `"Simulation started"` entry in `animas.log`** -- not because the
call was dropped, but because the backend was still processing the *previous* case's delayed internal
"done" bookkeeping (observed gap: the backend logged a case's own `"Simulation done"` event roughly
**15 minutes after** that case's actual RTL simulation had already finished and its result was fully
readable in `output/zsim.log`). A retry issued during this window can itself get silently queued rather
than rejected or immediately dispatched.

**Consequence observed once**: a `run_simulation` call returned a full, successful-looking response
(`elapsed_s: 12.5`, complete `output_tail` showing a finished case with correct scores) far too quickly
to be a genuine fresh ~10-minute RTL run -- this was the backend reporting an **already-completed result
from an earlier, nominally-"timed-out" call**, not confirmation that *this* call freshly ran anything.
Shortly afterward, a **second, genuinely new run of the same case silently started** (visible via a new
`SIM_BANNER` with the same `run_id` overwriting `output/zsim.log`), apparently a delayed dispatch of one
of the earlier calls that really had just been queued, not dropped.

**Practical consequence for this project**: a case's result must be captured from the tool call's own
returned `output_tail` text at the moment a genuinely-complete response is received (reconstructing the
log file from that captured text if necessary), rather than assumed to still be safely readable from the
shared `output/zsim.log` moments later -- a subsequent queued dispatch can overwrite it before a `cp`
completes. When a redundant duplicate dispatch of an already-verified case is detected in progress, the
safest response is to let it drain to completion (it reproduces the same deterministic result and does
not corrupt anything) rather than attempting to cancel it or immediately launching further work on top,
which would only compound the backlog.
