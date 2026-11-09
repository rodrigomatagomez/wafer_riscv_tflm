# results_chat: a local-LLM explainer and chart generator for the full20_final_001 experiment

A host-side web application that explains the already-verified
wafer_riscv_tflm results (run `full20_final_001`) to a human audience: a
dashboard, an open-ended bilingual (English/Spanish) chat assistant
backed by a **local** LLM running on this same server, and natural-
language chart generation. **This is a documentation/communication tool
added after the experiment finished -- it does not re-run, modify, or
affect the simulation, model, or any evidence file in any way.** See
"Scope and safety" below.

This upgrades an earlier, narrower version of this app (fixed-FAQ-only,
no charts, LLM untested in this environment -- see `docs/decisions.md`
D-011) to support genuinely open-ended questions and on-request charts,
grounded in project evidence, with a real local model doing the
conversational work. See `docs/decisions.md` D-012 onward for the design
rationale behind this upgrade.

## What this is NOT

- It does not run inside the simulated RISC-V processor. The classifier
  (quantized TFLM model) runs *inside* the RTL simulation; this chat
  application -- including its local LLM -- is a *separate* process on
  the host server that only reads the result files the simulation already
  produced.
- It cannot execute shell commands, launch or control a simulation, train
  or modify the model, or write to the project tree. There is no such
  route in the backend, and the LLM itself is never given tool/shell
  access -- it only ever returns text (see "Scope and safety").
- It does not invent numbers, in chat answers OR in charts. Every number
  comes from `backend/evidence.py` (which only reads the project's saved
  result files); charts are rendered by deterministic Python functions
  from a strictly validated specification that an LLM can only select
  categorical filters in, never raw data (see "How charts stay accurate"
  below).

## Architecture

```
apps/results_chat/
  backend/
    evidence.py       -- loads results/*.json + the raw run log once at
                          startup; computes every derived number with its
                          exact provenance attached (Fact(value,
                          source_file, source_field)). Also exposes the
                          full ml_metrics.json/memory_usage.json dicts and
                          both models' training_history for chart_engine.py.
    qa_engine.py       -- deterministic, pattern-matched bilingual FAQ
                          intents (completion, agreement, classifier
                          quality, a case lookup, timing, memory, a
                          physical-measurement refusal, etc.). No LLM.
    social.py          -- bilingual detection of greetings/thanks/
                          farewells/"what can you do" capability questions,
                          answered directly with no retrieval/citation/LLM
                          call; strips a social phrase glued onto a real
                          question (e.g. "Hola, ¿puedes explicarme qué
                          hace este proyecto?") before the remainder goes
                          through the normal routing below.
    knowledge_base.py  -- pure-Python TF-IDF retrieval over a curated,
                          source-linked project overview plus README.md /
                          docs/decisions.md / docs/handoff/*  / 
                          docs/findings.md / results/status_summary.md /
                          claims_evidence.csv, chunked by section, with a
                          small Spanish->English term bridge so Spanish
                          questions still retrieve the (English) docs.
    llm_adapter.py     -- server-side adapter to a conversational LLM.
                          DEFAULT path: auto-detects a local llama-server
                          on this host (see "Setting up the local LLM").
                          Also supports a remote Anthropic or any OpenAI-
                          compatible endpoint if explicitly configured.
                          Never assumes credentials/a server exist.
    chart_engine.py    -- a strict schema (kind + categorical params) for
                          9 chart types, each rendered by a deterministic
                          function that reads real Evidence data. Raises
                          ChartDataUnavailable (never fabricates) for
                          unsupported/out-of-range requests.
    chart_cache.py     -- a dedicated, bounded, path-safe on-disk cache
                          for rendered PNG/SVG/CSV + a JSON manifest, keyed
                          by a hash of the exact chart spec.
    chart_router.py     -- deterministic bilingual parsing of natural-
                          language chart requests (and follow-ups:
                          normalize, language-switch, download) into the
                          same strict spec chart_engine.py validates.
    chat_pipeline.py   -- orchestrates one chat turn: social conversation
                          -> download follow-up -> chart request (regex,
                          or LLM-proposed JSON spec as a fallback, always
                          re-validated) -> fixed FAQ intent -> open-ended
                          RAG question, with per-session history and
                          chart/case follow-up state.
    app.py             -- Flask app wiring the above into HTTP routes,
                          including chart file downloads. Binds to
                          127.0.0.1 by default.
  frontend/
    index.html, app.js, style.css  -- vanilla JS, no build step, no CDN
                          dependency; renders charts inline with PNG/SVG/
                          CSV download links.
  llm_runtime/         -- the local LLM runtime (gitignored: binaries and
                          weights, NOT the provenance record):
    llama.cpp/           self-built llama.cpp (CPU-only), see below.
    models/               the downloaded GGUF model file.
    MODEL_PROVENANCE.json  exact model/runtime/license/hash/measured
                          performance record (this file IS committed).
  tests/               -- pytest suite (217 tests): evidence, qa_engine,
                          social (greeting/thanks/capability detection),
                          knowledge_base, chart_engine/cache/router,
                          chat_pipeline (LLM forced off, deterministic),
                          the live Flask API, AND test_live_llm.py (real
                          network calls to a running local server --
                          skipped, not silently passed, if none is up).
  demo.py              -- black-box HTTP demonstration/smoke-test script
                          covering social conversation, FAQ, open-ended,
                          charts, and downloads.
  run.sh / stop.sh     -- start/stop both the local LLM and the Flask app.
  requirements.txt, requirements-dev.txt
  venv/                -- isolated virtualenv (not the project's ml/venv).
  chart_cache/         -- gitignored, regenerable derived-chart cache.
```

