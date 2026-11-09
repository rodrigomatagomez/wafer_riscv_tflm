"""Factual-answer-mode question engine.

Deterministic, read-only, pattern-matched Q&A over the Evidence snapshot
(see evidence.py). This module never calls an LLM and never executes
anything; it only formats numbers that evidence.py already computed from
the authoritative project files, with an explicit citation for each
answer.

Bilingual (English/Spanish): language is either passed explicitly by the
caller (frontend toggle) or guessed from the question text via a small
keyword heuristic. The heuristic is intentionally simple and documented as
a limitation -- it is not a language-ID model.

Every answer is a dict:
    {
        "answer": str,
        "citations": [str, ...],
        "intent": str,
        "lang": "en" | "es",
        "followups": [str, ...],
    }
Unsupported questions return intent="unsupported" and an explicit
"the evidence does not contain that information" message (bilingual),
never a fabricated guess.
"""
from __future__ import annotations

import re
from typing import Optional

from evidence import Evidence, CaseResult

UNSUPPORTED_EN = (
    "The project's saved evidence does not contain that information. "
    "I can only answer questions covered by the files under results/ and "
    "docs/ for the full20_final_001 experiment -- I'm not able to look "
    "anything up beyond what's on disk."
)
UNSUPPORTED_ES = (
    "La evidencia guardada del proyecto no contiene esa información. "
    "Solo puedo responder preguntas cubiertas por los archivos en results/ "
    "y docs/ del experimento full20_final_001; no puedo buscar nada más "
    "allá de lo que existe en disco."
)

_SPANISH_CHARS = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
# Common Spanish words with no accent and no English-homograph collision --
# a single occurrence is enough to call it Spanish (unlike _SPANISH_WORDS
# below, which needs 2+ matches since its entries are weaker/ambiguous
# signals on their own). Found necessary because a bare "hola" or "gracias"
# -- real, expected greeting input -- has neither an accent nor two
# matching stopwords, and was being misdetected as English.
_SPANISH_STRONG_SIGNAL = re.compile(
    r"\b(hola|gracias|adios|chau|chao|saludos|buenas|oye)\b", re.IGNORECASE,
)
_SPANISH_WORDS = re.compile(
    r"\b(que|como|cuantos?|cuando|donde|cual(es)?|son|fue|caso|casos|fueron|"
    r"fallo|empate|fallaron|fallido|precision|exactitud|memoria|tiempo|ciclos|"
    r"frecuencia|potencia|area|servidor|evidencia|coincide|coinciden|esta|"
    r"completo|experimento|clasificador|corre|ejecuta|chip)\b",
    re.IGNORECASE,
)

# Physical-measurement keywords that must always be answered as unsupported,
# in both languages, even if the question also contains a recognized
# evidence-related keyword (e.g. "what frequency did the simulation run at").
_PHYSICAL_UNSUPPORTED_EN = re.compile(
    r"\b(clock\s*(speed|frequency)|ghz|mhz|physical\s*chip|silicon|asic|"
    r"fpga|tape[- ]?out|power|consum\w*|watts?|milliwatts?|"
    r"die\s*area|mm2|mm\^2|square\s*millimeters?|energy\s*efficiency|"
    r"joules?)\b",
    re.IGNORECASE,
)
_PHYSICAL_UNSUPPORTED_ES = re.compile(
    r"\b(frecuencia\s*(del\s*reloj|de\s*reloj)?|ghz|mhz|chip\s*f[ií]sico|"
    r"silicio|fpga|potencia|vatios?|consumo\s*(de\s*energ[ií]a|el[eé]ctrico)|"
    r"[aá]rea\s*(del?\s*)?(chip|troquel|silicio)|mil[ií]metros?\s*cuadrados?|"
    r"eficiencia\s*energ[eé]tica)\b",
    re.IGNORECASE,
)


