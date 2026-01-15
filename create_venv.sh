#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

echo "Creating virtual environment at ${VENV_DIR}" 
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip

if [ -f "${PROJECT_ROOT}/setup.py" ]; then
  python -m pip install -e "${PROJECT_ROOT}"
fi

echo "Virtual environment ready. Activate with:"
echo "source ${VENV_DIR}/bin/activate"
