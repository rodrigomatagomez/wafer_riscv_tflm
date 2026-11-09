"""Deterministic tests for chat_pipeline.py with the LLM explicitly
disabled (RESULTS_CHAT_LLM_PROVIDER=none), so these pass identically
whether or not a local llama-server happens to be running on this host.
Live LLM behavior is covered separately in test_live_llm.py, which
performs genuine network calls to a running server and skips (rather than
silently passing against factual mode) if none is reachable."""
import pytest

import chart_cache
from chat_pipeline import handle_message, new_session_state


@pytest.fixture(autouse=True)
def _force_factual_mode(monkeypatch, chart_cache_dir):
    monkeypatch.setenv("RESULTS_CHAT_LLM_PROVIDER", "none")


def test_completion_question_factual(ev):
    state = new_session_state()
    r = handle_message("Is this experiment functionally complete?", ev, None, state)
    assert r["mode"] == "factual"
    assert r["intent"] == "completion"
    assert "full20_final_001" in r["answer"]


def test_chart_request_confusion_matrix(ev):
    state = new_session_state()
    r = handle_message("Plot the confusion matrix.", ev, None, state)
    assert r["intent"] == "chart"
    assert r["chart"]["kind"] == "confusion_matrix"
    assert r["chart"]["chart_id"]
    assert state["last_chart_spec"]["kind"] == "confusion_matrix"
    assert state["last_chart_id"] == r["chart"]["chart_id"]


def test_chart_normalize_follow_up(ev):
    state = new_session_state()
    handle_message("Plot the confusion matrix.", ev, None, state)
    r2 = handle_message("Now show me the normalized version.", ev, None, state)
    assert r2["chart"]["kind"] == "confusion_matrix"
    assert r2["chart"]["provenance"]["normalize"] is True


def test_chart_language_switch_follow_up(ev):
    state = new_session_state()
    handle_message("Plot F1 by class.", ev, "en", state)
    r2 = handle_message("Put that chart in Spanish.", ev, "en", state)
    assert r2["lang"] == "es"
    assert r2["chart"]["kind"] == "f1_by_class"
    assert "clase" in r2["answer"].lower()


def test_chart_download_follow_up_resurfaces_same_chart(ev):
    state = new_session_state()
    r1 = handle_message("Show me the scores for case 16.", ev, "en", state)
    r2 = handle_message("Let me download it.", ev, "en", state)
    assert r2["intent"] == "chart"
    assert r2["chart"]["chart_id"] == r1["chart"]["chart_id"]


def test_chart_case_out_of_range_is_explicit_not_fabricated(ev):
    state = new_session_state()
    r = handle_message("Show me the scores for case 47.", ev, "en", state)
    assert r["intent"] == "chart_unavailable"
    assert "chart" not in r or r.get("chart") is None
    assert "0-19" in r["answer"] or "not exist" in r["answer"].lower()


def test_chart_ambiguous_request_asks_for_clarification(ev):
    state = new_session_state()
    r = handle_message("Can you make me a chart?", ev, "en", state)
    assert r["intent"] == "chart_clarify"
    assert "confusion matrix" in r["answer"].lower()


def test_physical_measurement_chart_request_refused(ev):
    # Not a recognized chart kind at all -- chart_router won't even match
    # a kind, so this exercises the "ambiguous -> clarify" path, which is
    # itself a safe non-fabrication outcome (never silently plots something
    # unrelated).
    state = new_session_state()
    r = handle_message("Plot the power consumption over time.", ev, "en", state)
    assert r["intent"] in ("chart_clarify", "chart_unavailable", "physical_unsupported")
    assert "chart" not in r or r.get("chart") is None


def test_open_ended_question_factual_mode_shows_excerpts(ev):
    state = new_session_state()
    r = handle_message("What training protocol was used for the model?", ev, "en", state)
    assert r["mode"] == "factual"
    assert r["intent"] == "open_ended_factual"
    assert r["citations"]
    assert "Factual mode" in r["answer"]


def test_open_ended_unrelated_question_refused(ev):
    # See tests/test_knowledge_base.py for why this uses a dog-birthday-
    # party phrasing rather than the earlier "pizza place" example -- that
    # exact phrase is now quoted in docs/decisions.md D-014 as a worked
    # retrieval example and legitimately retrieves it.
    state = new_session_state()
    r = handle_message("Can you help me plan a birthday party for my dog?", ev, "en", state)
    assert r["intent"] == "unsupported"
    assert "does not contain that information" in r["answer"]


