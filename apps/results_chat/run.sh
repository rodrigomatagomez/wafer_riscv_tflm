#!/usr/bin/env bash
# Start the results_chat backend: the local llama-server LLM (if the
# runtime/model have been set up -- see README.md "Setting up the local
# LLM") plus the Flask app, both bound to localhost only by default.
# See README.md for SSH port-forwarding instructions to reach it remotely.
#
# Set RESULTS_CHAT_SKIP_LOCAL_LLM=1 to start only the Flask app (factual
# mode / to use a different LLM provider configured via env vars instead).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="$HERE/llm_runtime"
LLAMA_SERVER_BIN="$RUNTIME/llama.cpp/build/bin/llama-server"
MODEL_GLOB=("$RUNTIME"/models/*.gguf)
LLAMA_PIDFILE="$RUNTIME/llama-server.pid"
LLAMA_LOG="$RUNTIME/llama-server.log"

if [ ! -d "$HERE/venv" ]; then
  echo "venv not found at $HERE/venv -- run: python3 -m venv venv && venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

export RESULTS_CHAT_PROJECT_ROOT="${RESULTS_CHAT_PROJECT_ROOT:-$(cd "$HERE/../.." && pwd)}"
export RESULTS_CHAT_HOST="${RESULTS_CHAT_HOST:-127.0.0.1}"
export RESULTS_CHAT_PORT="${RESULTS_CHAT_PORT:-8787}"
LOCAL_LLM_HOST="127.0.0.1"
LOCAL_LLM_PORT="${RESULTS_CHAT_LOCAL_LLM_PORT:-8788}"
export RESULTS_CHAT_LOCAL_LLM_URL="http://${LOCAL_LLM_HOST}:${LOCAL_LLM_PORT}"
# RESULTS_CHAT_LLM_PROVIDER / ANTHROPIC_API_KEY / LLM_API_BASE / LLM_API_KEY /
# LLM_MODEL are intentionally left unset here unless already set in your
# shell -- see README.md "Enabling a remote LLM provider instead". Leaving
# everything unset auto-detects the local llama-server started below.

STARTED_LLAMA_SERVER=0

cleanup() {
  if [ "$STARTED_LLAMA_SERVER" = "1" ] && [ -f "$LLAMA_PIDFILE" ]; then
    pid="$(cat "$LLAMA_PIDFILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping local llama-server (pid $pid)..."
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$LLAMA_PIDFILE"
  fi
}
trap cleanup EXIT INT TERM

if [ "${RESULTS_CHAT_SKIP_LOCAL_LLM:-0}" = "1" ]; then
  echo "RESULTS_CHAT_SKIP_LOCAL_LLM=1 -- not starting the local LLM; running in factual mode"
  echo "unless a remote RESULTS_CHAT_LLM_PROVIDER is set."
elif [ ! -x "$LLAMA_SERVER_BIN" ] || [ ! -f "${MODEL_GLOB[0]}" ]; then
  echo "Local llama-server binary or model not found under $RUNTIME -- see README.md"
  echo "'Setting up the local LLM' to build/download it. Running in factual mode for now."
else
  if curl -s -o /dev/null -m 2 "$RESULTS_CHAT_LOCAL_LLM_URL/health"; then
    echo "A llama-server is already running and healthy at $RESULTS_CHAT_LOCAL_LLM_URL -- reusing it."
  else
    MODEL_FILE="${MODEL_GLOB[0]}"
    echo "Starting local llama-server: model=$(basename "$MODEL_FILE") port=$LOCAL_LLM_PORT threads=4"
    nohup "$LLAMA_SERVER_BIN" \
      --model "$MODEL_FILE" \
      --host "$LOCAL_LLM_HOST" --port "$LOCAL_LLM_PORT" \
      --threads 4 --threads-batch 4 \
      --ctx-size 4096 --n-gpu-layers 0 --parallel 1 \
      > "$LLAMA_LOG" 2>&1 &
    echo $! > "$LLAMA_PIDFILE"
    STARTED_LLAMA_SERVER=1
    echo "llama-server starting (pid $(cat "$LLAMA_PIDFILE")), log: $LLAMA_LOG"
    for _ in $(seq 1 60); do
      if curl -s -o /dev/null -m 1 "$RESULTS_CHAT_LOCAL_LLM_URL/health"; then
        echo "llama-server is healthy."
        break
      fi
      sleep 1
    done
    if ! curl -s -o /dev/null -m 1 "$RESULTS_CHAT_LOCAL_LLM_URL/health"; then
      echo "WARNING: llama-server did not become healthy within 60s -- check $LLAMA_LOG" >&2
      echo "Continuing to start the Flask app anyway; it will run in factual mode." >&2
    fi
  fi
fi

echo "Project root: $RESULTS_CHAT_PROJECT_ROOT"
echo "Binding to:   $RESULTS_CHAT_HOST:$RESULTS_CHAT_PORT"
"$HERE/venv/bin/python3" "$HERE/backend/app.py"
