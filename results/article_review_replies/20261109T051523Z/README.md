# Review-reply package: 20261109T051523Z

Compact reply to the Animas/Zenith evidence questions raised in the
Animas/Zenith review of the congress article. This package does **not**
rewrite the paper, does **not** rerun the long (20-case) TFLM experiment,
does **not** retrain any model, and does **not** alter the accepted
`full20_final_001` evidence under `results/final_run_evidence/`. Any new
measurement here is a short, bounded, independently-verified check —
nothing is backfilled onto the historical record as if it had always been
measured.

**Author-provided context, not a finding of this agent**: the user has
stated that the graphical server desktop was accessed through TigerVNC.
This is recorded here as stated context; it was not inferred from, or
cross-checked against, any process/session inspection performed in this
package.

## Contents

```
README.md                                  -- this file
answers.json                                -- 12 reviewer-comment answers (Spanish), each
                                                tagged confirmed / partially_supported / unavailable,
                                                with evidence locators and open questions
manifest.json                               -- file listing + SHA-256 for every file in this package,
                                                plus distributed_as/distributed_sha256 for each
                                                compressed raw log (see "Raw log distribution" below)
checks/
  commands_used.txt                         -- every exact command executed for this package
  reproduce_ramlite_revalidation.sh          -- small script to re-run the 4 new bounded tests
                                                (+2 reps each), derived only from
                                                scripts/build_fw.sh, scripts/gen_random_program.py,
                                                and documented zenith flags -- not invented
  host_and_version_evidence.txt             -- raw output: flatpak/zenith version+help, host/CPU/RAM/affinity
  zenith_help.txt                           -- full zenith --help text (installed v1.0.2 binary)
  ramlite_reval_a_full.log(.gz)              -- NEW: test_002 directed test, injected wait, ram=full
  ramlite_reval_b_lite.log(.gz)               -- NEW: test_002 directed test, injected wait, ram=lite
  ramlite_reval_c_full.log(.gz) (+rep2/rep3)  -- NEW: 1100-instr random program, seed 4242, ram=full
  ramlite_reval_d_lite.log(.gz) (+rep2/rep3)  -- NEW: 1100-instr random program, seed 4242, ram=lite
  test002_full_vs_lite_retire_diff*.txt      -- diff outputs (raw and cycle-stripped)
  random1100_full_vs_lite_retire_diff*.txt   -- diff outputs (raw and cycle-stripped)
  section2_incident_classification_table.md -- per-incident timeout/cancellation classification
  section4_sra_history_and_current_warnings.md
  section5_mcp_tools_and_reproduction.md
  section6_open_questions_for_mifral_authors.md
```

## Raw log distribution (`.log` vs. `.log.gz`)

This repository's `.gitignore` has a blanket `*.log` rule, so the 8 raw
Zenith logs above cannot be published as plain `.log` files. Each one is
distributed as a gzip-compressed `<name>.log.gz` sibling (not matched by
any ignore rule), produced with `gzip -k -9` (original `.log` preserved
locally, never deleted). Every `.log`/`.log.gz` pair was round-trip
verified (`diff <original> <(zcat compressed)>` → exit 0) before
publication. `manifest.json` records **both** the uncompressed `sha256`
(`path`) and the compressed `distributed_sha256` (`distributed_as`) for
each of the 8 pairs, so integrity can be checked against whichever form a
reader actually has on disk.

## Headline findings (details and evidence locators in `answers.json`)

1. **Version identity**: Animas Flatpak branch (1.0.2), its OSTree commit,
   and Zenith's own self-reported engine version (`v1.0.2`) are three
   distinct pieces of information that happen to share "1.0.2" — kept
   separate here, not conflated.
2. **Host identification**: fresh CPU model/topology/hostname were
   recovered (not previously recorded anywhere in this project); no
   historical CPU load/affinity for `full20_final_001` exists in any
   evidence file, so that is marked unavailable, not backfilled.
3. **Timer scope**: Zenith's own authoritative `--help` text, for the
   exact installed binary, documents **nothing** about whether
   "simulated for HH:MM:SS" includes compile/elaboration. This is a real
   gap in the vendor's own documentation. Recommended wording: "time
   reported by Zenith," not "pure event-loop throughput."
4. **RAM-lite re-validation (the core new evidence in this package)**:
   independently reconfirmed the reviewer's finding that the project's
   previously stored "lite vs. full under injected waits" files
   (`ramlite_val_c/d/e/f/g`) **all** declare `ram=full` in their own
   banners — no valid lite/full pairing exists there under injected
   waits. Two **new**, short, banner-verified runs were executed (directed
   `test_002` under its own historical wait config, and the 1100-instruction
   random program under the historical `ram_model_lite` validation's wait
   config + `--seed 4242`), each as a true full/lite pair. Result:
   **instruction-level (PC/instruction/register-writeback) sequences match
   exactly** between `ram=full` and `ram=lite` in both new tests, but
   **cycle counts differ slightly** under injected waits (test_002: 1037 vs.
   1042; random program: 25445 vs. 25583) — a more precise, and different,
   finding than the historical "exact match including cycle numbers" claim,
   which this new evidence does not reproduce. See the corrected note added
   to `docs/decisions.md` D-007.
5. **SRA bug history**: the bug and fix are documented narratively in three
   independent files, but the original buggy source line, its compiler
   diagnostic, and any diff were never preserved anywhere accessible —
   declared unavailable, not reconstructed.
6. **MCP tool usage**: tools with a real invocation + evidence pointer are
   separated from tools that were only discovered/registered but never
   exercised in this project.
7. **Reproduction procedure**: documented exactly, including the explicit
   caveat that the xdg-document-portal path is session-specific and not
   guaranteed stable, and that `synth_tool=yosys` is configured but no
   synthesis was ever run.
8. **Open items for Mifral**: listed explicitly in
   `checks/section6_open_questions_for_mifral_authors.md`; nothing was sent
   to Mifral or any third party.

## What this package does not claim

- Does not claim the "Wall-clock cap (30 min)" message's exact origin is
  confirmed — only that Zenith itself is ruled out, and the
  `timeout_seconds` attribution is by elimination, not direct trace.
- Does not claim the historical injected-wait lite/full cycle-exact
  equivalence claim in `docs/decisions.md` D-007 is valid; it corrects that
  record (preserving the original text) based on this package's own new,
  verified evidence.
- Does not claim any Word-document changes have been applied, and does not
  claim any item marked "partially supported" or "unavailable" above is
  closed.