def detect_language(text: str, explicit: Optional[str] = None) -> str:
    """Lightweight heuristic, not a language-ID model (documented limitation).

    Spanish if the text contains an accented letter, ñ, ¿ or ¡ (very reliable
    for Spanish questions, essentially never present in English), OR at least
    two common Spanish stopwords/keywords are present. Otherwise English.
    """
    if explicit in ("en", "es"):
        return explicit
    if _SPANISH_CHARS.search(text):
        return "es"
    if _SPANISH_STRONG_SIGNAL.search(text):
        return "es"
    if len(_SPANISH_WORDS.findall(text)) >= 2:
        return "es"
    return "en"


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _case_block_en(c: CaseResult) -> str:
    match_word = "MATCH" if c.rtl_matches_native else "MISMATCH"
    correct_word = "correct" if c.classifier_correct else "a misclassification"
    tie_note = ""
    if c.has_score_tie:
        tie_note = (
            f" The RTL scores contain a tie: {', '.join(c.tie_class_names)} are "
            f"both the maximum score ({max(c.rtl_scores)}); both RTL and the "
            f"native oracle resolve it identically to class index "
            f"{c.rtl_predicted_class}, which is why they still agree exactly."
        )
    return (
        f"Case {c.case_id} (sample_id {c.sample_id}): ground truth is "
        f"'{c.ground_truth_class_name}'. Native TFLM predicted class "
        f"{c.native_predicted_class} with scores {c.native_scores}. RTL "
        f"predicted class {c.rtl_predicted_class} with scores {c.rtl_scores} "
        f"-- RTL vs native: {match_word}. This is {correct_word} relative to "
        f"the ground truth.{tie_note} Invoke() took "
        f"{c.invoke_elapsed_cycles:,} RTL cycles "
        f"(start cycle {c.invoke_start_cycle}, end cycle {c.invoke_end_cycle})."
    )


def _case_block_es(c: CaseResult) -> str:
    match_word = "COINCIDE" if c.rtl_matches_native else "NO COINCIDE"
    correct_word = "correcta" if c.classifier_correct else "una clasificación errónea"
    tie_note = ""
    if c.has_score_tie:
        tie_note = (
            f" Las puntuaciones de RTL tienen un empate: {', '.join(c.tie_class_names)} "
            f"comparten la puntuación máxima ({max(c.rtl_scores)}); tanto RTL "
            f"como el oráculo nativo lo resuelven de forma idéntica hacia la "
            f"clase {c.rtl_predicted_class}, por eso coinciden exactamente."
        )
    return (
        f"Caso {c.case_id} (sample_id {c.sample_id}): la clase real (ground "
        f"truth) es '{c.ground_truth_class_name}'. TFLM nativo predijo la "
        f"clase {c.native_predicted_class} con puntuaciones {c.native_scores}. "
        f"RTL predijo la clase {c.rtl_predicted_class} con puntuaciones "
        f"{c.rtl_scores} -- RTL vs nativo: {match_word}. Esto es "
        f"{correct_word} respecto a la clase real.{tie_note} Invoke() tomó "
        f"{c.invoke_elapsed_cycles:,} ciclos de RTL "
        f"(ciclo de inicio {c.invoke_start_cycle}, ciclo final {c.invoke_end_cycle})."
    )


_CASE_NUM_RE = re.compile(r"\bcase\s*#?\s*(\d{1,2})\b|\bcaso\s*#?\s*(\d{1,2})\b", re.IGNORECASE)

