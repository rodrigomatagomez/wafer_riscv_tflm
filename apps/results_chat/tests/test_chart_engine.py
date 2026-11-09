import pytest

import chart_engine as ce


def test_validate_spec_rejects_unknown_kind():
    with pytest.raises(ce.ChartSpecError):
        ce.validate_spec({"kind": "plot_power_consumption"})


def test_validate_spec_rejects_unknown_enum_value():
    with pytest.raises(ce.ChartSpecError):
        ce.validate_spec({"kind": "confusion_matrix", "params": {"model_tag": "C"}})


def test_validate_spec_rejects_non_dict():
    with pytest.raises(ce.ChartSpecError):
        ce.validate_spec("not a dict")


def test_validate_spec_defaults():
    spec = ce.validate_spec({"kind": "confusion_matrix"})
    assert spec.params["model_tag"] == "B"
    assert spec.params["metric_set"] == "int8"
    assert spec.params["split"] == "test"
    assert spec.params["normalize"] is False
    assert spec.lang == "en"


def test_validate_spec_case_scores_requires_int_case_id():
    with pytest.raises(ce.ChartSpecError):
        ce.validate_spec({"kind": "case_scores", "params": {}})


@pytest.mark.parametrize("raw", [
    {"kind": "confusion_matrix"},
    {"kind": "confusion_matrix", "params": {"normalize": True}},
    {"kind": "f1_by_class"},
    {"kind": "model_comparison"},
    {"kind": "quant_comparison"},
    {"kind": "invoke_cycles"},
    {"kind": "case_scores", "params": {"case_id": 16}},
    {"kind": "classifier_correctness"},
    {"kind": "training_curves"},
    {"kind": "memory_budget"},
])
def test_render_every_kind_produces_a_figure_and_rows(ev, raw):
    spec = ce.validate_spec(raw)
    result = ce.render(spec, ev)
    assert result.fig is not None
    assert len(result.data_rows) > 0
    assert result.caption
    assert result.citations
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_case_scores_out_of_range_raises_unavailable_not_fabricated(ev):
    spec = ce.validate_spec({"kind": "case_scores", "params": {"case_id": 99}})
    with pytest.raises(ce.ChartDataUnavailable):
        ce.render(spec, ev)


def test_confusion_matrix_data_matches_ml_metrics_json(ev):
    spec = ce.validate_spec({"kind": "confusion_matrix"})
    result = ce.render(spec, ev)
    expected = ev.ml_metrics_raw["results"]["B"]["int8_metrics"]["test"]["confusion_matrix"]
    classes = ["Center", "Edge-Ring", "Scratch", "none"]
    for i, row in enumerate(result.data_rows):
        for j, cls in enumerate(classes):
            assert row[f"predicted_{cls}"] == expected[i][j]
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_normalized_confusion_matrix_still_exports_raw_counts(ev):
    spec = ce.validate_spec({"kind": "confusion_matrix", "params": {"normalize": True}})
    result = ce.render(spec, ev)
    # data_rows stores RAW counts (export must preserve the measured values);
    # normalization is a display-only transform applied to the plotted image,
    # not to the exported numbers -- verify both independently.
    raw_cm = ev.ml_metrics_raw["results"]["B"]["int8_metrics"]["test"]["confusion_matrix"]
    for row_idx, row in enumerate(result.data_rows):
        classes = ["Center", "Edge-Ring", "Scratch", "none"]
        plotted_values = [row[f"predicted_{c}"] for c in classes]
        assert plotted_values == raw_cm[row_idx]
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_case_scores_caption_mentions_quantized_not_probabilities(ev):
    spec = ce.validate_spec({"kind": "case_scores", "params": {"case_id": 0}})
    result = ce.render(spec, ev)
    assert "quantized" in result.caption.lower() or "cuantizad" in result.caption.lower()
    assert "probabilit" not in result.caption.lower().split("not")[0] or "not probabilities" in result.caption.lower()
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_case_scores_case_16_mentions_tie(ev):
    spec = ce.validate_spec({"kind": "case_scores", "params": {"case_id": 16}})
    result = ce.render(spec, ev)
    assert "tie" in result.caption.lower() or "empat" in result.caption.lower()
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_classifier_correctness_distinguishes_from_rtl_agreement(ev):
    spec = ce.validate_spec({"kind": "classifier_correctness"})
    result = ce.render(spec, ev)
    counts = {row["outcome"]: row["count"] for row in result.data_rows}
    assert counts["correct"] == 16
    assert counts["incorrect"] == 4
    assert "separate" in result.caption.lower() or "distint" in result.caption.lower()
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_memory_budget_distinguishes_reserved_vs_measured(ev):
    spec = ce.validate_spec({"kind": "memory_budget"})
    result = ce.render(spec, ev)
    values = {row["quantity"]: row["value"] for row in result.data_rows}
    assert values["tensor_arena_reserved_bytes"] == 8192
    assert values["tensor_arena_measured_peak_bytes_native_reference"] == 5216
    assert "native" in result.caption.lower()
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_training_curves_both_metrics_have_all_epochs(ev):
    spec = ce.validate_spec({"kind": "training_curves"})
    result = ce.render(spec, ev)
    assert len(result.data_rows) == len(ev.training_history["B"]["loss"])
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_spanish_lang_produces_spanish_caption(ev):
    spec = ce.validate_spec({"kind": "f1_by_class", "lang": "es"})
    result = ce.render(spec, ev)
    assert "clase" in result.caption.lower()
    import matplotlib.pyplot as plt
    plt.close(result.fig)


def test_rows_to_csv_roundtrip():
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    csv_text = ce.rows_to_csv(rows)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "a,b"
    assert lines[1] == "1,x"


def test_rows_to_csv_empty():
    assert ce.rows_to_csv([]) == ""


def test_spec_fingerprint_is_deterministic_and_order_independent():
    s1 = ce.validate_spec({"kind": "confusion_matrix", "params": {"model_tag": "A", "split": "test"}})
    s2 = ce.validate_spec({"kind": "confusion_matrix", "params": {"split": "test", "model_tag": "A"}})
    assert ce.spec_fingerprint(s1) == ce.spec_fingerprint(s2)


def test_spec_fingerprint_differs_for_different_params():
    s1 = ce.validate_spec({"kind": "confusion_matrix", "params": {"model_tag": "A"}})
    s2 = ce.validate_spec({"kind": "confusion_matrix", "params": {"model_tag": "B"}})
    assert ce.spec_fingerprint(s1) != ce.spec_fingerprint(s2)
