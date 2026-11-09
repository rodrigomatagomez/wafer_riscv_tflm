"""Orchestrates one chat turn: social conversation, chart requests,
fixed-intent FAQ questions, and open-ended retrieval-grounded (RAG)
questions, in that priority order, with per-session conversation history
and chart-follow-up state.

Routing priority for one incoming message:
  0. Social conversation (social.py): a greeting, thanks, farewell, or
     "what can you do" capability question. If the ENTIRE message is
     social (e.g. "hi", "gracias", "¿qué puedes hacer?"), answer directly
     with a canned bilingual reply -- no retrieval, no citation, no LLM
     call, since there is no project-specific claim to ground. If a
     social phrase is glued onto a real question (e.g. "Hola, ¿puedes
     explicarme qué hace este proyecto?"), the social phrase is stripped
     before the remainder goes through the normal routing below, and a
     short acknowledgment is prepended to whatever real answer comes back.
  1. "let me download it" / "déjame descargarla" with a chart already
     shown this session -> resurface that chart's existing download links
     (no re-render, no LLM call).
  2. Looks like a chart request (chart_router.py) -> parse deterministically;
     if that fails but an LLM is available, ask the LLM for a strict JSON
     spec instead; either way the result is validated by
     chart_engine.validate_spec() before anything is rendered.
  3. Matches one of qa_engine.py's fixed intents (completion, agreement,
     classifier quality, a case lookup, timing, memory, physical-measurement
     refusal, etc.) -> that deterministic, precisely-cited answer, optionally
     passed through the LLM for more natural phrasing (unchanged from the
     previous version of this app).
  4. Otherwise: open-ended question. Retrieve relevant knowledge-base
     chunks (knowledge_base.py); if none are relevant, refuse explicitly.
     If some are found, ground an LLM call in exactly those chunks (never
     letting the LLM introduce a number that isn't in them); if no LLM is
     configured or the call fails, fall back to showing the retrieved
     excerpts directly, clearly labeled as factual mode.

This module never executes model-generated code and never accepts a
model-generated number as a measured result for a chart -- see
chart_engine.py's and llm_adapter.py's module docstrings for exactly how
that's enforced.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import chart_cache
import chart_engine as ce
import chart_router as cr
import knowledge_base as kb_mod
import llm_adapter
import social
from evidence import Evidence
from qa_engine import UNSUPPORTED_EN, UNSUPPORTED_ES, answer as factual_answer, detect_language

log = logging.getLogger("results_chat")

MAX_HISTORY_MESSAGES = 8  # 4 user/assistant pairs
RAG_SYSTEM_PROMPT_EN = """You are a technical assistant explaining ONE specific, already-completed \
hardware/ML verification project (an RV32IM RISC-V processor running a TensorFlow Lite Micro \
classifier, final accepted run id full20_final_001) to a general audience, including at technical \
conferences.

Answer the user's question using the PROJECT CONTEXT sections given below as your source of \
project-specific facts. You may also use ordinary general technical knowledge for background concepts \
the user asks about (e.g. "what is a confusion matrix"), but you must make clear when you are doing so.

