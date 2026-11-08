# Limitations and open questions

Read this alongside docs/handoff/claims_evidence.csv (status column) and
docs/issues.md (full issue histories). This file is the single place a
later writer should check before asserting anything was "achieved."

## Unmet targets

- **ML quality target not met.** The prompt's target is quantized test
  macro-F1 >= 0.85. The actual measured value for the chosen model
  (model_B_int8.tflite) is **0.7709** (results/ml_metrics.json,
  `final_test_macro_f1_int8`). This was not worked around: no threshold
  change, no label change, no test-set substitution, no open-ended
  architecture search beyond the prompt's explicit A-then-B protocol.

## As-of-handoff status of the 20-case RTL vs. native comparison

- The **native x86 TFLM reference oracle** (build/native_reference/) ran
  all 20 cases successfully (build/native_reference/output.jsonl has 20
  lines, one per case, with scores and predicted_class).
- The **bare-metal RV32IM firmware** was built, linked, and loaded onto
  the RTL-simulated processor via Animas/Zenith. At the time this handoff
  snapshot was written, the firmware had progressed past model
  initialization (resolver setup, model load, interpreter construction,
  `AllocateTensors()` success) and had begun real `Invoke()` execution for
  case 0 (MMIO_MEASURE=1 observed in the live simulation log at RTL cycle
  351185). **Whether the full 20-case loop completed, how many cases
  finished, and whether their outputs agreed with the native oracle was
  not yet known when this file was written** -- check results/rtl_comparison.json
  and results/status_summary.md (if present and newer than this file) for
  the actual final outcome; if those files are absent or still show an
  in-progress state, the 20-case criterion must be reported as incomplete,
  with however many cases DID complete reported honestly (not rounded up
  to 20/20).
- Each `Invoke()` call on the RTL is genuinely expensive: the first
  layer's FULLY_CONNECTED op (2048 input features x 32 hidden units =
  65536 multiply-accumulate operations) alone requires roughly that many
  hardware MUL instructions (each ~33 cycles on this multicycle core's
  sequential multiplier) plus loop-control overhead, observed empirically
  to put a single `Invoke()` in the multi-million-RTL-cycle range. This is
  a genuine property of running real int8 FULLY_CONNECTED reference-kernel
  arithmetic, instruction-by-instruction, on a non-pipelined multicycle
  core -- not a measurement artifact.

## RTL simulation engineering notes (relevant to reproducing or continuing this run)

- Animas/Zenith's MCP tool bridge had two distinct connectivity issues
  during this session (see docs/issues.md ISS-002): an initial
  session-handshake desync (resolved externally, not by this agent), and
  later, `run_simulation` calls for long-running jobs returning
  "timeout"/"headless" status to the calling tool after ~60-300 seconds
  **while the underlying Zenith simulation kept running independently** in
  an Animas backend/daemon process. This means the MCP tool's own
  timeout is not a reliable signal of whether the simulation actually
  finished -- `output/zsim.log` (and `get_last_sim_result` /
  `read_simulation_log`) must be checked directly, and the log itself can
  be **block-buffered**, lagging several seconds to tens of seconds behind
  the simulator's actual (CPU-time-confirmed) progress.
