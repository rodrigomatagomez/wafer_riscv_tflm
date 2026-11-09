"""Lightweight, dependency-free retrieval over the project's documentation,
for grounding open-ended chat answers (RAG).

Design choices, explained because they look unusual at a glance:

- Pure-Python TF-IDF + cosine similarity, no numpy/sklearn/faiss and no
  embedding model. The corpus is small (a handful of markdown files,
  roughly 60-100 chunks after splitting on headers) -- a sparse
  dictionary-based vector is fast enough and keeps this module's only
  dependency on the standard library, consistent with the "start
  conservatively, don't add heavy downloads" instruction.
- Chunking is by markdown `##`/`###` headers. This corpus is already
  well-organized into sections; splitting there (rather than by a fixed
  character window) keeps each chunk's citation meaningful ("docs/decisions.md
  D-006", not "docs/decisions.md chars 4000-5500").
- A small bilingual keyword-expansion table bridges Spanish queries
  against this English-only documentation corpus: retrieval always scores
  against an English-biased expanded query, so a Spanish question like
  "¿qué protocolo de entrenamiento se usó?" still matches the English
  "training protocol" chunk. The LLM (if configured) is responsible for
  producing the final Spanish *prose*; this module only needs to find the
  right English source material.
"""
from __future__ import annotations

import csv
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "to", "for", "and", "or", "but", "not", "no",
    "this", "that", "these", "those", "it", "its", "as", "by", "with",
    "from", "than", "then", "so", "do", "does", "did", "has", "have",
    "had", "can", "could", "would", "should", "will", "shall", "what",
    "which", "who", "whom", "how", "why", "when", "where", "about",
    "you", "your", "yours", "me", "my", "mine", "we", "us", "our", "ours",
    "i", "please", "tell", "explain",
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "en", "y", "o", "pero", "no", "es", "son", "fue", "fueron", "ser",
    "este", "esta", "esto", "estos", "estas", "que", "como", "por", "para",
    "con", "se", "su", "sus", "tu", "tus", "mi", "mis", "nosotros",
    "puedes", "puede", "podrias", "podria", "hay", "tambien",
}


