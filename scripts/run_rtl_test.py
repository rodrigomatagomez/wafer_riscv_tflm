#!/usr/bin/env python3
"""Parse a captured Animas/Zenith simulation log (tb/soc_tb.sv's structured
stdout markers) into a durable, structured JSON run record.

This script does NOT invoke Animas itself -- Animas/Zenith is driven through
the mcp__animas__* MCP tool bridge (see docs/animas_capabilities.md), which
is not reachable from a standalone script in this environment. The actual
simulation must be launched separately (by the calling agent, through
run_simulation or a documented standalone `zenith` invocation); this script
only turns the resulting log text into comparable, provenance-tagged
evidence. The caller must supply --invocation describing exactly how that
simulation was launched, so the run record does not silently imply a launch
mechanism that didn't happen.

Prior versions of this project's comments referenced this script by name
without it existing (claude_implementation_prompt.txt Section 8's explicit
warning: "Do not claim a checker exists merely because a comment names
it."). This is the real implementation.
"""
import argparse
import hashlib
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
RE_HEARTBEAT = re.compile(
    r"^HEARTBEAT cycle=(\d+) pc=([0-9a-fA-F]+) retired=(\d+) case_id=(\d+)")
RE_RETIRE = re.compile(r"^RETIRE cycle=(\d+)")
RE_ERR_HALT = re.compile(
    r"^ERR_HALT cycle=(\d+) cause=(\d+) pc=([0-9a-fA-F]+) instr=([0-9a-fA-F]+)")
RE_MMIO_TX = re.compile(r"^MMIO_TX cycle=(\d+) byte=(\d+)")
RE_MMIO_MEASURE = re.compile(r"^MMIO_MEASURE cycle=(\d+) value=(\d+)")
RE_MMIO_PRED = re.compile(
    r"^MMIO_PREDICTED_CLASS cycle=(\d+) case_id=(\d+) class=(\d+) "
    r"score0=(-?\d+) score1=(-?\d+) score2=(-?\d+) score3=(-?\d+)")