Rules you must follow:
1. Any project-specific number or measured result you state must come from the PROJECT CONTEXT below \
-- cite it using the bracketed citation already attached to that section, e.g. [source: results/ml_metrics.json]. \
Never state a project-specific number that is not present in the given context.
2. If the question asks about something that was apparently never decided, recorded, or measured by \
this project (based on the given context), say so plainly -- do not guess or invent an answer.
3. Preserve these distinctions whenever relevant: (a) RTL-vs-native agreement (20/20, exact score+class \
match) is NOT the same as classifier accuracy (the classifier itself is correct on only 16/20 of those \
same fixed cases; overall measured test accuracy is ~76.96%, macro-F1 0.77093, on 599 held-out samples, \
and the project's 0.85 target was NOT met); (b) the reported scores are raw quantized int8 logits, not \
probabilities; (c) simulation wall-clock time is not physical-chip latency; (d) the 5216-byte tensor-arena \
figure was measured on the native x86 reference, not independently on the RV32 firmware; (e) no physical \
clock frequency, power, or die area was ever measured for this project -- if asked, say so.
4. You run on the host server. The classifier under discussion ran on a simulated RISC-V processor; you \
are a separate, later addition and must not conflate yourself with it.
5. You cannot execute code, run a simulation, train a model, or modify any file -- you can only explain.
6. Reply in the same language as the user's question (English or Spanish).

PROJECT CONTEXT:
{context}
"""

CHART_SPEC_SYSTEM_PROMPT = """You turn a user's natural-language chart request into a single JSON \
object describing which already-computed project dataset to plot. You never invent data values -- you \
only select from this fixed schema. Output ONLY the JSON object, nothing else.

Schema:
{{"kind": one of ["confusion_matrix","f1_by_class","model_comparison","quant_comparison",
"invoke_cycles","case_scores","classifier_correctness","training_curves","memory_budget"],
 "params": {{...kind-specific optional keys, all from fixed enums...}},
 "lang": "en" or "es"}}

Allowed params per kind:
- confusion_matrix: model_tag ("A"|"B"), metric_set ("float"|"int8"), split ("val"|"test"), normalize (true|false)
- f1_by_class: model_tag, metric_set, split
- model_comparison: metric ("accuracy"|"macro_f1"), metric_set, split
- quant_comparison: model_tag, metric ("accuracy"|"macro_f1"), split
- case_scores: case_id (integer 0-19, REQUIRED)
- training_curves: model_tag, metric ("loss"|"accuracy"|"both")
- invoke_cycles, classifier_correctness, memory_budget: no params

If the user is asking for something this schema cannot represent (e.g. physical clock frequency, power, \
die area, or anything not in the kind list), output exactly: {{"unavailable": true, "reason": "<short reason>"}}

User's request: {request}
"""


def _format_history_for_llm(history: list) -> list:
    return [{"role": m["role"], "content": m["content"]} for m in history[-MAX_HISTORY_MESSAGES:]]


def new_session_state() -> dict:
    return {"last_case_id": None, "last_chart_spec": None, "last_chart_id": None, "history": []}


def _push_history(state: dict, user_msg: str, assistant_msg: str):
    state["history"].append({"role": "user", "content": user_msg})
    state["history"].append({"role": "assistant", "content": assistant_msg})
    if len(state["history"]) > MAX_HISTORY_MESSAGES:
        state["history"] = state["history"][-MAX_HISTORY_MESSAGES:]


def _chart_response(manifest: dict, mode: str, lang: str, llm_assisted_parsing: bool) -> dict:
    return {
        "answer": manifest["caption"],
        "citations": manifest["citations"],
        "intent": "chart",
        "lang": lang,
        "followups": [],
        "mode": mode,
        "llm_assisted_parsing": llm_assisted_parsing,
        "chart": {
            "chart_id": manifest["chart_id"],
            "kind": manifest["kind"],
            "title": manifest["title"],
            "png_url": f"/api/chart/{manifest['chart_id']}.png",
            "svg_url": f"/api/chart/{manifest['chart_id']}.svg",
            "csv_url": f"/api/chart/{manifest['chart_id']}.csv",
            "data_rows": manifest["data_rows"],
            "provenance": manifest["provenance"],
        },
    }


def _try_llm_chart_spec(message: str, lang: str, cfg) -> Optional[dict]:
    prompt = CHART_SPEC_SYSTEM_PROMPT.format(request=message)
    messages = [{"role": "user", "content": prompt}]
    try:
        text = llm_adapter.generate(messages, cfg, max_tokens=200, temperature=0.0)
    except llm_adapter.LLMError as exc:
        log.warning("LLM chart-spec call failed: %s", exc)
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        log.warning("LLM chart-spec was not valid JSON: %r", text[:200])
        return None
    if obj.get("unavailable"):
        return {"unavailable": True, "reason": obj.get("reason", "")}
    obj.setdefault("lang", lang)
    return obj


def _handle_chart(message: str, lang: str, ev: Evidence, state: dict, cfg) -> dict:
    raw_spec = cr.parse_chart_request(message, lang, state.get("last_chart_spec"))
    llm_assisted = False
    if raw_spec is None and llm_adapter.is_configured(cfg):
        llm_result = _try_llm_chart_spec(message, lang, cfg)
        llm_assisted = True
        if llm_result and llm_result.get("unavailable"):
            msg = llm_result.get("reason") or (
                "That data was not collected for this project." if lang == "en"
                else "Esos datos no fueron recopilados para este proyecto."
            )
            return {"answer": msg, "citations": [], "intent": "chart_unavailable",
                    "lang": lang, "followups": [], "mode": "factual"}
        raw_spec = llm_result

    if raw_spec is None:
        hint = _t(lang,
                   "I can chart: a confusion matrix, F1 by class, a Model A vs B comparison, a "
                   "float vs int8 comparison, Invoke() cycles for the 20 cases, a specific case's four "
                   "scores, correct vs incorrect counts, training curves, or the memory budget. "
                   "Which one would you like?",
                   "Puedo graficar: una matriz de confusión, F1 por clase, una comparación Modelo A vs B, "
                   "una comparación flotante vs int8, los ciclos de Invoke() de los 20 casos, las cuatro "
                   "puntuaciones de un caso específico, el conteo de correctos vs incorrectos, curvas de "
                   "entrenamiento, o el presupuesto de memoria. ¿Cuál te interesa?")
        return {"answer": hint, "citations": [], "intent": "chart_clarify", "lang": lang,
                "followups": [], "mode": "factual"}

    try:
        spec = ce.validate_spec(raw_spec)
    except ce.ChartSpecError as exc:
        msg = _t(lang, f"I couldn't build that chart: {exc}", f"No pude generar esa gráfica: {exc}")
        return {"answer": msg, "citations": [], "intent": "chart_invalid", "lang": lang,
                "followups": [], "mode": "factual"}

    try:
        manifest = chart_cache.get_or_render(spec, ev)
    except ce.ChartDataUnavailable as exc:
        return {"answer": str(exc), "citations": [], "intent": "chart_unavailable", "lang": lang,
                "followups": [], "mode": "factual"}

    state["last_chart_spec"] = raw_spec
    state["last_chart_id"] = manifest["chart_id"]
    # Report the LANGUAGE ACTUALLY RENDERED (spec.lang, which a "put it in
    # Spanish" follow-up may have overridden), not the detected language of
    # the incoming request text -- those two differ precisely for that
    # follow-up case.
    return _chart_response(manifest, mode="factual", lang=spec.lang, llm_assisted_parsing=llm_assisted)


def _redisplay_last_chart(lang: str, state: dict) -> Optional[dict]:
    chart_id = state.get("last_chart_id")
    if not chart_id:
        return None
    manifest = chart_cache.manifest_by_id(chart_id)
    if manifest is None:
        return None
    resp = _chart_response(manifest, mode="factual", lang=lang, llm_assisted_parsing=False)
    resp["answer"] = _t(lang,
                          "Here it is again: " + manifest["caption"],
                          "Aquí está de nuevo: " + manifest["caption"])
    return resp


def _t(lang: str, en: str, es: str) -> str:
    return es if lang == "es" else en


def _build_rag_context(hits: list) -> str:
    blocks = []
    for score, chunk in hits:
        citation = f"[source: {chunk.source_file} - {chunk.section_title}]"
        blocks.append(f"{citation}\n{chunk.text.strip()[:1500]}")
    return "\n\n---\n\n".join(blocks)


def _factual_excerpt_answer(hits: list, lang: str) -> dict:
    intro = _t(lang,
               "Factual mode (no local LLM running): here are the most relevant project sections "
               "for your question.",
               "Modo fáctico (sin LLM local en ejecución): estas son las secciones del proyecto más "
               "relevantes para tu pregunta (el texto permanece en inglés, el idioma de la "
               "documentación original).")
    parts = [intro]
    citations = []
    for score, chunk in hits[:3]:
        excerpt = chunk.text.strip()
        if len(excerpt) > 400:
            excerpt = excerpt[:400].rsplit(" ", 1)[0] + "..."
        parts.append(f"\n[{chunk.source_file} :: {chunk.section_title}]\n{excerpt}")
        citations.append(f"{chunk.source_file} :: {chunk.section_title}")
    return {"answer": "\n".join(parts), "citations": citations, "intent": "open_ended_factual",
            "lang": lang, "followups": [], "mode": "factual"}


# A pure TF-IDF gate under-retrieves the single most common opening
# question ("what is/does this project do") because "project" itself is
# low-IDF (it appears in nearly every chunk, so it carries little
# discriminative weight) -- found during testing: "What does this project
# do?" retrieved nothing above threshold even though
# knowledge/project_overview.md's own intro section exists specifically to
# answer it. Rather than loosening the general relevance gate (which would
# reopen the false-positive class D-014 already fixed), this generic
# phrasing is recognized directly and guaranteed to include that section.
_GENERIC_OVERVIEW_EN = re.compile(
    r"\b(what (does|is) this project|tell me about (this|the) project|"
    r"explain (this|the) project|what is this project about|"
    r"what is this (about|for)|give me an overview|"
    r"overview of (this|the) project)\b", re.IGNORECASE)
_GENERIC_OVERVIEW_ES = re.compile(
    r"\b(que hace (este|el) proyecto|hablame (del|sobre el) proyecto|"
    r"cuentame (del|sobre el|de este) proyecto|explicame (el|este) proyecto|"
    r"de que trata (este|el) proyecto|que es este proyecto|"
    r"dame un resumen)\b", re.IGNORECASE)


def _is_generic_overview_question(message: str) -> bool:
    folded = kb_mod.fold_accents(message)
    return bool(_GENERIC_OVERVIEW_EN.search(folded)) or bool(_GENERIC_OVERVIEW_ES.search(folded))


def _ensure_overview_chunk(kb, hits: list) -> list:
    overview = next(
        (c for c in kb.chunks if c.source_file.endswith("project_overview.md")
         and c.section_title.strip().lower().startswith("what was built")),
        None,
    )
    if overview is None or any(c.chunk_id == overview.chunk_id for _, c in hits):
        return hits
    return [(1.0, overview)] + hits


def _handle_open_ended(message: str, lang: str, ev: Evidence, state: dict, cfg) -> dict:
    kb = kb_mod.get_knowledge_base(ev.project_root)
    hits = kb.retrieve(message, k=3)
    if _is_generic_overview_question(message):
        hits = _ensure_overview_chunk(kb, hits)[:4]
    if not hits:
        return {"answer": UNSUPPORTED_ES if lang == "es" else UNSUPPORTED_EN, "citations": [],
                "intent": "unsupported", "lang": lang, "followups": [], "mode": "factual"}

    if not llm_adapter.is_configured(cfg):
        return _factual_excerpt_answer(hits, lang)

    context = _build_rag_context(hits)
    system_prompt = RAG_SYSTEM_PROMPT_EN.format(context=context)
    # Bounded to the last 2 turns (not the full MAX_HISTORY_MESSAGES) for
    # this path specifically: the RAG system prompt is already long
    # (grounding context + rules), and prompt length is the dominant cost
    # on a 4-thread CPU server -- see README.md "Measured latency" for the
    # actual effect this had (~40s -> ~15-20s typical for a first reply).
    history = _format_history_for_llm(state["history"])[-2:]
    messages = llm_adapter.build_messages(system_prompt, history, message)
    try:
        text = llm_adapter.generate(messages, cfg, max_tokens=320, temperature=0.3)
    except llm_adapter.LLMError as exc:
        log.warning("LLM open-ended call failed, falling back to excerpts: %s", exc)
        return _factual_excerpt_answer(hits, lang)

    citations = [f"{chunk.source_file} :: {chunk.section_title}" for _, chunk in hits]
    return {"answer": text, "citations": citations, "intent": "open_ended_llm", "lang": lang,
            "followups": [], "mode": "llm"}


def _route_substantive_message(message: str, lang: str, ev: Evidence, state: dict, cfg) -> dict:
    """Routes a message already confirmed to have real (non-purely-social)
    content: download follow-up -> chart -> fixed FAQ intent -> open-ended
    RAG. `message` here may be the social-phrase-stripped remainder of the
    original user text (see handle_message), so chart/intent/retrieval
    matching isn't diluted by a leading "hola," or "thanks,"."""
    if cr.is_download_request(message):
        resp = _redisplay_last_chart(lang, state)
        if resp is not None:
            return resp
        # falls through to open-ended handling if nothing to redisplay

    has_prior_chart = state.get("last_chart_spec") is not None
    if cr.is_chart_request(message) or (has_prior_chart and cr.is_chart_modifier_only(message)):
        return _handle_chart(message, lang, ev, state, cfg)

    fixed = factual_answer(message, ev, lang_hint=lang, last_case_id=state.get("last_case_id"))
    if fixed["intent"] != "unsupported":
        if "case_id" in fixed:
            state["last_case_id"] = fixed["case_id"]
        used_llm = False
        if llm_adapter.is_configured(cfg) and fixed["intent"] != "physical_unsupported":
            evidence_snippet = fixed["answer"] + "\nCitations: " + "; ".join(fixed["citations"])
            history = _format_history_for_llm(state["history"])
            messages = llm_adapter.build_messages(
                "Rephrase the following already-verified answer more conversationally, in the same "
                "language as the user's question, WITHOUT changing any number, fact, or citation. If "
                "unsure, just repeat the given answer verbatim.\n\nVERIFIED ANSWER:\n" + evidence_snippet,
                history, message,
            )
            try:
                text = llm_adapter.generate(messages, cfg, max_tokens=400, temperature=0.2)
                fixed = dict(fixed)
                fixed["answer"] = text
                used_llm = True
            except llm_adapter.LLMError as exc:
                log.warning("LLM rephrase failed, using factual answer: %s", exc)
        fixed["mode"] = "llm" if used_llm else "factual"
        return fixed

    return _handle_open_ended(message, lang, ev, state, cfg)


def handle_message(message: str, ev: Evidence, lang_hint: Optional[str], state: dict) -> dict:
    lang = detect_language(message, lang_hint)
    cfg = llm_adapter.load_config()

    social_info = social.analyze(message)
    if social_info.is_purely_social:
        # A plain greeting/thanks/farewell/capability question has no
        # project-specific claim to ground -- answer directly, no
        # retrieval, no citation, no LLM call needed.
        resp = social.respond(social_info.categories, lang)
        _push_history(state, message, resp["answer"])
        return resp

    # A social phrase glued onto a real question (e.g. "Hola, ¿puedes
    # explicarme qué hace este proyecto?" or "Thanks, what about case
    # 16?"): route the STRIPPED remainder (so "hola"/"gracias" don't
    # dilute chart/intent matching or retrieval relevance), then prepend a
    # short acknowledgment to whatever real answer comes back. Session
    # follow-up state (last_case_id, last_chart_spec, history) is resolved
    # from `state`, which is unaffected by the stripping.
    effective_message = social_info.stripped_text if social_info.categories else message
    resp = _route_substantive_message(effective_message, lang, ev, state, cfg)

    if social_info.categories:
        prefix = social.greeting_prefix(social_info.categories, resp.get("lang", lang))
        if prefix:
            resp = dict(resp)
            resp["answer"] = prefix + resp["answer"]

    _push_history(state, message, resp["answer"])
    return resp
