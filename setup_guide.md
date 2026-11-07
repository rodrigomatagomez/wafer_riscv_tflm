# Project setup and documentation handoff

All project-authored material will be in English. The project root on Claude's Linux environment will be named `wafer_riscv_tflm`. Claude will resolve its absolute path and create the project structure. The SystemVerilog processor core will be written from scratch.

## What to give Claude now

1. Access to Animas tools and the documentation those tools expose.
2. Access to a Linux terminal and a writable working directory.
3. The complete contents of `claude_implementation_prompt.txt` as one initial instruction.
4. Preferably, the actual WM-811K dataset at the location below.

No existing RTL or pretrained model is required. The implementation prompt requires Claude to discover real Animas interfaces, prepare a suitable RISC-V compiler if available, train and quantize the model, verify the processor, and execute actual TFLM firmware on simulated RTL.

## Dataset location

The prepared handoff package includes the original dataset and a provenance file. Its public download was verified during package preparation; Claude must still verify local file access from its own environment. Future download availability can change.

Obtain WM-811K from [Kaggle](https://www.kaggle.com/datasets/qingyi/wm811k-wafer-map). Extract the archive if necessary and place the file normally named `LSWMD.pkl` inside the Linux filesystem visible to Claude:

```text
wafer_riscv_tflm/
  data/
    raw/
      LSWMD.pkl
```

A Windows path or a chat attachment is sufficient only if Claude's Linux terminal can actually read the resulting file. Use the file-transfer mechanism already available in your environment. Claude will inspect the schema, select classes, partition the samples, preprocess them, and train the model.

If the file is absent, the prompt instructs Claude to attempt a documented download. If access is unavailable, it must record the blocker and continue independent processor work. Real wafer-data experiments remain incomplete until real data is available.

## Fixed implementation scope

- Classes: `Center`, `Edge-Ring`, `Scratch`, and `none`.
- Input: 32x32 maps with valid-die and defective-die channels.
- Model: a small dense network trained by Claude and quantized to int8.
- Processor: a new multicycle RV32IM core with memory and output registers.
- Inference: actual TFLM firmware executing on RTL simulated through Animas.
- Evidence: processor tests, measured model metrics, and 20 comparisons with native TFLM.
- Demonstration: real wafer maps and captured RTL results, with cycle measurements and reference agreement.

Training and preprocessing occur on the host. Neural inference occurs on the simulated processor. Quality thresholds are targets until measured. The prototype's functional tests do not constitute formal RISC-V certification or industrial classifier validation.

## Two separate stages

Stage 1 is implementation and evidence collection. Claude must maintain English development records throughout the work: chronological events, decisions, discoveries, experiments, failures, fixes, original logs, and actual result files. It must also create a project-specific documentation handoff. It should not spend the implementation deadline writing a polished paper or presentation.

Stage 2 is a later AI-assisted writing session. The writer will use the evidence package to create the requested documentation, paper, or slides under the venue's actual requirements. It must distinguish plans from implemented features and verified results.

After implementation, the key entry points will be:

```text
wafer_riscv_tflm/docs/handoff/README.md
wafer_riscv_tflm/docs/handoff/documentation_instructions.md
wafer_riscv_tflm/docs/handoff/claims_evidence.csv
wafer_riscv_tflm/docs/handoff/artifact_manifest.json
```

These are required future outputs of Claude's implementation run; they have not been generated here as experimental evidence.

## What to give the documentation AI later

Start a separate session with access to the finished project files or a transferred evidence bundle preserving the same relative paths. Give it `documentation_ai_prompt.txt` and the venue/template requirements if available. Its first action should be reading the project-specific handoff generated during implementation.

The generic documentation prompt provided here is a starting instruction. The implementation agent must also produce project-specific documentation instructions containing actual findings, file references, results, and unresolved issues.

One initial instruction can initiate many tool calls and repair iterations. It does not guarantee that an unprepared environment will finish within a day. Any incomplete work must remain clearly identified in the evidence and subsequent writing.
