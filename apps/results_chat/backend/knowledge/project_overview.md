# Project overview: wafer_riscv_tflm (for the results-chat assistant)

This is a concise, citation-dense synthesis written specifically to ground
this chat assistant's open-ended answers. It is NOT a new primary source of
evidence -- every claim here points to the actual authoritative file. If
this summary and a cited file ever disagree, the cited file is correct;
treat that as a bug in this summary, not in the file.

## What was built

A from-scratch RV32IM RISC-V processor core (SystemVerilog, `rtl/`),
simulated in Animas/Zenith, running real TensorFlow Lite Micro (pinned
commit) int8 inference to classify WM-811K wafer-map defect patterns into
4 classes (Center, Edge-Ring, Scratch, none). [README.md intro;
docs/handoff/README.md "Final implementation state"]

## Architecture

- **Processor**: RV32IM multicycle core -- base integer ISA plus the
  complete M extension (MUL/MULH/MULHSU/MULHU/DIV/DIVU/REM/REMU), written
  from the public ISA spec without reading any existing core.
  [rtl/rv32im_core.sv, rtl/rv32im_alu.sv, rtl/rv32im_muldiv.sv,
  rtl/rv32im_regfile.sv; docs/handoff/claims_evidence.csv C009]
- **System**: `rtl/mmio.sv` (memory-mapped I/O: TX, STATUS, MEASURE,
  PREDICTED_CLASS registers used by the firmware to report results) and
  `rtl/soc_top.sv` (top-level integration). [docs/handoff/claims_evidence.csv C010]
- **Testbench**: `tb/soc_tb.sv` drives the core against a RAM model
  (`tb/ram_model.sv`, and a validated lightweight alternative
  `tb/ram_model_lite.sv` selectable via `+define+RAM_LITE`) and emits
  structured log markers (`SIM_BANNER`, `HEARTBEAT`, `MMIO_*`,
  `MMIO_PREDICTED_CLASS`) that downstream scripts parse. [docs/decisions.md D-007]
- **Firmware**: bare-metal C++ (`sw/app/main_firmware.cc`), built with
  `crt0.S` + newlib + libstdc++ (TFLM needs `memcpy`/`new`/`delete`),
  linking the pinned-commit TFLM reference kernels and the quantized model
  embedded as a C array. [README.md Requirements/Reproduction step 7;
  docs/decisions.md D-004 for a toolchain-linkage bug fix]
- **Native x86 reference oracle**: the same TFLM source tree and model
  bytes, built for the host instead of RV32, used as the ground truth for
  RTL-vs-native comparison. [README.md Reproduction step 6;
  results/native_reference/provenance.json]

## Verification methodology

- **Processor**: 9 directed tests (ALU ops, x0, sign extension, shifts,
  compares, branches, JAL/JALR, byte/halfword/word loads/stores with
  write-strobe isolation, injected memory wait-states, the complete M
  extension incl. div-by-zero/signed-overflow, 4 distinct error-halt
  causes, a compiled C program) -- all pass. Plus a 1100-instruction
  fixed-seed (2026) random program compared instruction-by-instruction
  against an independent Python ISA reference model (`scripts/isa_reference_model.py`,
  used instead of Spike, which is installed but non-functional on this
  host) -- 0 mismatches. Two real RTL bugs were found and fixed via this
  infrastructure (ALU SRA truncation; MMIO address-decode width).
  [results/cpu_verification.json; docs/decisions.md D-002]
- **RTL-vs-native (the main experiment)**: 20 fixed comparison cases (5
  per class, selected by sample_id order within the test split, after the
  model was frozen, no cherry-picking) are run through the firmware on the
  RTL-simulated processor and compared against the native oracle. The
  final, accepted run is `full20_final_001`: all 20 cases' Invoke() calls
  completed, and `scripts/check_final_run.py` (a strict, independently-
  written single-run acceptance checker, validated against synthetic
  logs before trusting it on real data) confirmed an exact match of all
  four integer scores and the predicted class for every case, exit code 0.
  [results/final_run_evidence/; results/rtl_comparison.json;
  README.md "Final result"; docs/decisions.md D-009, D-010]

## Dataset and preprocessing

- **Dataset**: WM-811K wafer maps (811,457 rows total; 162,598 rows in the
  4 target classes). 4000 samples selected (1000/class, seed 2026),
  lot-aware 70.03/15.00/14.98 train/val/test split (0 lots spanning
  splits, 0 cross-split duplicate maps). [data/raw/dataset_provenance.json;
  docs/decisions.md D-003; results/status_summary.md "Measured results"]
- **Preprocessing**: each wafer map resized (nearest-neighbor) and
  centered with zero padding to a fixed 32x32x2 tensor (2 channels:
  die-present, defective-die), binary {0,1} valued. [results/preprocessing_report.json]
- **No class weighting** was applied: per-class training counts are
  within 2% of each other after the capped selection, which the project
  judged not to warrant correction. [docs/decisions.md D-005]

## Model training and quantization