_INTENTS = [
    # order matters: more specific intents should be checked before general ones
    ("tie", re.compile(r"\b(tie|tied|tying)\b", re.IGNORECASE),
     re.compile(r"\bempat(e|ado|an|ados)\b", re.IGNORECASE)),
    ("misclassified", re.compile(
        r"\b(misclassif\w*|wrong\s+(case|prediction)s?|which cases? (are|were) wrong|errors?)\b",
        re.IGNORECASE),
     re.compile(r"\b(mal clasificad\w*|equivocad\w*|errores?|casos? err[oó]neos?)\b", re.IGNORECASE)),
    ("classifier_quality", re.compile(
        r"\b(accuracy|macro[- ]?f1|f1[- ]score|quality|how good|0\.85|target)\b", re.IGNORECASE),
     re.compile(r"\b(precisi[oó]n|exactitud|calidad|f1|objetivo|meta)\b", re.IGNORECASE)),
    ("memory", re.compile(r"\b(memory|arena|ram|bytes|heap)\b", re.IGNORECASE),
     re.compile(r"\b(memoria|arena|ram|bytes|pila)\b", re.IGNORECASE)),
    ("physical_unsupported", _PHYSICAL_UNSUPPORTED_EN, _PHYSICAL_UNSUPPORTED_ES),
    ("timing", re.compile(
        r"\b(how long|wall[- ]?clock|cycles?|latency|speed|how fast|duration|time did)\b",
        re.IGNORECASE),
     re.compile(r"\b(cu[aá]nto\s+(tiempo|tard[oó])|tiempo|ciclos?|latencia|velocidad|duraci[oó]n)\b", re.IGNORECASE)),
    ("where_runs", re.compile(
        r"\bwhere\s+(does|is)\b.{0,40}\b(run|hosted|located)\b|\bhost\s*server\b|\bwhich\s+machine\b",
        re.IGNORECASE),
     re.compile(r"\bd[oó]nde\b.{0,40}\b(corre|ejecuta|alojado|aloja)\b|\bservidor\b.{0,20}\bchat\b|\bqu[eé]\s+m[aá]quina\b", re.IGNORECASE)),
    ("agreement", re.compile(
        r"\b(agree|match(es|ed)?|exact match|20/20|all (20 )?cases|rtl.*native|native.*rtl)\b",
        re.IGNORECASE),
     re.compile(r"\b(coincid\w*|veinte casos|20 casos|rtl.*nativo|nativo.*rtl)\b", re.IGNORECASE)),
    ("completion", re.compile(
        r"\b(complet(e|ed|ion)|finish(ed)?|done|status|did it work|final result|succeeded)\b",
        re.IGNORECASE),
     re.compile(r"\b(complet\w*|termin\w*|funcion[oó]|estado|resultado final|logr[oó]|éxito)\b", re.IGNORECASE)),
    ("provenance", re.compile(
        r"\b(evidence|source files?|how (was|is) this verified|reproduce|checker|sha-?256|hash)\b",
        re.IGNORECASE),
     re.compile(r"\b(evidencia|archivos? fuente|c[oó]mo se verific[oó]|reproducir|hash)\b", re.IGNORECASE)),
]


def classify_intent(question: str) -> str:
    m = _CASE_NUM_RE.search(question)
    if m:
        return "case_lookup"
    for name, en_re, es_re in _INTENTS:
        if en_re.search(question) or es_re.search(question):
            return name
    return "unsupported"


def _extract_case_id(question: str) -> Optional[int]:
    m = _CASE_NUM_RE.search(question)
    if not m:
        return None
    num = m.group(1) or m.group(2)
    return int(num)


def answer(question: str, ev: Evidence, lang_hint: Optional[str] = None,
           last_case_id: Optional[int] = None) -> dict:
    lang = detect_language(question, lang_hint)
    intent = classify_intent(question)

    if intent == "case_lookup":
        cid = _extract_case_id(question)
        return _answer_case(cid, ev, lang)

    # "what about that one" / "y ese" style follow-ups without an explicit
    # number: reuse the last case discussed, if any.
    if last_case_id is not None and re.search(
        r"\b(that one|this case|it)\b", question, re.IGNORECASE
    ) and intent == "unsupported":
        return _answer_case(last_case_id, ev, lang)

    handler = _HANDLERS.get(intent)
    if handler is None:
        return {
            "answer": UNSUPPORTED_ES if lang == "es" else UNSUPPORTED_EN,
            "citations": [],
            "intent": "unsupported",
            "lang": lang,
            "followups": _suggested_followups(lang),
        }
    return handler(ev, lang)


