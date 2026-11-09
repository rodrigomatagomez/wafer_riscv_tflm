# Section 6 — items that need Mifral authors' confirmation

These are explicitly left open. Nothing below has been sent to anyone;
this is a list for the paper's authors to decide on and relay to Mifral
themselves if they choose.

1. **Product-documentation/version reference.** We have only the installed
   binary's own `--version`/`--help` output and `flatpak info` metadata
   (branch 1.0.2, commit `b527718946f7d52b00e09ce47ac5d26047dcfaaeb70a45e8f51a5a41e5c5b285`,
   Zenith self-reported `v1.0.2`). No public Mifral manual, spec sheet, or
   versioned changelog was found or should be invented. If the article
   needs a citable reference for Animas/Zenith, the authors need to ask
   Mifral what (if anything) is publicly citable.
2. **Preferred affiliation/company naming.** `Mifral Tech S.A. de C.V.` is
   the copyright string shown by the binary itself
   (`flatpak run ... zenith --version`). Whether this is the name Mifral
   wants used in the article (vs. a shorter/marketing name) needs their
   confirmation.
3. **Approval to mention LibreLane/FPGA.** This project's `synth_tool` is
   configured as `yosys` in `project.apf`, but **no synthesis run was ever
   executed** (confirmed: no synthesis evidence anywhere in
   `docs/development_log.jsonl`, `docs/experiments.jsonl`, or `results/`).
   Any mention of LibreLane, FPGA targets, or synthesis results in the
   article would currently be **unsupported by any evidence in this
   project** and should not be included without the authors first running
   and confirming an actual synthesis, and without separately checking
   whether naming LibreLane/any specific FPGA toolchain needs Mifral's
   sign-off.
4. **Private product semantics still unconfirmed:**
   - Whether `timeout_seconds` is officially documented by Mifral as a
     per-job wall-clock allowance (our own finding is self-consistent
     project documentation + elimination-based inference, not a Mifral
     spec).
   - Whether the "Wall-clock cap (30 min) reached" message's exact origin
     (which backend component renders it) is confirmed by Mifral -- we
     only ruled out Zenith itself via `--help`.
   - Whether `--seed`'s silent drop in `ui_remote_control`/daemon mode is
     known/intended Mifral behavior or an undocumented defect worth
     reporting to them.
   - Whether the xdg-document-portal mount path's instability across
     sessions is expected Animas behavior or something Mifral would want
     to harden.

**Not done, per explicit instruction:** no IEEE language-standard citation
is treated as proof of Zenith's conformance to that standard, and no
message has been sent to Mifral or any third party.