- Per-instruction RETIRE tracing and full ZWDB waveform capture, if left
  enabled, produce enormous files (observed: >200 MB ZWDB and >25 MB log
  per few-million-cycle partial run) and measurably slow simulation
  throughput. `tb/soc_tb.sv` gates RETIRE tracing behind a `+TRACE=1`
  plusarg (default off) specifically for this reason; `set_sim_options`
  was also used to request `waveform_mode: "off"` for the large functional
  firmware run. One anomaly observed: a `set_sim_options` + source-file
  edit made shortly before a `run_simulation` call did not always appear
  to take effect on the very next run (a stale/cached project-settings
  snapshot was suspected); if continuing this work, always confirm the
  actually-used command line (visible in the tool's own response) matches
  the intended flags before trusting a run's output.
- This host has no alternative RTL simulator (no Verilator, Icarus
  Verilog, VCS, or Xcelium were found); Animas/Zenith is the only option,
  so any future continuation of the 20-case run must go through it.

## Processor verification scope

- The independent ISA reference used for processor verification is a
  from-scratch Python interpreter (scripts/isa_reference_model.py), not
  Spike or Sail. Spike is installed on this host but cannot run (missing
  `libboost_regex.so.1.66.0`/`libboost_system.so.1.66.0` with no
  compatible build anywhere on the system; see docs/issues.md ISS-001).
  This is a real, disclosed limitation of the verification evidence's
  independence, not a hidden one.
- The random-instruction comparison (1100 instructions, 0 mismatches)
  covers only register-only ALU and M-extension instructions (no
  loads/stores/branches/jumps), by deliberate design (keeps the random
  program memory-safe without needing a separate safety analysis). Control
  flow and memory instructions are instead covered by the 9 directed
  tests, which are necessarily much smaller in combinatorial coverage.
- Reset was only exercised at the start of each simulation (power-on
  reset), never as a deliberate mid-execution reset pulse.
- No formal verification (model checking, equivalence checking) was
  performed; all processor-correctness evidence is simulation-based.

## Model/quantization scope

- Calibration for int8 quantization used up to 200 class-balanced
  samples drawn only from the training split (never from validation or
  test), per the prompt's explicit requirement.
- The int8 output scores are raw model logits/quantized values, not
  calibrated probabilities -- this must not be described as a confidence
  percentage in any later document.
- A `STATUS=1` MMIO write (if/when observed) means the firmware's
  internal control flow finished all 20 cases without an execution error
  (allocation failure or `Invoke()` returning non-OK); it is **not** by
  itself evidence that RTL and native outputs agreed. Agreement is a
  separate, explicit comparison (results/rtl_comparison.json).

## Evidence-strength caveats (binding; apply to this file, results/*, and any later document)

These statements were made explicit during a 2026-11-07/08 continuation
session, after auditing this project's records for places where a
measurement could be over-read. Each was checked against the current
`docs/` and `results/` content; none of this project's current claims were
found to directly contradict them, but they are recorded verbatim here as
binding constraints on how the existing evidence may be characterized going
forward (including by the separate documentation-writing AI this handoff is
for):

- **Unfinished inference does not prove absence of an RTL defect.** The
  "this is not a defect, just a slow non-pipelined multiplier" explanation
  in `docs/issues.md` ISS-004 is an engineering inference from the observed
  instruction mix and cycle budget, not a proof. It remains possible that a
  latent RTL defect exists that has simply not yet been exercised by a
  completed `Invoke()`. Only an actual completed, matching inference (or a
  completed, mismatching one that triggers real debugging) upgrades this
  from "consistent with correct behavior" to "verified."
- **The local-static initialization workaround does not by itself prove a
  compiler bug.** ISS-003's fix (moving TFLM objects to file scope) is
  confirmed to resolve the observed symptom, but the exact defect inside
  the guarded-local-static codegen path was never isolated (no guard-check
  assembly was inspected). Do not describe ISS-003 as "a GCC/toolchain
  bug" in later documents; describe only what was observed (symptom) and
  what fixed it (global-scope workaround), as `docs/issues.md` already
  does.
- **Native-host arena usage is not an independently measured RV32 arena
  footprint.** `results/memory_usage.json`'s `arena_used_bytes=5216` comes
  from the native x86 reference binary's `MicroInterpreter::arena_used_bytes()`,
  not from any RV32/RTL-side instrumentation (the firmware was never
  instrumented to report its own `arena_used_bytes()` over MMIO). It is a
  reliable proxy because the model, op resolver, and arena size are
  byte-for-byte identical between the native and RV32 builds, but it must
  continue to be labeled as a native-side measurement, not an RTL
  measurement, in any later document.
- **Reported timing is not independently verified timing unless the
  original supporting log is preserved.** The ~3,696 RTL-cycles/sec
  throughput figure in `results/rtl_comparison.json` is traceable to
  `animas.log`'s own `"Simulation started"`/`"Simulation done"` timestamps
  (preserved; see `docs/issues.md` ISS-004) and to the retained
  `output/zsim.log` snapshot for that exact run (see
  `docs/baseline_snapshots/20261107T235657Z_pre_continuation/`). Any new
  timing figure produced in a later continuation must likewise cite a
  preserved log/timestamp pair, not a recalled or recomputed estimate, to
  be reported as "measured" rather than "estimated."
- **Model quality remains below target even if hardware verification
  succeeds.** The unmet quantized test macro-F1 target (0.7709 vs. the
  0.85 target; see "Unmet targets" above) is an independent acceptance
  criterion from RTL/native output agreement. Completing all 20
  RTL-vs-native comparisons with exact agreement (a hardware-correctness
  result) must never be described, in this document or any later one, as
  also having met or superseded the separate, still-unmet ML quality
  target.

## Line-ending policy

- **Policy (established 2026-11-07/08 continuation)**: all text files
  authored or edited by this project (`.sv`, `.cc`, `.h`, `.py`, `.sh`,
  `.md`, `.json`, `.jsonl`) use **LF** line endings, no exceptions. This
  was checked directly (`cat -A` / `file`) on representative files from
  each category in this continuation (`scripts/build_firmware.sh`,
  `tb/soc_tb.sv`, `sw/app/main_firmware.cc`) and all were already LF; no
  CRLF files were found in the current working tree as of this check.
- **Why this needed stating explicitly**: an earlier preparation step (see
  `PREPARATION_RECORD.md` / the original handoff package) noted that some
  text-file SHA-256 hashes inside the originally-reviewed Windows-prepared
  ZIP archive only matched the expected values after CRLF-to-LF
  normalization. That is a text line-ending conversion, not evidence of
  binary model/data corruption -- the two must not be conflated in any
  later document. No corrupted binary artifact was ever actually found;
  the apparent hash mismatches were fully explained by the normalization
  step.
- **Going forward**: any new file this project adds should be authored
  with LF endings (the default for every tool used in this session —
  heredocs, the Write/Edit tools, and this host's text editors). If a
  future contributor's tooling introduces CRLF endings, normalize to LF
  before computing or comparing any SHA-256 fingerprint against this
  project's recorded hashes, and record that normalization step explicitly
  rather than silently re-hashing.

## Not performed / explicitly out of scope

- No synthesis, timing closure, FPGA bitstream generation, or power/area
  estimation was performed at any point.
- No real silicon, FPGA, or physical hardware execution occurred;
  everything is RTL simulation via Animas/Zenith.
- Simulated RTL cycle counts and Zenith's own wall-clock simulation time
  are unrelated to any real hardware clock frequency; no real-time or
  throughput claim about physical silicon can be derived from the numbers
  in this project.
- This is a single autonomous implementation attempt; no claim is made
  about reliability or reproducibility across repeated independent runs
  of the same prompt.
- The classifier performs pattern classification only; it does not
  identify the physical root cause of a wafer defect and does not
  establish industrial deployment readiness.