def _answer_case(cid: Optional[int], ev: Evidence, lang: str) -> dict:
    if cid is None:
        msg = (
            "I can look up any case from 0 to 19 -- which one would you like?"
            if lang == "en" else
            "Puedo consultar cualquier caso del 0 al 19 -- ¿cuál te interesa?"
        )
        return {"answer": msg, "citations": [], "intent": "case_lookup_missing_id",
                "lang": lang, "followups": _suggested_followups(lang)}
    if not (0 <= cid <= 19) or ev.case(cid) is None:
        msg = (
            f"Case {cid} is out of range for this 20-case experiment (valid IDs: 0-19)."
            if lang == "en" else
            f"El caso {cid} está fuera de rango para este experimento de 20 casos (IDs válidos: 0-19)."
        )
        return {"answer": msg, "citations": [], "intent": "case_lookup_out_of_range",
                "lang": lang, "followups": _suggested_followups(lang)}
    c = ev.case(cid)
    text = _case_block_en(c) if lang == "en" else _case_block_es(c)
    citations = [
        "results/comparison_manifest.json (cases[*].sample_id, class_idx)",
        "results/final_run_evidence/full20_final_001_check_report.json (rows[*], cases_parsed[*])",
        c.log_citation(),
    ]
    followups = [f"case {cid + 1}"] if cid < 19 else []
    if not c.classifier_correct:
        followups.append("misclassified cases" if lang == "en" else "casos mal clasificados")
    return {"answer": text, "citations": citations, "intent": "case_lookup",
            "lang": lang, "followups": followups, "case_id": cid}


def _answer_completion(ev: Evidence, lang: str) -> dict:
    if lang == "es":
        text = (
            f"Sí, la finalización funcional está establecida. La ejecución final "
            f"'{ev.run_id.value}' completó los {ev.n_cases.value} casos de comparación "
            f"desde el ciclo 0, con el marcador final '{ev.checker_verdict.value}' "
            f"(código de salida del verificador: {ev.checker_exit_code.value}). "
            f"Esto significa que las {ev.n_matched_rtl_native.value} comparaciones "
            f"RTL-contra-nativo coinciden exactamente -- no significa que el "
            f"clasificador en sí sea perfecto (ver la pregunta sobre calidad del "
            f"clasificador)."
        )
    else:
        text = (
            f"Yes, functional completion is established. The final run "
            f"'{ev.run_id.value}' completed all {ev.n_cases.value} comparison cases "
            f"from cycle 0, with the final marker '{ev.checker_verdict.value}' "
            f"(checker exit code: {ev.checker_exit_code.value}). This means all "
            f"{ev.n_matched_rtl_native.value} RTL-vs-native comparisons match "
            f"exactly -- it does not mean the classifier itself is perfect (see "
            f"the classifier-quality question for that distinction)."
        )
    citations = [ev.run_id.cite(), ev.checker_verdict.cite(), ev.n_matched_rtl_native.cite()]
    followups = ["classifier accuracy", "simulation timing"] if lang == "en" else \
        ["precisión del clasificador", "tiempo de simulación"]
    return {"answer": text, "citations": citations, "intent": "completion", "lang": lang, "followups": followups}


def _answer_agreement(ev: Evidence, lang: str) -> dict:
    n = ev.n_cases.value
    m = ev.n_matched_rtl_native.value
    if lang == "es":
        text = (
            f"Las {m} de {n} comparaciones RTL-contra-nativo coinciden exactamente: "
            f"para cada uno de los {n} casos, las cuatro puntuaciones enteras y la "
            f"clase predicha que produce el procesador RTL simulado son idénticas, "
            f"bit a bit, a las del oráculo nativo de TFLM. Esto es una afirmación "
            f"distinta de si el clasificador acierta la clase real: el modelo en sí "
            f"solo es correcto en {ev.n_classifier_correct_on_fixed_cases}/{n} de "
            f"estos casos fijos -- RTL reproduce exactamente la salida nativa, "
            f"incluyendo sus errores."
        )
    else:
        text = (
            f"All {m} of {n} RTL-vs-native comparisons match exactly: for every "
            f"one of the {n} cases, the four integer scores and the predicted "
            f"class produced by the RTL-simulated processor are bit-for-bit "
            f"identical to the native TFLM oracle's output. This is a different "
            f"claim from whether the classifier gets the ground-truth class "
            f"right: the model itself is only correct on "
            f"{ev.n_classifier_correct_on_fixed_cases}/{n} of these fixed cases "
            f"-- RTL reproduces the native output exactly, including its errors."
        )
    citations = [ev.n_matched_rtl_native.cite(), "results/final_run_evidence/full20_final_001_check_report.json (rows[*].status)"]
    followups = ["which cases are misclassified", "case 0"] if lang == "en" else \
        ["qué casos están mal clasificados", "caso 0"]
    return {"answer": text, "citations": citations, "intent": "agreement", "lang": lang, "followups": followups}


