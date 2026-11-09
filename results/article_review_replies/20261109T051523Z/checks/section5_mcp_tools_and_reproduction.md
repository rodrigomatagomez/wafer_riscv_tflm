# Section 5 — MCP tools actually invoked vs. merely discovered; reproduction

## Tools with a real invocation + evidence pointer (log/event citation)

| Tool | Evidence pointer | What it actually showed |
|---|---|---|
| `list_projects` | `docs/development_log.jsonl`, `docs/issues.md:28`; live re-run 2026-11-09 (this package) | returns `active_project` with a real portal `root_path` |
| `get_project_info` | `docs/development_log.jsonl`, `docs/issues.md` | project config / top module / registered sources |
| `get_zenith_help` | `docs/development_log.jsonl`, `docs/issues.md:131` (ISS-009); live re-run 2026-11-09 | confirmed no wall-clock-seconds flag exists in Zenith |
| `run_simulation` | `docs/development_log.jsonl` (many events), `docs/decisions.md`, `docs/experiments.jsonl` | launched many real jobs; both `ui_remote_control` and `headless` execution modes observed |
| `get_last_sim_result` | `docs/development_log.jsonl`, `docs/storage_cleanup.md`, `docs/issues.md` | `log_line_count`, `end_time` fields used to diagnose stalls |
| `get_sim_diagnostics` | `docs/development_log.jsonl:37` (E038) — "confirmed via `get_sim_diagnostics` that zero errors/fatals were ever raised" | real error/fatal counts for a real run |
| `read_simulation_log` | `docs/issues.md:29` — confirmed "SANITY PASS" text in the real log | raw `zsim.log` text |
| `read_source_file` | `docs/issues.md:29` — confirmed a testbench edit was correctly on disk | raw source-file text |
| `set_sim_options` | `docs/animas_capabilities.md:200` — "Observed directly: two separate runs launched with `set_sim_options(waveform_mode=\"off\")`" | confirmed `waveform_mode` take-effect |

## Tools discovered/registered but **not** confirmed exercised

Quoted directly, `docs/animas_capabilities.md:126`: "`search_simulation_log`,
`summarize_assertion_failures` were registered but not yet needed for the
directed-test scale used here."

`docs/findings.md:24` (from the early ISS-002-blocked period): "tool
names/parameters/capabilities beyond what is visible in the tool schemas
themselves (`list_projects`, `get_project_info`, `get_zenith_help`,
`check_project_paths`, `get_hierarchy`, `run_simulation`, etc.) have not
been exercised or confirmed against the real backend." No later entry in
`docs/development_log.jsonl` records an actual `check_project_paths` or
`get_hierarchy` call with a real result, so both remain in this
"documented capability, not confirmed tested" bucket, along with:
`get_elab_diagnostics`, `read_simulation_log_lines`, `add_source_file`,
`remove_source_file`, `set_file_role`, `set_sim_top`, `set_rtl_top`,
`overwrite_source_file`, `patch_source_file`, `read_source_file_lines`,
`register_existing_file`, `list_source_files`, `list_all_files`, and the
entire waveform/signal-query family (`list_signals`,
`load_signals_to_waveform`, `setup_debug_view`, `screenshot_waveform`,
`screenshot_schematic`, `query_signals_at_time`, `query_signals_window`,
`query_signals_at_clock_edge`, `get_signal_stats`,
`find_signal_transitions`, `find_signals_changed_between`,
`find_signals_with_value`, `find_value_in_packed_bus`, `get_clock_info`,
`get_timescale`, `list_zwdb_scopes`, `set_waveform_view`,
`set_active_waveform_tab`, `delete_waveform_tab`, `list_tab_signals`,
`clear_tab_markers`, `add_waveform_marker`, `set_emphasis_rules`).

This split is not a judgment that the un-exercised tools don't work -- only
that this project never needed waveform-level debugging (its evidence is
captured via structured log markers, per
`docs/animas_capabilities.md:120-127`'s own stated reason), so no
synthesis/waveform result should be read as validated.

## Final standalone reproduction procedure (as actually used, D-009)

1. Have the Animas GUI open with this project (grants the portal access);
   call `mcp__animas__list_projects` to read the current
   `active_project.root_path` -- a live, this-session value, e.g.
   `/run/flatpak/doc/d6f0a558/wafer_riscv_tflm`. **This exact hash is not
   guaranteed stable**: it is assigned by `xdg-document-portal` per grant,
   and may change on an Animas restart, host reboot, or new portal grant.
   Always re-read it via `list_projects` immediately before use rather than
   hard-coding a previously observed value.
2. Invoke the installed Zenith binary standalone, inside the Flatpak
   sandbox, backgrounded as a plain host process (bypasses the Animas MCP
   daemon and its `timeout_seconds`/silent-flag-dropping behavior
   entirely):
   ```
   flatpak run --branch=1.0.2 --command=sh com.mifraltech.animaseda -c \
     "cd '<portal_root_path>' && zenith <rtl+tb .sv files> -top soc_tb \
      [+define+RAM_LITE] +MEMFILE=<portal-relative path> +MAXCYCLES=<n> \
      +TRACE=<0|1> +RUNID=<id> [+READYWAIT=] [+RANDWAIT=] [+FIXEDLAT=] \
      [+HEARTBEAT=] [--seed <N>]" > <logfile> 2>&1
   ```
3. Omit `--zwdb` entirely to avoid ZWDB generation (confirmed: zero
   `.zwdb` files created for any of the runs in this package).
4. Before trusting any run's result, grep its own output for `SIM_BANNER`
   and verify every field (`ram=`, `fixedlat=`, `readywait=`, `randwait=`)
   matches what was intended -- this project's own prior evidence
   (`ramlite_val_e/f/g`) shows a mismatch can otherwise go unnoticed.

Confirmed live (2026-11-09, this package): the portal path above
(`/run/flatpak/doc/d6f0a558/wafer_riscv_tflm`) is **not** visible from an
ordinary host shell (`ls` on it fails with "No such file or directory")
-- it is only resolvable from inside the Flatpak sandbox (e.g. through
`flatpak run --command=sh ... -c "ls <path>"`), confirming this is a
sandbox-scoped FUSE mount, not a regular host path.

## `synth_tool` caveat

A `synth_tool` (`yosys`) is referenced as configured/available in prior
project documentation, but no synthesis run is recorded anywhere in
`docs/development_log.jsonl`, `docs/experiments.jsonl`, or `results/`. No
synthesis result (timing, area, LUT/cell count) should be inferred from
the mere presence of this configuration -- there is no evidence any
synthesis job was ever executed.