- Two configurations were trained under a fixed protocol: Model A
  (hidden=16) and Model B (hidden=32), both `Flatten -> Dense(hidden,
  ReLU) -> Dense(4)`. Model B was selected over A by quantized
  VALIDATION macro-F1 only (0.7681 vs 0.7538) -- per the project's
  explicit rule, no open-ended architecture search was performed beyond
  trying A then B. [docs/decisions.md D-006; results/ml_metrics.json
  `selection_rule`, `chosen_configuration`]
- **Final measured quality (Model B, int8, TEST split, n=599)**: accuracy
  = 0.7696160267111853 (~76.96%), macro-F1 = 0.7709299728883321. The
  project's target was macro-F1 >= 0.85 -- **this target was NOT met**,
  and this was reported as-is (no threshold/label/test-set change).
  [results/ml_metrics.json `final_test_macro_f1_int8`,
  `quality_target_met_on_test`]
- The model is fully int8 (input/output and both FULLY_CONNECTED
  operators; one RESHAPE op). [results/model_B_int8_operator_analysis.txt]
- **Training/validation curves** (14 epochs each) are stored for both
  configurations. [results/training_history_A.json,
  results/training_history_B.json]

## Memory

- Firmware text+data+bss = 894,941 bytes, fits the 1 MiB RAM region with
  the required 64 KiB reserved stack (headroom 88,099 bytes).
  [results/memory_usage.json `memory_budget_check`]
- Tensor arena: 8,192 bytes statically reserved; 5,216 bytes measured
  PEAK use -- but that peak measurement came from the **native x86
  reference oracle** (`MicroInterpreter::arena_used_bytes()`), not from an
  independent instrumentation of the RV32 firmware itself. The firmware
  uses the identical model/resolver/arena-size configuration, making the
  native figure a reliable proxy, not an RV32-measured fact.
  [results/memory_usage.json `tensor_arena`]

## Timing

- The final RTL run took 142,937,769 simulated hardware clock cycles,
  which Zenith reports took 01:35:52 of simulator WALL-CLOCK time on the
  host machine. The wall-clock figure is simulation time (discrete-event
  software simulation), not physical-chip inference latency -- it does
  not scale with or represent any real clock frequency, since no
  synthesis, timing closure, or physical implementation was performed.
  The cycle count is the figure relevant to relative hardware timing.
  [results/final_run_evidence/full20_final_001_fingerprints.json]

## Key distinctions this assistant must preserve (do not blur these)

1. **20/20 RTL-vs-native agreement is not classifier accuracy.** All 20
   cases match the native oracle exactly; the classifier itself is only
   correct on 16/20 of those same fixed cases (misclassified: case_id 0,
   11, 15, 16). RTL reproduces the model's output exactly, including its
   mistakes.
2. **Test accuracy ~76.96%, macro-F1 0.77093, on the 599-sample test
   split -- the 0.85 target was not met.** This is independent of RTL
   correctness.
3. **Scores are quantized logits (raw int8 model outputs), not
   probabilities.** No softmax/calibration was applied for the reported
   scores.
4. **Simulation wall-clock time is not chip latency.**
5. **The 5,216-byte tensor-arena figure is from the native reference, not
   an independently measured RV32 peak.**
6. **No physical measurement was collected**: clock frequency, power, die
   area, or any FPGA/ASIC implementation result. If asked for these,
   say plainly that the evidence does not contain that information --
   never estimate or fabricate a number for them.
7. **This chat assistant runs on the host server, not inside the
   simulated RISC-V.** The classifier is the thing that ran on the
   RTL-simulated processor; this assistant (including its local LLM) is a
   separate, later, host-side addition that only reads already-saved
   evidence.

## Limitations and what's explicitly out of scope

- No synthesis, timing closure, FPGA bitstream, or power/area result.
- No real silicon or physical hardware execution -- Animas/Zenith RTL
  simulation only.
- Processor verification used a from-scratch Python reference model, not
  Spike/Sail (Spike present but non-functional on this host).
- No claim of reliability across repeated independent runs -- one
  accepted run (`full20_final_001`) is the final evidence; earlier
  historical partial-match states (7/20, 8/20) are preserved separately
  and are not part of the final claim.
  [docs/handoff/limitations_and_open_questions.md;
  README.md "What was NOT done / explicitly out of scope"]

## Later host-side additions (not part of the frozen experiment)

- `apps/results_chat/` itself: a read-only dashboard + chat explainer,
  added after the experiment finished. [docs/decisions.md D-011]
- This upgrade: a local LLM (for open-ended conversation) and a chart
  generator, both read-only, both added after the experiment finished.
  [docs/decisions.md D-012 and later, docs/development_log.jsonl]

## Where to look for more detail

- `README.md` -- entry point, reproduction steps, final result summary.
- `docs/decisions.md` -- every non-obvious design choice, numbered D-001
  onward, with question/alternatives/rationale/evidence/consequences.
- `docs/handoff/README.md` -- handoff entry point and historical timeline.
- `docs/handoff/limitations_and_open_questions.md` -- the most complete
  account of what is NOT established by this project's evidence.
- `docs/handoff/claims_evidence.csv` -- one row per claim, with a
  status column (verified/measured/implemented/failed/not_tested) that
  must not be upgraded in casual conversation (e.g. "measured" is not
  "proven").
- `results/final_run_evidence/` -- the final run's complete raw evidence.
