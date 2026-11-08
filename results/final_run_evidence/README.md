# Final run evidence: `full20_final_001`

This directory holds the complete, self-contained evidence for the one final,
accepted, 20/20-matching RTL run. It is produced by a single execution from
cycle 0 of the frozen firmware against the frozen model and the 20 fixed
comparison cases, launched by standalone `flatpak run --branch=1.0.2
--command=zenith com.mifraltech.animaseda ...` (bypasses the Animas MCP
daemon; no `--zwdb`, so no waveform file is produced). See
`full20_final_001_fingerprints.json`'s `launch_method`/`sim_banner` fields for
the exact configuration, and `docs/handoff/README.md` for the full
reproduction command.

## Files

| File | Role |
|---|---|
| `full20_final_001_raw_log.txt.gz` | Complete, unmodified stdout/stderr capture of the simulation (gzip of `results/rtl_logs/full20_final_001_live.log`; `raw_log_sha256` in the fingerprints file is the hash of the uncompressed original). |
| `full20_final_001_run_record.json` | `scripts/run_rtl_test.py`'s structured parse of the raw log (per-case Invoke cycles, scores, predicted classes, outcome classification). |
| `full20_final_001_check_report.json` | `scripts/check_final_run.py`'s strict single-run acceptance report. `"accepted": true`, `"exit_code": 0`. This is the authoritative pass/fail verdict for this run. |
| `full20_final_001_fingerprints.json` | Model/firmware/manifest hashes, launch method, banner, timing, final cycle/status markers, and the classifier's known 16/20 accuracy on these fixed cases (separate from RTL correctness). |
| `full20_final_001_firmware_config.json` | `scripts/build_firmware.sh`'s build record for the exact firmware used (`case_full`, covers cases 0-19, ELF SHA-256 `622d1816...`). |
| `full20_final_001_firmware.elf` / `.hex` / `.map` / `.size` / `.dis` | The exact firmware binary simulated, in every form produced by the build (linked ELF, Verilog `$readmemh` hex, link map, `size` report, full disassembly). |
| `native_reference_output.jsonl` / `native_reference_provenance.json` | Copy of the native x86 TFLM oracle's per-case output and its provenance (model hash, TFLM commit, build script), for a self-contained comparison baseline without depending on `results/native_reference/` staying unchanged. |

## Result

All 20 cases (case_id 0-19) completed exactly once, in order, with correct
provenance (model hash, firmware ELF hash, banner configuration all verified
against the expected frozen values), no error halts, no timeouts, monotonic
cycle counts, and exactly one correctly-ordered final `MMIO_STATUS=1` after
the last case. All four integer scores and the predicted class for every
case are an exact, bit-for-bit match against the native TFLM oracle.

The classifier itself is correct on 16 of these 20 fixed cases and wrong on
4 (case_id 0, 11, 15, 16) -- this is the model's pre-existing, honestly
measured quality limitation (quantized test macro-F1 = 0.7709, below the
0.85 target), not an RTL defect: the RTL reproduces the native oracle's
output exactly even where that output is itself a misclassification.

## Measured timing

- Simulated hardware cycles: 142,937,769 (init ~351K + 20 x ~7,031,500/case
  Invoke() + inter-case overhead).
- Wall-clock: 01:35:52 (5,752s, as reported by Zenith itself) / 5,754s (as
  measured from log file birth to final write) -- the 2s difference is
  process-startup/log-flush overhead outside the simulated run itself.
