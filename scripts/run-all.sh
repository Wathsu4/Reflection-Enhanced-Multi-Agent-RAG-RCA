#!/usr/bin/env bash
# Run all three services concurrently and clean them up on Ctrl-C.
#
# We deliberately don't depend on `concurrently` (npm) or `tmux` so
# this works on any unixy box with bash. The trap ensures that if the
# user Ctrl-C's the parent, the child PIDs are sent SIGTERM and the
# script doesn't leave dangling uvicorns or pnpm-dev processes.
#
# Usage:
#   bash scripts/run-all.sh dev      # start classifier + agent + frontend
#   bash scripts/run-all.sh agent    # start only the agent service
#   bash scripts/run-all.sh classifier
#   bash scripts/run-all.sh frontend

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CMD="${1:-dev}"

PIDS=()
cleanup() {
  echo
  echo "shutting down..."
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  # Give them a beat to drain, then SIGKILL stragglers.
  sleep 1
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

start_classifier() {
  echo "[classifier] starting on :8001"
  (cd classifier-service && uv run uvicorn app.main:app \
      --host 0.0.0.0 --port 8001) &
  PIDS+=($!)
}

start_agent() {
  echo "[agent] starting on :8000"
  (cd rca-agent-system && uv run python server.py) &
  PIDS+=($!)
}

start_frontend() {
  echo "[frontend] starting on :3000"
  (cd frontend && pnpm dev) &
  PIDS+=($!)
}

case "$CMD" in
  dev)
    start_classifier
    # Tiny stagger so the classifier model finishes loading before the
    # frontend's first health-poll fires.
    sleep 4
    start_agent
    sleep 2
    start_frontend
    ;;
  classifier)
    start_classifier
    ;;
  agent)
    start_agent
    ;;
  frontend)
    start_frontend
    ;;
  *)
    echo "unknown command: $CMD" >&2
    echo "usage: $0 [dev|classifier|agent|frontend]" >&2
    exit 2
    ;;
esac

# Wait for any child to exit; if any does, propagate via cleanup trap.
wait -n "${PIDS[@]}"
