"""Social-conversation detection and canned bilingual replies.

Greetings, thanks, farewells, and "what can you do" capability questions
must not require document retrieval or an evidence citation -- a plain
"hi" has no project-specific content to ground. This module detects those
patterns (bilingual, tolerant of real variation, not just a literal
string match) and distinguishes two cases:

  - purely social ("hi", "hola", "gracias", "¿qué puedes hacer?"):
    answered directly here, deterministically, no retrieval/LLM call.
  - mixed (a greeting glued onto a real question, e.g. "Hola, ¿puedes
    explicarme qué hace este proyecto?"): the social phrase is stripped
    out before the remainder is handed to the normal routing pipeline
    (chart / FAQ / open-ended retrieval), so the greeting doesn't dilute
    intent classification or retrieval relevance, and the caller can still
    prepend a short, warm acknowledgment to whatever real answer comes
    back.

Nothing here touches evidence, retrieval, or the LLM -- it is pure text
classification, run once per incoming message before any of that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import knowledge_base as kb_mod

# Each pattern is matched case-insensitively and stripped (replaced with a
# space) when computing the "substantive remainder" of a message. Patterns
# are phrased as complete words/phrases (not short substrings) to avoid
# stripping part of a real sentence -- e.g. "hi" only matches as a whole
# word, never inside "high".
_GREETING_EN = re.compile(
    r"\b(hi there|hello there|hey there|good morning|good afternoon|"
    r"good evening|how are you|how's it going|hows it going|greetings|"
    r"hiya|hi|hello|hey|yo)\b", re.IGNORECASE)
_GREETING_ES = re.compile(
    r"\b(buenos dias|buenas tardes|buenas noches|como estas|como esta|"
    r"que tal estas|que tal|hola|buenas|saludos)\b", re.IGNORECASE)

_THANKS_EN = re.compile(
    r"\b(thank you very much|thanks a lot|thank you|thanks|thx|ty|"
    r"much appreciated|appreciate it|appreciated)\b", re.IGNORECASE)
_THANKS_ES = re.compile(
    r"\b(muchas gracias|mil gracias|te lo agradezco|muy amable|gracias)\b",
    re.IGNORECASE)

_FAREWELL_EN = re.compile(
    r"\b(good bye|goodbye|see you later|see you|see ya|take care|"
    r"farewell|have a good day|have a nice day|bye)\b", re.IGNORECASE)
_FAREWELL_ES = re.compile(
    r"\b(hasta luego|hasta pronto|nos vemos|que tengas buen dia|"
    r"cuidate|adios|chao|chau)\b", re.IGNORECASE)

_CAPABILITY_EN = re.compile(
    r"\b(what can you do|what do you do|how can you help( me)?|"
    r"how do you help|who are you|what are you|"
    r"what can you help( me)? with)\b", re.IGNORECASE)
_CAPABILITY_ES = re.compile(
    r"\b(que puedes hacer|que sabes hacer|como puedes ayudar(me)?|"
    r"como me puedes ayudar|en que me puedes ayudar|quien eres|"
    r"que eres)\b", re.IGNORECASE)

# Order matters only for picking a single reply category when a message is
# purely social and happens to match more than one class (rare) --
# capability questions get the most useful (longest) canned reply.
_CATEGORY_PATTERNS = [
    ("capability", _CAPABILITY_EN, _CAPABILITY_ES),
    ("thanks", _THANKS_EN, _THANKS_ES),
    ("farewell", _FAREWELL_EN, _FAREWELL_ES),
    ("greeting", _GREETING_EN, _GREETING_ES),
]


@dataclass
class SocialAnalysis:
    categories: list = field(default_factory=list)
    stripped_text: str = ""
    is_purely_social: bool = False


def analyze(text: str) -> SocialAnalysis:
    # Match against an accent-folded copy so "¿qué puedes hacer?" matches
    # the same (unaccented) pattern as "que puedes hacer" -- folding is
    # length-preserving per character (NFKD decomposes e.g. 'é' into 'e' +
    # a combining mark, which is then dropped), so offsets in the folded
    # copy line up with the original for the substitutions below.
    folded = kb_mod.fold_accents(text)
    categories = []
    stripped = folded
    for name, pat_en, pat_es in _CATEGORY_PATTERNS:
        matched = bool(pat_en.search(stripped)) or bool(pat_es.search(stripped))
        if matched:
            categories.append(name)
            stripped = pat_en.sub(" ", stripped)
            stripped = pat_es.sub(" ", stripped)

    stripped = re.sub(r"\s+", " ", stripped).strip(" ,.;:!-¡¿?")

    if not categories:
        return SocialAnalysis(categories=[], stripped_text=text, is_purely_social=False)

    remainder_tokens = kb_mod.tokenize(stripped)
    purely_social = len(remainder_tokens) == 0
    return SocialAnalysis(categories=categories, stripped_text=stripped,
                           is_purely_social=purely_social)


_GREETING_REPLY_EN = (
    "Hi! I can explain the wafer_riscv_tflm RISC-V/TFLM verification results "
    "(architecture, methodology, results, limitations) and generate charts "
    "from them -- all grounded in the project's saved evidence. Ask me "
    "anything, e.g. \"Is this experiment complete?\" or \"Plot F1 by class.\""
)
_GREETING_REPLY_ES = (
    "¡Hola! Puedo explicarte los resultados de verificación RISC-V/TFLM de "
    "wafer_riscv_tflm (arquitectura, metodología, resultados, limitaciones) "
    "y generar gráficas a partir de ellos -- todo basado en la evidencia "
    "guardada del proyecto. Pregúntame lo que quieras, por ejemplo: "
    "\"¿Está completo el experimento?\" o \"Grafica el F1 por clase.\""
)

_THANKS_REPLY_EN = "You're welcome! Let me know if you have more questions about the project."
_THANKS_REPLY_ES = "¡De nada! Avísame si tienes más preguntas sobre el proyecto."

_FAREWELL_REPLY_EN = "Goodbye! Feel free to come back anytime you have questions about these results."
_FAREWELL_REPLY_ES = "¡Hasta luego! Vuelve cuando quieras si tienes preguntas sobre estos resultados."

_CAPABILITY_REPLY_EN = (
    "I can: (1) answer open-ended questions about this project's "
    "architecture, methodology, verification, and limitations, grounded in "
    "its saved documentation with source citations; (2) answer precise "
    "questions about the final results (completion status, RTL-vs-native "
    "agreement, classifier accuracy, a specific case, timing, memory); "
    "(3) generate charts on request (confusion matrix, F1 by class, model "
    "comparisons, per-case scores, training curves, memory budget) with "
    "PNG/SVG/CSV downloads. I only use real, saved evidence -- I'll tell "
    "you plainly if something (like physical power or clock frequency) "
    "was never measured, rather than guessing."
)
_CAPABILITY_REPLY_ES = (
    "Puedo: (1) responder preguntas abiertas sobre la arquitectura, "
    "metodología, verificación y limitaciones de este proyecto, basándome "
    "en su documentación guardada con citas de fuente; (2) responder "
    "preguntas precisas sobre los resultados finales (estado de "
    "finalización, concordancia RTL-nativo, exactitud del clasificador, un "
    "caso específico, tiempos, memoria); (3) generar gráficas a pedido "
    "(matriz de confusión, F1 por clase, comparaciones de modelos, "
    "puntuaciones por caso, curvas de entrenamiento, presupuesto de "
    "memoria) con descargas en PNG/SVG/CSV. Solo uso evidencia real y "
    "guardada -- te diré claramente si algo (como la potencia física o la "
    "frecuencia de reloj) nunca se midió, en vez de adivinar."
)

_FOLLOWUPS_EN = ["Is this experiment functionally complete?", "Plot F1 by class."]
_FOLLOWUPS_ES = ["¿Está completo el experimento?", "Grafica el F1 por clase."]

_REPLY_TABLE = {
    "greeting": (_GREETING_REPLY_EN, _GREETING_REPLY_ES, _FOLLOWUPS_EN, _FOLLOWUPS_ES),
    "thanks": (_THANKS_REPLY_EN, _THANKS_REPLY_ES, [], []),
    "farewell": (_FAREWELL_REPLY_EN, _FAREWELL_REPLY_ES, [], []),
    "capability": (_CAPABILITY_REPLY_EN, _CAPABILITY_REPLY_ES, _FOLLOWUPS_EN, _FOLLOWUPS_ES),
}

# Priority for picking ONE reply when multiple categories matched a purely
# social message (e.g. "Hi, what can you do?").
_REPLY_PRIORITY = ["capability", "thanks", "farewell", "greeting"]


def respond(categories: list, lang: str) -> dict:
    category = next((c for c in _REPLY_PRIORITY if c in categories), categories[0])
    en, es, fen, fes = _REPLY_TABLE[category]
    answer = es if lang == "es" else en
    followups = fes if lang == "es" else fen
    return {
        "answer": answer,
        "citations": [],
        "intent": f"social_{category}",
        "lang": lang,
        "followups": followups,
        "mode": "factual",
    }


def greeting_prefix(categories: list, lang: str) -> str:
    """A short, warm opener to prepend to a real answer when the message
    was a greeting/thanks glued onto a substantive question (not purely
    social -- see `analyze()`'s is_purely_social)."""
    if "thanks" in categories:
        return ("¡De nada! " if lang == "es" else "You're welcome! ")
    if "greeting" in categories:
        return ("¡Hola! " if lang == "es" else "Hi! ")
    return ""