def _answer_classifier_quality(ev: Evidence, lang: str) -> dict:
    acc = ev.test_accuracy.value
    f1 = ev.test_macro_f1.value
    target = ev.quality_target_macro_f1.value
    met = ev.quality_target_met.value
    n_correct = ev.n_classifier_correct_on_fixed_cases
    n_total = len(ev.cases)
    if lang == "es":
        text = (
            f"La calidad del clasificador se mide en el conjunto de prueba "
            f"completo, no solo en estos {n_total} casos fijos: exactitud = "
            f"{acc:.4f} ({_fmt_pct(acc)}), macro-F1 = {f1:.5f}. El objetivo del "
            f"proyecto era macro-F1 ≥ {target}, y {'se cumplió' if met else 'NO se cumplió'}. "
            f"En estos {n_total} casos fijos específicos usados para la "
            f"comparación RTL, el clasificador predice la clase real correcta "
            f"en {n_correct}/{n_total} (casos erróneos: {', '.join(str(c) for c in ev.misclassified_case_ids)}). "
            f"Esto es independiente de la verificación RTL: las {ev.n_matched_rtl_native.value} "
            f"coincidencias RTL-nativo no cambian esta limitación de calidad."
        )
    else:
        text = (
            f"Classifier quality is measured on the full held-out test split, "
            f"not just these {n_total} fixed cases: accuracy = {acc:.4f} "
            f"({_fmt_pct(acc)}), macro-F1 = {f1:.5f}. The project's target was "
            f"macro-F1 ≥ {target}, and it was {'met' if met else 'NOT met'}. "
            f"On these {n_total} specific fixed cases used for the RTL "
            f"comparison, the classifier predicts the correct ground-truth "
            f"class in {n_correct}/{n_total} "
            f"(misclassified: {', '.join(str(c) for c in ev.misclassified_case_ids)}). "
            f"This is independent of RTL verification -- the "
            f"{ev.n_matched_rtl_native.value}/{len(ev.cases)} RTL-vs-native "
            f"matches do not change this quality limitation."
        )
    citations = [ev.test_accuracy.cite(), ev.test_macro_f1.cite(), ev.quality_target_met.cite()]
    followups = ["case 0", "case 16", "which cases are misclassified"] if lang == "en" else \
        ["caso 0", "caso 16", "qué casos están mal clasificados"]
    return {"answer": text, "citations": citations, "intent": "classifier_quality", "lang": lang, "followups": followups}


def _answer_misclassified(ev: Evidence, lang: str) -> dict:
    ids = ev.misclassified_case_ids
    details = []
    for cid in ids:
        c = ev.case(cid)
        if lang == "es":
            details.append(f"caso {cid} (real: {c.ground_truth_class_name}, predicho: clase {c.rtl_predicted_class})")
        else:
            details.append(f"case {cid} (ground truth: {c.ground_truth_class_name}, predicted: class {c.rtl_predicted_class})")
    if lang == "es":
        text = (
            f"El clasificador se equivoca en {len(ids)} de los {len(ev.cases)} "
            f"casos fijos: {'; '.join(details)}. En todos estos casos, la "
            f"ejecución RTL coincide exactamente con el oráculo nativo -- es "
            f"decir, el procesador reproduce fielmente la salida del modelo, "
            f"incluyendo sus errores; no es un fallo del hardware."
        )
    else:
        text = (
            f"The classifier gets {len(ids)} of the {len(ev.cases)} fixed cases "
            f"wrong: {'; '.join(details)}. In every one of these cases, the RTL "
            f"run matches the native oracle exactly -- i.e. the processor "
            f"faithfully reproduces the model's output, including its errors; "
            f"this is not a hardware failure."
        )
    citations = ["results/final_run_evidence/full20_final_001_check_report.json (rows[*])",
                 "results/comparison_manifest.json (cases[*].class_idx)"]
    followups = [f"case {ids[0]}"] if ids else []
    return {"answer": text, "citations": citations, "intent": "misclassified", "lang": lang, "followups": followups}


