#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

if [ ! -d "$VENV_DIR" ]; then
  echo "[MLforge] creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

PY="$VENV_DIR/bin/python"
if [ ! -x "$PY" ]; then
  echo "[MLforge] virtual environment python not found: $PY" >&2
  exit 1
fi

if [ -f requirements.txt ]; then
  echo "[MLforge] installing requirements"
  "$PY" -m pip install -r requirements.txt
fi

case "${1:-server}" in
  server)
    echo "[MLforge] starting server at http://$HOST:$PORT"
    exec "$PY" -m uvicorn server:app --host "$HOST" --port "$PORT"
    ;;
  cli)
    shift
    exec "$PY" main.py "$@"
    ;;
  check-codex)
    exec "$PY" main.py --check-codex
    ;;
  smoke-codex)
    exec "$PY" main.py --smoke-codex
    ;;
  *)
    exec "$PY" main.py "$@"
    ;;
esac
