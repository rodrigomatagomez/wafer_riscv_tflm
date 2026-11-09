import pytest

import social


# --- purely social: must be detected and answered without any project content ---

@pytest.mark.parametrize("text,expected_category", [
    ("hi", "greeting"),
    ("Hi", "greeting"),
    ("hi!", "greeting"),
    ("Hello!", "greeting"),
    ("hey", "greeting"),
    ("hiya", "greeting"),
    ("good morning", "greeting"),
    ("hola", "greeting"),
    ("Hola!", "greeting"),
    ("buenas", "greeting"),
    ("¿qué tal?", "greeting"),
    ("¿cómo estás?", "greeting"),
    ("thanks", "thanks"),
    ("thank you", "thanks"),
    ("thanks a lot", "thanks"),
    ("gracias", "thanks"),
    ("muchas gracias", "thanks"),
    ("bye", "farewell"),
    ("goodbye", "farewell"),
    ("adios", "farewell"),
    ("chau", "farewell"),
    ("hasta luego", "farewell"),
    ("what can you do?", "capability"),
    ("What do you do?", "capability"),
    ("who are you?", "capability"),
    ("¿qué puedes hacer?", "capability"),
    ("que puedes hacer", "capability"),
    ("¿cómo puedes ayudarme?", "capability"),
])
def test_purely_social_detection(text, expected_category):
    a = social.analyze(text)
    assert a.is_purely_social, f"{text!r} should be purely social, got categories={a.categories}"
    assert expected_category in a.categories


def test_purely_social_response_has_no_citations_and_is_factual():
    a = social.analyze("hi")
    resp = social.respond(a.categories, "en")
    assert resp["citations"] == []
    assert resp["mode"] == "factual"
    assert resp["intent"] == "social_greeting"


def test_purely_social_response_language_matches_request():
    a = social.analyze("hola")
    resp_es = social.respond(a.categories, "es")
    resp_en = social.respond(a.categories, "en")
    assert resp_es["answer"] != resp_en["answer"]
    assert "Hola" in resp_es["answer"] or "hola" in resp_es["answer"].lower()


def test_capability_response_mentions_charts_and_citations_and_refusals():
    a = social.analyze("what can you do?")
    resp = social.respond(a.categories, "en")
    lowered = resp["answer"].lower()
    assert "chart" in lowered
    assert "citat" in lowered or "source" in lowered
    assert "never measured" in lowered or "tell you" in lowered


# --- mixed messages: greeting/thanks glued onto a real question ---

@pytest.mark.parametrize("text,expected_categories,remainder_has_content", [
    ("Hola, ¿puedes explicarme qué hace este proyecto?", ["greeting"], True),
    ("Hi, what is the classifier accuracy?", ["greeting"], True),
    ("Thanks, what about case 16?", ["thanks"], True),
    ("Gracias, ¿qué pasó con el caso 16?", ["thanks"], True),
])
def test_mixed_message_not_purely_social(text, expected_categories, remainder_has_content):
    a = social.analyze(text)
    assert not a.is_purely_social
    for cat in expected_categories:
        assert cat in a.categories
    assert len(a.stripped_text.strip()) > 0


def test_mixed_message_stripped_text_removes_greeting_word():
    a = social.analyze("Hola, ¿puedes explicarme qué hace este proyecto?")
    assert "hola" not in a.stripped_text.lower()
    assert "proyecto" in a.stripped_text.lower()


def test_greeting_prefix_nonempty_for_greeting_and_thanks():
    assert social.greeting_prefix(["greeting"], "en").strip()
    assert social.greeting_prefix(["greeting"], "es").strip()
    assert social.greeting_prefix(["thanks"], "en").strip()
    assert social.greeting_prefix([], "en") == ""


# --- messages that must NOT be treated as social at all ---

@pytest.mark.parametrize("text", [
    "What about case 16?",
    "What is the classifier's accuracy?",
    "Is this experiment functionally complete?",
    "Plot F1 by class.",
    "¿Cuál es el empate en el caso 16?",
    "How long did the simulation take?",
])
def test_non_social_questions_are_not_flagged(text):
    a = social.analyze(text)
    assert a.categories == []
    assert not a.is_purely_social
    assert a.stripped_text == text


def test_word_boundary_does_not_false_positive_inside_other_words():
    # "hi" must not match inside "high", "chip", etc.
    a = social.analyze("What was the chip's high score?")
    assert "greeting" not in a.categories
