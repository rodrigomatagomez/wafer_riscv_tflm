# Documentation handoff: entry point

**Project root:** `/home/rmata/Documents/git/wafer_riscv_tflm`

## FINAL RESULT (2026-11-08): all 20/20 RTL-vs-native cases match

A finalization session completed after the two update paragraphs below
resolved every blocker they describe and obtained the actual final result:
run `full20_final_001` (standalone Zenith invocation, no waveform capture,
no Animas-daemon-level wall-clock cap) completed all 20 cases from cycle 0
(142,937,769 simulated cycles, 01:35:52 wall-clock, `$finish` exit code 0).
`scripts/check_final_run.py` -- a strict, independently-written single-run
acceptance checker, validated against synthetic malformed/good logs before
being trusted on real data -- confirms exit code 0: all four integer scores
and the predicted class match the native oracle exactly, for every one of
the 20 cases. **The 20-case RTL-vs-native acceptance criterion, the one
unmet criterion described below, is now met.** Full evidence:
`results/final_run_evidence/` (see its own `README.md`). The model's own
quality limitation (quantized test macro-F1 = 0.7709, below the 0.85
target) is unchanged and remains separately reported -- RTL correctness and
model quality are independent claims; 4 of the 20 fixed cases are
misclassifications that the RTL reproduces exactly from the native oracle.
`results/rtl_comparison.json` now reflects this single final run only, not
merged with the historical partial evidence described below (preserved
separately in `results/rtl_comparison_partial_per_case_runs.json`).

The two paragraphs immediately below are left intact as the accurate
historical record of the project's state before this finalization; they
describe exactly the blockers that were then fixed (see `docs/decisions.md`
D-009/D-010 and `docs/issues.md` ISS-008/ISS-009).

## Final implementation state (one paragraph) -- HISTORICAL, see FINAL RESULT above

A new RV32IM multicycle RISC-V core was designed and written from scratch in
SystemVerilog, compiles/elaborates cleanly in Animas/Zenith, and passes a
9-test directed suite plus a 1100-instruction fixed-seed random comparison
against an independent Python ISA reference model with zero mismatches (Spike
is installed but non-functional on this host; see docs/issues.md ISS-001). A
small dense wafer-pattern classifier (4 classes) was trained on real WM-811K
data and quantized to int8; its quantized test macro-F1 (0.7709) did not meet
the 0.85 target, and this was preserved honestly rather than altered. TFLM was
pinned at a specific commit and used to build both a native x86 reference
oracle (ran all 20 comparison cases) and bare-metal RV32IM firmware. The
firmware was built, fits the memory budget, and — after fixing a real C++
static-initialization bug — correctly boots on the RTL-simulated processor,
initializes TFLM, and begins real `Invoke()` execution (confirmed at RTL cycle
351185). **The full 20-case RTL-vs-native comparison did not complete within
the session's wall-clock time** (0 of 20 cases finished; a bounded probe run
reached its 5,000,000-cycle limit still inside case 0's `Invoke()`, after
Invoke() had already started at cycle 351185 — establishing at least
4,648,815 RTL cycles elapsed strictly within `Invoke()` without completing,
not that `Invoke()` as a whole needs more than 5,000,000 cycles; see
`docs/issues.md` ISS-004's correction note). This is the project's one unmet
acceptance criterion.

## Continuation update (2026-11-07/08): infrastructure added, then blocked -- HISTORICAL

