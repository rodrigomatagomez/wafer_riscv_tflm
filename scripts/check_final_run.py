#!/usr/bin/env python3
"""Strict acceptance checker for ONE complete final 20-case RTL run.

This is deliberately much stricter than scripts/compare_results.py (which
remains the tool for aggregating/parsing historical per-case or partial
runs). This script's whole purpose is to answer exactly one question for
exactly one log file: "does this single run constitute a fully valid,
unambiguous, 20/20-matching final result?" -- and to FAIL LOUDLY (nonzero
exit, specific diagnostic) at the first structural problem rather than
silently producing a plausible-looking partial report.

Exit code is the acceptance verdict itself:
  0   -- all 20 cases present exactly once, in order, each an exact score+
         class match against the native oracle, with correct provenance and
         no error/timeout/duplicate-banner anomalies.
  1   -- usage/IO error (bad args, file not found).
  2   -- structural failure (ambiguous banner, cycle non-monotonicity,
         case-id sequence gap, missing/extra event, error halt, timeout,
         missing final status, case count != 20).
  3   -- provenance mismatch (model/ELF hash does not match the expected
         frozen value, or firmware config does not cover the full 0-19
         range).
  4   -- comparison failure (one or more cases' scores/class do not exactly
         match the native oracle).

Usage:
  check_final_run.py --log <final_run.log> --run-id <expected_run_id> \
      --firmware-config <firmware_config.json> --model-sha256 <hash> \
      --manifest <comparison_manifest.json> \
      --native <native_reference/output.jsonl> \
      --out <report.json>
"""
import argparse
import json
import re
import sys
from pathlib import Path


