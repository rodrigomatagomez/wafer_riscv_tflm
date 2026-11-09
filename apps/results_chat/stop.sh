#!/usr/bin/env bash
# Stop the results_chat Flask app and the local llama-server, identified
# narrowly by their exact command line (not by a broad process-name
# match), so this cannot affect any unrelated process on a shared host.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_PIDFILE="$HERE/llm_runtime/llama-server.pid"

stop_by_pattern() {
  local pattern="$1" label="$2"
  local pids
  pids="$(pgrep -f -- "$pattern" 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    echo "$label: not running."
    return
  fi
  for pid in $pids; do
    cmd="$(ps -o cmd= -p "$pid" 2>/dev/null || true)"
    if [ -z "$cmd" ]; then
      continue
    fi
    echo "Stopping $label (pid $pid): $cmd"
    kill "$pid" 2>/dev/null || true
  done
}

stop_by_pattern "$HERE/backend/app.py" "Flask app"
stop_by_pattern "$HERE/llm_runtime/llama.cpp/build/bin/llama-server" "llama-server"
rm -f "$LLAMA_PIDFILE"

sleep 1
echo
echo "Remaining matching processes (should be none):"
pgrep -af -- "$HERE/backend/app.py|$HERE/llm_runtime/llama.cpp/build/bin/llama-server" 2>/dev/null || echo "  (none)"
