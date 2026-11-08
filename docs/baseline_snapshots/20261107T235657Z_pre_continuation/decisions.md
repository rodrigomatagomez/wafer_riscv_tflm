# Decisions

Format: ID, question, alternatives, selected option, rationale, evidence, consequences, status (active/superseded).

## D-001: Use the existing directory as the project root

- **Question**: Should the project be created in a new nested directory, or in-place?
- **Alternatives**: (a) create `wafer_riscv_tflm/wafer_riscv_tflm/...`; (b) use the current working directory directly.
- **Selected**: (b). The working directory is already named `wafer_riscv_tflm` and contains the handoff package.
- **Rationale**: START_HERE.md explicitly instructs: "If Claude's working directory is this folder, it must use it directly rather than create another nested folder with the same name."
- **Evidence**: `pwd` = `/home/rmata/Documents/git/wafer_riscv_tflm`.
- **Consequences**: All paths in this document set are relative to `/home/rmata/Documents/git/wafer_riscv_tflm`.
- **Status**: active.

## D-002: Use a hand-written Python ISA reference model instead of Spike

- **Question**: What serves as the independent ISA reference for comparing retired-instruction traces against the RV32IM core (prompt Section 6)?
- **Alternatives**: (a) Spike (preinstalled at `/edatools/opensrc/spike/1.1.1-dev`); (b) Sail; (c) a from-scratch Python functional model, per the prompt's explicit contingency.
- **Selected**: (c), a from-scratch Python RV32IM functional model (`scripts/isa_reference_model.py`), built directly from the RISC-V ISA specification without reading or reusing any DUT RTL logic.
- **Rationale**: Spike is present but cannot run on this host — it is linked against `libboost_regex.so.1.66.0` / `libboost_system.so.1.66.0`, and no compatible Boost 1.66 build exists anywhere on the system (see docs/issues.md ISS-001). Sail was not found on the host and would require a build from source, which is a worse use of the implementation deadline than writing a compact reference interpreter for a 2-extension (I+M), no-privilege-mode subset. The prompt explicitly sanctions this fallback: "If unavailable within the deadline, implement a separate functional verification model from the specification, without reusing DUT logic, and record that limitation."
- **Evidence**: docs/issues.md ISS-001 (ldd output, missing library search).
- **Consequences**: Verification evidence is against an independently authored second implementation of the ISA, not against an externally maintained, widely trusted reference such as Spike/Sail. This is weaker evidence than a Spike comparison and is reported as such in docs/handoff/limitations_and_open_questions.md.
- **Status**: active.

## D-003: Re-download the WM-811K dataset rather than treat it as missing

- **Question**: PACKAGE_CONTENTS.json records `data/raw/LSWMD.pkl` as included (2095505977 bytes, sha256 `1d04fccb...`), but the file was not actually present on disk when implementation started. Should this be treated as a hard blocker, or should the documented download script be run first?
- **Alternatives**: (a) treat as a hard blocker and skip all dataset-dependent work; (b) run `scripts/download_dataset.py`, which uses Kaggle's public documented download endpoint, and only treat the dataset as unavailable if that fails.
- **Selected**: (b).
- **Rationale**: The prompt explicitly requires attempting a documented download before declaring the dataset unavailable, and START_HERE.md phrases the inclusion as conditional ("when included"). Network access to the Kaggle endpoint was already confirmed available.
- **Evidence**: `scripts/download_dataset.py` run output; downloaded file SHA-256 (`1d04fccb3dd3176b276878b926b20fead7e077c5751e4d353ea9741a5e7b5c65`) matches the hash independently recorded in `PACKAGE_CONTENTS.json`, which is strong evidence the re-downloaded bytes are identical to what was originally verified during package preparation.
- **Consequences**: Dataset provenance in `data/raw/dataset_provenance.json` reflects a retrieval timestamp from this implementation session (2026-11-07), not the original preparation-time retrieval. Both retrievals are recorded; neither is fabricated.
- **Status**: active.

## D-004: Library shim (`LD_LIBRARY_PATH`) to repair the RISC-V GNU toolchain's broken `cc1`/`cc1plus`

