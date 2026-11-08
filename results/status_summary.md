# Implementation status summary

Absolute project path: `/home/rmata/Documents/git/wafer_riscv_tflm`

This is a factual implementation record (prompt Section 9), not the formal
paper. It states measured results, failures, and incomplete acceptance
criteria plainly.

## FINAL RESULT (2026-11-08): all 20/20 RTL-vs-native cases match

A later finalization pass (same model, same frozen 20 fixed comparison
cases, same firmware source, no retraining and no easier inputs) launched
one new, complete, from-cycle-0 RTL simulation, run ID `full20_final_001`,
via a standalone Zenith invocation that bypasses the Animas MCP daemon
entirely (removing both the earlier wall-clock cap and the waveform-storage
problem described below). **The run completed on its own
(`$finish exit code 0` at simulated cycle 142,937,769, wall-clock 01:35:52)
with all 20 cases present exactly once, and a strict, independently-written
acceptance checker (`scripts/check_final_run.py`) confirms an exact match
of all four integer scores and the predicted class, for every one of the 20
cases, against the native TFLM oracle** (`exit_code 0`,
`"ACCEPTED: ALL 20/20 CASES MATCH"`). Complete evidence is in
`results/final_run_evidence/` (see its `README.md`); the authoritative
`results/rtl_comparison.json` now reflects this run alone, not merged with
any earlier historical partial evidence (preserved separately in
`results/rtl_comparison_partial_per_case_runs.json`).

This supersedes every "incomplete"/"not met"/"0 of 20"/"blocked on Animas
access" statement below, which describes the state at an earlier point in
the same project before the launch/storage/checker problems described in
those sections were fixed. The rest of this document is left intact as the
real historical record of how that state was reached and resolved; readers
wanting only the final number should stop at this section.

**The classifier's own quality limitation is unchanged by this RTL result**
and is reported separately: quantized test macro-F1 = 0.7709 (below the
0.85 target). On these 20 fixed cases the classifier itself is correct on
16/20 and wrong on 4 (case_id 0, 11, 15, 16) -- the RTL reproduces the
native oracle's output exactly even where that output is a
misclassification. Successful RTL verification does not change this
pre-existing ML result.

## Acceptance criteria (prompt Section 11)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Data availability | met | `data/raw/dataset_provenance.json`, SHA-256 verified |
| 2 | Processor tests passing | **met** | `results/cpu_verification.json`: 9/9 directed tests pass; 1100/1100 random instructions exact-match an independent reference model |
| 3 | Trained/quantized model | met (produced; quality target not met) | `results/ml_metrics.json` |
| 4 | Linked firmware | met | `build/firmware/firmware.elf`, fits 1 MiB RAM budget with 64 KiB stack reserved (`results/memory_usage.json`) |
| 5 | RTL inference (real TFLM Invoke() on RTL) | **met** | all 20 cases' `Invoke()` completed on RTL in run `full20_final_001`; see `results/final_run_evidence/` |
| 6 | 20/20 RTL vs. native comparisons | **met** | `results/rtl_comparison.json`: 20/20 matched, strict checker exit code 0 |
| 7 | Measured ML metrics | met | `results/ml_metrics.json` |
| 8 | Demonstration | met (final RTL outputs, including misclassifications) | `results/demo.html` |
| 9 | Complete documentation handoff | met | `docs/handoff/` |

## Measured results

- **Dataset**: WM-811K, 811,457 rows total; 162,598 rows in the 4 target
  classes; 4000 samples selected (1000/class, seed 2026), lot-aware
  70.03/15.00/14.98 split, 0 lots spanning splits, 0 cross-split duplicate
  maps.
- **Model**: Model A (hidden=16) and Model B (hidden=32) both trained per
  the fixed protocol; Model B chosen by quantized validation macro-F1
  (0.7681 vs. 0.7538). **Quantized test macro-F1 = 0.7709, below the 0.85
  target.** Reported as-is; no threshold, label, or test-set change was
  made. Model is fully int8 (input/output and both operators: RESHAPE,
  FULLY_CONNECTED x2). `models/model_B_int8.tflite`,
  SHA-256 `7e11c5faea02c99464d6f939c3b10067bd93a6d72d5e650797f6249755ba69ea`.
