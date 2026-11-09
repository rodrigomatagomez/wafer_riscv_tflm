import json
import shutil
from pathlib import Path

import pytest

from evidence import EvidenceError, load_evidence


def test_real_evidence_loads_without_warnings(ev):
    assert ev.load_warnings == []


def test_twenty_cases_all_rtl_native_matched(ev):
    assert len(ev.cases) == 20
    assert ev.n_cases.value == 20
    assert ev.n_matched_rtl_native.value == 20
    assert all(c.rtl_matches_native for c in ev.cases)


def test_classifier_correct_on_sixteen_of_twenty(ev):
    assert ev.n_classifier_correct_on_fixed_cases == 16
    assert sorted(ev.misclassified_case_ids) == [0, 11, 15, 16]


def test_case_16_has_tie_between_scratch_and_none(ev):
    c = ev.case(16)
    assert c.has_score_tie is True
    assert set(c.tie_class_names) == {"Scratch", "none"}
    assert c.rtl_scores == c.native_scores == [41, 10, 49, 49]
    assert c.rtl_predicted_class == c.native_predicted_class == 2
    assert c.ground_truth_class_name == "none"
    assert c.classifier_correct is False
    assert c.rtl_matches_native is True


def test_case_0_is_a_misclassification_but_rtl_matches_native(ev):
    c = ev.case(0)
    assert c.ground_truth_class_name == "Center"
    assert c.rtl_predicted_class == 2
    assert c.classifier_correct is False
    assert c.rtl_matches_native is True
    assert c.has_score_tie is False


def test_classifier_quality_numbers_match_ml_metrics_json(ev):
    # These are the exact figures the task statement asks the assistant to
    # explain correctly: ~76.96% accuracy, 0.77093 macro-F1, target unmet.
    assert round(ev.test_accuracy.value, 4) == 0.7696
    assert round(ev.test_macro_f1.value, 5) == 0.77093
    assert ev.quality_target_macro_f1.value == 0.85
    assert ev.quality_target_met.value is False


def test_tensor_arena_measurement_is_attributed_to_native_reference(ev):
    assert ev.tensor_arena_reserved_bytes.value == 8192
    assert ev.tensor_arena_measured_peak_bytes.value == 5216
    assert "native" in ev.tensor_arena_measurement_source_note.value.lower()


def test_cpu_verification_passes(ev):
    assert ev.cpu_directed_tests_pass.value is True
    assert ev.cpu_random_instruction_mismatches.value == 0


def test_every_fact_has_a_real_citation(ev):
    for name in [
        "run_id", "checker_verdict", "n_matched_rtl_native", "test_accuracy",
        "test_macro_f1", "tensor_arena_measured_peak_bytes", "final_cycle",
    ]:
        fact = getattr(ev, name)
        assert fact.source_file, f"{name} has no source_file"
        assert fact.source_field, f"{name} has no source_field"
        # the cited file must actually exist on disk relative to project root
        assert (ev.project_root / fact.source_file).is_file(), (
            f"{name} cites {fact.source_file}, which does not exist"
        )


def test_case_log_citation_matches_a_real_log_line(ev):
    c = ev.case(16)
    citation = c.log_citation()
    assert "cycle=" in citation
    log_path = ev.project_root / "results/rtl_logs/full20_final_001_live.log"
    assert log_path.is_file()
    text = log_path.read_text()
    assert f"MMIO_PREDICTED_CLASS cycle={c.prediction_log_cycle} case_id=16" in text


def test_missing_evidence_file_raises_evidence_error(tmp_path):
    # Simulate missing/inconsistent evidence: an empty project root with
    # none of the required result files. The loader must fail loudly with
    # EvidenceError, not crash with an unrelated traceback or silently
    # return empty/zeroed data.
    with pytest.raises(EvidenceError):
        load_evidence(tmp_path)


def test_malformed_json_raises_evidence_error(tmp_path, ev):
    # Copy the real evidence tree, then corrupt one required file, to
    # confirm the loader distinguishes "malformed" from "missing" and still
    # fails loudly rather than guessing.
    _mirror_minimal_project(tmp_path, ev.project_root)
    bad_path = tmp_path / "results/ml_metrics.json"
    bad_path.write_text("{not valid json")
    with pytest.raises(EvidenceError):
        load_evidence(tmp_path)


def test_case_count_mismatch_is_recorded_as_a_warning_not_hidden(tmp_path, ev):
    # Inconsistent evidence: check_report.json missing one case's row.
    # The loader must surface this as a load_warning rather than silently
    # reporting a wrong total as if it were clean.
    _mirror_minimal_project(tmp_path, ev.project_root)
    check_path = tmp_path / "results/final_run_evidence/full20_final_001_check_report.json"
    data = json.loads(check_path.read_text())
    data["rows"] = data["rows"][:-1]  # drop the last case's row
    check_path.write_text(json.dumps(data))

    loaded = load_evidence(tmp_path)
    assert len(loaded.cases) == 19
    assert any("expected 20 cases" in w for w in loaded.load_warnings)


def _mirror_minimal_project(dst: Path, src_root: Path):
    needed = [
        "results/final_run_evidence/full20_final_001_fingerprints.json",
        "results/final_run_evidence/full20_final_001_check_report.json",
        "results/comparison_manifest.json",
        "results/ml_metrics.json",
        "results/memory_usage.json",
        "results/cpu_verification.json",
        "results/rtl_comparison.json",
    ]
    for rel in needed:
        src = src_root / rel
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, target)
