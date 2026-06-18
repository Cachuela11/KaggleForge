#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -n "${PYTHON_BIN:-}" ]; then
  PYTHON_CMD="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
else
  PYTHON_CMD="python"
fi

VENV_DIR="${VENV_DIR:-.venv}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

if [ ! -d "$VENV_DIR" ]; then
  echo "[KaggleForge] creating virtual environment: $VENV_DIR"
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

if [ -x "$VENV_DIR/bin/python" ]; then
  PY="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  PY="$VENV_DIR/Scripts/python.exe"
else
  PY=""
fi

if [ ! -x "$PY" ]; then
  echo "[KaggleForge] virtual environment python not found under: $VENV_DIR" >&2
  echo "[KaggleForge] checked: $VENV_DIR/bin/python and $VENV_DIR/Scripts/python.exe" >&2
  exit 1
fi

if [ -f requirements.txt ]; then
  echo "[KaggleForge] installing requirements"
  "$PY" -m pip install -r requirements.txt
fi

case "${1:-server}" in
  server)
    echo "[KaggleForge] starting server at http://$HOST:$PORT"
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
