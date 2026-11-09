"""Read-only loader for the project's authoritative evidence files.

This module never writes to the project tree, never executes shell
commands, and never touches the simulator. It reads a fixed set of
already-verified JSON/log files produced by the frozen full20_final_001
experiment and derives the numbers this chat application reports, each
tagged with the exact source file and field it came from.

Preferring final evidence over historical partial results (per the task
instructions): results/final_run_evidence/ and results/rtl_comparison.json
(which reflects the single final run) are the sources of truth for RTL
outcomes. results/rtl_comparison_partial_per_case_runs.json is historical
and is only surfaced if a user explicitly asks about it.
"""
from __future__ import annotations

import gzip
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


class EvidenceError(Exception):
    """Raised when a required evidence file is missing or malformed."""


def _project_root() -> Path:
    env_root = os.environ.get("RESULTS_CHAT_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # apps/results_chat/backend/evidence.py -> project root is 3 parents up
    return Path(__file__).resolve().parents[3]


@dataclass
class Fact:
    """A single reported number/string with its exact provenance."""
    value: Any
    source_file: str
    source_field: str

    def cite(self) -> str:
        return f"{self.source_file} ({self.source_field})"


@dataclass
class CaseResult:
    case_id: int
    sample_id: int
    ground_truth_class_idx: int
    ground_truth_class_name: str
    native_scores: list
    native_predicted_class: int
    rtl_scores: list
    rtl_predicted_class: int
    invoke_elapsed_cycles: Optional[int]
    invoke_start_cycle: Optional[int]
    invoke_end_cycle: Optional[int]
    prediction_log_cycle: Optional[int]
    rtl_matches_native: bool
    classifier_correct: bool
    has_score_tie: bool
    tie_class_names: list = field(default_factory=list)

    def log_citation(self) -> str:
        if self.prediction_log_cycle is not None:
            return (
                f"results/rtl_logs/full20_final_001_live.log "
                f"(MMIO_PREDICTED_CLASS cycle={self.prediction_log_cycle} case_id={self.case_id})"
            )
        return (
            f"results/final_run_evidence/full20_final_001_check_report.json "
            f"(cases_parsed[case_id={self.case_id}])"
        )


@dataclass
class Evidence:
    project_root: Path
    load_warnings: list

    # Final run identity / provenance
    run_id: Fact
    sim_banner: Fact
    final_cycle: Fact
    wall_clock_seconds: Fact
    wall_clock_zenith_reported: Fact
    checker_exit_code: Fact
    checker_verdict: Fact
    model_sha256: Fact
    firmware_elf_sha256: Fact
    tflm_commit: Fact

    # Aggregate RTL-vs-native outcome
    n_cases: Fact
    n_matched_rtl_native: Fact

    # Classifier quality (from ml_metrics.json, model B, int8, test split)
    classes: Fact
    test_accuracy: Fact
    test_macro_f1: Fact
    quality_target_macro_f1: Fact
    quality_target_met: Fact
    per_class_f1_test: Fact
    confusion_matrix_test: Fact

    # Memory
    tensor_arena_reserved_bytes: Fact
    tensor_arena_measured_peak_bytes: Fact
    tensor_arena_measurement_source_note: Fact

    # Processor verification
    cpu_directed_tests_pass: Fact
    cpu_random_instruction_mismatches: Fact

    # Per-case table (final evidence)
    cases: list

    # Full raw dicts, for the chart engine's flexible model/split/metric_set
    # filtering (the Fact fields above cover the single canonical B/int8/test
    # figures qa_engine.py reports by default).
    ml_metrics_raw: dict = field(default_factory=dict)
    memory_usage_raw: dict = field(default_factory=dict)
    training_history: dict = field(default_factory=dict)

    # Derived
    n_classifier_correct_on_fixed_cases: int = 0
    misclassified_case_ids: list = field(default_factory=list)
    tie_case_ids: list = field(default_factory=list)

    def case(self, case_id: int) -> Optional[CaseResult]:
        for c in self.cases:
            if c.case_id == case_id:
                return c
        return None


def _read_json(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise EvidenceError(f"missing evidence file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"malformed JSON in evidence file: {path}: {exc}") from exc


_PRED_RE = re.compile(r"^MMIO_PREDICTED_CLASS cycle=(\d+) case_id=(\d+)")


def _parse_prediction_cycles(root: Path, warnings: list) -> dict:
    """Best-effort: map case_id -> the exact cycle of its MMIO_PREDICTED_CLASS
    log line, for precise log-location citations. Not fatal if unavailable --
    the per-case table still works from the JSON evidence without this."""
    live_log = root / "results/rtl_logs/full20_final_001_live.log"
    gz_log = root / "results/final_run_evidence/full20_final_001_raw_log.txt.gz"

    lines = None
    try:
        if live_log.is_file():
            lines = live_log.read_text(errors="replace").splitlines()
        elif gz_log.is_file():
            with gzip.open(gz_log, "rt", errors="replace") as f:
                lines = f.read().splitlines()
    except OSError as exc:
        warnings.append(f"could not read raw log for prediction-cycle citations: {exc}")
        return {}

    if lines is None:
        warnings.append(
            "neither results/rtl_logs/full20_final_001_live.log nor "
            "results/final_run_evidence/full20_final_001_raw_log.txt.gz was found; "
            "per-case log-location citations will fall back to the JSON evidence file"
        )
        return {}

    out = {}
    for line in lines:
        m = _PRED_RE.match(line)
        if m:
            out[int(m.group(2))] = int(m.group(1))
    return out


def load_evidence(project_root: Optional[Path] = None) -> Evidence:
    root = project_root or _project_root()
    warnings: list = []

    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(root))
        except ValueError:
            return str(p)

    fp_path = root / "results/final_run_evidence/full20_final_001_fingerprints.json"
    check_path = root / "results/final_run_evidence/full20_final_001_check_report.json"
    manifest_path = root / "results/comparison_manifest.json"
    ml_path = root / "results/ml_metrics.json"
    mem_path = root / "results/memory_usage.json"
    cpu_path = root / "results/cpu_verification.json"
    rtlcmp_path = root / "results/rtl_comparison.json"

    fp = _read_json(fp_path)
    check = _read_json(check_path)
    manifest = _read_json(manifest_path)
    ml = _read_json(ml_path)
    mem = _read_json(mem_path)
    cpu = _read_json(cpu_path)
    rtlcmp = _read_json(rtlcmp_path)

    training_history = {}
    for tag in ("A", "B"):
        th_path = root / f"results/training_history_{tag}.json"
        if th_path.is_file():
            training_history[tag] = _read_json(th_path)
        else:
            warnings.append(f"missing {rel(th_path)} -- training-curve charts for model {tag} will be unavailable")

    classes = ml["classes"]
    b_test_int8 = ml["results"]["B"]["int8_metrics"]["test"]

    manifest_cases = {c["case_id"]: c for c in manifest["cases"]}
    parsed_cases = {c["case_id"]: c for c in check.get("cases_parsed", [])}
    prediction_cycles = _parse_prediction_cycles(root, warnings)

    cases: list[CaseResult] = []
    for row in check["rows"]:
        cid = row["case_id"]
        mrow = manifest_cases.get(cid)
        if mrow is None:
            warnings.append(
                f"case_id {cid} present in check report but missing from "
                f"{rel(manifest_path)} -- excluded from the per-case table"
            )
            continue
        gt_idx = mrow["class_idx"]
        gt_name = classes[gt_idx]
        rtl_scores = row["rtl_scores"]
        rtl_pred = row["rtl_predicted_class"]
        max_score = max(rtl_scores)
        tie_indices = [i for i, s in enumerate(rtl_scores) if s == max_score]
        has_tie = len(tie_indices) > 1
        tie_names = [classes[i] for i in tie_indices] if has_tie else []
        prow = parsed_cases.get(cid, {})

        cases.append(CaseResult(
            case_id=cid,
            sample_id=mrow["sample_id"],
            ground_truth_class_idx=gt_idx,
            ground_truth_class_name=gt_name,
            native_scores=row["native_scores"],
            native_predicted_class=row["native_predicted_class"],
            rtl_scores=rtl_scores,
            rtl_predicted_class=rtl_pred,
            invoke_elapsed_cycles=row.get("invoke_elapsed_cycles"),
            invoke_start_cycle=prow.get("invoke_start_cycle"),
            invoke_end_cycle=prow.get("invoke_end_cycle"),
            prediction_log_cycle=prediction_cycles.get(cid),
            rtl_matches_native=(row["status"] == "MATCH"),
            classifier_correct=(rtl_pred == gt_idx),
            has_score_tie=has_tie,
            tie_class_names=tie_names,
        ))
    cases.sort(key=lambda c: c.case_id)

    if len(cases) != 20:
        warnings.append(
            f"expected 20 cases in {rel(check_path)}, found {len(cases)}"
        )

    misclassified = [c.case_id for c in cases if not c.classifier_correct]
    tie_cases = [c.case_id for c in cases if c.has_score_tie]
    n_correct = sum(1 for c in cases if c.classifier_correct)
    n_matched = sum(1 for c in cases if c.rtl_matches_native)

    ev = Evidence(
        project_root=root,
        load_warnings=warnings,

        run_id=Fact(fp["run_id"], rel(fp_path), "run_id"),
        sim_banner=Fact(fp["sim_banner"], rel(fp_path), "sim_banner"),
        final_cycle=Fact(fp["final_cycle"], rel(fp_path), "final_cycle"),
        wall_clock_seconds=Fact(fp["wall_clock_seconds_measured"], rel(fp_path), "wall_clock_seconds_measured"),
        wall_clock_zenith_reported=Fact(fp["wall_clock_as_reported_by_zenith"], rel(fp_path), "wall_clock_as_reported_by_zenith"),
        checker_exit_code=Fact(fp["strict_checker_exit_code"], rel(fp_path), "strict_checker_exit_code"),
        checker_verdict=Fact(fp["strict_checker_verdict"], rel(fp_path), "strict_checker_verdict"),
        model_sha256=Fact(fp["model_sha256"], rel(fp_path), "model_sha256"),
        firmware_elf_sha256=Fact(fp["firmware_elf_sha256"], rel(fp_path), "firmware_elf_sha256"),
        tflm_commit=Fact(fp["tflm_commit"], rel(fp_path), "tflm_commit"),

        n_cases=Fact(rtlcmp["n_cases"], rel(rtlcmp_path), "n_cases"),
        n_matched_rtl_native=Fact(rtlcmp["summary_counts"]["matched"], rel(rtlcmp_path), "summary_counts.matched"),

        classes=Fact(classes, rel(ml_path), "classes"),
        test_accuracy=Fact(b_test_int8["accuracy"], rel(ml_path), "results.B.int8_metrics.test.accuracy"),
        test_macro_f1=Fact(ml["final_test_macro_f1_int8"], rel(ml_path), "final_test_macro_f1_int8"),
        quality_target_macro_f1=Fact(ml["quality_target_macro_f1"], rel(ml_path), "quality_target_macro_f1"),
        quality_target_met=Fact(ml["quality_target_met_on_test"], rel(ml_path), "quality_target_met_on_test"),
        per_class_f1_test=Fact(b_test_int8["per_class_f1"], rel(ml_path), "results.B.int8_metrics.test.per_class_f1"),
        confusion_matrix_test=Fact(b_test_int8["confusion_matrix"], rel(ml_path), "results.B.int8_metrics.test.confusion_matrix"),

        tensor_arena_reserved_bytes=Fact(mem["tensor_arena"]["reserved_capacity_bytes"], rel(mem_path), "tensor_arena.reserved_capacity_bytes"),
        tensor_arena_measured_peak_bytes=Fact(mem["tensor_arena"]["measured_peak_use_bytes_native_reference"], rel(mem_path), "tensor_arena.measured_peak_use_bytes_native_reference"),
        tensor_arena_measurement_source_note=Fact(mem["tensor_arena"]["note"], rel(mem_path), "tensor_arena.note"),

        cpu_directed_tests_pass=Fact(
            all(str(t.get("result", "")).startswith("PASS") for t in cpu["directed_tests"])
            if isinstance(cpu.get("directed_tests"), list) else None,
            rel(cpu_path), "directed_tests[*].result",
        ),
        cpu_random_instruction_mismatches=Fact(
            cpu["random_instruction_comparison"].get("mismatch_count"),
            rel(cpu_path), "random_instruction_comparison.mismatch_count",
        ),

        cases=cases,
        ml_metrics_raw=ml,
        memory_usage_raw=mem,
        training_history=training_history,
    )
    ev.n_classifier_correct_on_fixed_cases = n_correct
    ev.misclassified_case_ids = misclassified
    ev.tie_case_ids = tie_cases

    if ev.n_matched_rtl_native.value != n_matched:
        warnings.append(
            f"results/rtl_comparison.json reports {ev.n_matched_rtl_native.value} matched "
            f"but recomputing from the per-case rows gives {n_matched}"
        )

    return ev


_CACHED: Optional[Evidence] = None


def get_evidence(refresh: bool = False) -> Evidence:
    """Return a process-wide cached Evidence snapshot.

    Evidence files are static (the experiment is frozen), so caching avoids
    re-reading/re-parsing on every chat/dashboard request. Pass refresh=True
    only for tests or explicit diagnostics.
    """
    global _CACHED
    if _CACHED is None or refresh:
        _CACHED = load_evidence()
    return _CACHED
