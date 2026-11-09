import re

import pytest

from qa_engine import answer, detect_language, classify_intent


# --- language detection ----------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Is this experiment functionally complete?", "en"),
    ("What about case 16?", "en"),
    ("¿Está completo el experimento?", "es"),
    ("¿Qué pasó con el caso 16?", "es"),
    ("¿Cuál fue la potencia del chip?", "es"),
    ("Cuanto tiempo tomo la simulacion", "es"),  # no accents, but 2+ keywords
    # Bare greeting/thanks words: no accent, no 2+ keyword matches, but an
    # unambiguous single Spanish word with no English collision -- a real
    # gap found when "hola" alone was misdetected as English.
    ("hola", "es"),
    ("Hola!", "es"),
    ("gracias", "es"),
    ("adios", "es"),
    ("hi", "en"),
    ("hello", "en"),
    ("thanks", "en"),
])
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_explicit_language_overrides_detection():
    assert detect_language("completely ambiguous text", explicit="es") == "es"
    assert detect_language("texto totalmente en espanol de prueba", explicit="en") == "en"


# --- intent classification --------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("What about case 16?", "case_lookup"),
    ("¿Qué pasó con el caso 3?", "case_lookup"),
    ("Is this experiment complete?", "completion"),
    ("Do all 20 cases match the native reference?", "agreement"),
    ("What is the classifier's accuracy?", "classifier_quality"),
    ("Which cases are misclassified?", "misclassified"),
    ("What's the tie about?", "tie"),
    ("How long did the simulation run?", "timing"),
    ("What was the tensor arena memory usage?", "memory"),
    ("What clock frequency did the chip run at?", "physical_unsupported"),
    ("How many watts did it use?", "physical_unsupported"),
    ("Where does this chat assistant run?", "where_runs"),
    ("How was this verified?", "provenance"),
    ("What's your favorite pizza topping?", "unsupported"),
])
def test_intent_classification(text, expected):
    assert classify_intent(text) == expected


# --- required explanatory distinctions (task's 6 numbered requirements) ----

def test_distinction_1_rtl_agreement_vs_classifier_correctness(ev):
    r = answer("Do all 20 cases match the native reference?", ev)
    assert "20" in r["answer"]
    assert "16" in r["answer"]  # classifier only correct on 16/20
    assert r["citations"]


def test_distinction_2_accuracy_and_macro_f1_and_unmet_target(ev):
    r = answer("What is the classifier's accuracy and macro-F1?", ev)
    assert "76.96%" in r["answer"] or "0.7696" in r["answer"]
    assert "0.77093" in r["answer"]
    assert "0.85" in r["answer"]
    assert "NOT met" in r["answer"] or "no se cumpli" in r["answer"].lower()


def test_distinction_3_wall_clock_is_not_physical_latency(ev):
    r = answer("How long did the simulation take?", ev)
    assert "not physical-chip inference latency" in r["answer"] or \
           "no es la latencia de inferencia de un chip" in r["answer"]


def test_distinction_4_arena_measurement_is_from_native_not_rv32(ev):
    r = answer("What was the memory usage of the tensor arena?", ev)
    assert "NATIVE" in r["answer"].upper()
    assert "5,216" in r["answer"] or "5216" in r["answer"]
    lowered = r["answer"].lower()
    assert "not from an independent measurement" in lowered or \
           "no de una medici" in lowered


def test_distinction_5_physical_measurements_unsupported(ev):
    for q in [
        "What was the chip's clock frequency in GHz?",
        "How much power did the chip consume?",
        "What was the die area in mm2?",
    ]:
        r = answer(q, ev)
        assert r["intent"] == "physical_unsupported"
        assert "does not contain that information" in r["answer"]


def test_distinction_6_chat_runs_on_host_not_simulated_riscv(ev):
    r = answer("Where does this chat assistant run?", ev)
    assert "HOST SERVER" in r["answer"].upper() or "SERVIDOR ANFITRI" in r["answer"].upper()
    assert "simulated" in r["answer"].lower() or "simulado" in r["answer"].lower()


