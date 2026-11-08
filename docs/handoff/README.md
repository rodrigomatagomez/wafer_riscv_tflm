# Documentation handoff: entry point

**Project root:** `/home/rmata/Documents/git/wafer_riscv_tflm`

## Final implementation state (one paragraph)

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

## Continuation update (2026-11-07/08): infrastructure added, still blocked

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
and `docs/decisions.md` D-007/D-008 for full detail). **None of this
changes the 20-case RTL-vs-native status (still 0/20) or the ML quality
result** -- both remain exactly as stated in the paragraph above.
`mcp__animas__*` tool calls failed with `MCP error -32602: Invalid request
parameters` throughout this continuation, confirmed NOT fixed by an Animas
application restart that happened independently of this agent (see
`docs/issues.md` ISS-002 recurrence #3) -- a later session should check
whether that connectivity issue has been resolved before anything else.

## Authoritative result files (read these, not the development log, for numbers)

- `results/ml_metrics.json` — model metrics (float and int8, both configs).
- `results/cpu_verification.json` — processor test results.
- `results/random_instruction_comparison.json` — 1100-instruction comparison.
- `results/memory_usage.json` — program/arena/stack memory accounting.
- `results/native_reference/output.jsonl` + `provenance.json` — durable copy of the native oracle's per-case output (also still present under `build/native_reference/`).
- `results/rtl_comparison.json` — **20-case RTL-vs-native status: incomplete, 0/20**.
- `results/demo.html` — static demonstration page (RTL columns explicitly marked not completed).
- `results/status_summary.md` — the factual implementation record.

## Stale results that must NOT be used

None known as of this handoff — this is the first and only full training/
quantization run (`RUN-train-quantize-001`), and the only tflite-micro
commit used throughout (`4eaa491c1c8dedd9a3baf421968afd0d5b82f6aa`, see
`third_party/TFLM_VERSION.txt`). The firmware has been built twice
(`RUN-firmware-build-001` then `RUN-firmware-build-002`, which only added
the `CASE_START`/`CASE_COUNT` feature and reuses the identical model/TFLM
sources -- the default-config ELF hash is unchanged, `622d1816...`); neither
build has yet completed a full RTL inference. If a later session reruns any
of these, mark the earlier run IDs superseded explicitly rather than leaving
ambiguity.

## Recommended reading order

1. `docs/handoff/documentation_instructions.md` (project-specific instructions
   for the next AI session — read this before anything else).
2. This file.
3. `docs/handoff/claims_evidence.csv`.
4. `docs/handoff/limitations_and_open_questions.md`.
5. `docs/development_log.jsonl`, `docs/decisions.md`, `docs/findings.md`,
   `docs/issues.md`, `docs/experiments.jsonl`.
6. The result files listed above.

## Separation of implementation evidence vs. later writing

Everything under `docs/`, `results/`, `rtl/`, `tb/`, `sw/`, `ml/`,
`scripts/`, `build/`, and `models/` is implementation evidence produced
during Stage 1 (this autonomous session). No formal paper, slide deck, or
polished narrative was written during this stage, per the prompt's explicit
instruction to keep Stage 1 and Stage 2 (writing) separate. The next session
should write into a new `documentation_output/`-style location (per
`documentation_ai_prompt.txt`) and must not alter any file listed above
except to append a note if it discovers an error in this handoff.
