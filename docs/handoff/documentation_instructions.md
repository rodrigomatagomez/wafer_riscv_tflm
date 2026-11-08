# Instructions for the documentation-writing AI session

You are starting a SEPARATE session from the one that implemented this
project. You were not present for the implementation; everything you know
about it must come from the files in this repository. Write in English.

## What was built (one paragraph, verify against the evidence before repeating)

A new multicycle RV32IM RISC-V processor core, written from scratch in
SystemVerilog (rtl/), verified with directed tests plus a 1100-instruction
random comparison against an independent Python ISA reference model
(scripts/isa_reference_model.py, used instead of Spike because Spike is
installed but non-functional on this host -- see docs/issues.md ISS-001).
A small dense classifier for 4 WM-811K wafer-map pattern classes (Center,
Edge-Ring, Scratch, none) was trained on the host and quantized to int8;
the quantized test macro-F1 (0.7709) fell short of the 0.85 target and
this was preserved as a real result, not altered. TensorFlow Lite Micro
was pinned at commit 4eaa491c1c8dedd9a3baf421968afd0d5b82f6aa and used,
via its official project-generation script, to build both (a) a native
x86 reference oracle and (b) bare-metal RV32IM firmware that runs on the
RTL-simulated processor through Animas/Zenith. Check
docs/handoff/limitations_and_open_questions.md for whether the full
20-case RTL-vs-native comparison finished by the time implementation work
ended -- do not assume it did. (As of the 2026-11-08 finalization, it did:
all 20 cases matched the native oracle exactly in run `full20_final_001`,
verified by `scripts/check_final_run.py` exit code 0 -- see
`results/final_run_evidence/`. Still read the limitations file yourself
rather than taking this parenthetical as a substitute for checking the
evidence; it also tells you about the model's own unmet quality target,
which this RTL result does not change.)

## Reading order

1. This file, then docs/handoff/README.md.
2. docs/handoff/claims_evidence.csv -- the master claim-to-evidence table.
   Every quantitative statement you write must trace to a row here (or to
   a newly-verified fact you check yourself against the named evidence
   file). A row's `status` column tells you what kind of claim it is
   (verified/measured/implemented/failed/not_tested) -- preserve that
   distinction in your writing; do not upgrade "measured" to "proven" or
   "failed" to "close enough."
3. docs/handoff/limitations_and_open_questions.md -- read this BEFORE
   drafting results, not after. It names the specific places where the
   implementation session's own evidence is incomplete or uncertain.
4. docs/development_log.jsonl (chronological), docs/decisions.md (design
   choices and why), docs/findings.md (labeled observed/inferred/
   unverified), docs/issues.md (bugs found, including two real RTL bugs
   found and fixed via actual test execution -- these are good material
   for a "verification methodology" or "development process" section,
   since they demonstrate the test infrastructure actually working).
5. docs/experiments.jsonl -- one record per real run (dataset download,
   selection/split, preprocessing, training/quantization, random-instruction
   comparison), each with a run_id you can cross-reference from
   claims_evidence.csv.
6. The actual result files: results/cpu_verification.json,
   results/ml_metrics.json, results/memory_usage.json, and (check whether
   they exist and are populated, since the 20-case run's completion status
   was uncertain at handoff time) results/rtl_comparison.json,
   results/demo.html, results/status_summary.md.

## Before writing

Ask me (the user) for the target venue/template/length/citation style if
none is supplied with this handoff -- do not guess a paper format. While
waiting, you may prepare an evidence inventory and outline grounded in the
files above.

## Rules

- Never invent a metric, log line, tool capability, citation, or
  execution count. If claims_evidence.csv doesn't have a row for
  something, say it is unverified rather than asserting it.
- Model accuracy/macro-F1 (results/ml_metrics.json) and RTL-vs-native
  agreement (results/rtl_comparison.json, if present) are two DIFFERENT
  kinds of correctness. Do not conflate them.
- Raw int8 model outputs are not confidence percentages.
- A `STATUS=1` MMIO write means firmware control flow finished without an
  internal error; it does not by itself mean RTL outputs matched the
  native oracle.
- Passing a directed/random-instruction test suite is simulation-based
  evidence, not formal ISA certification.
- Simulated RTL cycle counts say nothing about real silicon clock
  frequency, power, area, or timing closure -- none of those were
  measured, and say so explicitly if asked about them.
- This is a single autonomous attempt; do not generalize to a reliability
  claim about repeated runs.
- If the 20-case comparison did not reach 20/20 by the time implementation
  ended, report the actual completed count and their actual agreement
  result -- do not round up, and do not describe a partially-completed run
  as if the deadline simply wasn't reached for documentation purposes only.
- Do not rerun training, change RTL, or alter any frozen result to improve
  the narrative. If you believe a new experiment is needed, propose it
  separately to me and keep the original evidence intact.
- Label clearly which results correspond to Model A vs. Model B, and
  which `.tflite` SHA-256 (results/ml_metrics.json,
  docs/handoff/artifact_manifest.json) the reported RTL/native comparison
  actually used -- do not let a stale result be read as current.

## Proposed outline (adapt to actual evidence; do not treat as fixed)

1. Problem and scope (wafer-map pattern classification; explicit
   non-goals: root-cause analysis, industrial deployment readiness).
2. Autonomous workflow and tools (Animas/Zenith discovery, environment
   setup, two real environment bugs found and fixed -- see
   docs/issues.md ISS-001/ISS-002 -- as evidence of genuine engineering
   rather than a scripted demo).
3. Processor architecture (multicycle FSM, memory interface, MMIO map,
   M-extension datapath) and its from-scratch provenance (D-... decisions
   in docs/decisions.md).
4. Verification methodology (directed tests, independent reference model,
   random-instruction comparison, the two real RTL bugs found this way).
5. Wafer data and model (schema discovery, selection/split protocol,
   preprocessing, Model A/B protocol, quantization).
6. TFLM integration (pinned commit, project-generation tree, platform
   port, the real local-static-initialization bug found and fixed).
7. Experimental results: ML metrics (quality target NOT met, reported
   honestly), processor verification results, RTL-vs-native comparison
   (actual completed-case count and agreement).
8. Limitations and reproducibility (from
   docs/handoff/limitations_and_open_questions.md directly).

## Figures/tables actually supported by files (verify before using)

- Confusion matrices and per-class F1: results/ml_metrics.json.
- Preprocessing before/after: results/preprocessing_examples/*.png (8
  images: 2 per class).
- Quantization operator/tensor table: results/model_B_int8_operator_analysis.txt.
- Processor test summary table: results/cpu_verification.json
  (directed_tests array).
- Random-instruction comparison: results/random_instruction_comparison.json.
- Memory budget diagram (reserved vs. measured): results/memory_usage.json.
- RTL-vs-native per-case comparison table: results/rtl_comparison.json, if
  and only if it exists and reflects a completed or partially-completed
  run at the time you read it -- check its own internal status fields
  first.

Any diagram illustrating architecture (e.g. the multicycle FSM, the
memory/MMIO bus) that is not a screenshot of an actual tool output is a
conceptual diagram you are drawing from the RTL/description -- label it
as conceptual, not as a captured artifact.
