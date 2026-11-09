# Section 4 — SRA before/after and diagnostics

## What is actually preserved

- `docs/development_log.jsonl:18` (E019, timestamp 2026-11-07T21:30:00Z):
  "RTL bug found: SRA used `logic'(...)` cast (defaults to 1-bit),
  truncating the arithmetic-shift result. Fixed; rerun confirmed PASS."
  `evidence_paths: ["output/zsim.log"]`.
- `output/zsim.log` is **currently 0 bytes** (confirmed fresh: `ls -la
  output/zsim.log` → `-rw-r--r--. 1 rmata edausers 0 Nov 8 05:28
  output/zsim.log`). The file this event cites as evidence does not contain
  the original compiler diagnostic or run output today.
- `docs/issues.md` has **zero** occurrences of the string "SRA" (`grep -ci
  sra docs/issues.md` → `0`). No separate narrative entry for this bug
  exists there.
- `docs/handoff/claims_evidence.csv` line for claim C011 explicitly admits:
  "sha256 of rtl/rv32im_alu.sv not separately recorded; see docs/issues.md
  for the diff" — **this pointer does not resolve to anything** (confirmed
  above). No original buggy source line, diff, or raw compiler warning for
  this specific bug survives anywhere in the accessible repository history
  or logs.
- `results/cpu_verification.json` ("test_001_basic_alu" entry,
  `bug_found_and_fixed`) gives the same narrative description (buggy cast
  truncated to 1 bit, `SRAI(0x80000000,31)` produced `1` instead of
  `0xFFFFFFFF`) but is itself a documentary/narrative record, not a
  preserved diff or log.

## What this means for the reviewer's question

- **CONFIRMED**: the bug's existence, its fix, and its passing-rerun
  outcome (narrated consistently across 3 independent documents:
  `development_log.jsonl` E019, `cpu_verification.json`,
  `claims_evidence.csv` C011).
- **UNAVAILABLE**: the original buggy source line's exact text, the
  original compiler diagnostic/warning text, and any committed diff — none
  were ever logged to a surviving file, and no git history exists for this
  project (not a git repository) to recover a prior revision from.
- This reply package does **not** reconstruct a plausible-looking buggy
  line and present it as the original. Only the current, fixed line is
  shown below, with a current, freshly-captured (2026-11-09) compiler
  warning for the same line, kept explicitly separate from any historical
  claim:

```
rtl/rv32im_alu.sv:23:  ALU_SRA:   result = a_s >>> b[4:0]; // signed->unsigned assignment copies bits as-is
```

Current (today's, not historical) compiler warning on that exact line,
captured from `results/article_review_replies/20261109T051523Z/checks/ramlite_reval_a_full.log`:

```
rtl/rv32im_alu.sv:23:27: warning: [ZEN-2436] implicit conversion changes signedness from 'logic signed[31:0]' to 'logic[31:0]'
      ALU_SRA:   result = a_s >>> b[4:0]; // signed->unsigned assignment copies bits as-is
```

**Important distinction**: this current warning is about *signedness*
conversion, not a *width*-truncation warning — it is not the same category
of diagnostic as the original 1-bit-truncation bug (which would have been
a width/size warning on the `logic'(...)` cast that no longer exists in the
source). This current warning must not be read as corroborating the
historical bug; it is evidence about today's code only.

`docs/development_log.jsonl:15` (E016) and `:16` (E017) document a
**separate** bug (MMIO `OFF_STATUS` 5-bit field truncating a 6-bit value,
aliasing STATUS onto TX) — this is not the SRA bug and must not be
conflated with it, despite both being width/truncation-category RTL bugs
found via compiler warnings early in the project.