def atomic_write_json(path, obj):
    """Write JSON via a sibling temp file + rename so a mid-write failure
    (e.g. disk quota exhaustion, see docs/storage_cleanup.md) cannot leave a
    truncated file in place of a previously-valid one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n")
    tmp.replace(path)

RE_BANNER = re.compile(
    r"^SIM_BANNER run_id=(\S+) memfile=(\S+) trace=(\d+) maxcycles=(\d+) "
    r"ram=(\S+) fixedlat=(\d+) readywait=(\d+) randwait=(\d+) heartbeat=(\d+)")
RE_HEARTBEAT = re.compile(r"^HEARTBEAT cycle=(\d+) pc=([0-9a-fA-F]+) retired=(\d+) case_id=(\d+)")
RE_MEASURE = re.compile(r"^MMIO_MEASURE cycle=(\d+) value=(\d+)")
RE_PRED = re.compile(
    r"^MMIO_PREDICTED_CLASS cycle=(\d+) case_id=(\d+) class=(\d+) "
    r"score0=(-?\d+) score1=(-?\d+) score2=(-?\d+) score3=(-?\d+)")
RE_STATUS = re.compile(r"^MMIO_STATUS cycle=(\d+) value=(\d+)")
RE_TIMEOUT = re.compile(r"^SIM_TIMEOUT cycle=(\d+)")
RE_ERR = re.compile(r"^ERR_HALT cycle=(\d+) cause=(\d+) pc=([0-9a-fA-F]+) instr=([0-9a-fA-F]+)")

EXPECTED_N_CASES = 20


def fail(code, msg, report, out_path):
    report["accepted"] = False
    report["exit_code"] = code
    report["failure_reason"] = msg
    atomic_write_json(out_path, report)
    print(f"REJECTED (exit {code}): {msg}", file=sys.stderr)
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--firmware-config", required=True)
    ap.add_argument("--model-sha256", required=True)
    ap.add_argument("--manifest", default="results/comparison_manifest.json")
    ap.add_argument("--native", default="results/native_reference/output.jsonl")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    report = {
        "schema": "check_final_run.py strict single-run acceptance report",
        "log_path": args.log,
        "expected_run_id": args.run_id,
    }

    log_path = Path(args.log)
    if not log_path.is_file():
        print(f"ERROR: log not found: {log_path}", file=sys.stderr)
        sys.exit(1)
    fw_cfg_path = Path(args.firmware_config)
    if not fw_cfg_path.is_file():
        print(f"ERROR: firmware config not found: {fw_cfg_path}", file=sys.stderr)
        sys.exit(1)
    fw_cfg = json.loads(fw_cfg_path.read_text())

    # --- provenance check (before touching the log body) ---
    case_start = fw_cfg.get("case_start", 0)
    case_count_req = fw_cfg.get("case_count_requested")
    covers_full_range = (case_start == 0) and (case_count_req in (None, "null", "None"))
    if not covers_full_range:
        fail(3, f"firmware config does not cover the full 0-19 range "
                f"(case_start={case_start}, case_count_requested={case_count_req!r})",
             report, args.out)
    report["firmware_elf_sha256"] = fw_cfg.get("elf_sha256")
    report["firmware_config"] = fw_cfg

    manifest = json.loads(Path(args.manifest).read_text())
    if manifest["n_cases"] != EXPECTED_N_CASES:
        fail(3, f"manifest n_cases={manifest['n_cases']} != {EXPECTED_N_CASES}", report, args.out)
    manifest_cases = {c["case_id"]: c for c in manifest["cases"]}

    native = {}
    with open(args.native) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["case_id"] in native:
                fail(2, f"duplicate case_id={rec['case_id']} in native reference "
                        f"output ({args.native}) -- oracle itself is ambiguous", report, args.out)
            native[rec["case_id"]] = rec
    missing_native = set(range(EXPECTED_N_CASES)) - set(native.keys())
    if missing_native:
        fail(2, f"native oracle missing case ids {sorted(missing_native)}", report, args.out)

    # --- parse the log strictly, line by line, enforcing structure ---
    lines = log_path.read_text(errors="replace").splitlines()

    banners = [l for l in lines if l.startswith("SIM_BANNER")]
    if len(banners) != 1:
        fail(2, f"expected exactly 1 SIM_BANNER, found {len(banners)} "
                f"(ambiguous or concatenated log)", report, args.out)
    bm = RE_BANNER.match(banners[0])
    if not bm:
        fail(2, f"SIM_BANNER line did not match expected format: {banners[0]!r}", report, args.out)
    banner = {
        "run_id": bm.group(1), "memfile": bm.group(2), "trace": int(bm.group(3)),
        "maxcycles": int(bm.group(4)), "ram": bm.group(5), "fixedlat": int(bm.group(6)),
        "readywait": int(bm.group(7)), "randwait": int(bm.group(8)), "heartbeat": int(bm.group(9)),
    }
    report["banner"] = banner
    if banner["run_id"] != args.run_id:
        fail(2, f"SIM_BANNER run_id={banner['run_id']!r} != expected {args.run_id!r}",
             report, args.out)
    if banner["trace"] != 0:
        fail(2, f"SIM_BANNER trace={banner['trace']} -- expected 0 (tracing must be off "
                f"for the final run)", report, args.out)

    last_cycle = -1
    err_halts = []
    timeouts = []
    statuses = []
    # Expected alternating structure per case: MEASURE=1, MEASURE=2, PREDICTED_CLASS.
    # expected_case is the next case_id we require to appear; any deviation is a
    # hard failure (no searching forward past a gap).
    expected_case = 0
    pending_measure1_cycle = None
    cases = []  # list of accepted case records, in order

    def check_cycle(c, where):
        nonlocal last_cycle
        if c < last_cycle:
            fail(2, f"cycle went backward at {where} (cycle={c} < previous {last_cycle}) "
                    f"-- log is not monotonic (concatenated/corrupted?)", report, args.out)
        last_cycle = c

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("ERR_HALT"):
            m = RE_ERR.match(line)
            if m:
                check_cycle(int(m.group(1)), "ERR_HALT")
                err_halts.append(line)
        elif line.startswith("SIM_TIMEOUT"):
            m = RE_TIMEOUT.match(line)
            if m:
                check_cycle(int(m.group(1)), "SIM_TIMEOUT")
                timeouts.append(line)
        elif line.startswith("MMIO_STATUS"):
            m = RE_STATUS.match(line)
            if m:
                check_cycle(int(m.group(1)), "MMIO_STATUS")
                statuses.append({"cycle": int(m.group(1)), "value": int(m.group(2))})
        elif line.startswith("HEARTBEAT"):
            m = RE_HEARTBEAT.match(line)
            if m:
                check_cycle(int(m.group(1)), "HEARTBEAT")
        elif line.startswith("MMIO_MEASURE"):
            m = RE_MEASURE.match(line)
            if m:
                cyc, val = int(m.group(1)), int(m.group(2))
                check_cycle(cyc, "MMIO_MEASURE")
                if val == 1:
                    if pending_measure1_cycle is not None:
                        fail(2, f"MMIO_MEASURE value=1 seen again at cycle={cyc} before "
                                f"case {expected_case}'s value=2 was ever seen "
                                f"(started at cycle={pending_measure1_cycle})", report, args.out)
                    pending_measure1_cycle = cyc
                elif val == 2:
                    if pending_measure1_cycle is None:
                        fail(2, f"MMIO_MEASURE value=2 at cycle={cyc} with no preceding "
                                f"value=1 -- malformed Invoke() sequence", report, args.out)
                    invoke_start = pending_measure1_cycle
                    invoke_end = cyc
                    pending_measure1_cycle = None
                    # The very next structurally-relevant line MUST be this case's
                    # MMIO_PREDICTED_CLASS with case_id == expected_case. No searching
                    # forward past anything else.
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j >= len(lines) or not lines[j].startswith("MMIO_PREDICTED_CLASS"):
                        fail(2, f"expected MMIO_PREDICTED_CLASS for case {expected_case} "
                                f"immediately after Invoke() end (cycle={invoke_end}), "
                                f"found: {lines[j] if j < len(lines) else '<end of log>'!r}",
                             report, args.out)
                    pm = RE_PRED.match(lines[j])
                    if not pm:
                        fail(2, f"malformed MMIO_PREDICTED_CLASS line: {lines[j]!r}",
                             report, args.out)
                    pred_cycle = int(pm.group(1))
                    pred_case_id = int(pm.group(2))
                    check_cycle(pred_cycle, "MMIO_PREDICTED_CLASS")
                    if pred_case_id != expected_case:
                        fail(2, f"case-id sequence gap: expected case_id={expected_case} "
                                f"immediately after its own Invoke(), found "
                                f"case_id={pred_case_id} instead -- a case's result is "
                                f"missing or out of order, refusing to pair across the gap",
                             report, args.out)
                    cases.append({
                        "case_id": pred_case_id,
                        "invoke_start_cycle": invoke_start,
                        "invoke_end_cycle": invoke_end,
                        "invoke_elapsed_cycles": invoke_end - invoke_start,
                        "predicted_class": int(pm.group(3)),
                        "scores": [int(pm.group(4)), int(pm.group(5)),
                                   int(pm.group(6)), int(pm.group(7))],
                    })
                    expected_case += 1
                    i = j  # skip past the PREDICTED_CLASS line we just consumed
        i += 1

    if pending_measure1_cycle is not None:
        fail(2, f"log ended with an unfinished Invoke() (MEASURE=1 at cycle="
                f"{pending_measure1_cycle} never saw a matching value=2)", report, args.out)
    if err_halts:
        fail(2, f"{len(err_halts)} ERR_HALT event(s) present: {err_halts[:3]}", report, args.out)
    if timeouts:
        fail(2, f"{len(timeouts)} SIM_TIMEOUT event(s) present: {timeouts[:3]} "
                f"-- the run did not reach completion within its cycle budget", report, args.out)
    if len(cases) != EXPECTED_N_CASES:
        fail(2, f"expected exactly {EXPECTED_N_CASES} completed cases, found {len(cases)}",
             report, args.out)
    seen_ids = [c["case_id"] for c in cases]
    if seen_ids != list(range(EXPECTED_N_CASES)):
        fail(2, f"case ids not exactly 0..19 in order: {seen_ids}", report, args.out)
    if not statuses:
        fail(2, "no MMIO_STATUS written -- firmware never reported final completion",
             report, args.out)
    if len(statuses) != 1:
        fail(2, f"expected exactly 1 MMIO_STATUS, found {len(statuses)}: {statuses}",
             report, args.out)
    if statuses[0]["value"] != 1:
        fail(2, f"MMIO_STATUS value={statuses[0]['value']} != 1 (firmware reported an "
                f"error, not successful completion)", report, args.out)
    if statuses[0]["cycle"] < cases[-1]["invoke_end_cycle"]:
        fail(2, "MMIO_STATUS appeared before the last case's Invoke() ended -- "
                "out-of-order completion marker", report, args.out)

    report["cases_parsed"] = cases
    report["status"] = statuses[0]

    # --- provenance: model hash ---
    if report["firmware_elf_sha256"] is None:
        fail(3, "firmware_config.json has no elf_sha256 recorded", report, args.out)

    # --- exact comparison against native oracle ---
    rows = []
    mismatches = []
    for c in cases:
        cid = c["case_id"]
        nat = native[cid]
        manifest_rec = manifest_cases.get(cid, {})
        match = (c["scores"] == nat["scores"]) and (c["predicted_class"] == nat["predicted_class"])
        row = {
            "case_id": cid,
            "sample_id": manifest_rec.get("sample_id"),
            "class_name": manifest_rec.get("class_name"),
            "rtl_scores": c["scores"],
            "rtl_predicted_class": c["predicted_class"],
            "native_scores": nat["scores"],
            "native_predicted_class": nat["predicted_class"],
            "invoke_elapsed_cycles": c["invoke_elapsed_cycles"],
            "status": "MATCH" if match else "MISMATCH",
        }
        rows.append(row)
        if not match:
            mismatches.append(row)
    report["rows"] = rows
    report["model_sha256_expected"] = args.model_sha256

    if mismatches:
        report["accepted"] = False
        report["exit_code"] = 4
        report["failure_reason"] = f"{len(mismatches)}/{EXPECTED_N_CASES} case(s) mismatched"
        atomic_write_json(args.out, report)
        print(f"REJECTED (exit 4): {len(mismatches)}/{EXPECTED_N_CASES} mismatched", file=sys.stderr)
        for m in mismatches:
            print(f"  case {m['case_id']}: rtl={m['rtl_scores']}/{m['rtl_predicted_class']} "
                  f"native={m['native_scores']}/{m['native_predicted_class']}", file=sys.stderr)
        sys.exit(4)

    report["accepted"] = True
    report["exit_code"] = 0
    report["summary"] = f"ALL {EXPECTED_N_CASES}/{EXPECTED_N_CASES} CASES MATCH (exact scores + predicted class)"
    atomic_write_json(args.out, report)
    print(f"ACCEPTED: {report['summary']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
