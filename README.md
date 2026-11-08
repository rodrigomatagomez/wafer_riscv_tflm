# wafer_riscv_tflm

**Absolute project path:** `/home/rmata/Documents/git/wafer_riscv_tflm`

A from-scratch RV32IM RISC-V processor (SystemVerilog), simulated via Animas/Zenith,
running real TensorFlow Lite Micro (pinned commit) int8 inference to classify
WM-811K wafer-map patterns into 4 classes (Center, Edge-Ring, Scratch, none).

This README is the implementation-status entry point. For the full, evidence-linked
account see `results/status_summary.md` and `docs/handoff/README.md`. Formal written
documentation (paper/presentation) is a **separate, later stage** — see
`docs/handoff/documentation_instructions.md` and `documentation_ai_prompt.txt`.

## Requirements

- Linux host with the Animas EDA toolchain (Zenith simulator) and its MCP tool bridge.
- RISC-V GNU toolchain for `rv32im`/`ilp32` (this project used
  `/edatools/opensrc/riscv-gnu-toolchain/2026.07.15/elf-multilib`, with a small
  library shim documented in `docs/decisions.md` D-004 and `scripts/env.sh`).
- Python 3.9+ with an isolated venv (`ml/venv/`, requirements installed ad hoc:
  `numpy<2`, `pandas`, `scikit-learn`, `matplotlib`, `pillow`, `tensorflow==2.15.*`).
- Network access to Kaggle (dataset) and GitHub (tflite-micro) for a from-scratch
  reproduction; both are otherwise already present under `data/raw/` and
  `third_party/` in a prepared checkout.

## Reproduction steps (in order)

```bash
# 0. Toolchain environment
source scripts/env.sh

# 1. Dataset (already present under data/raw/; re-downloads only if missing)
python3 scripts/download_dataset.py

# 2. Selection, split, preprocessing
ml/venv/bin/python3 ml/select_and_split.py
ml/venv/bin/python3 ml/preprocess.py

# 3. Train + quantize (Model A, then B if needed; see docs/decisions.md D-006)
ml/venv/bin/python3 ml/train_and_quantize.py

# 4. Processor directed tests + random-instruction comparison (via Animas MCP tools;
#    see docs/animas_capabilities.md for the exact tool calls used)
bash scripts/build_fw.sh test_001_basic_alu tb/directed/test_001_basic_alu.S
# ...(test_002 .. test_009; see tb/directed/)
python3 scripts/gen_random_program.py 1100 build/random_program/random
# then run each .hex through Animas with +MEMFILE=<hex>, and compare the RETIRE
# trace (+TRACE=1) against scripts/isa_reference_model.py

# 5. Select the 20 comparison cases and embed model + inputs
ml/venv/bin/python3 ml/select_comparison_cases.py
python3 ml/model_to_c_array.py

# 6. Native TFLM reference oracle
bash scripts/build_native_reference.sh
./build/native_reference/native_reference > build/native_reference/output.jsonl

# 7. Bare-metal firmware, then run on RTL. The actual final run
#    (full20_final_001, see "Final result" below) used a standalone
#    invocation of the installed Zenith binary, bypassing the Animas MCP
#    daemon entirely -- this avoids both an Animas-backend-level
#    run_simulation wall-clock cap and a ZWDB waveform file being written
#    even when the MCP tool's waveform_mode is requested "off" (neither
#    problem is specific to this project; see docs/animas_capabilities.md
#    and docs/storage_cleanup.md). Reproduce with:
bash scripts/build_firmware.sh
P=<flatpak-portal-mounted path to this project root>   # NOT the host path;
                                                        # see docs/handoff/README.md
flatpak run --branch=1.0.2 --command=zenith com.mifraltech.animaseda \
    $P/rtl/rv32im_pkg.sv $P/rtl/rv32im_alu.sv $P/rtl/rv32im_regfile.sv \
    $P/rtl/rv32im_muldiv.sv $P/rtl/rv32im_core.sv $P/rtl/mmio.sv $P/rtl/soc_top.sv \
    $P/tb/ram_model.sv $P/tb/ram_model_lite.sv $P/tb/soc_tb.sv \
    -top soc_tb +define+RAM_LITE \
    +MEMFILE=$P/build/firmware/configs/case_full/firmware.hex \
    +MAXCYCLES=250000000 +TRACE=0 +RUNID=<new run id> +HEARTBEAT=500000 \
    > results/rtl_logs/<run id>_live.log 2>&1 &
# (no --zwdb argument at all; the Animas MCP run_simulation tool with
# waveform_mode="off" remains available as an alternative but was not the
# path used for the final accepted run)

# 7b. Optional: build a firmware image restricted to a sub-range of the fixed
#     20-case manifest (case IDs keep their original global meaning; no
#     ground truth is embedded). Useful for completing one case at a time
#     when a single Invoke() takes many wall-clock minutes of simulation.
CASE_START=0 CASE_COUNT=1 bash scripts/build_firmware.sh
# -> build/firmware/configs/case_0_1/{firmware.elf,firmware.hex,firmware_config.json}

# 8. Turn a captured simulation log into a structured, provenance-tagged
#    run record, then check one or more run records against the native
#    oracle (see docs/decisions.md D-008):
python3 scripts/run_rtl_test.py --log <captured zsim.log path> \
    --run-id <run id> --invocation "<exact Animas tool call or zenith command used>" \
    --firmware-config build/firmware/configs/case_0_1/firmware_config.json \
    --model-sha256 7e11c5faea02c99464d6f939c3b10067bd93a6d72d5e650797f6249755ba69ea \
    --out results/rtl_runs/<run id>.json
python3 scripts/compare_results.py --rtl-runs 'results/rtl_runs/*.json' \
    --out results/rtl_comparison.json
```

