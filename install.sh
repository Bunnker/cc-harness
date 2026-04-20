#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: python3/python not found" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/scripts/install_skill_pack.py" install \
  --source "$SCRIPT_DIR" \
  --lock-file "$SCRIPT_DIR/skills.lock.json" \
  "$@"