- **Question**: `riscv64-unknown-elf-gcc`/`g++` (16.1.0, from the `riscv-gnu-toolchain/elf-multilib/2026.07.15-elf` module) failed to run at all: `cc1`/`cc1plus` reported `libmpfr.so.4: cannot open shared object file`, and after supplying that, `libgmp.so.7: cannot open shared object file`. The host's system libraries are newer (`libmpfr.so.6`, `libgmp.so.10`) and not ABI-compatible drop-ins.
- **Alternatives**: (a) treat the toolchain as unusable and look for another RV32 toolchain/build one from source; (b) locate the exact missing SONAMEs elsewhere on the host and supply them via `LD_LIBRARY_PATH` without touching the toolchain installation itself.
- **Selected**: (b). Exact-SONAME copies of `libmpfr.so.4` and `libgmp.so.7` exist under the Xilinx Vivado 2025.2 installation tree (`/edatools/amd/xilinx-vivado/2025.2/...`), bundled there for Vivado's own tools. Symlinking just these two specific files into a small, isolated shim directory (not adding the entire Vivado `lib` directory to `LD_LIBRARY_PATH`, which was tried first and broke `g++` itself by shadowing `libstdc++.so.6` with an older, incompatible build) resolved both missing-library errors.
- **Rationale**: Building riscv-gnu-toolchain from source was explicitly discouraged by the prompt ("Avoid a full toolchain source build when a suitable local or prebuilt alternative exists"); a prebuilt, correctly-targeted toolchain already exists on this host and only has a narrow, repairable linkage problem.
- **Evidence**: see docs/development_log.jsonl E014; verified by compiling and linking a minimal freestanding RV32IM/ilp32 C++17 program to a valid ELF (`readelf -h`, `objdump -d` inspected).
- **Consequences**: Every build command for sw/ firmware must set `LD_LIBRARY_PATH` to include this shim directory (recorded in scripts/env.sh) in addition to loading the `riscv-gnu-toolchain/elf-multilib/2026.07.15-elf` module. This is a host environment workaround, not a toolchain or RTL design choice.
- **Status**: active.

## D-005: No class-weighting applied during training

- **Question**: Section 4 says to derive class weights from training data "if class imbalance warrants" them. Should they be used?
- **Alternatives**: (a) apply inverse-frequency class weights; (b) skip them.
- **Selected**: (b). The actual training-split class counts after selection/split (Center 711, Edge-Ring 691, Scratch 701, none 698) are within 2% of each other — not an imbalance that warrants correction.
- **Rationale**: The per-class selection cap (1000 unique samples/class, Section 3) already enforces near-perfect balance before any split occurs; the prompt only asks for weights when warranted, and this is not such a case.
- **Evidence**: docs/experiments.jsonl RUN-select-split-001; printed class counts in logs/train_and_quantize_run2.log.
- **Consequences**: None; documented so a later reader does not wonder why weights are absent.
- **Status**: active.

## D-006: Quality target (quantized test macro-F1 >= 0.85) not met; proceed without further architecture search

- **Question**: Model A (hidden=16) and Model B (hidden=32), trained and quantized under the exact protocol in Section 4, reached quantized validation macro-F1 of 0.754 and 0.768 respectively, both below the 0.85 target. The prompt permits trying A then B and choosing between them by quantized validation performance only — it explicitly forbids an open-ended architecture search. What happens next?
- **Alternatives**: (a) keep tuning architecture/hyperparameters until 0.85 is reached; (b) accept Model B (higher quantized validation macro-F1: 0.768 vs 0.754), report the true quantized test macro-F1 (0.771), and continue the functional (processor + TFLM) demonstration with this model as specified.
- **Selected**: (b).
- **Rationale**: The prompt is explicit: "Do not launch an open-ended architecture search" and "If the target is not reached, preserve the actual result, explain the limitation, and continue the functional demonstration. Do not change the threshold, labels, or test data to claim success."
- **Evidence**: docs/experiments.jsonl RUN-train-quantize-001; results/ml_metrics.json.
- **Consequences**: The quality target (test macro-F1 >= 0.85) is an unmet, explicitly reported acceptance criterion. The 20-case RTL-vs-native-TFLM agreement criterion is a separate, independent acceptance criterion (bit-exact agreement between RTL and the native reference, not agreement with ground truth) and is not affected by this shortfall — Model B's real misclassifications are expected to reproduce identically on both RTL and the native reference.
- **Status**: active.
