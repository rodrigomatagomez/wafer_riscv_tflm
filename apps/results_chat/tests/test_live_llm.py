"""Genuine, network-calling tests against a REAL running llama-server.

These are deliberately separate from the mocked/factual-mode tests
elsewhere in this suite: per the task's explicit instruction, "passing
mocked adapter tests does not establish live LLM operation." Every test
here makes an actual HTTP call to the local model server and inspects a
real generated response (and, for a couple of tests, measures real wall-
clock latency). If no local server is reachable at collection time, the
whole module is skipped with a clear reason -- it never silently falls
back to asserting against factual-mode behavior instead.

Run with the local server already started (see README.md):
    cd apps/results_chat && ./run.sh   # starts llama-server + Flask
    venv/bin/python3 -m pytest tests/test_live_llm.py -v
"""
import time

import pytest

import llm_adapter
from chat_pipeline import handle_message, new_session_state

_cfg = llm_adapter.LLMConfig(provider="local", model="local",
                              api_base="http://127.0.0.1:8788", local_url="http://127.0.0.1:8788")
_LOCAL_LLM_UP = llm_adapter._local_server_healthy(_cfg.local_url)

pytestmark = pytest.mark.skipif(
    not _LOCAL_LLM_UP,
    reason="no local llama-server reachable at http://127.0.0.1:8788 -- start it via "
           "apps/results_chat/run.sh (or llama-server directly) before running this file",
)


def test_server_health_endpoint_is_real():
    assert llm_adapter._local_server_healthy("http://127.0.0.1:8788") is True


def test_real_english_inference_latency_and_content():
    messages = [{"role": "user", "content": "In one short sentence, what is RISC-V?"}]
    t0 = time.time()
    text = llm_adapter.generate(messages, _cfg, max_tokens=60, temperature=0.2)
    elapsed = time.time() - t0
    assert len(text) > 5
    assert elapsed < 30.0, f"response took {elapsed:.1f}s, unexpectedly slow for a 1.5B model on 4 threads"
    print(f"\n[live] English inference: {elapsed:.2f}s, {len(text)} chars: {text!r}")


def test_real_spanish_inference():
    messages = [{"role": "user", "content": "En una frase breve, ¿qué es RISC-V?"}]
    text = llm_adapter.generate(messages, _cfg, max_tokens=60, temperature=0.2)
    assert len(text) > 5
    # a real Spanish reply should contain at least one common Spanish word/accent
    lowered = text.lower()
    assert any(w in lowered for w in ("es ", "una", "de ", "el ", "la ", "ó", "é", "í", "ñ")), text


def test_real_multiturn_history_is_used():
    # Phrased as a "remember this code word" task rather than a personal
    # preference ("my favorite number") -- an earlier version of this test
    # used the latter and Qwen2.5-1.5B-Instruct reliably refused it with a
    # safety-tuned "I don't have access to your personal preferences"
    # response EVEN THOUGH the fact was correctly present in the messages
    # array (verified directly: the model declines to use it, which is a
    # real small-model behavior, not an adapter bug). This phrasing avoids
    # that refusal pattern while still genuinely exercising conversation
    # history.
    messages = llm_adapter.build_messages(
        "You are a helpful assistant. Be concise.",
        [{"role": "user", "content": "Remember this code word: octopus."},
         {"role": "assistant", "content": "Understood, the code word is octopus."}],
        "What was the code word I asked you to remember?",
    )
    text = llm_adapter.generate(messages, _cfg, max_tokens=30, temperature=0.0)
    assert "octopus" in text.lower()


def test_pipeline_open_ended_question_actually_uses_llm(ev, monkeypatch):
    monkeypatch.delenv("RESULTS_CHAT_LLM_PROVIDER", raising=False)
    state = new_session_state()
    t0 = time.time()
    r = handle_message("What training protocol was used for this model?", ev, "en", state)
    elapsed = time.time() - t0
    assert r["mode"] == "llm"
    assert r["intent"] == "open_ended_llm"
    assert len(r["answer"]) > 20
    print(f"\n[live] open-ended RAG+LLM: {elapsed:.2f}s: {r['answer'][:150]!r}")


def test_pipeline_spanish_open_ended_question_replies_in_spanish(ev, monkeypatch):
    monkeypatch.delenv("RESULTS_CHAT_LLM_PROVIDER", raising=False)
    state = new_session_state()
    r = handle_message("¿Qué protocolo de entrenamiento se usó para este modelo?", ev, "es", state)
    assert r["mode"] == "llm"
    assert r["lang"] == "es"


def test_pipeline_faq_rephrase_preserves_exact_numbers(ev, monkeypatch):
    monkeypatch.delenv("RESULTS_CHAT_LLM_PROVIDER", raising=False)
    state = new_session_state()
    r = handle_message("What is the classifier's accuracy and macro-F1?", ev, "en", state)
    assert r["mode"] == "llm"
    # the LLM is instructed to rephrase without changing numbers -- verify
    # the exact measured figures survived the rephrase.
    assert "0.77093" in r["answer"] or "77.09" in r["answer"] or "0.7709" in r["answer"]


def test_pipeline_chart_answer_stays_factual_even_with_live_llm(ev, monkeypatch):
    # Charts must NEVER be LLM-phrased (the caption is always deterministic
    # chart_engine output) -- confirm this holds even when a real LLM is
    # actually available and used elsewhere in the same session.
    monkeypatch.delenv("RESULTS_CHAT_LLM_PROVIDER", raising=False)
    state = new_session_state()
    r = handle_message("Plot F1 by class.", ev, "en", state)
    assert r["intent"] == "chart"
    assert r["mode"] == "factual"


def test_pipeline_unsupported_physical_question_not_sent_to_llm(ev, monkeypatch):
    monkeypatch.delenv("RESULTS_CHAT_LLM_PROVIDER", raising=False)
    state = new_session_state()
    r = handle_message("What was the chip's power consumption in watts?", ev, "en", state)
    assert r["mode"] == "factual"
    assert r["intent"] == "physical_unsupported"
    assert "does not contain that information" in r["answer"]


def test_pipeline_mixed_greeting_and_project_question_reaches_real_llm(ev, monkeypatch):
    # The exact bug-report phrase: a greeting glued onto a real question
    # must still reach the local LLM for the substantive part, not fall
    # back to the "evidence does not contain that information" refusal.
    monkeypatch.delenv("RESULTS_CHAT_LLM_PROVIDER", raising=False)
    state = new_session_state()
    r = handle_message("Hola, ¿puedes explicarme qué hace este proyecto?", ev, None, state)
    assert r["mode"] == "llm"
    assert r["intent"] == "open_ended_llm"
    assert r["lang"] == "es"
    assert len(r["answer"]) > 20
    assert r["citations"]


def test_pipeline_bare_greeting_never_calls_llm(ev, monkeypatch):
    # Greetings are answered deterministically even when a live LLM is
    # available -- there is no reason to pay the latency for "hi".
    monkeypatch.delenv("RESULTS_CHAT_LLM_PROVIDER", raising=False)
    state = new_session_state()
    t0 = time.time()
    r = handle_message("hi", ev, None, state)
    elapsed = time.time() - t0
    assert r["mode"] == "factual"
    assert r["intent"] == "social_greeting"
    assert elapsed < 1.0, f"greeting took {elapsed:.2f}s -- should be near-instant, not an LLM call"
