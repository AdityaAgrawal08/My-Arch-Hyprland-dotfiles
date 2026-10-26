#!/usr/bin/env bash
# Run the doc-tools integration suite.
#
# The suite uses the real wrappers in local/.local/bin, the installed
# venv (~/.local/share/doctools/venv by default), and writes fixtures/results
# under the repository's gitignored state/ directory.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${DOC_TOOLS_VENV:-$HOME/.local/share/doctools/venv}"
VENV_PY="$VENV/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "error: doc-tools venv missing: $VENV" >&2
  echo "Run: $ROOT/local/.local/share/doctools/setup.sh" >&2
  exit 2
fi

mkdir -p "$ROOT/state/doc-tools-tests" "$ROOT/state/doc-tools-fixtures"

export DOC_TOOLS_VENV="$VENV"
export PYTHONPYCACHEPREFIX="$ROOT/state/doc-tools-pycache"
export PYTHONIOENCODING="utf-8"
export TMPDIR="$ROOT/state/doc-tools-tmp"
export LC_ALL="${LC_ALL:-C.UTF-8}"
mkdir -p "$TMPDIR"

cd "$ROOT"
exec "$VENV_PY" -m unittest discover -s tests -p 'test_doc_tools.py' -v