def fold_accents(text: str) -> str:
    """Strip accents/diacritics (é->e, ñ->n, etc.) so stopword/bridge
    lookups don't depend on whether the input happened to use accented
    characters -- a real gap found during testing: the bridge table's
    keys are unaccented ("verificacion"), but raw Spanish tokens kept
    their accents ("verificación") and so never matched it."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))

# Spanish -> English technical-term bridge. Not a general translator --
# just enough domain vocabulary that Spanish questions retrieve the right
# (English) documentation chunks. Extend this list rather than replacing
# the retrieval approach if cross-lingual recall is found lacking later.
_ES_EN_BRIDGE = {
    "clasificador": "classifier", "clasificacion": "classification",
    "arquitectura": "architecture", "entrenamiento": "training",
    "entrenar": "training", "memoria": "memory", "verificacion": "verification",
    "verificar": "verify", "conjunto": "dataset", "datos": "data",
    "preprocesamiento": "preprocessing", "limitaciones": "limitations",
    "decision": "decision", "decisiones": "decisions", "modelo": "model",
    "precision": "accuracy", "exactitud": "accuracy", "matriz": "matrix",
    "confusion": "confusion", "procesador": "processor", "firmware": "firmware",
    "simulacion": "simulation", "simulador": "simulator", "ciclos": "cycles",
    "tiempo": "time", "casos": "cases", "caso": "case", "cuantizado": "quantized",
    "cuantizacion": "quantization", "flotante": "float", "nativo": "native",
    "evidencia": "evidence", "resultado": "result", "resultados": "results",
    "calidad": "quality", "objetivo": "target", "meta": "target",
    "procesamiento": "preprocessing", "diseno": "design", "pila": "stack",
    "arena": "arena", "tensor": "tensor", "pesos": "weights",
    "cuadricula": "wafer", "oblea": "wafer", "mapa": "map",
    "defecto": "defect", "clase": "class", "clases": "classes",
    "comparacion": "comparison", "comparar": "compare", "grafica": "chart",
    "grafico": "chart", "curva": "curve", "curvas": "curve",
    "metodologia": "methodology", "metodo": "method", "protocolo": "protocol",
    "limitacion": "limitation", "fallo": "failure", "error": "error",
    "frecuencia": "frequency", "potencia": "power", "fisico": "physical",
    "chip": "chip", "silicio": "silicon", "latencia": "latency",
    "velocidad": "speed", "almacenamiento": "memory", "etiqueta": "label",
    "etiquetas": "labels", "verdadera": "ground truth", "real": "ground truth",
    "siguiente": "next", "futuro": "future", "proximo": "next",
    "proyecto": "project", "ayuda": "help", "ayudar": "help",
    "funciona": "works", "funciono": "worked", "hace": "does",
    "trata": "about", "cuentame": "tell", "explicame": "explain",
    "explicarme": "explain", "explicar": "explain", "muestrame": "show",
    "ensename": "show", "dime": "tell",
    "oraculo": "oracle", "compara": "compare", "comparo": "compared",
    "comparado": "compared", "comparada": "compared", "igual": "match",
    "iguales": "match", "coincidio": "matched", "coincidieron": "matched",
}

_TOKEN_RE = re.compile(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9_./-]+")


def tokenize(text: str) -> list:
    tokens = [fold_accents(t.lower()) for t in _TOKEN_RE.findall(text)]
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def expand_query_tokens(tokens: list) -> list:
    expanded = list(tokens)
    for t in tokens:
        bridged = _ES_EN_BRIDGE.get(t)
        if bridged:
            expanded.extend(bridged.split())
    return expanded


@dataclass
class Chunk:
    chunk_id: str
    source_file: str
    section_title: str
    text: str


class KnowledgeBase:
    def __init__(self, chunks: list):
        self.chunks = chunks
        self._df: dict = {}
        self._chunk_tf: list = []
        for c in chunks:
            tf = {}
            for tok in tokenize(c.text):
                tf[tok] = tf.get(tok, 0) + 1
            self._chunk_tf.append(tf)
            for tok in tf:
                self._df[tok] = self._df.get(tok, 0) + 1
        n = max(len(chunks), 1)
        self._idf = {tok: math.log(1 + n / df) for tok, df in self._df.items()}
        self._chunk_vec = []
        for tf in self._chunk_tf:
            vec = {tok: cnt * self._idf.get(tok, 0.0) for tok, cnt in tf.items()}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self._chunk_vec.append((vec, norm))

    def retrieve(self, query: str, k: int = 4, min_score: float = 0.05,
                 min_overlap_terms: int = 2, high_confidence_score: float = 0.25) -> list:
        """A hit is accepted if score >= min_score AND (it shares at least
        min_overlap_terms distinct tokens with the query, OR its score
        alone clears high_confidence_score). The overlap-count requirement
        exists because short chunks + short queries can produce a
        deceptively high cosine score from a single incidentally-shared
        common word (e.g. a 15-word chunk sharing just "place" with an
        unrelated query) -- found via a real false-positive during testing
        (an off-topic "recommend a pizza place" query matching a chunk on
        the word "place" alone, scoring above a flat threshold)."""
        q_tokens = expand_query_tokens(tokenize(query))
        if not q_tokens:
            return []
        q_token_set = set(q_tokens)
        qtf: dict = {}
        for tok in q_tokens:
            qtf[tok] = qtf.get(tok, 0) + 1
        qvec = {tok: cnt * self._idf.get(tok, 0.0) for tok, cnt in qtf.items()}
        qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0

        scored = []
        for chunk, tf, (cvec, cnorm) in zip(self.chunks, self._chunk_tf, self._chunk_vec):
            dot = sum(qvec.get(tok, 0.0) * cvec.get(tok, 0.0) for tok in qvec)
            score = dot / (qnorm * cnorm)
            if score < min_score:
                continue
            overlap = len(q_token_set & set(tf.keys()))
            if overlap < min(min_overlap_terms, len(q_token_set)) and score < high_confidence_score:
                continue
            scored.append((score, chunk))
        scored.sort(key=lambda sc: sc[0], reverse=True)
        return scored[:k]

    def by_id(self, chunk_id: str) -> Optional[Chunk]:
        for c in self.chunks:
            if c.chunk_id == chunk_id:
                return c
        return None


_HEADER_RE = re.compile(r"^(#{1,3})\s+(.*)$")


def chunk_markdown(path: Path, source_label: str, max_chars: int = 2200) -> list:
    """Split a markdown file into chunks at ## / ### headers. A long
    section is further split on paragraph boundaries so no single chunk
    is wildly larger than the others (keeps retrieval and citations at a
    roughly consistent granularity)."""
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    sections = []  # (title, body_lines)
    current_title = "(intro)"
    current_lines: list = []
    for line in lines:
        m = _HEADER_RE.match(line)
        if m and len(m.group(1)) <= 3:
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = m.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, current_lines))

    chunks = []
    for idx, (title, body_lines) in enumerate(sections):
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        if len(body) <= max_chars:
            parts = [body]
        else:
            paras = re.split(r"\n\s*\n", body)
            parts, cur = [], ""
            for p in paras:
                if len(cur) + len(p) > max_chars and cur:
                    parts.append(cur)
                    cur = p
                else:
                    cur = (cur + "\n\n" + p) if cur else p
            if cur:
                parts.append(cur)
        for pi, part in enumerate(parts):
            suffix = f"#{pi}" if len(parts) > 1 else ""
            chunk_id = f"{source_label}::{idx}{suffix}"
            chunks.append(Chunk(chunk_id=chunk_id, source_file=source_label,
                                 section_title=title, text=f"{title}\n{part}"))
    return chunks


def chunk_claims_csv(path: Path, source_label: str) -> list:
    """Each claims_evidence.csv row becomes its own chunk, carrying its
    status label (verified/measured/implemented/failed/not_tested)
    explicitly in the text -- this is the project's most precise source
    for distinguishing a measured fact from a general explanation."""
    chunks = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            claim_id = row.get("claim_id", "?")
            text = (
                f"Claim {claim_id} [status: {row.get('status', '?')}]: {row.get('claim_text', '')}\n"
                f"Evidence: {row.get('evidence_path', '')} ({row.get('evidence_locator', '')})\n"
                f"Limitations: {row.get('limitations', '')}"
            )
            chunks.append(Chunk(chunk_id=f"{source_label}::{claim_id}", source_file=source_label,
                                 section_title=f"Claim {claim_id} ({row.get('status', '?')})", text=text))
    return chunks


def build_default_knowledge_base(project_root: Path) -> KnowledgeBase:
    app_root = Path(__file__).resolve().parent
    sources = [
        (app_root / "knowledge" / "project_overview.md", "apps/results_chat/backend/knowledge/project_overview.md"),
        (project_root / "README.md", "README.md"),
        (project_root / "docs" / "decisions.md", "docs/decisions.md"),
        (project_root / "docs" / "handoff" / "README.md", "docs/handoff/README.md"),
        (project_root / "docs" / "handoff" / "limitations_and_open_questions.md", "docs/handoff/limitations_and_open_questions.md"),
        (project_root / "docs" / "findings.md", "docs/findings.md"),
        (project_root / "results" / "status_summary.md", "results/status_summary.md"),
    ]
    all_chunks = []
    for path, label in sources:
        if path.is_file():
            all_chunks.extend(chunk_markdown(path, label))

    claims_path = project_root / "docs" / "handoff" / "claims_evidence.csv"
    if claims_path.is_file():
        all_chunks.extend(chunk_claims_csv(claims_path, "docs/handoff/claims_evidence.csv"))

    return KnowledgeBase(all_chunks)


_CACHED_KB: Optional[KnowledgeBase] = None


def get_knowledge_base(project_root: Path, refresh: bool = False) -> KnowledgeBase:
    global _CACHED_KB
    if _CACHED_KB is None or refresh:
        _CACHED_KB = build_default_knowledge_base(project_root)
    return _CACHED_KB