RE_MMIO_STATUS = re.compile(r"^MMIO_STATUS cycle=(\d+) value=(\d+)")
RE_SIM_TIMEOUT = re.compile(r"^SIM_TIMEOUT cycle=(\d+)")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_log(lines):
    banner = None
    heartbeats = []
    retire_count = 0
    first_retire_cycle = None
    last_retire_cycle = None
    err_halt = None
    tx_bytes = []
    measures = []       # list of (cycle, value)
    predictions = []     # list of dicts
    status = None
    sim_timeout_cycle = None

    for raw in lines:
        line = raw.rstrip("\n")
        m = RE_BANNER.match(line)
        if m:
            banner = {
                "run_id": m.group(1), "memfile": m.group(2),
                "trace": int(m.group(3)), "maxcycles": int(m.group(4)),
                "ram": m.group(5), "fixedlat": int(m.group(6)),
                "readywait": int(m.group(7)), "randwait": int(m.group(8)),
                "heartbeat": int(m.group(9)),
            }
            continue
        m = RE_HEARTBEAT.match(line)
        if m:
            heartbeats.append({
                "cycle": int(m.group(1)), "pc": m.group(2),
                "retired": int(m.group(3)), "case_id": int(m.group(4)),
            })
            continue
        m = RE_RETIRE.match(line)
        if m:
            retire_count += 1
            c = int(m.group(1))
            if first_retire_cycle is None:
                first_retire_cycle = c
            last_retire_cycle = c
            continue
        m = RE_ERR_HALT.match(line)
        if m:
            err_halt = {
                "cycle": int(m.group(1)), "cause": int(m.group(2)),
                "pc": m.group(3), "instr": m.group(4),
            }
            continue
        m = RE_MMIO_TX.match(line)
        if m:
            tx_bytes.append({"cycle": int(m.group(1)), "byte": int(m.group(2))})
            continue
        m = RE_MMIO_MEASURE.match(line)
        if m:
            measures.append((int(m.group(1)), int(m.group(2))))
            continue
        m = RE_MMIO_PRED.match(line)
        if m:
            predictions.append({
                "cycle": int(m.group(1)), "case_id": int(m.group(2)),
                "predicted_class": int(m.group(3)),
                "scores": [int(m.group(4)), int(m.group(5)),
                           int(m.group(6)), int(m.group(7))],
            })
            continue
        m = RE_MMIO_STATUS.match(line)
        if m:
            status = {"cycle": int(m.group(1)), "value": int(m.group(2))}
            continue
        m = RE_SIM_TIMEOUT.match(line)
        if m:
            sim_timeout_cycle = int(m.group(1))
            continue

    # Pair MMIO_MEASURE (1=start,2=end) entries in log order into per-case
    # Invoke() spans, then attach the nearest following MMIO_PREDICTED_CLASS
    # entry (should be emitted immediately after Invoke() returns, before
    # the next case's MEASURE=1).
    cases = []
    pred_idx = 0
    i = 0
    pending_start = None
    log_end_cycle = None
    if heartbeats:
        log_end_cycle = max(log_end_cycle or 0, heartbeats[-1]["cycle"])
    if measures:
        log_end_cycle = max(log_end_cycle or 0, measures[-1][0])
    if sim_timeout_cycle is not None:
        log_end_cycle = max(log_end_cycle or 0, sim_timeout_cycle)

    while i < len(measures):
        cyc, val = measures[i]
        if val == 1:
            if pending_start is not None:
                # Two consecutive start markers with no end in between --
                # the previous case's Invoke() never completed before the
                # log ended or before another start was (incorrectly, or
                # because the log was truncated) observed. Record it as
                # incomplete rather than silently discarding it.
                cases.append({
                    "case_id": None,
                    "invoke_start_cycle": pending_start,
                    "invoke_end_cycle": None,
                    "invoke_elapsed_cycles": None,
                    "invoke_elapsed_cycles_lower_bound":
                        (cyc - pending_start) if cyc > pending_start else None,
                    "predicted_class": None, "scores": None,
                    "status": "incomplete_superseded_by_next_start",
                })
            pending_start = cyc
        elif val == 2 and pending_start is not None:
            start_cyc = pending_start
            end_cyc = cyc
            pending_start = None
            pred = None
            for p in predictions[pred_idx:]:
                if p["cycle"] >= end_cyc:
                    pred = p
                    break
            if pred is not None:
                pred_idx = predictions.index(pred) + 1
            cases.append({
                "case_id": pred["case_id"] if pred else None,
                "invoke_start_cycle": start_cyc,
                "invoke_end_cycle": end_cyc,
                "invoke_elapsed_cycles": end_cyc - start_cyc,
                "invoke_elapsed_cycles_lower_bound": None,
                "predicted_class": pred["predicted_class"] if pred else None,
                "scores": pred["scores"] if pred else None,
                "status": "completed" if pred else "completed_no_prediction_marker",
            })
        i += 1

    if pending_start is not None:
        elapsed_lb = (log_end_cycle - pending_start) if log_end_cycle else None
        cases.append({
            "case_id": None,
            "invoke_start_cycle": pending_start,
            "invoke_end_cycle": None,
            "invoke_elapsed_cycles": None,
            "invoke_elapsed_cycles_lower_bound": elapsed_lb,
            "predicted_class": None, "scores": None,
            "status": "incomplete_at_log_end",
        })

    # Outcome classification. Important per claude_implementation_prompt.txt
    # Section 3/this continuation's Section 3: a tool-call return is not the
    # same thing as the simulator finishing -- a log with none of
    # MMIO_STATUS/SIM_TIMEOUT/ERR_HALT must be reported as "truncated_log",
    # not silently treated as either a pass or a timeout.
    if err_halt is not None:
        outcome = "error_halt"
    elif status is not None and status["value"] == 1:
        outcome = "completed_status_ok"
    elif status is not None and status["value"] == 2:
        outcome = "completed_status_error"
    elif status is not None:
        outcome = f"completed_status_unknown_value_{status['value']}"
    elif sim_timeout_cycle is not None:
        outcome = "sim_timeout"
    else:
        outcome = "truncated_log_no_terminal_marker"

    return {
        "banner": banner,
        "outcome": outcome,
        "status_marker": status,
        "sim_timeout_cycle": sim_timeout_cycle,
        "err_halt": err_halt,
        "retire_trace": {
            "line_count": retire_count,
            "first_cycle": first_retire_cycle,
            "last_cycle": last_retire_cycle,
        },
        "heartbeat_count": len(heartbeats),
        "last_heartbeat": heartbeats[-1] if heartbeats else None,
        "mmio_tx_bytes": tx_bytes,
        "mmio_tx_ascii": "".join(chr(b["byte"]) for b in tx_bytes
                                  if 32 <= b["byte"] < 127),
        "cases": cases,
        "log_end_cycle_estimate": log_end_cycle,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", required=True, help="path to the captured raw simulation log text")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--invocation", required=True,
                     help="exact description of the Animas tool call or Zenith command that produced this log")
    ap.add_argument("--elf", help="path to the firmware ELF actually simulated, for hashing")
    ap.add_argument("--firmware-config", help="path to a firmware_config.json from scripts/build_firmware.sh")
    ap.add_argument("--model-sha256")
    ap.add_argument("--started-at", help="ISO8601 UTC timestamp; omit if genuinely unknown")
    ap.add_argument("--finished-at", help="ISO8601 UTC timestamp; omit if genuinely unknown")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    log_path = Path(args.log)
    if not log_path.is_file():
        print(f"ERROR: log file not found: {log_path}", file=sys.stderr)
        sys.exit(2)
    lines = log_path.read_text(errors="replace").splitlines(keepends=True)
    parsed = parse_log(lines)

    elf_sha256 = None
    firmware_config = None
    if args.firmware_config:
        firmware_config = json.loads(Path(args.firmware_config).read_text())
        elf_sha256 = firmware_config.get("elf_sha256")
        if args.elf is None:
            args.elf = firmware_config.get("elf_path")
    if args.elf and elf_sha256 is None:
        elf_sha256 = sha256_file(args.elf)

    record = {
        "run_id": args.run_id,
        "invocation": args.invocation,
        "started_at_utc": args.started_at,
        "finished_at_utc": args.finished_at,
        "log_path": str(log_path),
        "log_sha256": sha256_file(log_path),
        "firmware_elf_sha256": elf_sha256,
        "firmware_config": firmware_config,
        "model_sha256": args.model_sha256,
        "parsed": parsed,
    }
    out_path = Path(args.out)
    atomic_write_json(out_path, record)
    print(f"Wrote {out_path}")
    print(f"  outcome: {parsed['outcome']}")
    print(f"  cases parsed: {len(parsed['cases'])}")
    for c in parsed["cases"]:
        print(f"    case_id={c['case_id']} status={c['status']} "
              f"invoke_elapsed={c['invoke_elapsed_cycles']} "
              f"lower_bound={c['invoke_elapsed_cycles_lower_bound']} "
              f"pred={c['predicted_class']} scores={c['scores']}")


if __name__ == "__main__":
    main()
