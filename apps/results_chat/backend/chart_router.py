"""Deterministic, bilingual chart-request detection and parameter
extraction from natural language.

This is the fallback (and, in factual mode, the ONLY) path that turns a
message like "Grafica el F1 por clase" or "Now compare A and B" into a
chart_engine.ChartSpec-shaped dict. When an LLM is configured, app.py may
additionally ask it to propose a spec for a harder-to-parse phrasing, but
whatever the LLM returns is still run through chart_engine.validate_spec()
-- this module and the LLM path both only ever produce the same
restricted dict shape (kind + enum params), never raw numbers.

Follow-up handling: `parse_chart_request` accepts the previous turn's
chart spec (if any) and merges into it for requests that only change one
aspect ("muéstrame la matriz normalizada" -> reuse kind=confusion_matrix
from context if the user said "matriz", else keep the prior kind and just
add normalize=True; "pon esa gráfica en español" -> reuse the entire prior
spec, change only lang). A bare "let me download it" with no new kind
detected and a prior chart available returns a `redisplay` signal instead
of a new spec, so app.py can just resurface the existing chart's links.
"""
from __future__ import annotations

import re
from typing import Optional

_CHART_WORDS = re.compile(
    r"\b(chart|graph|plot|visuali[sz]e|figure|grafica|gr[aá]fico|gr[aá]fica|"
    r"visualiza|diagrama)\b",
    re.IGNORECASE,
)
_DOWNLOAD_WORDS = re.compile(
    # \w* after the Spanish stem covers clitic-pronoun forms like
    # "descargarla"/"descárgala" (verb + attached "it"), not just the bare
    # infinitive -- a real gap found via the task's own example phrase.
    r"\b(download\w*|descarg\w*)\b", re.IGNORECASE,
)
_SPANISH_LANG_REQUEST = re.compile(
    r"\b(en espa[ñn]ol|in spanish|espa[ñn]ol)\b", re.IGNORECASE,
)
_ENGLISH_LANG_REQUEST = re.compile(
    r"\b(in english|en ingl[eé]s)\b", re.IGNORECASE,
)

_KIND_PATTERNS = [
    ("confusion_matrix", re.compile(
        r"\b(confusion\s*)?matrix\b|\bmatriz\s*(de\s*confusi[oó]n)?\b", re.IGNORECASE)),
    ("f1_by_class", re.compile(
        r"\bf1[\s-]*(by|per)[\s-]*class\b|\bf1\s*por\s*clase\b|\bper[- ]class f1\b",
        re.IGNORECASE)),
    ("quant_comparison", re.compile(
        r"\bfloat\s*(vs\.?|versus|and|y)\s*int8\b|\bint8\s*(vs\.?|versus|and|y)\s*float\b|"
        r"\bflotante\s*(vs\.?|contra|y)\s*int8\b|\bcuantizaci[oó]n\b",
        re.IGNORECASE)),
    ("model_comparison", re.compile(
        r"\b(model\s*a\s*(vs\.?|versus|and)\s*(model\s*)?b|modelo\s*a\s*(vs\.?|contra|y)\s*(modelo\s*)?b|"
        r"compare\s*a\s*(and|vs\.?)\s*b|compara\s*a\s*y\s*b)\b",
        re.IGNORECASE)),
    ("case_scores", re.compile(
        r"\bscores?\s*(for|of|del?|de la)?\s*case\s*#?\s*(\d+)\b|"
        r"\b(scores?|puntuaciones)\s*(del|de)\s*caso\s*#?\s*(\d+)\b|"
        r"\bcase\s*#?\s*(\d+).{0,20}\bscores?\b|\bcaso\s*#?\s*(\d+).{0,20}\b(puntuaciones|scores?)\b",
        re.IGNORECASE)),
    ("invoke_cycles", re.compile(
        r"\binvoke\s*cycles\b|\bciclos\s*(de\s*)?invoke\b|\bcycles?\s*for\s*(the\s*)?(20|twenty)\s*cases\b|"
        r"\bciclos\s*de\s*los\s*20\s*casos\b",
        re.IGNORECASE)),
    ("classifier_correctness", re.compile(
        r"\bcorrect\s*(vs\.?|and|/)\s*incorrect\b|\bcorrectos?\s*(vs\.?|y|/)\s*incorrectos?\b|"
        r"\bhow many (are )?correct\b|\bcu[aá]ntos\s*(son\s*)?correctos\b",
        re.IGNORECASE)),
    ("training_curves", re.compile(
        r"\btraining\b.{0,25}\b(curve|history)\b|\b(curve|history)\b.{0,25}\btraining\b|"
        r"\bvalidation\s*curve\b|\bcurva\s*(de\s*)?(entrenamiento|validaci[oó]n)\b",
        re.IGNORECASE)),
    ("memory_budget", re.compile(
        r"\bmemory\s*(budget|usage|visuali[sz]ation)\b|\bpresupuesto\s*de\s*memoria\b|\buso\s*de\s*memoria\b",
        re.IGNORECASE)),
]