def _answer_tie(ev: Evidence, lang: str) -> dict:
    tie_ids = ev.tie_case_ids
    if not tie_ids:
        msg = ("No case in this experiment has a tied top score." if lang == "en"
               else "Ningún caso de este experimento tiene un empate en la puntuación máxima.")
        return {"answer": msg, "citations": [], "intent": "tie", "lang": lang, "followups": []}
    cid = tie_ids[0]
    c = ev.case(cid)
    if lang == "es":
        text = (
            f"Caso {cid}: las puntuaciones RTL son {c.rtl_scores} -- las clases "
            f"{', '.join(c.tie_class_names)} empatan en la puntuación máxima "
            f"({max(c.rtl_scores)}). Tanto la implementación RTL como la nativa "
            f"resuelven el empate de forma idéntica, eligiendo la clase "
            f"{c.rtl_predicted_class} (el primer índice con el valor máximo); "
            f"por eso siguen coincidiendo exactamente entre sí, aunque la "
            f"clase real sea '{c.ground_truth_class_name}' y por tanto esta "
            f"predicción sea incorrecta frente a la clase real."
        )
    else:
        text = (
            f"Case {cid}: the RTL scores are {c.rtl_scores} -- classes "
            f"{', '.join(c.tie_class_names)} tie for the maximum score "
            f"({max(c.rtl_scores)}). Both the RTL and native implementations "
            f"resolve the tie identically, picking class {c.rtl_predicted_class} "
            f"(the first index holding the maximum value); that is why they "
            f"still match each other exactly, even though the ground truth is "
            f"'{c.ground_truth_class_name}', making this prediction incorrect "
            f"relative to the ground truth."
        )
    citations = ["results/final_run_evidence/full20_final_001_check_report.json (rows[*].rtl_scores)",
                 c.log_citation()]
    return {"answer": text, "citations": citations, "intent": "tie", "lang": lang,
            "followups": [f"case {cid}"], "case_id": cid}


def _answer_timing(ev: Evidence, lang: str) -> dict:
    if lang == "es":
        text = (
            f"La ejecución final tardó {ev.final_cycle.value:,} ciclos de reloj "
            f"simulados, reportados por Zenith como {ev.wall_clock_zenith_reported.value} "
            f"de tiempo de reloj (reloj de pared) del simulador "
            f"({ev.wall_clock_seconds.value} s medidos). Esto es tiempo de "
            f"SIMULACIÓN en la máquina host, no la latencia de inferencia de un "
            f"chip físico: cada ciclo de RTL se evalúa mediante software de "
            f"simulación de eventos discretos, que es muchos órdenes de magnitud "
            f"más lento que la ejecución real en silicio a su frecuencia de "
            f"reloj prevista. El número de ciclos simulados (los "
            f"{ev.final_cycle.value:,} ciclos, o ~7.03 millones de ciclos por "
            f"cada llamada a Invoke()) es la cifra relevante para la latencia "
            f"relativa del hardware; el tiempo de reloj de pared del simulador no lo es."
        )
    else:
        text = (
            f"The final run took {ev.final_cycle.value:,} simulated clock "
            f"cycles, reported by Zenith as {ev.wall_clock_zenith_reported.value} "
            f"of simulator wall-clock time ({ev.wall_clock_seconds.value} s "
            f"measured). This is SIMULATION time on the host machine, not "
            f"physical-chip inference latency: each RTL cycle is evaluated by "
            f"discrete-event simulation software, which is many orders of "
            f"magnitude slower than running on actual silicon at its intended "
            f"clock frequency. The simulated cycle count (the "
            f"{ev.final_cycle.value:,} cycles, or ~7.03 million cycles per "
            f"Invoke() call) is the figure relevant to relative hardware "
            f"latency; the simulator's wall-clock time is not."
        )
    citations = [ev.final_cycle.cite(), ev.wall_clock_seconds.cite(), ev.wall_clock_zenith_reported.cite()]
    followups = ["memory usage", "case 0 cycles"] if lang == "en" else \
        ["uso de memoria", "ciclos del caso 0"]
    return {"answer": text, "citations": citations, "intent": "timing", "lang": lang, "followups": followups}