### Request flow for one chat message

0. **Social conversation** (`social.py`): a greeting, thanks, farewell, or
   "what can you do" capability question, bilingual and tolerant of real
   variation ("hi"/"hello"/"hey"/"hola"/"buenas"/"good morning"/etc.). If
   the ENTIRE message is social (e.g. "hi", "gracias", "¿qué puedes
   hacer?"), it is answered directly with a canned bilingual reply -- no
   retrieval, no citation, no LLM call, since there is no project-specific
   claim to ground. If a social phrase is glued onto a real question (e.g.
   "Hola, ¿puedes explicarme qué hace este proyecto?"), the social phrase
   is stripped before the remainder goes through the steps below, and a
   short acknowledgment ("¡Hola! " / "You're welcome! ") is prepended to
   whatever real answer comes back.
1. **Download/redisplay follow-up** ("let me download it" /
   "déjame descargarla"): if a chart was already shown this session,
   resurface its existing links -- no re-render, no LLM call.
2. **Chart request**: `chart_router.py` tries to parse the message
   deterministically (including follow-ups: "now show the normalized
   version", "put that chart in Spanish", which modify the *previous*
   chart's spec). If that fails and an LLM is available, the LLM is asked
   to propose a spec as strict JSON (schema documented inline in its
   prompt) -- either way, the result is validated by
   `chart_engine.validate_spec()` before anything is rendered. An
   unavailable/out-of-range request (a case id outside 0-19, a physical
   measurement that was never collected) returns an explicit refusal, not
   a chart.
3. **Fixed FAQ intent** (`qa_engine.py`): completion, RTL/native
   agreement, classifier quality, a case lookup, the case-16 tie, timing,
   memory, a physical-measurement refusal, "where does this run",
   provenance. If matched, optionally passed through the LLM to rephrase
   more conversationally -- the LLM is explicitly instructed not to change
   any number or citation; if the LLM call fails, the deterministic
   answer is used as-is.
4. **Open-ended question**: `knowledge_base.py` retrieves up to 3 relevant
   documentation chunks. If none are relevant, the app refuses explicitly
   ("the evidence does not contain that information"). If some are found
   and an LLM is available, it answers grounded ONLY in those chunks (with
   an instruction to distinguish project-specific measured facts, cited
   per-chunk, from general background knowledge, and to say plainly when
   something was apparently never decided/recorded). If no LLM is
   available, the retrieved excerpts are shown directly, clearly labeled
   as factual mode.

Every response reports `"mode": "llm"` or `"mode": "factual"` truthfully
-- never claims LLM output when none was used.

## Setting up the local LLM

This is what was actually built and measured in this environment --
reproduce it exactly, or substitute your own choices and re-measure.

**1. Check resources first** (this app was built conservatively for a
shared, multi-user EDA server -- re-check before assuming these limits
still apply on a different host):
```bash
nproc --all              # this host: 88 CPUs, no cgroup CPU quota
free -h                  # this host: 124 GiB RAM, ~94 GiB available
df -h /home               # this host: 85 GiB free at build time
nvidia-smi -L 2>&1 | head # this host: no GPU present
```

**2. Build llama.cpp (CPU-only) into the isolated runtime directory:**
```bash
cd apps/results_chat/llm_runtime
git clone --branch v0.9.0 --depth 1 https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF -DGGML_AVX512=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON \
  -DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_VULKAN=OFF \
  -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_SERVER=ON
cmake --build build --config Release -j 8
```
(Adjust `-DGGML_AVX512`/`-DGGML_AVX2`/etc. to your actual CPU's features;
this host is an Intel Xeon Gold 6152 with AVX/AVX2/AVX512F/FMA/F16C.)

**3. Download the model** (official Qwen GGUF quantization, Apache-2.0,
~1.04 GiB, well under the 3 GiB cap):
```bash
cd apps/results_chat/llm_runtime
mkdir -p models
curl -L -o models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
sha256sum models/qwen2.5-1.5b-instruct-q4_k_m.gguf
# expect: 6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e
```
Full provenance (source repo revision, license, exact hash, why this
model/quantization was chosen) is recorded in
`llm_runtime/MODEL_PROVENANCE.json` -- that file is committed to the repo
even though the binaries/weights themselves are gitignored.

**4. Start everything** (builds+model already in place):
```bash
cd apps/results_chat
./run.sh
```
`run.sh` starts `llama-server` first (4 threads, `--parallel 1`, no GPU
layers, 4096-token context), waits for its `/health` endpoint, then starts
the Flask app on port 8787 (the preserved default). `GET /api/mode` will
report `"mode": "llm", "provider": "local"` once both are up. Use
`RESULTS_CHAT_SKIP_LOCAL_LLM=1 ./run.sh` to start only the Flask app
(factual mode, or to point at a different provider -- see below).

**Launch flags actually used** (conservative, as required): `--threads 4
--threads-batch 4` (never more than 4 CPU threads), `--parallel 1` (one
generation at a time), `--n-gpu-layers 0` (no GPU was detected on this
host -- would be used if one were allocated), `--ctx-size 4096`.

## How charts stay accurate (never fabricated)

A chart request is turned into a small dict: `{"kind": "...", "params":
{...}, "lang": "en"|"es"}`. `kind` must be one of 9 fixed values
(confusion matrix, F1 by class, model A/B comparison, float/int8
comparison, Invoke() cycles, a case's 4 scores, correct/incorrect counts,
training curves, memory budget); `params` are small fixed enums (which
model, which split, which case id, normalize true/false). **There is no
field anywhere in this schema for a raw plotted number.** Whether the
spec came from the deterministic regex parser or from the LLM, it is
re-validated by `chart_engine.validate_spec()` against that exact schema
before any rendering happens, and the actual numbers are always re-read
fresh from `Evidence` at render time. A request for data that was never
collected (clock frequency, power, die area) or an out-of-range case
(`case_id=47`) raises `ChartDataUnavailable` with an explicit bilingual
message -- the app never silently substitutes or invents a graph.

Supported chart kinds: confusion matrix (raw or normalized, any model/
split/quantization), F1 by class, Model A vs. B comparison, float vs.
int8 comparison, Invoke() cycles for all 20 final cases, a selected
case's 4 quantized scores (with predicted/true label and tie detection),
correct/incorrect classifier counts (explicitly distinguished from the
20/20 RTL-vs-native agreement in its own caption), stored training/
validation curves (both models, 14 epochs each), and the memory budget
(reservation vs. measurement, explicitly distinguished).

Every chart response includes: an inline PNG, a caption stating units/
scope/caveats, citations to the source file/field, and download links for
PNG, SVG (vector), and CSV (the plotted values plus a provenance header
with the exact filters/normalization/source citation used -- see
`chart_cache.py`'s CSV header format). Rendered artifacts live in a
dedicated, bounded (`MAX_ENTRIES=200`), path-safety-checked cache
directory (`chart_cache/`, gitignored) -- never in the original evidence
tree, and `/api/chart/<id>.<ext>` only ever resolves an id this app
generated itself (hex fingerprint, fixed extension whitelist), never an
arbitrary filesystem path.

## Evidence sources (what the numbers are actually computed from)

| File | Used for |
|---|---|
| `results/final_run_evidence/full20_final_001_fingerprints.json` | run id, SIM_BANNER, final cycle, wall-clock, checker verdict/exit code, model/firmware/TFLM hashes |
| `results/final_run_evidence/full20_final_001_check_report.json` | per-case RTL scores/predicted class, native scores/predicted class, match status, Invoke() start/end cycle |
| `results/comparison_manifest.json` | per-case sample_id, ground-truth class_idx/class_name |
| `results/ml_metrics.json` | classifier accuracy/macro-F1 for A and B, float and int8, val and test splits; per-class F1; confusion matrices; 0.85 target, met/not-met |
| `results/memory_usage.json` | tensor arena reserved vs. measured-peak bytes (and that the peak figure comes from the native reference), firmware size breakdown, RAM budget |
| `results/training_history_A.json`, `results/training_history_B.json` | stored per-epoch loss/accuracy/val_loss/val_accuracy curves |
| `results/cpu_verification.json` | processor directed-test pass/fail, 1100-instruction random comparison mismatch count |
| `results/rtl_comparison.json` | authoritative final n_cases/n_matched summary |
| `results/rtl_logs/full20_final_001_live.log` (or its gzip copy in `final_run_evidence/`) | exact `MMIO_PREDICTED_CLASS cycle=...` log-line citations per case |
| `README.md`, `docs/decisions.md`, `docs/handoff/README.md`, `docs/handoff/limitations_and_open_questions.md`, `docs/findings.md`, `docs/handoff/claims_evidence.csv`, `results/status_summary.md` | open-ended question grounding (`knowledge_base.py`), chunked by section/claim |

Historical, superseded evidence
(`results/rtl_comparison_partial_per_case_runs.json`, the 7/20 and 8/20
partial-match states) is deliberately **not** read by this app.

## Actual mode tested

**Both modes were genuinely tested in this environment.** Factual mode
(no LLM) was the only mode available in the narrower, earlier version of
this app. For this upgrade, a **real local LLM was built, downloaded,
started, and exercised live**:

- `tests/test_live_llm.py` makes actual HTTP calls to the running
  `llama-server` (English inference, Spanish inference, multi-turn
  history, a real open-ended RAG question through the full pipeline, a
  real FAQ rephrase, and a confirmation that chart answers stay
  deterministic even with the LLM live) -- it skips with a clear reason
  if no server is reachable, rather than silently passing against
  factual-mode behavior. All of these passed against the real server.
- A 13+-turn live HTTP session (`demo.py`, and an ad hoc extended
  verification session) exercised open-ended questions, Spanish
  paraphrases, follow-ups, all 9 chart kinds, language-switch/normalize/
  download follow-ups, actual file downloads, and missing-data refusals
  -- end to end against the real deployed server, not mocked.

`GET /api/mode` always reports truthfully which mode is active and why
(e.g. "no server answered a health check" if `RESULTS_CHAT_LLM_PROVIDER=local`
was forced but nothing is listening); the app never claims LLM output
when it produced a factual-mode answer, and vice versa.

### Measured latency and memory (real, not estimated)

| Scenario | Latency | Notes |
|---|---|---|
| Single short English prompt (smoke test) | 1.3s, ~20 tok/s | First measurement, idle server |
| Single short Spanish prompt | 2.3s, ~21 tok/s | |
| FAQ rephrase (short grounded prompt) | 3-9s typical | Observed range 3.2s-8.9s across a live session |
| Open-ended RAG question (long grounding prompt, up to 320 generated tokens) | 12-30s typical | Dominated by prompt length (system prompt + 3 retrieved chunks + history) on a 4-thread CPU budget |
| Chart request (deterministic, no LLM call) | <0.2s | matplotlib Agg rendering only |
| `llama-server` process RSS, idle/first request | ~1.84 GB | |
| `llama-server` process RSS, after a sustained multi-turn session | ~2.2 GB | KV cache growth within the 4096-token context; still far below the 94 GiB available |

Full detail: `llm_runtime/MODEL_PROVENANCE.json`. The open-ended path was
tuned once during verification (max_tokens 500->320, retrieved chunks
4->3, history window trimmed to the last 2 turns for this path only)
specifically to cut this latency from an initially-measured ~40s down to
the ~12-30s range above -- both the before and after numbers are real
measurements, not estimates.

### Enabling a remote LLM provider instead

Set these before `./run.sh` (local auto-detection is skipped if
`RESULTS_CHAT_LLM_PROVIDER` is explicitly set to something else):

**Anthropic API directly:**
```bash
export RESULTS_CHAT_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...        # your own key; never commit this
export ANTHROPIC_MODEL=claude-haiku-4-5-20251001   # optional, this is the default
```

**Any other OpenAI-chat-completions-compatible endpoint:**
```bash
export RESULTS_CHAT_LLM_PROVIDER=openai_compatible
export LLM_API_BASE=http://127.0.0.1:11434/v1
export LLM_MODEL=llama3.1:8b
export LLM_API_KEY=...                           # omit for a local server with no auth
```

## Keeping credentials and model weights out of Git

- Remote-provider credentials are read only from environment variables at
  call time inside `llm_adapter.py`; never written to a file, never
  logged, never present in any `/api/*` JSON response (`/api/mode` only
  reports `configured: true/false` and the provider/model name).
- `apps/results_chat/venv/`, `llm_runtime/llama.cpp/` (the built binaries),
  and `llm_runtime/models/` (the downloaded weights) are all gitignored.
  `llm_runtime/MODEL_PROVENANCE.json` is explicitly NOT ignored -- the
  provenance record is the point, even though the multi-gigabyte weights
  it describes are not committed.
- `chart_cache/` (derived, regenerable chart artifacts) is also gitignored.

## Exact startup instructions

```bash
cd apps/results_chat
python3 -m venv venv                       # first time only
venv/bin/pip install -r requirements.txt   # first time only
# then build llama.cpp + download the model per "Setting up the local LLM"
./run.sh                                   # starts local LLM + Flask, binds 127.0.0.1:8787
```

Stop everything cleanly:
```bash
./stop.sh
```
(or just Ctrl+C a foreground `./run.sh` -- it traps and stops the local
LLM subprocess it started before exiting.)

Override host/port if needed:
```bash
RESULTS_CHAT_PORT=8080 RESULTS_CHAT_LOCAL_LLM_PORT=8799 ./run.sh
```
`RESULTS_CHAT_HOST` defaults to `127.0.0.1` and the app warns loudly (but
does not refuse) if set to anything else -- there is no authentication in
this app.

### Running the tests

```bash
cd apps/results_chat
venv/bin/pip install -r requirements-dev.txt   # first time only
venv/bin/python3 -m pytest tests/ -v
```
217 tests. `test_live_llm.py` requires the local server to actually be
running (start it first via `./run.sh`) -- it is skipped, with a clear
reason printed, if not; it is never silently replaced by a mock.

### Running the demonstration script

With the server already running (`./run.sh`):
```bash
cd apps/results_chat
venv/bin/python3 demo.py
```
Walks through FAQ questions, open-ended questions (English and Spanish,
with a follow-up), chart requests (including normalize/language-switch/
download follow-ups), actual file downloads, and missing-data refusals
against the live deployed server, printing the full transcript plus a
latency summary, and exits non-zero if any expected behavior is missing.

## Reaching it from your own computer (SSH port forwarding)

```bash
ssh -L 8787:127.0.0.1:8787 your_user@the_server_hostname
```
Then open `http://127.0.0.1:8787/` in your **own computer's** browser.
The local LLM's own port (8788 by default) does not need forwarding --
only the Flask app talks to it, and it already binds to `127.0.0.1`.

## Limitations

- **Language detection is a heuristic.** Accented characters/`¿`/`¡`, a
  small list of unambiguous single Spanish words (hola, gracias, adios,
  ...), or 2+ common Spanish stopwords, trigger Spanish; otherwise
  English. The frontend's language dropdown forces it explicitly.
- **Social-conversation detection (`social.py`) is pattern-based, not
  exhaustive.** It covers common greeting/thanks/farewell/capability
  phrasings in both languages, verified against the task's own example
  set plus natural variations, but an unusual phrasing it doesn't
  recognize will fall through to the normal open-ended path (and, if nothing
  relevant retrieves, an explicit refusal) rather than a canned social
  reply -- a slightly wrong fallback, never a silent failure.
- **Retrieval is TF-IDF, not semantic/embedding-based.** It finds
  documentation chunks sharing (possibly bridged) vocabulary with the
  query; a question using entirely novel phrasing for a concept that IS
  documented might retrieve nothing and get refused, even though an
  embedding-based retriever might have found it. A real false positive
  (a short chunk matching an off-topic query on one incidental shared
  word) was found and fixed during testing by requiring either 2+
  overlapping terms or a high-confidence score -- see
  `knowledge_base.py`'s `retrieve()` docstring.
- **The local model is small (1.5B parameters) and occasionally exhibits
  small-model behavior.** One concretely observed example: asked to
  recall a fact stated earlier in the same conversation when that fact
  was phrased as a personal preference ("my favorite number is 42"), the
  model declined with a privacy-flavored refusal even though the fact was
  correctly present in its context window (verified directly: the
  messages array was correct; the model simply chose not to use it for
  that phrasing). Differently-phrased context recall worked reliably.
  Treat open-ended answers as "a fluent summary of the cited sections",
  not as infallible -- the citations are what to verify a claim against.
- **Conversation memory and chart-cache state are in-process and
  ephemeral**, bounded in size, never written to disk.
- **Open-ended latency (12-30s typical) is real and CPU-bound** by the
  conservative 4-thread limit -- a demo audience should expect this pace
  for open-ended questions; chart and FAQ-intent responses are fast.
- **Single-process Flask development server**, appropriate for a small
  demonstration tool, not load-tested for a large concurrent audience.

## Scope and safety (why this cannot affect the original experiment)

- The entire application is read-only against the project tree: grep
  `apps/results_chat/backend/*.py` yourself for `open(..., "w")`,
  `subprocess`, `os.system`, `eval`, or `exec` against the project tree --
  none exist outside `chart_cache.py`'s own bounded, dedicated cache
  directory (also checked by
  `tests/test_api.py::test_chat_endpoint_is_read_only_by_construction`).
- The LLM itself has no tools, no shell access, and no file access of any
  kind -- it is called with a single text-completion HTTP request and its
  text reply is either shown directly (chat) or parsed as a small JSON
  spec that is re-validated against a fixed schema before use (charts). It
  cannot act on anything, only describe it.
- It loads evidence once at process startup, keeps it in memory, and
  never re-reads or re-derives it from a running simulation.
- It runs as a separate OS process from any Animas/Zenith session; it has
  no RPC/IPC channel to the simulator and imports no simulator-control
  code.
- Adding, modifying, or removing this application (or its local LLM)
  cannot change `results/rtl_comparison.json`, `results/final_run_evidence/`,
  or any other evidence file for `full20_final_001` -- re-verified via a
  fresh `scripts/check_final_run.py` run after building this upgrade
  (still `ACCEPTED`, exit code 0).
