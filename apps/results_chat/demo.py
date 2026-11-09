#!/usr/bin/env python3
"""Short demonstration script for the results_chat application.

Walks through the exact kind of exchange a congress-demo audience would
see: completion status, RTL-vs-native agreement, classifier quality, a
specific misclassified case, the case-16 tie, timing, memory, an
unsupported physical-measurement question, open-ended questions (English
and Spanish, with a follow-up), chart requests (confusion matrix, F1 by
class, A/B comparison, case scores, with a normalize follow-up, a
language-switch follow-up, and a download follow-up), and actual file
downloads. Prints each question/answer/citation/mode/chart so it can be
read directly as a transcript, and exits non-zero if the server is
unreachable or any expected behavior is missing.

This script only sends HTTP GET/POST requests to the already-running
server; it does not import or execute any backend code directly, so it
also doubles as an external, black-box check that the real HTTP API
behaves as documented -- including, when a local LLM is actually running,
genuine live inference (not a mock).

Usage:
    ./run.sh &                      # start llama-server + Flask first
    venv/bin/python3 demo.py        # then run this script
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:" + os.environ.get("RESULTS_CHAT_PORT", "8787")

SOCIAL_SCRIPT = [
    ("hi", None),
    ("hola", None),
    ("gracias", None),
    ("¿qué puedes hacer?", None),
    ("Hola, ¿puedes explicarme qué hace este proyecto?", None),
]

FAQ_SCRIPT = [
    ("Is this experiment functionally complete?", None),
    ("Do all 20 RTL results match the native reference?", None),
    ("What is the classifier's accuracy and macro-F1?", None),
    ("Which cases did the classifier misclassify?", None),
    ("What about case 16?", None),
    ("What's the tie in case 16?", None),
    ("What was the chip's physical clock frequency and power consumption?", None),
    ("Where does this chat assistant run?", None),
]

OPEN_ENDED_SCRIPT = [
    ("Can you explain the overall architecture of this project?", "en"),
    ("And what about the verification methodology specifically?", "en"),
    ("¿Por qué no se alcanzó el objetivo de calidad de 0.85?", "es"),
]

CHART_SCRIPT = [
    ("Plot the confusion matrix, normalized.", "en"),
    ("Graph F1 by class.", "en"),
    ("Now compare A and B.", "en"),
    ("Enséñame los scores del caso 16.", "es"),
    ("Pon esa gráfica en español.", "es"),
    ("Déjame descargarla.", "es"),
]


def post(path, payload, timeout=60):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"content-type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()), time.time() - t0


def get(path, timeout=15):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_raw(path, timeout=15):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("content-type")


def main():
    try:
        health = get("/api/health")
    except (urllib.error.URLError, ConnectionRefusedError) as exc:
        print(f"FAIL: could not reach {BASE} -- is the server running? (./run.sh) ({exc})", file=sys.stderr)
        return 1
    print(f"Server reachable: {health}\n")

    mode = get("/api/mode")
    print(f"Mode: {mode['mode']} (provider={mode['provider']}, configured={mode['configured']})")
    print(f"  {mode['note']}\n")
    if mode["mode"] != "llm":
        print("NOTE: no local LLM is currently reachable -- open-ended questions below will run in "
              "factual-excerpt mode (deterministic FAQ answers and chart generation are unaffected). "
              "Start the local LLM via ./run.sh (not RESULTS_CHAT_SKIP_LOCAL_LLM=1) to see live inference.\n")

    dash = get("/api/dashboard")
    print("Dashboard summary:")
    print(f"  run_id={dash['completion']['run_id']} "
          f"rtl_vs_native={dash['rtl_vs_native']['n_matched']}/{dash['rtl_vs_native']['n_cases']} "
          f"classifier_correct={dash['classifier_quality']['n_correct_on_fixed_cases']}/{dash['classifier_quality']['n_fixed_cases']}")
    print()

    failures = []
    latencies = []

    def run_turn(session_id, question, lang=None):
        payload = {"message": question, "session_id": session_id}
        if lang:
            payload["lang"] = lang
        r, dt = post("/api/chat", payload)
        latencies.append((question[:40], dt, r["mode"]))
        print(f"Q [{r['lang']}]: {question}")
        tag = r["intent"] + (f"/{r['chart']['kind']}" if r.get("chart") else "")
        print(f"A [{r['mode']}/{tag}] ({dt:.2f}s): {r['answer'][:400]}")
        if r.get("chart"):
            c = r["chart"]
            print(f"   Chart: {c['title']} -- {c['png_url']} | {c['svg_url']} | {c['csv_url']}")
        if r["citations"]:
            print(f"   Sources: {' | '.join(r['citations'][:3])}")
        if r["followups"]:
            print(f"   Suggested follow-ups: {', '.join(r['followups'])}")
        print()
        return r

    print("--- Social conversation (greetings/thanks/capability -- no evidence required) ---\n")
    for q, lang in SOCIAL_SCRIPT:
        r = run_turn("demo-social", q, lang)
        if r["intent"] == "unsupported":
            failures.append(f"social turn wrongly refused: {q}")
        if r["intent"].startswith("social_") and r["citations"]:
            failures.append(f"purely-social turn should have no citations: {q}")

    print("--- FAQ / fixed-intent questions ---\n")
    for q, lang in FAQ_SCRIPT:
        r = run_turn("demo-faq", q, lang)
        if r["intent"] == "unsupported":
            failures.append(q)

    print("--- Open-ended questions (grounded in project documentation) ---\n")
    for q, lang in OPEN_ENDED_SCRIPT:
        r = run_turn("demo-open-ended", q, lang)
        if r["intent"] == "unsupported":
            failures.append(q)
        if not r["citations"]:
            failures.append(f"no citations for open-ended question: {q}")

    print("--- Chart requests, including follow-ups ---\n")
    chart_ids = []
    for q, lang in CHART_SCRIPT:
        r = run_turn("demo-charts", q, lang)
        if r.get("chart"):
            chart_ids.append(r["chart"]["chart_id"])
        elif r["intent"] not in ("chart_clarify",):
            failures.append(f"expected a chart for: {q} (got intent={r['intent']})")

    print("--- Missing-data behavior (never fabricate) ---\n")
    r = run_turn("demo-missing", "Show me the scores for case 47.")
    if r.get("chart") is not None:
        failures.append("case 47 should not have produced a chart (out of range)")
    r = run_turn("demo-missing", "What was the chip's power consumption in watts?")
    if "does not contain" not in r["answer"].lower():
        failures.append("physical-measurement question should explicitly refuse")

    print("--- Actual file downloads ---\n")
    if chart_ids:
        cid = chart_ids[0]
        for ext, ctype_expect in [("png", "image/png"), ("svg", "image/svg+xml"), ("csv", "text/csv")]:
            try:
                data, ctype = get_raw(f"/api/chart/{cid}.{ext}")
                print(f"  {cid}.{ext}: {len(data)} bytes, content-type={ctype}")
                if len(data) < 50 or ctype_expect not in ctype:
                    failures.append(f"download sanity check failed for {cid}.{ext}")
            except urllib.error.URLError as exc:
                failures.append(f"download failed for {cid}.{ext}: {exc}")
    print()

    print("=== LATENCY SUMMARY ===")
    for label, dt, m in latencies:
        print(f"  {label:42s} {dt:6.2f}s  mode={m}")
    print()

    if failures:
        print("DEMO FAILED:", failures, file=sys.stderr)
        return 1
    print("Demo completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