def _answer_memory(ev: Evidence, lang: str) -> dict:
    reserved = ev.tensor_arena_reserved_bytes.value
    measured = ev.tensor_arena_measured_peak_bytes.value
    if lang == "es":
        text = (
            f"El tensor arena reserva {reserved:,} bytes estáticamente "
            f"(sw/app/wafer_common.h, kTensorArenaSize). El uso pico medido es "
            f"de {measured:,} bytes, pero esa medición proviene del ORÁCULO "
            f"NATIVO x86 (MicroInterpreter::arena_used_bytes(), impreso por "
            f"sw/app/main_native.cc), NO de una medición independiente dentro "
            f"del firmware ejecutándose en el procesador RV32 simulado. El "
            f"firmware RV32 usa exactamente el mismo modelo, el mismo "
            f"resolutor de operadores y la misma constante de tamaño de "
            f"arena, por lo que la cifra nativa es una referencia confiable, "
            f"pero no fue instrumentada por separado para informar su propio "
            f"arena_used_bytes() sobre MMIO."
        )
    else:
        text = (
            f"The tensor arena statically reserves {reserved:,} bytes "
            f"(sw/app/wafer_common.h, kTensorArenaSize). The measured peak use "
            f"is {measured:,} bytes, but that measurement comes from the "
            f"NATIVE x86 ORACLE (MicroInterpreter::arena_used_bytes(), printed "
            f"by sw/app/main_native.cc), NOT from an independent measurement "
            f"inside the firmware running on the simulated RV32 processor. "
            f"The RV32 firmware uses the exact same model, op resolver, and "
            f"arena-size constant, so the native figure is a reliable proxy, "
            f"but it was not separately instrumented to report its own "
            f"arena_used_bytes() over MMIO."
        )
    citations = [ev.tensor_arena_reserved_bytes.cite(), ev.tensor_arena_measured_peak_bytes.cite(),
                 ev.tensor_arena_measurement_source_note.cite()]
    return {"answer": text, "citations": citations, "intent": "memory", "lang": lang, "followups": []}


def _answer_physical_unsupported(ev: Evidence, lang: str) -> dict:
    if lang == "es":
        text = (
            "La evidencia guardada del proyecto no contiene esa información. "
            "Este proyecto es una verificación de simulación RTL de un "
            "procesador RISC-V; no se realizó síntesis, cierre de temporización, "
            "ni implementación en FPGA o silicio real. No se midió la "
            "frecuencia de reloj física, el consumo de potencia ni el área del "
            "chip -- esas cifras simplemente no existen en esta evidencia."
        )
    else:
        text = (
            "The project's saved evidence does not contain that information. "
            "This project is an RTL simulation verification of a RISC-V "
            "processor; no synthesis, timing closure, or FPGA/silicon "
            "implementation was performed. Physical clock frequency, power "
            "consumption, and chip area were not measured -- those figures "
            "simply do not exist in this evidence."
        )
    return {"answer": text, "citations": [], "intent": "physical_unsupported", "lang": lang, "followups": []}


def _answer_where_runs(ev: Evidence, lang: str) -> dict:
    if lang == "es":
        text = (
            "El clasificador (el modelo TensorFlow Lite Micro cuantizado) se "
            "ejecuta DENTRO del procesador RISC-V RV32IM simulado, bajo el "
            "simulador Zenith/Animas -- esa es la ejecución verificada en "
            "full20_final_001. Este asistente de chat, en cambio, es una "
            "aplicación aparte que se ejecuta en el SERVIDOR ANFITRIóN (fuera "
            "de la simulación), leyendo los archivos de evidencia ya "
            "guardados. El chat no se ejecuta dentro del RISC-V simulado y no "
            "puede iniciar, modificar ni controlar ninguna simulación."
        )
    else:
        text = (
            "The classifier (the quantized TensorFlow Lite Micro model) runs "
            "INSIDE the simulated RV32IM RISC-V processor, under the "
            "Zenith/Animas simulator -- that is the verified execution in "
            "full20_final_001. This chat assistant, by contrast, is a "
            "separate application running on the HOST SERVER (outside the "
            "simulation), reading the already-saved evidence files. The chat "
            "does not run inside the simulated RISC-V and cannot start, "
            "modify, or control any simulation."
        )
    return {"answer": text, "citations": [], "intent": "where_runs", "lang": lang, "followups": []}