A later continuation session added (but could not yet exercise against real
RTL, due to an Animas MCP connectivity blocker explained below):
compile-time `CASE_START`/`CASE_COUNT` firmware range selection
(`sw/app/main_firmware.cc`, `scripts/build_firmware.sh`), the real
`scripts/run_rtl_test.py`/`scripts/compare_results.py` checker scripts
(previously referenced by name in comments without existing), and
`tb/ram_model_lite.sv` (a lightweight, not-yet-validated alternative RAM
testbench model). It also moved the native oracle's output to a durable
`results/native_reference/` directory and corrected an overclaimed cycle
figure (see `results/status_summary.md`'s "Continuation session" section
and `docs/decisions.md` D-007/D-008 for full detail).
`mcp__animas__*` tool calls failed with `MCP error -32602: Invalid request
parameters` throughout this continuation, confirmed NOT fixed by an Animas
application restart that happened independently of this agent (see
`docs/issues.md` ISS-002 recurrence #3). **This connectivity issue was
resolved by the time of the finalization session** (see "FINAL RESULT"
above) -- `ram_model_lite.sv` is now validated and was used in the final
accepted run, and the checker scripts have now been exercised against real
final-run data, not just synthetic logs.

## Authoritative result files (read these, not the development log, for numbers)

- `results/ml_metrics.json` — model metrics (float and int8, both configs).
- `results/cpu_verification.json` — processor test results.
- `results/random_instruction_comparison.json` — 1100-instruction comparison.
- `results/memory_usage.json` — program/arena/stack memory accounting.
- `results/native_reference/output.jsonl` + `provenance.json` — durable copy of the native oracle's per-case output (also still present under `build/native_reference/`).
- `results/rtl_comparison.json` — **20-case RTL-vs-native status: 20/20 matched** (run `full20_final_001`; see `results/final_run_evidence/`).
- `results/demo.html` — static demonstration page with the final RTL outputs for all 20 cases, including the 4 cases where the model itself misclassifies (marked in red).
- `results/status_summary.md` — the factual implementation record (see its "FINAL RESULT" and "Finalization session" sections).

## Stale results that must NOT be used

- `results/rtl_comparison_partial_per_case_runs.json` (7/20, then 8/20 matched across several historical per-case runs) and the earlier `full20_attempt_001` run (produced zero usable output -- found stalled with an empty log, terminated, see `docs/issues.md` ISS-006 continuation) are **historical evidence only**. The current `results/rtl_comparison.json` reflects the single final run `full20_final_001` (20/20) and must not be confused with, or treated as merged from, these earlier states.
- This remains the first and only full training/quantization run
  (`RUN-train-quantize-001`), and the only tflite-micro commit used
  throughout (`4eaa491c1c8dedd9a3baf421968afd0d5b82f6aa`, see
  `third_party/TFLM_VERSION.txt`). The firmware has been built three times
  (`RUN-firmware-build-001`, `RUN-firmware-build-002` which added the
  `CASE_START`/`CASE_COUNT` feature, and one clean rebuild during
  finalization) -- all three produced the byte-identical ELF hash
  `622d1816...`, confirming reproducibility rather than assuming it.

## Recommended reading order

1. `docs/handoff/documentation_instructions.md` (project-specific instructions
   for the next AI session — read this before anything else).
2. This file.
3. `docs/handoff/claims_evidence.csv`.
4. `docs/handoff/limitations_and_open_questions.md`.
5. `docs/development_log.jsonl`, `docs/decisions.md`, `docs/findings.md`,
   `docs/issues.md`, `docs/experiments.jsonl`.
6. The result files listed above.

## Dev directory vs. git checkout

The active development directory used throughout this project,
`/home/rmata/Documents/git/wafer_riscv_tflm`, is **not itself a git
repository** (`git status` there returns "fatal: not a git repository").
A separate checkout, `/home/rmata/Documents/git/wafer_riscv_tflm_1`, **is**
a git repository (`origin/main`, HEAD was at commit `af708fc7` -- "Save
project status with compressed baseline evidence" -- before this
finalization's sync) and is the only one of the two with real git history.
Animas's active project in this session points at the dev directory, not
the git checkout, so all simulation work in this project correctly targets
the dev directory's files.

As the final step of this finalization session, the following intended
deliverables (the final-run evidence and the documents/scripts updated to
reflect it) were copied from the dev directory into the git checkout,
without touching its `.git` directory or any of its existing history:

- `README.md`, `results/rtl_comparison.json`, `results/status_summary.md`,
  `results/demo.html`
- `docs/decisions.md`, `docs/issues.md`, `docs/development_log.jsonl`,
  `docs/experiments.jsonl`, `docs/storage_cleanup.md`
- `docs/handoff/README.md`, `docs/handoff/claims_evidence.csv`,
  `docs/handoff/limitations_and_open_questions.md`,
  `docs/handoff/documentation_instructions.md`,
  `docs/handoff/final_artifact_manifest.json`
- `scripts/check_final_run.py` (new), `scripts/compare_results.py`,
  `scripts/run_rtl_test.py`, `scripts/build_firmware.sh`
- `results/final_run_evidence/` (the complete final-run evidence directory,
  ~15 MiB)

**Deliberately NOT synced** (regenerable, gitignored in that checkout via
its `/build/` and `/results/**/*.log` rules, or genuinely scratch/historical
material outside this finalization's deliverable set): `build/`,
`output/`, the per-case historical logs under `results/rtl_logs/` (the
8/20 partial-match evidence they back,
`results/rtl_comparison_partial_per_case_runs.json`, was already present
in the git checkout from an earlier phase and was not re-synced here since
it did not change), and `results/final_run_evidence/full20_final_001_live.log`
duplicate of the raw log (the directory's own compressed copy,
`full20_final_001_raw_log.txt.gz`, was synced instead).

This sync copied files only -- **no `git add` or `git commit` was
performed**, per this session's git-safety practice of never committing
without an explicit, separate user instruction. Run `git status` in
`/home/rmata/Documents/git/wafer_riscv_tflm_1` to see the resulting
modified/untracked file list before deciding whether and how to commit it.

## Separation of implementation evidence vs. later writing

Everything under `docs/`, `results/`, `rtl/`, `tb/`, `sw/`, `ml/`,
`scripts/`, `build/`, and `models/` is implementation evidence produced
during Stage 1 (this autonomous session). No formal paper, slide deck, or
polished narrative was written during this stage, per the prompt's explicit
instruction to keep Stage 1 and Stage 2 (writing) separate. The next session
should write into a new `documentation_output/`-style location (per
`documentation_ai_prompt.txt`) and must not alter any file listed above
except to append a note if it discovers an error in this handoff.