- **Processor verification**: RV32IM multicycle core (base integer + the
  complete M extension), written from scratch in SystemVerilog. 9 directed
  tests cover ALU ops, x0, sign extension, shifts, signed/unsigned
  compares, branches, JAL/JALR, byte/halfword/word loads/stores with
  write-strobe isolation, memory wait-states (explicitly injected), the
  complete M extension including division-by-zero and signed-overflow
  edge cases, 4 distinct error-halt causes (illegal instruction,
  misaligned load, misaligned store, misaligned PC, ECALL), and a
  compiled C program (recursion, arrays, loops). All 9 pass. A 1100-
  instruction fixed-seed (2026) random program, covering the ALU/OP-IMM/
  M-extension instruction space, retires identically on RTL and an
  independent Python ISA reference model (0 mismatches) — Spike could not
  be used (missing system libraries on this host; see `docs/issues.md`
  ISS-001). Two real RTL bugs were found and fixed via this test
  infrastructure during the session (an ALU SRA 1-bit-truncation cast
  bug, and an MMIO address-decode field-width bug); see `docs/issues.md`.
- **Memory**: firmware text+data+bss = 894,941 bytes; fits within the
  983,040 bytes available before the required 64 KiB reserved stack
  (headroom 88,099 bytes). Tensor arena: 8192 bytes reserved, 5216 bytes
  measured peak use (via the native reference, same model/arena-size
  configuration as the firmware).
- **TFLM integration**: tflite-micro pinned at commit
  `4eaa491c1c8dedd9a3baf421968afd0d5b82f6aa`. Native x86 reference oracle
  built from the same source tree, reference kernels, and model bytes;
  ran all 20 deterministic comparison cases successfully
  (`build/native_reference/output.jsonl`). Bare-metal firmware built
  against the same source tree with newlib + libstdc++ (not `-nostdlib`:
  TFLM needs `memcpy`/`memset`/`new`/`delete`). A real bug was found and
  fixed here too: function-local C++ statics with non-trivial
  constructors silently failed to construct under this
  toolchain/ABI-target combination's guarded-init codegen; moving the
  TFLM objects to file (global) scope, constructed via this project's own
  `crt0.S` `.init_array` loop, fixed it (see `docs/issues.md`).
- **RTL inference (20-case comparison)**: **incomplete.** The firmware
  correctly runs on RTL through model initialization and the start of
  `Invoke()` for case 0 (MMIO_MEASURE=1 observed at RTL cycle 351185). A
  bounded run (`+MAXCYCLES=5000000`) reached that cycle limit still inside
  case 0's `Invoke()` — establishing that **at least 5,000,000 - 351,185 =
  4,648,815 RTL cycles elapsed inside `Invoke()` without it completing**
  (the first FULLY_CONNECTED layer alone is 65,536 multiply-accumulate
  operations, each needing a ~33-cycle sequential multiply on this
  non-pipelined core). This is a corrected figure: an earlier version of
  this document stated Invoke() "requires well over 5,000,000 RTL
  cycles", which conflated the 351,185 pre-Invoke setup cycles with time
  spent inside Invoke() itself — see `docs/issues.md` ISS-004's
  correction note. No upper bound on Invoke()'s true total length is
  established by this run. The full 20-case firmware loop did not reach a
  `MMIO_STATUS` write within the wall-clock time available in this
  session. **0 of 20 cases are confirmed to agree with the native
  reference.** This is the one unmet acceptance criterion; see
  `docs/handoff/limitations_and_open_questions.md` for the full account,
  including real Animas/Zenith tool-connectivity behavior encountered
  while orchestrating long-running simulation jobs.

## Failures and fixes (both preserved with evidence; see docs/issues.md)

