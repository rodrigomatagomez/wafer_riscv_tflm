import chart_router as cr


def test_is_chart_request_positive_examples():
    for text in [
        "Grafica el F1 por clase.", "Plot F1 by class.", "Show me a chart of the confusion matrix.",
        "Compare Model A and B.", "Grafica la matriz de confusión.",
    ]:
        assert cr.is_chart_request(text), text


def test_is_chart_request_negative_examples():
    for text in ["Is this experiment complete?", "What is the classifier accuracy?", "Hello"]:
        assert not cr.is_chart_request(text), text


def test_exact_task_example_phrases_spanish():
    last_spec = None
    expected_kinds = ["f1_by_class", "model_comparison", "confusion_matrix", "case_scores"]
    turns = [
        "Grafica el F1 por clase.",
        "Ahora compara A y B.",
        "Muéstrame la matriz normalizada.",
        "Enséñame los scores del caso 16.",
    ]
    for text, expected_kind in zip(turns, expected_kinds):
        spec = cr.parse_chart_request(text, "es", last_spec)
        assert spec is not None, text
        assert spec["kind"] == expected_kind, f"{text} -> {spec}"
        last_spec = spec

    # "Pon esa gráfica en español." re-targets the last chart's language only.
    spec = cr.parse_chart_request("Pon esa gráfica en español.", "es", last_spec)
    assert spec["kind"] == last_spec["kind"]
    assert spec["lang"] == "es"

    assert cr.is_download_request("Déjame descargarla.")


def test_confusion_matrix_normalize_flag():
    spec = cr.parse_chart_request("Show me the normalized confusion matrix.", "en", None)
    assert spec["kind"] == "confusion_matrix"
    assert spec["params"]["normalize"] is True


def test_case_scores_extracts_case_id_both_languages():
    spec_en = cr.parse_chart_request("Show me the scores for case 16.", "en", None)
    spec_es = cr.parse_chart_request("Enséñame los scores del caso 16.", "es", None)
    assert spec_en["params"]["case_id"] == 16
    assert spec_es["params"]["case_id"] == 16


def test_case_scores_without_a_number_returns_none():
    assert cr.parse_chart_request("Show me the case scores.", "en", None) is None


def test_model_tag_and_split_extraction():
    spec = cr.parse_chart_request("Plot the confusion matrix for model A on the validation split.", "en", None)
    assert spec["params"]["model_tag"] == "A"
    assert spec["params"]["split"] == "val"


def test_quant_comparison_detection():
    spec = cr.parse_chart_request("Compare float and int8 accuracy for model A.", "en", None)
    assert spec["kind"] == "quant_comparison"
    assert spec["params"]["model_tag"] == "A"
    assert spec["params"]["metric"] == "accuracy"


def test_training_curves_metric_extraction():
    spec = cr.parse_chart_request("Plot the training loss curve for model A.", "en", None)
    assert spec["kind"] == "training_curves"
    assert spec["params"]["model_tag"] == "A"
    assert spec["params"]["metric"] == "loss"


def test_language_switch_follow_up_reuses_full_prior_spec():
    prior = {"kind": "case_scores", "params": {"case_id": 3}, "lang": "en"}
    spec = cr.parse_chart_request("Put that chart in Spanish.", "en", prior)
    assert spec["kind"] == "case_scores"
    assert spec["params"]["case_id"] == 3
    assert spec["lang"] == "es"


def test_download_request_bilingual():
    assert cr.is_download_request("Let me download it.")
    assert cr.is_download_request("Déjame descargarla.")
    assert cr.is_download_request("¿Puedo descargar esto?")
    assert not cr.is_download_request("What is the classifier accuracy?")


def test_unrelated_question_returns_none():
    assert cr.parse_chart_request("What is the classifier's accuracy?", "en", None) is None