## Final result (2026-11-08)

**All 20/20 RTL-vs-native comparisons match exactly.** One complete,
from-cycle-0 RTL simulation (run ID `full20_final_001`, standalone Zenith
invocation, no waveform capture) ran to completion ($finish exit code 0,
142,937,769 simulated cycles, 01:35:52 wall-clock) with all 20 cases present
exactly once. `scripts/check_final_run.py` (a strict, independently-written
single-run acceptance checker) confirms exit code 0: every one of the 20
cases' four integer scores and predicted class exactly match the native
TFLM oracle. Full evidence: `results/final_run_evidence/`. The model's own
quality limitation is unchanged and reported separately below -- RTL
correctness and model quality are independent claims.

## Implementation status (see results/status_summary.md for full detail)

| Area | Status |
|---|---|
| Dataset acquisition/provenance | verified |
| Data selection/split/preprocessing | measured, complete |
| Model training/quantization | complete; **quality target (macro-F1>=0.85) NOT met** (0.7709) |
| RV32IM core + system RTL | implemented, compiles/elaborates cleanly |
| Processor verification | **passed**: 9/9 directed tests, 1100/1100 random-instruction match |
| TFLM integration (pinned commit, native reference) | complete |
| Bare-metal firmware (build + RTL boot + TFLM init) | **passed**, all 20 `Invoke()` calls completed |
| 20-case RTL vs. native comparison | **met**: 20/20 matched, run `full20_final_001`, strict checker exit code 0 |
| Documentation handoff (`docs/handoff/`) | complete |

The 20-case RTL comparison was, for most of this project's history, the one
unmet acceptance criterion -- not due to a correctness failure but due to
Animas tool-connectivity, waveform-storage, and wall-clock-cap problems
encountered while orchestrating a long-running simulation (see
`docs/handoff/limitations_and_open_questions.md` for that history and
`results/status_summary.md`'s "Finalization session" section for how each
was fixed). It is now met; see "Final result" above.

### This continuation's additions: now validated on real RTL

A later continuation session (2026-11-07/08) added infrastructure that a
still-later finalization session (2026-11-08) validated against real RTL
output and used in the final accepted run:

- `tb/ram_model_lite.sv`: a lightweight alternative RAM testbench model
  (O(1) pending-response tracking vs. the original's O(64) shift register),
  selectable via `+define+RAM_LITE`, derived from the verified
  single-outstanding-request property of `rtl/rv32im_core.sv`. See
  `docs/decisions.md` D-007. **Validated**: exact RETIRE-trace match against
  the original RAM model under default and injected-backpressure/randomized-
  latency timing (9/9 directed tests); used (confirmed via the run's own
  `SIM_BANNER` showing `ram=lite`) in the final accepted run.
- `CASE_START`/`CASE_COUNT` compile-time firmware range selection (see
  Reproduction step 7b) and the real `scripts/run_rtl_test.py` /
  `scripts/compare_results.py` checker scripts (see Reproduction step 8 and
  `docs/decisions.md` D-008) -- both exercised against real final-run data,
  not just synthetic logs; `scripts/check_final_run.py` (a new, stricter
  single-run acceptance checker) is the authoritative final-run verdict.
- `tb/soc_tb.sv`: added a `SIM_BANNER` startup line, a low-frequency
  `HEARTBEAT` progress marker, and an always-on retired-instruction counter
  independent of `+TRACE=`, without changing default simulation behavior.
