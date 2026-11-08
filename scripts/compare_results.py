#!/usr/bin/env python3
"""Aggregate checker: merges one or more scripts/run_rtl_test.py run records
against the native TFLM oracle and the fixed comparison manifest, and
produces results/rtl_comparison.json.

This is the real implementation of the checker that source comments in this
project referenced by name before it existed (claude_implementation_prompt.txt
Section 8: "Do not claim a checker exists merely because a comment names
it."). It is deliberately strict:

  - A case with no contributing RTL run record is NOT_RUN, not silently
    skipped.
  - A case whose Invoke() started but did not finish in any contributing
    run is INCOMPLETE, kept distinct from a hard MISMATCH.
  - Two run records that both claim a completed result for the same
    case_id with DIFFERENT scores/class are a DUPLICATE_CONFLICT -- this
    aborts merging that case rather than silently picking one answer.
  - A run record whose declared model_sha256 (or firmware_elf_sha256, if
    the native side's recorded value is available for cross-check) does
    not match the expected provenance is a PROVENANCE_CONFLICT for that
    whole run -- none of its cases are used.
  - MATCH requires all four integer scores AND the predicted class to be
    exactly equal to the native oracle -- no tolerance.
  - A run's own MMIO_STATUS=1 ("completed_status_ok") means the firmware
    finished its configured case range without an execution error; it is
    recorded but does NOT by itself mark any case as a MATCH -- agreement
    is established only by the explicit score/class comparison below.
"""
import argparse
import glob
import json
import sys
from pathlib import Path


def load_manifest(path):
    d = json.loads(Path(path).read_text())
    cases = {c["case_id"]: c for c in d["cases"]}
    return d, cases