1. Spike (ISA reference simulator) cannot run on this host (missing
   `libboost_regex.so.1.66.0`/`libboost_system.so.1.66.0`, no compatible
   version anywhere on the system) — worked around with an independent
   from-scratch Python ISA reference model instead (documented prompt
   fallback).
2. RTL bug: ALU `SRA` used an erroneous `logic'(...)` cast that truncated
   the arithmetic-shift result to 1 bit. Found via directed test 001's
   first real RTL run; fixed in `rtl/rv32im_alu.sv`; confirmed by rerun.
3. RTL bug: MMIO `STATUS` register's byte-offset field was declared 1 bit
   too narrow, silently aliasing `STATUS` writes onto `TX`. Caught by
   Zenith's own compiler warnings before any test ran; fixed in
   `rtl/mmio.sv`.
4. Host environment bug: the RV32IM GNU toolchain's `cc1`/`cc1plus`
   couldn't run (missing `libmpfr.so.4`/`libgmp.so.7`); fixed via a small
   `LD_LIBRARY_PATH` shim to exact-SONAME copies found elsewhere on the
   host (Xilinx Vivado's bundled libraries), without touching the
   toolchain installation. See `docs/decisions.md` D-004.
5. Firmware bug: C++ function-local `static` objects with non-trivial
   constructors inside `main()` silently failed to construct (the
   TFLM `MicroAllocator`'s guard field read as already-set on the very
   first use). Fixed by moving the TFLM objects to global scope,
   constructed unconditionally via this project's own `crt0.S`
   `.init_array` loop. See `docs/issues.md` and `sw/app/main_firmware.cc`.
6. Build-script bugs (shell `set -e` + `pipefail` interacting badly with
   `grep -v` filtering all input; piping `module load` through anything
   runs it in a subshell, losing its `PATH` changes) — fixed in
   `scripts/env.sh`.

## What was NOT done / explicitly out of scope

- No synthesis, timing closure, FPGA bitstream, or power/area result.
- No real silicon or physical hardware execution; Animas/Zenith RTL
  simulation only.
- No claim of reliability across repeated independent runs — this is one
  autonomous attempt.
- Processor verification used a from-scratch Python reference model, not
  Spike or Sail (Spike present but non-functional on this host).

## Continuation session (2026-11-07/08): infrastructure added, blocked on Animas access

A later continuation picked up this exact state (verified against the files
above, not re-derived) and made progress that does not change any
acceptance-criteria row in the table above, pending real RTL access:

- Added compile-time `CASE_START`/`CASE_COUNT` range selection to
  `sw/app/main_firmware.cc` (default unchanged: all 20 cases; range
  validated via `static_assert`; global case-ID numbering preserved; no
  ground truth embedded) and matching support in `scripts/build_firmware.sh`
  (per-config ELF under `build/firmware/configs/<tag>/`, shared TFLM object
  cache reused across configs, `firmware_config.json` provenance record per
  build). Confirmed the default config's ELF is byte-identical
  (sha256 `622d1816...`) to the previously recorded build.
- Implemented the real `scripts/run_rtl_test.py` (log-to-run-record parser)
  and `scripts/compare_results.py` (aggregate checker) that earlier source
  comments referenced without either existing. Self-tested against
  synthetic logs (match, not-run, duplicate-conflict, provenance-conflict
  cases) -- see `docs/decisions.md` D-008 and `docs/experiments.jsonl`
  RUN-checker-scripts-validation-001.
- Authored `tb/ram_model_lite.sv` (a lightweight RAM testbench model) and
  wired compile-time selection into `tb/soc_tb.sv`, plus a `SIM_BANNER`,
  `HEARTBEAT`, and trace-independent retired-instruction counter -- see
  `docs/decisions.md` D-007. **Not yet validated against the original RAM
  model or against real RTL output.**
- Copied the native TFLM oracle's per-case output to a durable
  `results/native_reference/` directory (previously only under the ignored
  `build/` tree), with independently re-verified SHA-256 provenance.
- Corrected an overclaim in this file and in `docs/issues.md`/
  `results/rtl_comparison.json`/`docs/handoff/README.md`: the bounded probe
  established **at least 4,648,815 RTL cycles elapsed strictly within
  `Invoke()`** without completing (measured from `MMIO_MEASURE=1` at cycle
  351185 to `SIM_TIMEOUT` at cycle 5,000,000), not that `Invoke()` as a
  whole "requires more than 5,000,000 cycles."
- `mcp__animas__*` tool calls (`list_projects`, `get_zenith_help`) returned
  `MCP error -32602: Invalid request parameters` throughout this
  continuation, even after the Animas application was independently
  restarted (by an action outside this agent's control) -- see
  `docs/issues.md` ISS-002 recurrence #3. No further Animas restart was
  attempted. **All work requiring real RTL simulation (ram_model_lite
  validation, a bounded throughput benchmark, completing case 0's
  `Invoke()`, and the remaining 19-case sweep) remains blocked on this
  external connectivity issue as of this writing.**

## Finalization session (2026-11-08): Animas access restored, run completed

A later finalization session resolved the blockers described in the
continuation section above and obtained the final result stated at the top
of this document:

- **Animas MCP connectivity was restored** (no longer `-32602`); `run_simulation`
  tool calls worked again. However, two further problems were found and
  fixed before a trustworthy full run was possible:
  - `waveform_mode: "off"` was found **not reliably sufficient** to prevent
    a large ZWDB waveform file from being generated (an 8.1 GiB stale file
    from an earlier run was found and removed after confirming via
    `/proc/*/fd` that no process had it open -- see `docs/storage_cleanup.md`).
    Fixed by discovering and validating a standalone invocation of the same
    installed Zenith binary (`flatpak run --branch=1.0.2 --command=zenith
    com.mifraltech.animaseda ...`, no `--zwdb` argument at all), confirmed
    via pilot runs to produce zero waveform output and functionally
    identical results (3 regression tests matching previously-recorded
    cycle counts exactly).
  - A reported "wall-clock cap (30 min)" was tracked down to an
    Animas-backend-level `timeout_seconds` on the `run_simulation` tool
    call, not a Zenith simulator limit (confirmed via the installed
    binary's own `--help`: Zenith has no wall-clock-seconds flag). The same
    standalone invocation above also removes this limit entirely, since a
    backgrounded host process has no such cap.
  - `scripts/compare_results.py` was found to always exit 0 regardless of
    actual match count (a reporting bug, not a simulation bug) -- fixed to
    exit non-zero on any incomplete/mismatched/provenance-conflicting
    result, and a new, much stricter single-run acceptance checker,
    `scripts/check_final_run.py`, was written and validated against
    synthetic good/malformed logs before being trusted on real data.
  - `scripts/build_firmware.sh`'s object-reuse check was existence-only
    (could silently keep a stale object after a source change); fixed to
    be mtime-aware. One full clean rebuild from an empty `build/firmware/`
    confirmed a byte-identical ELF hash to every prior build
    (`622d1816...`), establishing reproducibility rather than assuming it.
- With these fixed, **one new, complete, unlimited-wall-clock run**
  (`full20_final_001`) was launched from cycle 0 against the exact same
  frozen firmware/model/20-case manifest, using the validated lightweight
  RAM model (`ram=lite` confirmed in the run's own `SIM_BANNER`) and
  `TRACE=0`. It completed in 142,937,769 simulated cycles / 01:35:52
  wall-clock, with all 20 cases present exactly once and an exact match
  against the native oracle for every case (`scripts/check_final_run.py`
  exit code 0). Full evidence: `results/final_run_evidence/`.
- The 8/20 (and earlier 7/20) historical partial-match evidence from
  per-case runs made during the still-blocked period is preserved
  separately in `results/rtl_comparison_partial_per_case_runs.json` and was
  **not** merged into this final 20/20 result -- the final result comes
  entirely from the single `full20_final_001` run.

## Entry points for the next (documentation) stage

- `docs/handoff/README.md`
- `docs/handoff/documentation_instructions.md`
