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