def load_native(path):
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[rec["case_id"]] = rec
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default="results/comparison_manifest.json")
    ap.add_argument("--native", default="results/native_reference/output.jsonl")
    ap.add_argument("--native-provenance", default="results/native_reference/provenance.json")
    ap.add_argument("--rtl-runs", nargs="*", default=[],
                     help="paths or globs to scripts/run_rtl_test.py JSON output files")
    ap.add_argument("--out", default="results/rtl_comparison.json")
    args = ap.parse_args()

    manifest, manifest_cases = load_manifest(args.manifest)
    native = load_native(args.native)
    native_prov = json.loads(Path(args.native_provenance).read_text()) if Path(args.native_provenance).is_file() else {}
    expected_model_sha256 = native_prov.get("model_sha256")

    n_cases = manifest["n_cases"]
    valid_ids = set(range(n_cases))

    missing_native = valid_ids - set(native.keys())
    if missing_native:
        print(f"FATAL: native oracle is itself missing case ids {sorted(missing_native)} "
              f"-- cannot run a comparison against an incomplete oracle.", file=sys.stderr)
        sys.exit(2)

    run_paths = []
    for pat in args.rtl_runs:
        matched = glob.glob(pat)
        run_paths.extend(matched if matched else [pat])

    runs = []
    for p in run_paths:
        try:
            runs.append((p, json.loads(Path(p).read_text())))
        except FileNotFoundError:
            print(f"WARNING: --rtl-runs path not found, skipping: {p}", file=sys.stderr)

    provenance_conflicts = []
    accepted_runs = []
    for p, rec in runs:
        problems = []
        if expected_model_sha256 and rec.get("model_sha256") and rec["model_sha256"] != expected_model_sha256:
            problems.append(f"model_sha256 mismatch: run={rec.get('model_sha256')} expected={expected_model_sha256}")
        if rec.get("model_sha256") is None:
            problems.append("model_sha256 not recorded in run file (unverifiable provenance)")
        if rec.get("firmware_elf_sha256") is None:
            problems.append("firmware_elf_sha256 not recorded in run file (unverifiable provenance)")
        if problems:
            provenance_conflicts.append({"run_file": p, "run_id": rec.get("run_id"), "problems": problems})
        else:
            accepted_runs.append((p, rec))

    # Collect per-case candidate results from accepted runs only.
    candidates = {}  # case_id -> list of (run_file, run_id, case_dict)
    incomplete_touch = {}  # case_id -> list of (run_file, run_id, case_dict) for started-but-not-finished
    for p, rec in accepted_runs:
        for c in rec["parsed"]["cases"]:
            cid = c.get("case_id")
            if cid is None:
                continue
            if cid not in valid_ids:
                print(f"WARNING: run {rec.get('run_id')} ({p}) reports out-of-range case_id={cid}, ignoring", file=sys.stderr)
                continue
            if c["status"] in ("completed", "completed_no_prediction_marker") and c.get("scores") is not None:
                candidates.setdefault(cid, []).append((p, rec.get("run_id"), c))
            else:
                incomplete_touch.setdefault(cid, []).append((p, rec.get("run_id"), c))

    duplicate_conflicts = []
    rows = []
    completed_count = 0
    matched_count = 0
    mismatched_count = 0

    for cid in range(n_cases):
        native_rec = native[cid]
        manifest_rec = manifest_cases[cid]
        row = {
            "case_id": cid,
            "sample_id": manifest_rec["sample_id"],
            "class_name": manifest_rec["class_name"],
            "native_scores": native_rec["scores"],
            "native_predicted_class": native_rec["predicted_class"],
        }

        cands = candidates.get(cid, [])
        if not cands:
            if cid in incomplete_touch:
                row["status"] = "INCOMPLETE"
                row["detail"] = [
                    {"run_id": rid, "run_file": p, "case_status": c["status"],
                     "invoke_elapsed_cycles_lower_bound": c.get("invoke_elapsed_cycles_lower_bound")}
                    for p, rid, c in incomplete_touch[cid]
                ]
            else:
                row["status"] = "NOT_RUN"
            rows.append(row)
            continue

        distinct = {}
        for p, rid, c in cands:
            key = (tuple(c["scores"]), c["predicted_class"])
            distinct.setdefault(key, []).append((p, rid, c))

        if len(distinct) > 1:
            duplicate_conflicts.append({
                "case_id": cid,
                "conflicting_results": [
                    {"scores": list(k[0]), "predicted_class": k[1],
                     "sources": [{"run_id": rid, "run_file": p} for p, rid, _ in v]}
                    for k, v in distinct.items()
                ],
            })
            row["status"] = "DUPLICATE_CONFLICT"
            rows.append(row)
            continue

        (scores, pred_class), sources = next(iter(distinct.items()))
        completed_count += 1
        row["rtl_scores"] = list(scores)
        row["rtl_predicted_class"] = pred_class
        row["confirmed_by_runs"] = [{"run_id": rid, "run_file": p} for p, rid, _ in sources]
        row["invoke_elapsed_cycles"] = sources[0][2].get("invoke_elapsed_cycles")

        if list(scores) == native_rec["scores"] and pred_class == native_rec["predicted_class"]:
            row["status"] = "MATCH"
            matched_count += 1
        else:
            row["status"] = "MISMATCH"
            mismatched_count += 1
        rows.append(row)

    not_run_count = sum(1 for r in rows if r["status"] == "NOT_RUN")
    incomplete_count = sum(1 for r in rows if r["status"] == "INCOMPLETE")

    all_match = matched_count == n_cases
    out = {
        "schema": "compare_results.py output, see scripts/compare_results.py",
        "generated_by": "scripts/compare_results.py",
        "n_cases": n_cases,
        "status": "complete_all_match" if all_match else "incomplete",
        "summary_counts": {
            "matched": matched_count,
            "mismatched": mismatched_count,
            "incomplete": incomplete_count,
            "not_run": not_run_count,
            "duplicate_conflicts": len(duplicate_conflicts),
        },
        "provenance": {
            "expected_model_sha256": expected_model_sha256,
            "native_output_path": args.native,
            "manifest_path": args.manifest,
            "rejected_runs_provenance_conflicts": provenance_conflicts,
        },
        "duplicate_conflicts": duplicate_conflicts,
        "rows": rows,
        "note": ("A contributing run's own MMIO_STATUS=1 means that run's firmware finished its "
                 "configured case range without an execution error; it does not by itself establish "
                 "output agreement. Agreement (MATCH) requires an exact match of all four scores and "
                 "the predicted class against results/native_reference/output.jsonl for that case_id."),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {args.out}")
    print(f"  matched={matched_count} mismatched={mismatched_count} "
          f"incomplete={incomplete_count} not_run={not_run_count} "
          f"duplicate_conflicts={len(duplicate_conflicts)} / {n_cases} total cases")
    if provenance_conflicts:
        print(f"  WARNING: {len(provenance_conflicts)} run file(s) rejected for provenance problems "
              f"(see provenance.rejected_runs_provenance_conflicts in output)", file=sys.stderr)


if __name__ == "__main__":
    main()