def test_session_history_accumulates(ev):
    state = new_session_state()
    assert state["history"] == []
    handle_message("Is this experiment complete?", ev, "en", state)
    assert len(state["history"]) == 2
    assert state["history"][0]["role"] == "user"
    assert state["history"][1]["role"] == "assistant"


def test_case_lookup_still_sets_last_case_id(ev):
    state = new_session_state()
    handle_message("What about case 5?", ev, "en", state)
    assert state["last_case_id"] == 5


# --- social-conversation routing (the bug this session fixes) ---------------

def test_bare_greeting_does_not_return_evidence_refusal(ev):
    state = new_session_state()
    r = handle_message("hi", ev, None, state)
    assert r["intent"] == "social_greeting"
    assert "does not contain that information" not in r["answer"]
    assert r["citations"] == []
    assert r["mode"] == "factual"


def test_hola_is_detected_as_spanish_greeting(ev):
    state = new_session_state()
    r = handle_message("hola", ev, None, state)
    assert r["intent"] == "social_greeting"
    assert r["lang"] == "es"
    assert "no contiene esa informaci" not in r["answer"]


def test_gracias_is_thanks_in_spanish(ev):
    state = new_session_state()
    r = handle_message("gracias", ev, None, state)
    assert r["intent"] == "social_thanks"
    assert r["lang"] == "es"


def test_capability_question_spanish(ev):
    state = new_session_state()
    r = handle_message("¿qué puedes hacer?", ev, None, state)
    assert r["intent"] == "social_capability"
    assert r["lang"] == "es"
    assert r["citations"] == []


def test_capability_question_english(ev):
    state = new_session_state()
    r = handle_message("What can you do?", ev, None, state)
    assert r["intent"] == "social_capability"
    assert r["lang"] == "en"


def test_farewell_does_not_require_evidence(ev):
    state = new_session_state()
    r = handle_message("bye", ev, None, state)
    assert r["intent"] == "social_farewell"
    assert r["citations"] == []


def test_mixed_greeting_and_project_question_still_gets_answered(ev):
    # The exact phrase from the bug report: a greeting must not prevent
    # answering the attached project question.
    state = new_session_state()
    r = handle_message("Hola, ¿puedes explicarme qué hace este proyecto?", ev, None, state)
    assert r["intent"] != "unsupported"
    assert "no contiene esa informaci" not in r["answer"]
    assert r["answer"].startswith("¡Hola!") or "Hola" in r["answer"][:10]


def test_mixed_greeting_in_english_still_gets_faq_answer(ev):
    state = new_session_state()
    r = handle_message("Hi, is this experiment complete?", ev, None, state)
    assert r["intent"] == "completion"
    assert r["answer"].lower().startswith("hi!")
    assert "full20_final_001" in r["answer"]


def test_thanks_plus_followup_still_resolves_case(ev):
    state = new_session_state()
    handle_message("What about case 11?", ev, "en", state)
    r = handle_message("Thanks, what about case 16?", ev, "en", state)
    assert r["intent"] == "case_lookup"
    assert "Case 16" in r["answer"]
    assert r["answer"].lower().startswith("you're welcome!")


def test_social_message_does_not_pollute_chart_follow_up_state(ev):
    state = new_session_state()
    handle_message("Plot F1 by class.", ev, "en", state)
    r = handle_message("thanks!", ev, "en", state)
    assert r["intent"] == "social_thanks"
    # chart follow-up state must survive an interleaved social turn
    assert state["last_chart_spec"]["kind"] == "f1_by_class"


def test_generic_overview_question_retrieves_in_factual_mode(ev):
    state = new_session_state()
    r = handle_message("What does this project do?", ev, "en", state)
    assert r["intent"] != "unsupported"
    assert any("project_overview.md" in c for c in r["citations"])


def test_generic_overview_question_spanish(ev):
    state = new_session_state()
    r = handle_message("¿Qué hace este proyecto?", ev, "es", state)
    assert r["intent"] != "unsupported"
    assert any("project_overview.md" in c for c in r["citations"])


def test_physical_unsupported_still_refuses_explicitly_after_social_fix(ev):
    state = new_session_state()
    r = handle_message("What was the chip's power consumption?", ev, "en", state)
    assert r["intent"] == "physical_unsupported"
    assert "does not contain that information" in r["answer"]
