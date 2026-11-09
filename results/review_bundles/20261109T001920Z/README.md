# Review bundle: 20261109T001920Z

A compact, self-contained package for a reviewer to inspect (1) the completed
RV32IM RISC-V / TensorFlow Lite Micro verification experiment and (2) the
later, separate host-side local-LLM chat and chart-generation application
built on top of it. See `status_summary.json` for the machine-readable
version of everything below.

## 1. The frozen experiment: `full20_final_001`

**All 20 RTL-vs-native comparisons match exactly** (bit-for-bit identical
scores and predicted class for every case). This was independently
re-verified at bundle-creation time -- see `evidence/checker_replay_report.json`
(a fresh run of `scripts/check_final_run.py`, **stored separately from**,
not overwriting, the original acceptance evidence under
`results/final_run_evidence/`) and `evidence/evidence_references.json`
(recomputed SHA-256 hashes for every key evidence file, cross-checked
against the values already on record).

**This is not the same claim as classifier accuracy.** Keep these separate:

| Claim | Value | Source |
|---|---|---|
| RTL-vs-native agreement (implementation correctness) | **20/20** | `results/rtl_comparison.json`, `results/final_run_evidence/` |
| Classifier correct on these same 20 fixed demo cases | **16/20** (wrong on case_id 0, 11, 15, 16) | `results/final_run_evidence/full20_final_001_check_report.json` vs. `results/comparison_manifest.json` ground truth |
| Classifier accuracy, full 599-sample test split | **76.96%** | `results/ml_metrics.json` |
| Classifier macro-F1, full 599-sample test split | **0.77093** | `results/ml_metrics.json` |
| Quality target (not met) | macro-F1 >= 0.85 | `results/ml_metrics.json` (`quality_target_met_on_test: false`) |

The RTL hardware reproduces the classifier's output exactly -- including the
classifier's own 4 mistakes on these fixed cases. A correct implementation
of an imperfect model is still a correct implementation.

## 2. The later addition: local-LLM chat + chart application

`apps/results_chat/` is a separate, read-only web app added after the
experiment above was already complete. It never runs inside the simulation
and cannot modify any evidence file. It now includes:

- **A real local LLM** (llama.cpp + Qwen2.5-1.5B-Instruct, Apache-2.0,
  CPU-only, built/downloaded/run on this same host) for open-ended,
  citation-grounded conversation -- see `model_provenance/MODEL_PROVENANCE.json`
  for exact source/revision/license/quantization/hash and measured
  resource/timing figures.
- **Natural-language chart generation** (9 kinds), always rendered
  deterministically from a strict, data-free specification -- the LLM can
  select which real dataset to plot, never invent a number.
- **Social-conversation routing** so a greeting doesn't require retrieval
  or produce a false "no evidence" refusal, while a project question
  attached to a greeting still gets a fully grounded answer.

### Test results

217 tests, **217 passed / 0 failed / 0 skipped** (local LLM server was
running during this run, so the live-LLM tests executed for real, not
skipped). Full breakdown: `test_results/summary.json`; raw pytest output:
`test_results/pytest_full_output.txt`.

### Live conversation transcript

`conversation_transcript/transcript.md` -- 6 real HTTP round-trips against
the actually-running server, covering exactly what a reviewer needs to see:
a bare greeting (answered instantly, no evidence/citation required), an
open-ended Spanish question answered by the real local LLM with citations,
a contextual follow-up resolved via session history and retrieval, a
specific case query, a chart-generation request, and an explicit refusal
for an unavailable physical measurement. Each turn records the actual
route/intent, answer mode (`llm` vs. `factual`), citations, and measured
wall-clock latency. One real small-model generation artifact (a minor
Spanish word substitution) is left unedited in the transcript and called
out explicitly, rather than cleaned up.

### Publication figures

`figures/` -- 5 figures, each exported as **PNG + SVG + CSV** (not browser
screenshots: generated directly by calling the same deterministic
`chart_engine.py` renderer the live app uses), with a caption, source
citation(s), and provenance (filters/normalization) recorded in
`figures/figures_manifest.json` and embedded in each CSV's header comments:

1. **`confusion_matrix_model_B_int8`** -- Model B, int8, test split (n=599), raw counts.
2. **`f1_by_class_model_B_int8`** -- per-class F1 with the original **0.85 target** drawn as a reference line.
3. **`model_A_vs_B_comparison`** -- Model A vs. B macro-F1 (int8, test split).
4. **`invoke_cycles_final_run`** -- Invoke() cycle count for all 20 cases of the accepted final run.
5. **`case_16_scores`** -- case 16's four quantized scores (native vs. RTL), showing the Scratch/none tie and the resulting misclassification.

All 5 were visually inspected at full resolution for legibility and
clipping. **One real issue was found and fixed**: the F1-by-class chart's
title overlapped a near-1.0 data label; `backend/chart_engine.py` was
corrected (wider y-axis headroom, two-line title) before this bundle's
figures were generated -- see `docs/decisions.md` for the full record if
synced, or `figures/figures_manifest.json`'s note here.

## 3. Remaining limitations (unchanged by this bundle)

- Classifier quality target (macro-F1 >= 0.85) was **not met** (measured 0.77093).
- Only one accepted end-to-end RTL run exists (`full20_final_001`); no
  repeated-run reliability claim is made.
- Processor verification used a from-scratch Python ISA reference model,
  not Spike/Sail (Spike is installed but non-functional on this host).
- No synthesis, timing closure, or FPGA/silicon result -- RTL simulation
  only. Simulated cycle counts are not physical-chip latency.
- The local LLM (1.5B parameters) occasionally exhibits small-model
  generation artifacts; evidence citations remain authoritative, not the
  LLM's prose.
- Knowledge-base retrieval is TF-IDF-based, not semantic/embedding-based.

## Contents

```
README.md                      -- this file
status_summary.json             -- machine-readable version of everything above
evidence/
  evidence_references.json      -- paths + recomputed SHA-256 for key evidence files (no bytes copied)
  checker_replay_report.json    -- fresh scripts/check_final_run.py re-run, stored separately from original
model_provenance/
  MODEL_PROVENANCE.json          -- local LLM: source/revision/license/quantization/hash/measured performance
test_results/
  summary.json                   -- pass/fail/skip counts, per test file
  pytest_full_output.txt         -- complete raw pytest -v output
conversation_transcript/
  transcript.json                -- structured (route/mode/citations/timing per turn)
  transcript.md                  -- human-readable version
figures/
  <5 figures>.png / .svg / .csv  -- publication figures
  figures_manifest.json          -- captions, citations, provenance, hashes
manifest.json                    -- full file listing + SHA-256 for every file in this bundle
```

## Reproduction

- Original experiment: see the project's top-level `README.md`,
  "Reproduction steps", and `results/final_run_evidence/README.md`.
- Chat/LLM/chart app: see `apps/results_chat/README.md`, "Exact startup
  instructions" and "Setting up the local LLM".
