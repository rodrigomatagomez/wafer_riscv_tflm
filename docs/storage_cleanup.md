# Storage cleanup record

Triggered by a `.git/index.lock: Disk quota exceeded` error. This document records the
diagnosis and cleanup actions taken, per the explicit constraint to not disturb the
active RTL simulation or restart Animas while freeing space.

## 1. Diagnosis

- **Project directory**: `/home/rmata/Documents/git/wafer_riscv_tflm` (this directory is
  *not itself* a git repository -- `git status` here returns "fatal: not a git
  repository"). A separate, related checkout, `/home/rmata/Documents/git/wafer_riscv_tflm_1`,
  **does** have a `.git` directory and is almost certainly where the reported
  `index.lock` error actually occurred. At the time of this check, no `index.lock` file
  was present there and `git status` succeeded cleanly (`on branch main, up to date with
  origin/main`, one unstaged change to `.gitignore`) -- consistent with the quota
  condition having already been transient/partially self-resolved by this point, or by
  this cleanup pass.
- **Quota tooling**: `quota`, `repquota`, `edquota` are not installed/available to this
  user. `xfs_quota -x -c 'report -h' /home` returned `XFS_GETQUOTA: Operation not
  permitted` for every entry -- querying the exact per-user quota value requires
  privilege this account does not have. The condition is a **per-user quota distinct
  from overall filesystem capacity**: `df -h /home` showed 75-77 GiB free (72-75% used
  of 300 GiB) throughout, i.e. the filesystem itself was never full. `/tmp` similarly had
  headroom (3.4 GiB free of 20 GiB). Inode usage on both `/home` and `/tmp` was low (2%
  and 7% respectively) -- this is a **block/byte quota condition, not an inode
  exhaustion**.
- **Active simulation check (before touching anything)**: the project's dedicated Zenith
  daemon for this session (PID 1201396, `/app/bin/zenith --daemon --port 45089`, parent
  `animas-backend` PID 1041663 -- the same backend instance used throughout this
  session) was found alive but **genuinely idle**: two separate `/proc/<pid>/stat`
  CPU-time measurements (6s and 10s apart) both showed **zero jiffies consumed**, and its
  working directory had reverted to `/home/rmata` (not the project directory) --
  consistent with the same "idle between jobs" signature already established earlier in
  this session, not an actively-progressing computation. `output/zsim.log` was also
  confirmed empty (0 bytes, `get_last_sim_result` independently reported
  `log_line_count: 0`) with no "done" ever logged in `animas.log` for the most recent
  `"Simulation started"` entry -- the most likely explanation is that the quota
  exhaustion itself prevented the simulator from writing its own log at the start of its
  most recent attempt. No file was removed until this idle state was independently
  confirmed via `/proc/<pid>/fd/` showing **no open file handle** to any log or waveform
  file for that process (checked across every `zenith` process on the host, not just
  this project's).
- **Largest consumers found**:
  - `/home/rmata/.cache/pip` -- 629 MiB (pip's HTTP/wheel cache for the `ml/venv`
    environment).
  - `output/soc_tb_mcp_1794126280.zwdb` -- 8.1 GiB (a ZWDB waveform file; `waveform_mode`
    was configured `"off"` for the run that apparently produced it, consistent with the
    already-documented gap in `docs/animas_capabilities.md` where `"off"` does not
    reliably prevent ZWDB generation). Confirmed via `/proc/*/fd` that no process had
    this file open.
  - `build/dataset_download/wm811k.zip` -- 150 MiB, the original downloaded dataset
    archive. Both its own SHA-256 and the extracted `data/raw/LSWMD.pkl`'s SHA-256 were
    already recorded in `data/raw/dataset_provenance.json`; both were re-verified via
    `sha256sum -c` immediately before deletion and matched exactly.
  - A separate, related checkout (`/home/rmata/Documents/git/wafer_riscv_tflm_1`, 5.3 GiB
    total, its own `ml/` + `data/` + `output/` + `build/`) was inspected but **not
    modified** -- it is a distinct git working copy with its own uncommitted change
    (`.gitignore`) and was outside this session's working scope; left for the user to
    clean up directly if desired. Its `output/` alone is 541 MiB and likely contains the
    same category of disposable waveform files, noted here as a secondary opportunity,
    not acted upon.

## 2. Essential work preserved (not touched)

Explicitly verified intact after cleanup, not merely assumed:
- `rtl/`, `tb/`, `sw/`, `scripts/`, `project.apf` -- untouched.
- `results/comparison_manifest.json`, `results/native_reference/` -- untouched.
- `models/model_B_int8.tflite` and all `build/firmware/configs/*/` outputs (firmware
  ELF/hex/map per case, including the active `case_full` config used by the in-flight
  `full20_attempt_001` run) -- untouched.
- `results/rtl_comparison_partial_per_case_runs.json` (8/20 matched via the earlier
  per-case runs) -- re-opened and confirmed still valid JSON with the expected count
  after cleanup.
- `docs/development_log.jsonl`, `docs/experiments.jsonl`, `docs/decisions.md`,
  `docs/issues.md`, `docs/handoff/` -- untouched; both `.jsonl` files re-parsed
  successfully after cleanup.
- `data/raw/LSWMD.pkl` (the actual dataset) -- **not deleted**; only the redundant
  compressed-archive copy of it was removed, per explicit authorization.
- `ml/venv` -- the installed environment itself was not touched; only its *download
  cache* (`~/.cache/pip`) was purged, which does not affect already-installed packages
  (`pip cache purge` removes cached wheels/HTTP responses, not site-packages).
- The active simulation's own working files: no `run_simulation` call was made, no
  process was signaled or killed, and no attempt was made to restart Animas during this
  pass.

## 3. Cleanup actions taken (in order)

| # | Action | Path | Size freed | Why regenerable / safe |
|---|---|---|---|---|
| 1 | `pip cache purge` (ml/venv's pip) | `~/.cache/pip` (629 MiB reported, 657.8 MB per pip's own count) | ~0.66 GB | Pure download/wheel cache; re-downloaded automatically on next `pip install` if ever needed; does not affect installed packages. |
| 2 | Removed unused ZWDB waveform file | `output/soc_tb_mcp_1794126280.zwdb` | 8.1 GiB | Confirmed via `/proc/*/fd` across every `zenith` process on the host that nothing had this file open; `waveform_mode` was `"off"` for the run in question so this was never intended to be kept; waveform files are regenerated automatically by any future `run_simulation` call. |
| 3 | Removed redundant dataset archive | `build/dataset_download/wm811k.zip` | 150 MiB | Both the archive's and the extracted file's SHA-256 already recorded in `data/raw/dataset_provenance.json` and re-verified via `sha256sum -c` immediately before deletion; the extracted, actually-used dataset file (`data/raw/LSWMD.pkl`) was left in place untouched; regenerable via `scripts/download_dataset.py` from the same recorded endpoint if ever needed again. |

**Total measured space recovered: ~8.9 GiB** (657.8 MB + 8.1 GiB + 150 MB), well above
the 2 GiB target, without touching any required artifact.

No git garbage collection, repacking, or history rewriting was performed. No large
backup archive was created. No broad/wildcard or recursive deletion was used -- every
removed path was individually identified, measured, and justified before deletion.

## 4. Post-cleanup verification

- `df -h /home`: 85 GiB free (up from 77 GiB before this pass), 72% used (down from 75%).
- Test writes succeeded both in the session scratchpad and directly in
  `docs/` (a throwaway probe file was created then immediately removed) -- confirming
  the quota condition no longer blocks ordinary writes in this project directory.
- `git status` in the actual git-tracked sibling checkout
  (`/home/rmata/Documents/git/wafer_riscv_tflm_1`) completed successfully with no
  `index.lock` present and no error -- consistent with the quota condition (which is
  shared across the whole `/home/rmata` tree, not per-subdirectory) now having headroom
  for normal git operations there. **This confirms git read operations work; it does
  not by itself confirm that any specific earlier failed `git add`/`git commit` in that
  repository actually succeeded** -- "no error now" is not evidence that a *previous*
  failed write silently went through. Anyone relying on a specific prior commit having
  landed should re-run `git status`/`git log` there directly to confirm, rather than
  inferring it from this cleanup alone.
- Per-user quota exact headroom remains unknown (no `quota`/`repquota` access from this
  account), but the measured ~8.9 GiB recovered, combined with the successful write
  tests above, indicates meaningful headroom has been restored.
- Inode usage was never the limiting factor (2% used on `/home` both before and after).

## 5. Remaining opportunity (not acted upon)

The sibling checkout `/home/rmata/Documents/git/wafer_riscv_tflm_1` (5.3 GiB, including a
541 MiB `output/` directory likely containing the same class of disposable waveform
files) was intentionally left untouched -- it is a separate git working copy with its own
pending uncommitted change and was outside this session's working scope. If further
space is needed, that `output/` directory is the next most likely safe target, but it
should be reviewed directly (the same open-file-descriptor check performed here applies
there too) rather than assumed clear.

## Summary

**Recovered**: ~8.9 GiB (pip cache 0.66 GiB + one unused ZWDB 8.1 GiB + one redundant
dataset archive 0.15 GiB). **Remaining headroom**: 85 GiB free on the 300 GiB `/home`
filesystem at the block level; exact per-user quota limit still unknown (no query tool
available to this account) but normal write operations (including in the git-tracked
sibling checkout) succeeded after cleanup. **Active simulation**: confirmed idle (not
actively progressing) before any cleanup action, via two independent CPU-time
measurements and an open-file-descriptor check; no process was signaled, killed, or
restarted, and no `run_simulation` call was made during this pass. **Essential
artifacts** (RTL/tb/sw sources, manifests, models, completed per-case results,
development records, and the dataset itself) were all verified intact afterward, not
merely assumed. The project can safely continue; whether the stalled/idle simulation
needs to be relaunched is a separate decision from this cleanup pass.

## 6. Final cleanup pass (2026-11-08, after the final run was accepted)

By the time the final run (`full20_final_001`) completed and was accepted, storage
was healthy (85 GiB free, 72% used on `/home`'s 300 GiB filesystem; no `.zwdb` file
anywhere under the project tree, confirmed via `find . -name '*.zwdb'`), so this pass
was deliberately minimal and conservative rather than another large sweep:

- Removed `results/rtl_logs/full20_attempt_001_checkpoint.log` (0 bytes). This was
  the placeholder log for the earlier `full20_attempt_001` run, which was
  independently confirmed stalled with zero usable output and terminated (see
  `docs/issues.md`, "ISS-006 (continued)"); the file held no information and no
  process had it open (confirmed via `lsof`) at the time of removal.
- Everything else under `results/rtl_logs/` was kept: the per-case logs backing the
  historical 7/20 and 8/20 partial-match evidence
  (`results/rtl_comparison_partial_per_case_runs.json`, explicitly preserved as
  separate baseline evidence, not merged into the final result), the RAM_LITE
  validation logs (`ramlite_val_*`, unique evidence for `docs/decisions.md` D-007),
  the benchmark logs (`bench_*`), and the large TRACE=1 diagnostic dump from the
  `case2_diag_001` stall investigation (`case2_diag_001_idle_at_cycle_5961876.log`,
  44.5 MiB -- unique evidence for a documented issue, not a duplicate, so not
  removed despite its size).
- The final run's own evidence (`results/final_run_evidence/`, `results/rtl_logs/
  full20_final_001_live.log`) was left in place. The sibling git checkout
  `wafer_riscv_tflm_1` had the intended final deliverables (not every scratch/
  historical file) copied into it as a separate, later step -- see
  `docs/handoff/README.md`'s "Dev directory vs. git checkout" section for the
  exact file list and what was deliberately left unsynced.
- No git garbage collection, repacking, or history rewriting was performed. No
  broad or wildcard deletion was used.
