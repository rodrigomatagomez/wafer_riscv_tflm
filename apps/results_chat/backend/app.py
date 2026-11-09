"""Flask backend for the wafer_riscv_tflm results-chat application.

Read-only by design: every route only reads already-saved evidence files
(via evidence.py), derives charts deterministically from them
(chart_engine.py/chart_cache.py), and formats/generates text (qa_engine.py,
chat_pipeline.py, and optionally a local LLM via llm_adapter.py). No route
executes a shell command, writes to the project tree, launches a
simulation, retrains anything, or accepts an arbitrary filesystem path.

Binds to 127.0.0.1 only by default (see run.sh / README.md for the
documented SSH port-forwarding setup to reach it from another machine).
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

import chart_cache
import llm_adapter
from chat_pipeline import handle_message, new_session_state
from evidence import EvidenceError, get_evidence
from qa_engine import SUGGESTED_QUESTIONS_EN, SUGGESTED_QUESTIONS_ES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("results_chat")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(__name__, static_folder=None)

# Ephemeral, in-memory, per-session conversation state (chat history, last
# case/chart discussed), to support natural follow-ups. Never written to
# disk and carries no evidence of its own -- purely conversational
# convenience, bounded in size (see _MAX_SESSIONS / chat_pipeline's
# MAX_HISTORY_MESSAGES).
_SESSION_STATE: dict = {}
_MAX_SESSIONS = 2000


def _session_get(session_id: str) -> dict:
    if session_id not in _SESSION_STATE and len(_SESSION_STATE) >= _MAX_SESSIONS:
        _SESSION_STATE.pop(next(iter(_SESSION_STATE)))
    return _SESSION_STATE.setdefault(session_id, new_session_state())


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def frontend_static(filename):
    # Only ever serves files that already exist under frontend/; Flask's
    # send_from_directory rejects path traversal outside that directory.
    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": time.time()})


@app.route("/api/mode")
def mode():
    cfg = llm_adapter.load_config()
    configured = llm_adapter.is_configured(cfg)
    if cfg.provider == "local":
        note = (
            f"Local LLM is running and reachable at {cfg.api_base} (llama.cpp server). "
            "Open-ended questions and chart requests are grounded in project evidence and phrased "
            "by this local model; see apps/results_chat/llm_runtime/MODEL_PROVENANCE.json for exactly "
            "which model/runtime."
            if configured else
            f"RESULTS_CHAT_LLM_PROVIDER=local but no server answered a health check at {cfg.api_base} -- "
            "is llama-server running? See apps/results_chat/README.md 'Starting the local LLM'. "
            "Falling back to factual-answer mode."
        )
    elif configured:
        note = f"Remote LLM provider '{cfg.provider}' is configured and reachable."
    else:
        note = (
            "No LLM provider is configured or reachable on this server. Running in factual-answer "
            "mode: FAQ-style answers come from a deterministic lookup, and open-ended questions "
            "surface the most relevant documentation excerpts directly, without LLM phrasing. "
            "See apps/results_chat/README.md 'Starting the local LLM' to enable local inference."
        )
    return jsonify({
        "mode": "llm" if configured else "factual",
        "provider": cfg.provider,
        "model": cfg.model if configured else None,
        "configured": configured,
        "note": note,
    })


@app.route("/api/suggested_questions")
def suggested_questions():
    lang = request.args.get("lang", "en")
    qs = SUGGESTED_QUESTIONS_ES if lang == "es" else SUGGESTED_QUESTIONS_EN
    return jsonify({"lang": lang, "questions": qs})


@app.route("/api/dashboard")
def dashboard():
    try:
        ev = get_evidence()
    except EvidenceError as exc:
        log.error("evidence load failed: %s", exc)
        return jsonify({"error": str(exc)}), 503

    cases = [
        {
            "case_id": c.case_id,
            "sample_id": c.sample_id,
            "ground_truth_class": c.ground_truth_class_name,
            "native_predicted_class": c.native_predicted_class,
            "native_scores": c.native_scores,
            "rtl_predicted_class": c.rtl_predicted_class,
            "rtl_scores": c.rtl_scores,
            "rtl_matches_native": c.rtl_matches_native,
            "classifier_correct": c.classifier_correct,
            "has_score_tie": c.has_score_tie,
            "tie_class_names": c.tie_class_names,
            "invoke_elapsed_cycles": c.invoke_elapsed_cycles,
        }
        for c in ev.cases
    ]
    return jsonify({
        "completion": {
            "run_id": ev.run_id.value,
            "checker_exit_code": ev.checker_exit_code.value,
            "checker_verdict": ev.checker_verdict.value,
            "citation": ev.checker_verdict.cite(),
        },
        "rtl_vs_native": {
            "n_cases": ev.n_cases.value,
            "n_matched": ev.n_matched_rtl_native.value,
            "citation": ev.n_matched_rtl_native.cite(),
        },
        "classifier_quality": {
            "test_accuracy": ev.test_accuracy.value,
            "test_macro_f1": ev.test_macro_f1.value,
            "quality_target_macro_f1": ev.quality_target_macro_f1.value,
            "quality_target_met": ev.quality_target_met.value,
            "per_class_f1_test": ev.per_class_f1_test.value,
            "n_correct_on_fixed_cases": ev.n_classifier_correct_on_fixed_cases,
            "n_fixed_cases": len(ev.cases),
            "misclassified_case_ids": ev.misclassified_case_ids,
            "citation": ev.test_macro_f1.cite(),
        },
        "timing": {
            "final_cycle": ev.final_cycle.value,
            "wall_clock_seconds": ev.wall_clock_seconds.value,
            "wall_clock_zenith_reported": ev.wall_clock_zenith_reported.value,
            "citation": ev.final_cycle.cite(),
            "caveat": (
                "Simulation wall-clock time is not physical-chip inference "
                "latency -- it is host-machine discrete-event-simulation "
                "time. The simulated cycle count is the hardware-relevant "
                "figure."
            ),
        },
        "memory": {
            "tensor_arena_reserved_bytes": ev.tensor_arena_reserved_bytes.value,
            "tensor_arena_measured_peak_bytes": ev.tensor_arena_measured_peak_bytes.value,
            "citation": ev.tensor_arena_measured_peak_bytes.cite(),
            "caveat": (
                "The measured peak bytes figure came from the native x86 "
                "reference oracle, not from an independent measurement on "
                "the simulated RV32 firmware."
            ),
        },
        "processor_verification": {
            "directed_tests_pass": ev.cpu_directed_tests_pass.value,
            "random_instruction_mismatches": ev.cpu_random_instruction_mismatches.value,
            "citation": ev.cpu_directed_tests_pass.cite(),
        },
        "provenance": {
            "model_sha256": ev.model_sha256.value,
            "firmware_elf_sha256": ev.firmware_elf_sha256.value,
            "tflm_commit": ev.tflm_commit.value,
            "sim_banner": ev.sim_banner.value,
        },
        "cases": cases,
        "load_warnings": ev.load_warnings,
        "historical_note": (
            "This dashboard reflects the single final run full20_final_001 "
            "only. Earlier historical partial-match evidence (7/20, 8/20) "
            "is preserved separately in "
            "results/rtl_comparison_partial_per_case_runs.json and is not "
            "merged into these numbers."
        ),
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    lang_hint = body.get("lang")
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > 2000:
        return jsonify({"error": "message too long (max 2000 characters)"}), 400

    try:
        ev = get_evidence()
    except EvidenceError as exc:
        log.error("evidence load failed: %s", exc)
        return jsonify({"error": "evidence unavailable: " + str(exc)}), 503

    state = _session_get(session_id)
    result = handle_message(message, ev, lang_hint, state)
    result["session_id"] = session_id
    return jsonify(result)


@app.route("/api/chart/<chart_id>.<ext>")
def chart_file(chart_id: str, ext: str):
    path = chart_cache.path_for(chart_id, ext)
    if path is None:
        return jsonify({"error": "chart not found"}), 404
    mimetype = {"png": "image/png", "svg": "image/svg+xml", "csv": "text/csv"}[ext]
    return send_file(path, mimetype=mimetype, as_attachment=(ext == "csv"),
                      download_name=f"{chart_id}.{ext}" if ext == "csv" else None)


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    host = os.environ.get("RESULTS_CHAT_HOST", "127.0.0.1")
    port = int(os.environ.get("RESULTS_CHAT_PORT", "8787"))
    if host not in ("127.0.0.1", "localhost", "::1"):
        log.warning(
            "RESULTS_CHAT_HOST=%s is not a loopback address -- this app has "
            "no authentication; binding it beyond localhost exposes the "
            "chat endpoint to the network. Proceeding because it was "
            "explicitly requested via the environment.", host,
        )
    log.info("Starting results_chat on %s:%s (llm configured=%s, provider=%s)",
              host, port, llm_adapter.is_configured(), llm_adapter.load_config().provider)
    app.run(host=host, port=port, debug=False)
