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

# 7. Bare-metal firmware, then run on RTL via Animas
bash scripts/build_firmware.sh
# load build/firmware/firmware.hex via Animas (+MEMFILE=..., waveform off,
# tracing off) and capture MMIO_* markers from output/zsim.log
```

## Implementation status (see results/status_summary.md for full detail)

| Area | Status |
|---|---|
| Dataset acquisition/provenance | verified |
| Data selection/split/preprocessing | measured, complete |
| Model training/quantization | complete; **quality target (macro-F1>=0.85) NOT met** (0.7709) |
| RV32IM core + system RTL | implemented, compiles/elaborates cleanly |
| Processor verification | **passed**: 9/9 directed tests, 1100/1100 random-instruction match |
| TFLM integration (pinned commit, native reference) | complete |
| Bare-metal firmware (build + RTL boot + TFLM init) | **passed** through `AllocateTensors()` and the start of `Invoke()` |
| 20-case RTL vs. native comparison | **incomplete**: 0/20 cases finished on RTL within session time (see below) |
| Documentation handoff (`docs/handoff/`) | complete |

The 20-case RTL comparison is the one unmet acceptance criterion. It is not a
correctness failure: the firmware correctly initializes TFLM and begins real
`Invoke()` execution on the RTL-simulated processor (confirmed at RTL cycle
351185), but a single `Invoke()` of this model on this non-pipelined multicycle
core requires well over 5,000,000 RTL cycles (confirmed: one run hit a
5,000,000-cycle safety limit still inside case 0's `Invoke()`), and the full
20-case run did not complete in the wall-clock time available. See
`docs/handoff/limitations_and_open_questions.md` for the complete account,
including real Animas/Zenith tool-connectivity issues encountered while
orchestrating long-running simulation jobs.
