# Findings

Statements are labeled **observed**, **inferred**, or **unverified**. Evidence references point to logs/commands under this project.

## Environment

- **observed**: Host is Rocky Linux 9.8 (`uname -a`, `/etc/os-release`), x86_64, 88 CPUs, 124 GiB RAM, 102 GiB free on `/home`. Ample for a quantized dense model and multicycle RTL simulation of a few thousand to low-millions of cycles.
- **observed**: System Python is 3.9.25 with no system-wide `pip`; an isolated venv (`ml/venv`) was created and used for all Python ML work, per the prompt's explicit instruction to isolate the Python environment.
- **observed**: Network egress to github.com and pypi.org succeeds (HTTP 200 on plain GET/HEAD).
- **observed**: `riscv64-unknown-elf-gcc` (RISC-V GNU toolchain, release 2026.07.15, elf-multilib build) is available via `module load riscv-gnu-toolchain/elf-multilib/2026.07.15-elf` at `/edatools/opensrc/riscv-gnu-toolchain/2026.07.15/elf-multilib/bin/`. Not yet verified: that it actually compiles/links a `-march=rv32im -mabi=ilp32` bare-metal C++17 program without unresolved runtime symbols (next step).
- **observed**: Spike 1.1.1-dev is installed but non-functional on this host (ISS-001); no Verilator, Icarus Verilog, VCS, Xcelium, or ModelSim/Questa binary was found anywhere on `$PATH` or under `/edatools` (searched explicitly). Animas is therefore the only usable RTL simulator on this host, making ISS-002 (Animas MCP connectivity) the single highest-priority blocker to resolve.
- **observed**: `riscv-dv` 2026.08.27 is installed at `/edatools/opensrc/riscv-dv/2026.08.27` with its own venv; evaluated for use as the fixed-seed random-instruction generator required by prompt Section 6, as an alternative/complement to a custom generator. Usability not yet verified.

## Dataset

- **observed**: The WM-811K archive downloaded from `https://www.kaggle.com/api/v1/datasets/download/qingyi/wm811k-wafer-map` via `scripts/download_dataset.py` extracts to `data/raw/LSWMD.pkl`, 2,095,505,977 bytes, SHA-256 `1d04fccb3dd3176b276878b926b20fead7e077c5751e4d353ea9741a5e7b5c65`. This matches the hash independently recorded in the handoff package's `PACKAGE_CONTENTS.json`, which was generated before this implementation session touched the file.
- **unverified**: Actual pandas DataFrame schema (column names, `waferMap`/`failureType`/`trianTestLabel`/`lotName` fields, encoding of the 4 target classes) — pending pandas install in `ml/venv` (in progress at time of writing). Will be recorded here once inspected directly; prompt explicitly warns not to assume schema.

## Animas

- **observed**: Animas is a desktop application (`com.mifraltech.animaseda`, flatpak-packaged, versions 1.0.1/1.0.2/master installed) that, once launched with a valid `$DISPLAY`, starts a backend process exposing an MCP server over SSE at `http://localhost:27500/mcp/sse` (port derived from login name; falls back to a random port if that port is already bound by another instance under the same account).
- **observed**: The project's `.mcp.json` registers this SSE endpoint as the `animas` MCP server.
- **observed**: `project.apf` is Animas's project file format (JSON: `apf_version`, `project` metadata, `sources` list with `path`/`role`/`library`, `settings` including `top_module`, `sim_top`, `sim_tool`, `synth_tool`, `elab_mode`). A stale `project.apf` from an unrelated prior "test" project (counter.sv/counter_tb.sv, neither file present on disk) existed in this directory before this session; the Animas app itself pruned the missing sources automatically on launch. This file will be repointed at the real RTL/testbench sources once they exist.
- **blocked**: No `mcp__animas__*` tool call has yet succeeded (ISS-002); tool names/parameters/capabilities beyond what is visible in the tool schemas themselves (list_projects, get_project_info, get_zenith_help, check_project_paths, get_hierarchy, run_simulation, etc.) have not been exercised or confirmed against the real backend.