def _answer_provenance(ev: Evidence, lang: str) -> dict:
    if lang == "es":
        text = (
            f"Este resultado se verificó con un comprobador estricto e "
            f"independiente (scripts/check_final_run.py), que compara cada una "
            f"de las 20 predicciones RTL con el oráculo nativo y exige una "
            f"coincidencia exacta de las 4 puntuaciones y la clase predicha. "
            f"Veredicto: '{ev.checker_verdict.value}' (código de salida "
            f"{ev.checker_exit_code.value}). Hashes de procedencia: modelo "
            f"sha256={ev.model_sha256.value[:16]}…, firmware ELF "
            f"sha256={ev.firmware_elf_sha256.value[:16]}…, commit de TFLM "
            f"{ev.tflm_commit.value}. Toda la evidencia en bruto está en "
            f"results/final_run_evidence/."
        )
    else:
        text = (
            f"This result was verified with a strict, independent checker "
            f"(scripts/check_final_run.py), which compares all 20 RTL "
            f"predictions against the native oracle and requires an exact "
            f"match of all 4 scores and the predicted class. Verdict: "
            f"'{ev.checker_verdict.value}' (exit code {ev.checker_exit_code.value}). "
            f"Provenance hashes: model sha256={ev.model_sha256.value[:16]}…, "
            f"firmware ELF sha256={ev.firmware_elf_sha256.value[:16]}…, TFLM "
            f"commit {ev.tflm_commit.value}. All raw evidence is under "
            f"results/final_run_evidence/."
        )
    citations = [ev.checker_verdict.cite(), ev.model_sha256.cite(), ev.firmware_elf_sha256.cite(), ev.tflm_commit.cite()]
    return {"answer": text, "citations": citations, "intent": "provenance", "lang": lang, "followups": []}


_HANDLERS = {
    "completion": _answer_completion,
    "agreement": _answer_agreement,
    "classifier_quality": _answer_classifier_quality,
    "misclassified": _answer_misclassified,
    "tie": _answer_tie,
    "timing": _answer_timing,
    "memory": _answer_memory,
    "physical_unsupported": _answer_physical_unsupported,
    "where_runs": _answer_where_runs,
    "provenance": _answer_provenance,
}


def _suggested_followups(lang: str) -> list:
    if lang == "es":
        return ["¿Qué pasó con el caso 16?", "¿Cuál es la precisión del clasificador?"]
    return ["What about case 16?", "What is the classifier's accuracy?"]


SUGGESTED_QUESTIONS_EN = [
    "Is this experiment functionally complete?",
    "Do all 20 RTL results match the native reference?",
    "What is the classifier's accuracy and macro-F1?",
    "What about case 16?",
    "What's the tie in case 16?",
    "What was the chip's clock frequency?",
    "Plot the confusion matrix, normalized.",
    "Graph F1 by class.",
    "Compare Model A and B.",
    "Show me the scores for case 16.",
    "Plot the training curves for model B.",
    "Why was Spike not used for processor verification?",
    "What are this project's main limitations?",
]

SUGGESTED_QUESTIONS_ES = [
    "¿Está este experimento funcionalmente completo?",
    "¿Coinciden los 20 resultados de RTL con la referencia nativa?",
    "¿Cuál es la exactitud y el macro-F1 del clasificador?",
    "¿Qué pasó con el caso 16?",
    "¿Cuál es el empate en el caso 16?",
    "¿Cuál fue la frecuencia de reloj del chip?",
    "Grafica la matriz de confusión normalizada.",
    "Grafica el F1 por clase.",
    "Compara el modelo A y B.",
    "Enséñame los scores del caso 16.",
    "Grafica las curvas de entrenamiento del modelo B.",
    "¿Por qué no se usó Spike para la verificación del procesador?",
    "¿Cuáles son las principales limitaciones del proyecto?",
]