# --- specific required validation questions --------------------------------

def test_completion_question(ev):
    r = answer("Is this experiment functionally complete?", ev)
    assert r["intent"] == "completion"
    assert "full20_final_001" in r["answer"]
    assert r["citations"]


def test_misclassified_cases_question_lists_all_four(ev):
    r = answer("Which cases are misclassified?", ev)
    for cid in ("0", "11", "15", "16"):
        assert f"case {cid} " in r["answer"] or f"caso {cid} " in r["answer"]


def test_case_0_question(ev):
    r = answer("What about case 0?", ev)
    assert r["intent"] == "case_lookup"
    assert "Center" in r["answer"]
    assert "misclassification" in r["answer"]
    assert any("full20_final_001_check_report.json" in c for c in r["citations"])


def test_case_16_tie_question(ev):
    r = answer("What's the tie in case 16?", ev)
    assert r["intent"] == "case_lookup"
    assert "tie" in r["answer"].lower()
    assert "Scratch" in r["answer"] and "none" in r["answer"]


def test_timing_question_cites_cycles_and_wallclock(ev):
    r = answer("How long did the simulation take?", ev)
    assert "142,937,769" in r["answer"] or "142937769" in r["answer"].replace(",", "")
    assert any("fingerprints.json" in c for c in r["citations"])


def test_memory_question(ev):
    r = answer("What was the tensor arena memory usage?", ev)
    assert "8,192" in r["answer"] or "8192" in r["answer"]


def test_unsupported_physical_measurement_question(ev):
    r = answer("What was the exact die area and power consumption?", ev)
    assert r["intent"] == "physical_unsupported"
    assert r["citations"] == []


# --- citations ---------------------------------------------------------------

def test_case_lookup_citations_include_log_location(ev):
    r = answer("What about case 16?", ev)
    assert any("cycle=" in c for c in r["citations"])
    assert any("full20_final_001_live.log" in c or "check_report.json" in c for c in r["citations"])


def test_citations_are_nonempty_for_evidence_backed_intents(ev):
    for q in [
        "Is this experiment complete?",
        "Do all cases match?",
        "What is the classifier accuracy?",
        "How long did it take?",
        "What was the memory usage?",
    ]:
        r = answer(q, ev)
        assert r["citations"], f"no citations for: {q}"


def test_unsupported_and_physical_questions_have_no_fabricated_citations(ev):
    r1 = answer("What's your favorite pizza topping?", ev)
    assert r1["citations"] == []
    r2 = answer("What was the clock frequency in MHz?", ev)
    assert r2["citations"] == []


# --- follow-ups --------------------------------------------------------------

def test_case_lookup_suggests_next_case_followup(ev):
    r = answer("What about case 5?", ev)
    assert "case 6" in r["followups"]


def test_misclassified_case_suggests_misclassified_list_followup(ev):
    r = answer("What about case 11?", ev)
    assert any("misclassified" in f for f in r["followups"])


def test_followup_resolves_last_case_without_explicit_number(ev):
    r1 = answer("What about case 11?", ev)
    assert r1.get("case_id") == 11
    r2 = answer("Is that one correct or a mistake?", ev, last_case_id=r1["case_id"])
    assert r2["intent"] == "case_lookup"
    assert "Case 11" in r2["answer"]


# --- unsupported / missing evidence -----------------------------------------

def test_fully_unsupported_question_gives_explicit_refusal(ev):
    r = answer("Can you recommend a good pizza place nearby?", ev)
    assert r["intent"] == "unsupported"
    assert "does not contain that information" in r["answer"]


def test_case_lookup_out_of_range(ev):
    r = answer("What about case 47?", ev)
    assert r["intent"] == "case_lookup_out_of_range"
    assert "0-19" in r["answer"] or "0 al 19" in r["answer"]
