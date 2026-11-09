"""Deterministic chart generation from a strictly validated specification.

Security/accuracy design (this is the part of the upgrade the task is
most explicit about getting right):

  - A "chart spec" is a small dict with a `kind` (one of a fixed enum)
    and a few categorical `params` (also fixed enums: which model, which
    split, which case id, normalize true/false, language). There is NO
    field anywhere in this schema for raw plotted numbers.
  - `validate_spec()` rejects anything outside the fixed enums -- an LLM
    (or the regex fallback classifier in chat_router.py) can only ever
    select *which real, already-computed dataset* to plot, never invent
    one. If validation fails, or the selected data genuinely was not
    collected (e.g. physical clock frequency/power/area, or an
    out-of-range case id), `render()` raises ChartDataUnavailable with an
    explicit bilingual explanation -- callers must surface that message,
    never fabricate a chart.
  - All actual numbers come from the `Evidence` snapshot (evidence.py),
    which itself only reads the project's saved result files. No chart
    function performs training, retraining, or simulation of any kind.
  - Rendering uses matplotlib's non-interactive Agg backend (set at
    import time, before pyplot is touched -- see
    https://matplotlib.org/stable/users/explain/figure/backends.html),
    appropriate for a headless server process with no display.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from evidence import Evidence  # noqa: E402

CLASSES = ["Center", "Edge-Ring", "Scratch", "none"]

KINDS = {
    "confusion_matrix", "f1_by_class", "model_comparison", "quant_comparison",
    "invoke_cycles", "case_scores", "classifier_correctness",
    "training_curves", "memory_budget",
}
MODEL_TAGS = {"A", "B"}
METRIC_SETS = {"float", "int8"}
SPLITS = {"val", "test"}
COMPARISON_METRICS = {"accuracy", "macro_f1"}
TRAINING_METRICS = {"loss", "accuracy", "both"}
LANGS = {"en", "es"}


class ChartSpecError(Exception):
    """The requested spec is malformed or outside the supported schema."""


class ChartDataUnavailable(Exception):
    """The spec is well-formed but the requested data does not exist /
    was never collected (e.g. physical measurements, an out-of-range
    case id). Carries a ready-to-display bilingual message."""


@dataclass
class ChartSpec:
    kind: str
    params: dict = field(default_factory=dict)
    lang: str = "en"


@dataclass
class ChartResult:
    fig: object
    data_rows: list  # list of dicts, suitable for csv.DictWriter
    caption: str
    citations: list
    provenance: dict
    title: str


def validate_spec(raw: dict) -> ChartSpec:
    if not isinstance(raw, dict):
        raise ChartSpecError("chart spec must be a JSON object")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ChartSpecError(f"unsupported chart kind: {kind!r} (supported: {sorted(KINDS)})")
    lang = raw.get("lang", "en")
    if lang not in LANGS:
        raise ChartSpecError(f"unsupported lang: {lang!r}")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ChartSpecError("params must be an object")

    clean: dict = {}
    if kind in ("confusion_matrix", "f1_by_class"):
        clean["model_tag"] = _enum(params, "model_tag", MODEL_TAGS, "B")
        clean["metric_set"] = _enum(params, "metric_set", METRIC_SETS, "int8")
        clean["split"] = _enum(params, "split", SPLITS, "test")
        if kind == "confusion_matrix":
            clean["normalize"] = bool(params.get("normalize", False))
    elif kind == "model_comparison":
        clean["metric"] = _enum(params, "metric", COMPARISON_METRICS, "macro_f1")
        clean["metric_set"] = _enum(params, "metric_set", METRIC_SETS, "int8")
        clean["split"] = _enum(params, "split", SPLITS, "test")
    elif kind == "quant_comparison":
        clean["model_tag"] = _enum(params, "model_tag", MODEL_TAGS, "B")
        clean["metric"] = _enum(params, "metric", COMPARISON_METRICS, "macro_f1")
        clean["split"] = _enum(params, "split", SPLITS, "test")
    elif kind == "case_scores":
        cid = params.get("case_id")
        if not isinstance(cid, int):
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                raise ChartSpecError("case_scores requires an integer case_id")
        clean["case_id"] = cid
    elif kind == "training_curves":
        clean["model_tag"] = _enum(params, "model_tag", MODEL_TAGS, "B")
        clean["metric"] = _enum(params, "metric", TRAINING_METRICS, "both")
    # invoke_cycles, classifier_correctness, memory_budget: no params

    return ChartSpec(kind=kind, params=clean, lang=lang)


def _enum(params: dict, key: str, allowed: set, default: str) -> str:
    val = params.get(key, default)
    if val not in allowed:
        raise ChartSpecError(f"{key}={val!r} not in {sorted(allowed)}")
    return val


def _t(lang: str, en: str, es: str) -> str:
    return es if lang == "es" else en


def _new_fig(figsize=(6.4, 4.8)):
    fig, ax = plt.subplots(figsize=figsize, dpi=120)
    return fig, ax


def _metrics_block(ev: Evidence, model_tag: str, metric_set: str, split: str) -> dict:
    try:
        return ev.ml_metrics_raw["results"][model_tag][f"{metric_set}_metrics"][split]
    except KeyError as exc:
        raise ChartDataUnavailable(
            f"No metrics recorded for model {model_tag}, {metric_set}, {split} split."
        ) from exc


def _render_confusion_matrix(spec: ChartSpec, ev: Evidence) -> ChartResult:
    p = spec.params
    block = _metrics_block(ev, p["model_tag"], p["metric_set"], p["split"])
    cm = block["confusion_matrix"]
    n = block["n"]
    cm_to_plot = cm
    if p["normalize"]:
        cm_to_plot = [[(v / sum(row) if sum(row) else 0.0) for v in row] for row in cm]

    fig, ax = _new_fig((6.0, 5.2))
    im = ax.imshow(cm_to_plot, cmap="Blues", vmin=0)
    ax.set_xticks(range(4)); ax.set_xticklabels(CLASSES, rotation=30, ha="right")
    ax.set_yticks(range(4)); ax.set_yticklabels(CLASSES)
    ax.set_xlabel(_t(spec.lang, "Predicted class", "Clase predicha"))
    ax.set_ylabel(_t(spec.lang, "Ground truth class", "Clase real"))
    for i in range(4):
        for j in range(4):
            val = cm_to_plot[i][j]
            text = f"{val:.2f}" if p["normalize"] else str(cm[i][j])
            ax.text(j, i, text, ha="center", va="center",
                     color="white" if val > (0.5 if p["normalize"] else max(max(r) for r in cm) / 2) else "black")
    norm_label = _t(spec.lang, "normalized", "normalizada")
    title = _t(spec.lang,
               f"Confusion matrix -- Model {p['model_tag']} ({p['metric_set']}, {p['split']} split, n={n})"
               + (f" [{norm_label}]" if p["normalize"] else ""),
               f"Matriz de confusión -- Modelo {p['model_tag']} ({p['metric_set']}, split {p['split']}, n={n})"
               + (f" [{norm_label}]" if p["normalize"] else ""))
    ax.set_title(title, fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()

    rows = []
    for i, gt in enumerate(CLASSES):
        row = {"ground_truth": gt}
        for j, pred in enumerate(CLASSES):
            row[f"predicted_{pred}"] = cm[i][j]
        rows.append(row)

    caption = _t(
        spec.lang,
        f"Confusion matrix for model {p['model_tag']} ({p['metric_set']} quantization), {p['split']} split, "
        f"n={n} samples. Rows are ground truth, columns are predicted class. "
        f"{'Values are row-normalized fractions.' if p['normalize'] else 'Values are raw sample counts.'} "
        "This is the classifier's own quality on the full held-out split, not the 20-case RTL-vs-native "
        "comparison (which is a different, exact-match claim -- see results/rtl_comparison.json).",
        f"Matriz de confusión del modelo {p['model_tag']} (cuantización {p['metric_set']}), split {p['split']}, "
        f"n={n} muestras. Las filas son la clase real y las columnas la clase predicha. "
        f"{'Los valores son fracciones normalizadas por fila.' if p['normalize'] else 'Los valores son conteos de muestras.'} "
        "Esta es la calidad propia del clasificador en todo el split, no la comparación RTL-contra-nativo de "
        "20 casos (que es una afirmación distinta de coincidencia exacta -- ver results/rtl_comparison.json).",
    )
    citations = [f"results/ml_metrics.json (results.{p['model_tag']}.{p['metric_set']}_metrics.{p['split']}.confusion_matrix)"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "confusion_matrix", **p, "n": n}, title=title)


def _render_f1_by_class(spec: ChartSpec, ev: Evidence) -> ChartResult:
    p = spec.params
    block = _metrics_block(ev, p["model_tag"], p["metric_set"], p["split"])
    f1s = block["per_class_f1"]
    values = [f1s[c] for c in CLASSES]

    target = ev.quality_target_macro_f1.value
    fig, ax = _new_fig()
    bars = ax.bar(CLASSES, values, color="#4a90d9")
    ax.axhline(target, color="#d94a4a", linestyle="--", linewidth=1.3,
               label=_t(spec.lang, f"0.85 target (macro-F1)", f"objetivo 0.85 (macro-F1)"))
    # Headroom above 1.0 so a near-1.0 bar's data label (placed at v+0.02)
    # never collides with the title -- a real clipping bug found by
    # visually inspecting a rendered figure (Edge-Ring's 0.990 label
    # overlapped the title text when ylim topped out at exactly 1.0).
    ax.set_ylim(0, 1.13)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_ylabel("F1")
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.3f}", ha="center", fontsize=9)
    ax.legend(loc="lower right", fontsize=8)
    met = block["macro_f1"] >= target
    title_line1 = _t(spec.lang,
                      f"F1 by class -- Model {p['model_tag']} ({p['metric_set']}, {p['split']} split)",
                      f"F1 por clase -- Modelo {p['model_tag']} ({p['metric_set']}, split {p['split']})")
    title_line2 = _t(spec.lang,
                      f"macro-F1={block['macro_f1']:.5f} ({'meets' if met else 'below'} 0.85 target)",
                      f"macro-F1={block['macro_f1']:.5f} ({'cumple' if met else 'por debajo del'} objetivo 0.85)")
    ax.set_title(f"{title_line1}\n{title_line2}", fontsize=9.5)
    title = f"{title_line1} -- {title_line2}"
    fig.tight_layout()

    rows = [{"class": c, "f1": f1s[c], "target_macro_f1": target} for c in CLASSES]
    caption = _t(
        spec.lang,
        f"Per-class F1 for model {p['model_tag']} ({p['metric_set']}), {p['split']} split "
        f"(macro-F1 = {block['macro_f1']:.5f}). The dashed line marks the project's original "
        f"quality target (macro-F1 >= {target}), which was {'met' if met else 'NOT met'} on this split.",
        f"F1 por clase para el modelo {p['model_tag']} ({p['metric_set']}), split {p['split']} "
        f"(macro-F1 = {block['macro_f1']:.5f}). La línea punteada marca el objetivo de calidad "
        f"original del proyecto (macro-F1 >= {target}), que {'se cumplió' if met else 'NO se cumplió'} "
        f"en este split.",
    )
    citations = [f"results/ml_metrics.json (results.{p['model_tag']}.{p['metric_set']}_metrics.{p['split']}.per_class_f1)",
                 "results/ml_metrics.json (quality_target_macro_f1)"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "f1_by_class", **p, "quality_target_macro_f1": target}, title=title)


def _render_model_comparison(spec: ChartSpec, ev: Evidence) -> ChartResult:
    p = spec.params
    vals = {}
    for tag in ("A", "B"):
        block = _metrics_block(ev, tag, p["metric_set"], p["split"])
        vals[tag] = block[p["metric"]]

    fig, ax = _new_fig((5.2, 4.4))
    bars = ax.bar(["A", "B"], [vals["A"], vals["B"]], color=["#9fb8d9", "#4a90d9"])
    ax.set_ylim(0, 1.0)
    metric_label = _t(spec.lang, "Macro-F1" if p["metric"] == "macro_f1" else "Accuracy",
                       "Macro-F1" if p["metric"] == "macro_f1" else "Exactitud")
    ax.set_ylabel(metric_label)
    for b, tag in zip(bars, ("A", "B")):
        ax.text(b.get_x() + b.get_width() / 2, vals[tag] + 0.02, f"{vals[tag]:.4f}", ha="center", fontsize=9)
    chosen = ev.ml_metrics_raw.get("chosen_configuration")
    title = _t(spec.lang,
               f"Model A vs B -- {metric_label} ({p['metric_set']}, {p['split']} split)",
               f"Modelo A vs B -- {metric_label} ({p['metric_set']}, split {p['split']})")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()

    rows = [{"model": tag, "metric": p["metric"], "value": vals[tag]} for tag in ("A", "B")]
    caption = _t(
        spec.lang,
        f"Model A (hidden=16) vs Model B (hidden=32), {metric_label} on the {p['split']} split "
        f"({p['metric_set']} quantization). Model {chosen} was the one selected and carried forward "
        f"(selection rule: {ev.ml_metrics_raw.get('selection_rule')}).",
        f"Modelo A (hidden=16) vs Modelo B (hidden=32), {metric_label} en el split {p['split']} "
        f"(cuantización {p['metric_set']}). El modelo {chosen} fue el seleccionado y usado en el resto "
        f"del proyecto (regla de selección: {ev.ml_metrics_raw.get('selection_rule')}).",
    )
    citations = [f"results/ml_metrics.json (results.A/B.{p['metric_set']}_metrics.{p['split']}.{p['metric']})",
                 "results/ml_metrics.json (chosen_configuration, selection_rule)"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "model_comparison", **p}, title=title)


def _render_quant_comparison(spec: ChartSpec, ev: Evidence) -> ChartResult:
    p = spec.params
    vals = {}
    for ms in ("float", "int8"):
        block = _metrics_block(ev, p["model_tag"], ms, p["split"])
        vals[ms] = block[p["metric"]]

    fig, ax = _new_fig((5.2, 4.4))
    bars = ax.bar(["float", "int8"], [vals["float"], vals["int8"]], color=["#d9a24a", "#4ad99a"])
    ax.set_ylim(0, 1.0)
    metric_label = _t(spec.lang, "Macro-F1" if p["metric"] == "macro_f1" else "Accuracy",
                       "Macro-F1" if p["metric"] == "macro_f1" else "Exactitud")
    ax.set_ylabel(metric_label)
    for b, ms in zip(bars, ("float", "int8")):
        ax.text(b.get_x() + b.get_width() / 2, vals[ms] + 0.02, f"{vals[ms]:.4f}", ha="center", fontsize=9)
    title = _t(spec.lang,
               f"Float vs int8 -- Model {p['model_tag']}, {metric_label} ({p['split']} split)",
               f"Flotante vs int8 -- Modelo {p['model_tag']}, {metric_label} (split {p['split']})")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()

    rows = [{"metric_set": ms, "metric": p["metric"], "value": vals[ms]} for ms in ("float", "int8")]
    caption = _t(
        spec.lang,
        f"Model {p['model_tag']}: float-checkpoint vs. int8-quantized {metric_label} on the {p['split']} split. "
        f"Quantization cost: {vals['float'] - vals['int8']:+.5f}.",
        f"Modelo {p['model_tag']}: {metric_label} de punto flotante vs. cuantizado int8 en el split {p['split']}. "
        f"Costo de cuantización: {vals['float'] - vals['int8']:+.5f}.",
    )
    citations = [f"results/ml_metrics.json (results.{p['model_tag']}.float_metrics.{p['split']}.{p['metric']})",
                 f"results/ml_metrics.json (results.{p['model_tag']}.int8_metrics.{p['split']}.{p['metric']})"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "quant_comparison", **p}, title=title)


def _render_invoke_cycles(spec: ChartSpec, ev: Evidence) -> ChartResult:
    cases = sorted(ev.cases, key=lambda c: c.case_id)
    xs = [c.case_id for c in cases]
    ys = [c.invoke_elapsed_cycles for c in cases]

    fig, ax = _new_fig((7.5, 4.2))
    ax.bar(xs, ys, color="#4a90d9")
    ax.set_xlabel(_t(spec.lang, "Case ID", "ID del caso"))
    ax.set_ylabel(_t(spec.lang, "Invoke() cycles (simulated)", "Ciclos de Invoke() (simulados)"))
    ax.set_xticks(xs)
    title = _t(spec.lang, "Invoke() cycles per case -- run full20_final_001",
               "Ciclos de Invoke() por caso -- ejecución full20_final_001")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()

    rows = [{"case_id": c.case_id, "invoke_elapsed_cycles": c.invoke_elapsed_cycles} for c in cases]
    caption = _t(
        spec.lang,
        "Simulated RTL clock cycles spent inside each case's Invoke() call, from the accepted final run. "
        "These are simulated hardware cycles (discrete-event simulation), not a physical-chip wall-clock "
        "latency measurement -- no synthesis or physical implementation was performed.",
        "Ciclos de reloj RTL simulados dentro de la llamada Invoke() de cada caso, de la ejecución final "
        "aceptada. Son ciclos de hardware simulados (simulación de eventos discretos), no una medición de "
        "latencia de reloj de un chip físico -- no se realizó síntesis ni implementación física.",
    )
    citations = ["results/final_run_evidence/full20_final_001_check_report.json (cases_parsed[*].invoke_elapsed_cycles)"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "invoke_cycles"}, title=title)


def _render_case_scores(spec: ChartSpec, ev: Evidence) -> ChartResult:
    cid = spec.params["case_id"]
    c = ev.case(cid)
    if c is None or not (0 <= cid <= 19):
        raise ChartDataUnavailable(
            f"Case {cid} does not exist in this 20-case experiment (valid IDs: 0-19)."
            if spec.lang == "en" else
            f"El caso {cid} no existe en este experimento de 20 casos (IDs válidos: 0-19)."
        )

    fig, ax = _new_fig((5.6, 4.4))
    x = range(4)
    width = 0.35
    ax.bar([i - width / 2 for i in x], c.native_scores, width, label=_t(spec.lang, "Native", "Nativo"), color="#9fb8d9")
    ax.bar([i + width / 2 for i in x], c.rtl_scores, width, label=_t(spec.lang, "RTL", "RTL"), color="#4a90d9")
    ax.set_xticks(list(x)); ax.set_xticklabels(CLASSES, rotation=20, ha="right")
    ax.set_ylabel(_t(spec.lang, "Quantized score (raw int8 logit)", "Puntuación cuantizada (logit int8 bruto)"))
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.legend(fontsize=8)
    correct = c.classifier_correct
    title = _t(spec.lang,
               f"Case {cid}: quantized scores (predicted: {CLASSES[c.rtl_predicted_class]}, "
               f"true: {c.ground_truth_class_name}, {'correct' if correct else 'MISCLASSIFIED'})",
               f"Caso {cid}: puntuaciones cuantizadas (predicho: {CLASSES[c.rtl_predicted_class]}, "
               f"real: {c.ground_truth_class_name}, {'correcto' if correct else 'MAL CLASIFICADO'})")
    ax.set_title(title, fontsize=9.5)
    fig.tight_layout()

    rows = [{"class": CLASSES[i], "native_score": c.native_scores[i], "rtl_score": c.rtl_scores[i]} for i in range(4)]
    tie_note = ""
    if c.has_score_tie:
        tie_note = _t(spec.lang,
                       f" Note: {', '.join(c.tie_class_names)} are tied for the maximum score.",
                       f" Nota: {', '.join(c.tie_class_names)} empatan en la puntuación máxima.")
    caption = _t(
        spec.lang,
        f"Four quantized class scores for case {cid} (sample_id {c.sample_id}). Scores are raw int8 model "
        f"logits, not probabilities. Ground truth: {c.ground_truth_class_name}. Predicted (both RTL and "
        f"native, which match exactly): {CLASSES[c.rtl_predicted_class]} -- "
        f"{'a correct prediction' if correct else 'a MISCLASSIFICATION relative to ground truth'}."
        + tie_note,
        f"Las cuatro puntuaciones cuantizadas por clase para el caso {cid} (sample_id {c.sample_id}). Son "
        f"logits int8 crudos del modelo, no probabilidades. Clase real: {c.ground_truth_class_name}. "
        f"Predicción (RTL y nativo coinciden exactamente): {CLASSES[c.rtl_predicted_class]} -- "
        f"{'una predicción correcta' if correct else 'una CLASIFICACIÓN ERRÓNEA respecto a la clase real'}."
        + tie_note,
    )
    citations = [c.log_citation(), "results/comparison_manifest.json (cases[*].class_idx)"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "case_scores", "case_id": cid}, title=title)


def _render_classifier_correctness(spec: ChartSpec, ev: Evidence) -> ChartResult:
    n_correct = ev.n_classifier_correct_on_fixed_cases
    n_total = len(ev.cases)
    n_wrong = n_total - n_correct

    fig, ax = _new_fig((4.6, 4.4))
    labels = [_t(spec.lang, "Correct", "Correcto"), _t(spec.lang, "Incorrect", "Incorrecto")]
    ax.bar(labels, [n_correct, n_wrong], color=["#4ad98a", "#d94a4a"])
    ax.set_ylabel(_t(spec.lang, "Number of cases (of 20)", "Número de casos (de 20)"))
    for i, v in enumerate([n_correct, n_wrong]):
        ax.text(i, v + 0.2, str(v), ha="center")
    title = _t(spec.lang, "Classifier correct vs. incorrect (20 fixed cases)",
               "Clasificador correcto vs. incorrecto (20 casos fijos)")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()

    rows = [{"outcome": "correct", "count": n_correct}, {"outcome": "incorrect", "count": n_wrong}]
    caption = _t(
        spec.lang,
        f"Of the 20 fixed comparison cases, the classifier's own prediction matches the ground-truth "
        f"label in {n_correct} and misses it in {n_wrong} (case_id {', '.join(str(i) for i in ev.misclassified_case_ids)}). "
        f"This is SEPARATE from RTL-vs-native agreement, which is 20/20 (the RTL hardware reproduces the "
        f"model's output exactly, including these {n_wrong} mistakes) -- see results/rtl_comparison.json.",
        f"De los 20 casos fijos de comparación, la predicción del propio clasificador coincide con la "
        f"etiqueta real en {n_correct} y falla en {n_wrong} (case_id {', '.join(str(i) for i in ev.misclassified_case_ids)}). "
        f"Esto es DISTINTO de la concordancia RTL-contra-nativo, que es 20/20 (el hardware RTL reproduce "
        f"exactamente la salida del modelo, incluyendo estos {n_wrong} errores) -- ver results/rtl_comparison.json.",
    )
    citations = ["results/final_run_evidence/full20_final_001_check_report.json (rows[*])",
                 "results/comparison_manifest.json (cases[*].class_idx)"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "classifier_correctness"}, title=title)


def _render_training_curves(spec: ChartSpec, ev: Evidence) -> ChartResult:
    p = spec.params
    tag = p["model_tag"]
    hist = ev.training_history.get(tag)
    if not hist:
        raise ChartDataUnavailable(
            f"No training history is stored for model {tag}."
            if spec.lang == "en" else
            f"No hay historial de entrenamiento guardado para el modelo {tag}."
        )
    epochs = list(range(1, len(hist["loss"]) + 1))

    if p["metric"] == "both":
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.2), dpi=120)
        ax1.plot(epochs, hist["loss"], label=_t(spec.lang, "train", "entren."), color="#4a90d9")
        ax1.plot(epochs, hist["val_loss"], label=_t(spec.lang, "validation", "validación"), color="#d94a4a")
        ax1.set_title("Loss"); ax1.set_xlabel(_t(spec.lang, "Epoch", "Época")); ax1.legend(fontsize=8)
        ax2.plot(epochs, hist["accuracy"], label=_t(spec.lang, "train", "entren."), color="#4a90d9")
        ax2.plot(epochs, hist["val_accuracy"], label=_t(spec.lang, "validation", "validación"), color="#d94a4a")
        ax2.set_title(_t(spec.lang, "Accuracy", "Exactitud")); ax2.set_xlabel(_t(spec.lang, "Epoch", "Época")); ax2.legend(fontsize=8)
        rows = [{"epoch": e, "loss": hist["loss"][i], "val_loss": hist["val_loss"][i],
                 "accuracy": hist["accuracy"][i], "val_accuracy": hist["val_accuracy"][i]}
                for i, e in enumerate(epochs)]
    else:
        fig, ax = _new_fig((6.4, 4.4))
        key, vkey = p["metric"], f"val_{p['metric']}"
        ax.plot(epochs, hist[key], label=_t(spec.lang, "train", "entren."), color="#4a90d9")
        ax.plot(epochs, hist[vkey], label=_t(spec.lang, "validation", "validación"), color="#d94a4a")
        ax.set_xlabel(_t(spec.lang, "Epoch", "Época")); ax.set_ylabel(p["metric"]); ax.legend(fontsize=8)
        rows = [{"epoch": e, p["metric"]: hist[key][i], vkey: hist[vkey][i]} for i, e in enumerate(epochs)]

    title = _t(spec.lang, f"Training curves -- Model {tag} ({len(epochs)} epochs)",
               f"Curvas de entrenamiento -- Modelo {tag} ({len(epochs)} épocas)")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()

    caption = _t(
        spec.lang,
        f"Stored training/validation curves for model {tag}, {len(epochs)} epochs, from the single "
        f"recorded training run (float checkpoint, before int8 quantization).",
        f"Curvas de entrenamiento/validación guardadas para el modelo {tag}, {len(epochs)} épocas, de la "
        f"única ejecución de entrenamiento registrada (checkpoint flotante, antes de la cuantización int8).",
    )
    citations = [f"results/training_history_{tag}.json"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "training_curves", **p}, title=title)


def _render_memory_budget(spec: ChartSpec, ev: Evidence) -> ChartResult:
    mem = ev.memory_usage_raw
    arena_reserved = mem["tensor_arena"]["reserved_capacity_bytes"]
    arena_measured = mem["tensor_arena"]["measured_peak_use_bytes_native_reference"]
    fw = mem["firmware_size_breakdown_bytes"]["total_text_data_bss"]
    stack = mem["reserved_stack_bytes"]
    headroom = mem["memory_budget_check"]["headroom_bytes"]
    ram_total = mem["ram_region"]["size_bytes"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.4), dpi=120)
    labels1 = [_t(spec.lang, "Reserved", "Reservado"), _t(spec.lang, "Measured peak\n(native ref.)", "Pico medido\n(ref. nativa)")]
    ax1.bar(labels1, [arena_reserved, arena_measured], color=["#d9a24a", "#4ad99a"])
    for i, v in enumerate([arena_reserved, arena_measured]):
        ax1.text(i, v + 50, str(v), ha="center", fontsize=9)
    ax1.set_ylabel(_t(spec.lang, "Bytes", "Bytes"))
    ax1.set_title(_t(spec.lang, "Tensor arena", "Tensor arena"), fontsize=10)

    labels2 = [_t(spec.lang, "Firmware\n(text+data+bss)", "Firmware\n(text+data+bss)"),
               _t(spec.lang, "Reserved\nstack", "Pila\nreservada"),
               _t(spec.lang, "Headroom", "Margen")]
    ax2.bar(labels2, [fw, stack, headroom], color=["#4a90d9", "#9fb8d9", "#cccccc"])
    for i, v in enumerate([fw, stack, headroom]):
        ax2.text(i, v + 5000, str(v), ha="center", fontsize=8)
    ax2.set_ylabel(_t(spec.lang, "Bytes", "Bytes"))
    ax2.set_title(_t(spec.lang, f"1 MiB RAM budget ({ram_total} bytes)", f"Presupuesto de RAM de 1 MiB ({ram_total} bytes)"), fontsize=10)

    title = _t(spec.lang, "Memory budget: reservation vs. measurement", "Presupuesto de memoria: reserva vs. medición")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()

    rows = [
        {"quantity": "tensor_arena_reserved_bytes", "value": arena_reserved},
        {"quantity": "tensor_arena_measured_peak_bytes_native_reference", "value": arena_measured},
        {"quantity": "firmware_text_data_bss_bytes", "value": fw},
        {"quantity": "reserved_stack_bytes", "value": stack},
        {"quantity": "headroom_bytes", "value": headroom},
        {"quantity": "ram_region_total_bytes", "value": ram_total},
    ]
    caption = _t(
        spec.lang,
        "Memory reservation (static, by construction) vs. measurement (what was actually observed in use). "
        "The tensor-arena PEAK figure (5216 bytes) was measured on the native x86 reference oracle, not by "
        "an independent instrumentation of the RV32 firmware -- the firmware uses the identical model/"
        "resolver/arena-size configuration, making this a reliable proxy, not an RV32-measured fact.",
        "Reserva de memoria (estática, por diseño) vs. medición (lo observado realmente en uso). La cifra "
        "PICO del tensor arena (5216 bytes) se midió en el oráculo de referencia nativo x86, no mediante "
        "instrumentación independiente del firmware RV32 -- el firmware usa la misma configuración de "
        "modelo/resolutor/tamaño de arena, por lo que es una referencia confiable, no un hecho medido en RV32.",
    )
    citations = ["results/memory_usage.json (tensor_arena, firmware_size_breakdown_bytes, memory_budget_check)"]
    return ChartResult(fig=fig, data_rows=rows, caption=caption, citations=citations,
                        provenance={"kind": "memory_budget"}, title=title)


_RENDERERS = {
    "confusion_matrix": _render_confusion_matrix,
    "f1_by_class": _render_f1_by_class,
    "model_comparison": _render_model_comparison,
    "quant_comparison": _render_quant_comparison,
    "invoke_cycles": _render_invoke_cycles,
    "case_scores": _render_case_scores,
    "classifier_correctness": _render_classifier_correctness,
    "training_curves": _render_training_curves,
    "memory_budget": _render_memory_budget,
}


def render(spec: ChartSpec, ev: Evidence) -> ChartResult:
    fn = _RENDERERS.get(spec.kind)
    if fn is None:
        raise ChartSpecError(f"no renderer for kind {spec.kind!r}")
    return fn(spec, ev)


def spec_fingerprint(spec: ChartSpec) -> str:
    payload = json.dumps({"kind": spec.kind, "params": spec.params, "lang": spec.lang}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def rows_to_csv(rows: list) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
