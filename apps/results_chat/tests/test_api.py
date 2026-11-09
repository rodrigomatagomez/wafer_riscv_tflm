import json


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_mode_is_factual_without_llm_env_vars(client):
    r = client.get("/api/mode")
    d = r.get_json()
    assert d["mode"] == "factual"
    assert d["configured"] is False
    assert "RESULTS_CHAT_LLM_PROVIDER" in d["note"] or "No LLM provider" in d["note"]


def test_dashboard_schema_and_numbers(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.get_json()
    assert d["rtl_vs_native"]["n_matched"] == 20
    assert d["rtl_vs_native"]["n_cases"] == 20
    assert d["classifier_quality"]["n_correct_on_fixed_cases"] == 16
    assert round(d["classifier_quality"]["test_accuracy"], 4) == 0.7696
    assert round(d["classifier_quality"]["test_macro_f1"], 5) == 0.77093
    assert d["classifier_quality"]["quality_target_met"] is False
    assert len(d["cases"]) == 20
    assert d["historical_note"]


def test_suggested_questions_bilingual(client):
    en = client.get("/api/suggested_questions?lang=en").get_json()
    es = client.get("/api/suggested_questions?lang=es").get_json()
    assert en["lang"] == "en" and len(en["questions"]) >= 5
    assert es["lang"] == "es" and len(es["questions"]) >= 5
    assert en["questions"] != es["questions"]


def test_chat_basic_question(client):
    r = client.post("/api/chat", json={"message": "Is this experiment complete?", "session_id": "t1"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["mode"] == "factual"
    assert d["intent"] == "completion"
    assert d["citations"]


def test_chat_missing_message_is_400(client):
    r = client.post("/api/chat", json={"session_id": "t2"})
    assert r.status_code == 400


def test_chat_too_long_message_is_400(client):
    r = client.post("/api/chat", json={"message": "x" * 3000, "session_id": "t3"})
    assert r.status_code == 400


def test_chat_case_lookup_and_session_followup(client):
    r1 = client.post("/api/chat", json={"message": "What about case 16?", "session_id": "sess-a"})
    d1 = r1.get_json()
    assert "Case 16" in d1["answer"]

    r2 = client.post("/api/chat", json={"message": "Is that one correct?", "session_id": "sess-a"})
    d2 = r2.get_json()
    assert "Case 16" in d2["answer"]


def test_chat_spanish_question(client):
    r = client.post("/api/chat", json={"message": "¿Cuál es la precisión del clasificador?", "session_id": "t4"})
    d = r.get_json()
    assert d["lang"] == "es"
    assert "0.77093" in d["answer"] or "76.96" in d["answer"]


def test_no_write_execute_or_simulation_control_routes_exist(flask_app):
    rules = {rule.rule for rule in flask_app.url_map.iter_rules()}
    forbidden_substrings = ["run", "exec", "shell", "train", "simulate", "launch", "write", "delete", "command"]
    for rule in rules:
        lowered = rule.lower()
        for bad in forbidden_substrings:
            # "/api/run..." style routes would match; a static path like
            # "/<path:filename>" or "/api/dashboard" never contains these words.
            assert bad not in lowered, f"route {rule} contains suspicious keyword '{bad}'"
    expected = {
        "/", "/<path:filename>", "/api/health", "/api/mode",
        "/api/suggested_questions", "/api/dashboard", "/api/chat",
    }
    assert expected.issubset(rules), f"missing expected routes: {expected - rules}"
    # Flask's default static-file route must be disabled (app.py passes
    # static_folder=None): there should be no implicit second file-serving
    # route beyond the explicit frontend_static one above.
    assert "/static/<path:filename>" not in rules


def test_static_file_serving_cannot_escape_frontend_dir(client):
    r = client.get("/../backend/app.py")
    assert r.status_code in (404, 400)


def test_chat_endpoint_is_read_only_by_construction():
    # Structural check: app.py's chat route handler must not import
    # subprocess/os.system/eval/exec -- grep the actual source file rather
    # than trust a docstring claim.
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "backend" / "app.py"
    text = src.read_text()
    for forbidden in ("subprocess", "os.system(", "eval(", "exec(", "os.popen("):
        assert forbidden not in text, f"app.py must not use {forbidden}"