_MODEL_B = re.compile(r"\b(model\s*b|modelo\s*b)\b", re.IGNORECASE)
_MODEL_A = re.compile(r"\b(model\s*a|modelo\s*a)\b", re.IGNORECASE)
_SET_FLOAT = re.compile(r"\bfloat\b|\bflotante\b", re.IGNORECASE)
_SET_INT8 = re.compile(r"\bint8\b|\bcuantizad[oa]\b", re.IGNORECASE)
_SPLIT_VAL = re.compile(r"\bvalidation\b|\bvalidaci[oó]n\b", re.IGNORECASE)
_SPLIT_TEST = re.compile(r"\btest\b|\bprueba\b", re.IGNORECASE)
_NORMALIZE = re.compile(r"\bnormali[sz]ed?\b|\bnormali[sz]ad[oa]\b", re.IGNORECASE)
_METRIC_ACC = re.compile(r"\baccuracy\b|\bexactitud\b|\bprecisi[oó]n\b", re.IGNORECASE)
_METRIC_F1 = re.compile(r"\bmacro[- ]?f1\b|\bf1\b", re.IGNORECASE)
_CASE_NUM = re.compile(r"\bcase\s*#?\s*(\d{1,2})\b|\bcaso\s*#?\s*(\d{1,2})\b", re.IGNORECASE)
_TRAIN_METRIC_LOSS = re.compile(r"\bloss\b|\bp[eé]rdida\b", re.IGNORECASE)
_TRAIN_METRIC_ACC = re.compile(r"\baccuracy\b|\bexactitud\b", re.IGNORECASE)


def is_chart_request(text: str) -> bool:
    return bool(_CHART_WORDS.search(text)) or any(p.search(text) for _, p in _KIND_PATTERNS)


def is_download_request(text: str) -> bool:
    return bool(_DOWNLOAD_WORDS.search(text))


def is_language_switch_request(text: str) -> Optional[str]:
    if _SPANISH_LANG_REQUEST.search(text):
        return "es"
    if _ENGLISH_LANG_REQUEST.search(text):
        return "en"
    return None


def is_chart_modifier_only(text: str) -> bool:
    """True for a follow-up that modifies the PREVIOUS chart without
    naming any new chart kind itself -- e.g. "put it in Spanish" or "show
    the normalized version". Callers should route these to the chart
    handler only when a previous chart actually exists this session."""
    return bool(is_language_switch_request(text)) or bool(_NORMALIZE.search(text))


def _detect_kind(text: str) -> Optional[str]:
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def parse_chart_request(text: str, lang: str, last_spec: Optional[dict] = None) -> Optional[dict]:
    """Returns a raw spec dict (kind + params + lang) ready for
    chart_engine.validate_spec(), or None if this doesn't look like a
    chart request at all (caller should fall through to Q&A handling)."""
    lang_override = is_language_switch_request(text)
    kind = _detect_kind(text)
    is_modifier_only = bool(lang_override) or bool(_NORMALIZE.search(text))

    if kind is None:
        if last_spec is not None and is_modifier_only:
            # "put it in Spanish" / "show the normalized version" with no
            # explicit new kind: treat as a modification of the previous
            # chart. Checked BEFORE the is_chart_request() bail-out below,
            # since a bare "show me the normalized version" doesn't itself
            # contain any chart/kind keyword -- only "normalized" -- and
            # would otherwise be wrongly rejected as not a chart request.
            kind = last_spec.get("kind")
        elif not is_chart_request(text):
            return None
        if kind is None:
            return None

    params: dict = {}
    if last_spec is not None and last_spec.get("kind") == kind:
        params.update(last_spec.get("params", {}))

    if kind in ("confusion_matrix", "f1_by_class", "quant_comparison"):
        if _MODEL_B.search(text):
            params["model_tag"] = "B"
        elif _MODEL_A.search(text):
            params["model_tag"] = "A"
        if _SET_FLOAT.search(text):
            params["metric_set"] = "float"
        elif _SET_INT8.search(text):
            params["metric_set"] = "int8"
        if _SPLIT_VAL.search(text):
            params["split"] = "val"
        elif _SPLIT_TEST.search(text):
            params["split"] = "test"
    if kind == "confusion_matrix" and _NORMALIZE.search(text):
        params["normalize"] = True
    if kind in ("model_comparison", "quant_comparison"):
        if _METRIC_ACC.search(text) and not _METRIC_F1.search(text):
            params["metric"] = "accuracy"
        elif _METRIC_F1.search(text):
            params["metric"] = "macro_f1"
        if kind == "model_comparison":
            if _SET_FLOAT.search(text):
                params["metric_set"] = "float"
            elif _SET_INT8.search(text):
                params["metric_set"] = "int8"
            if _SPLIT_VAL.search(text):
                params["split"] = "val"
            elif _SPLIT_TEST.search(text):
                params["split"] = "test"
        if kind == "quant_comparison":
            if _MODEL_B.search(text):
                params["model_tag"] = "B"
            elif _MODEL_A.search(text):
                params["model_tag"] = "A"
    if kind == "case_scores":
        m = _CASE_NUM.search(text)
        if m:
            num = m.group(1) or m.group(2)
            params["case_id"] = int(num)
        elif "case_id" not in params:
            return None  # a case-scores request with no case number anywhere
    if kind == "training_curves":
        if _MODEL_B.search(text):
            params["model_tag"] = "B"
        elif _MODEL_A.search(text):
            params["model_tag"] = "A"
        if _TRAIN_METRIC_LOSS.search(text) and not _TRAIN_METRIC_ACC.search(text):
            params["metric"] = "loss"
        elif _TRAIN_METRIC_ACC.search(text) and not _TRAIN_METRIC_LOSS.search(text):
            params["metric"] = "accuracy"

    out_lang = lang_override or lang or (last_spec.get("lang") if last_spec else None) or "en"
    return {"kind": kind, "params": params, "lang": out_lang}
