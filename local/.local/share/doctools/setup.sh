#!/usr/bin/env bash
# Create the doc-tools Python environment.
#
# The toolkit source stays in the dotfiles repository (Stow package `local`).
# Installed dependencies, caches and runtime state stay under $HOME:
#   ~/.local/share/doctools/venv
#   ~/.local/state/doctools/
set -euo pipefail

USER_HOME="$HOME"
VENV="${DOC_TOOLS_VENV:-$USER_HOME/.local/share/doctools/venv}"
STATE_ROOT="${DOC_TOOLS_STATE:-${XDG_STATE_HOME:-$USER_HOME/.local/state}/doctools}"

mkdir -p \
  "$(dirname -- "$VENV")" \
  "$STATE_ROOT/cache" \
  "$STATE_ROOT/config" \
  "$STATE_ROOT/home" \
  "$STATE_ROOT/pip-cache" \
  "$STATE_ROOT/runtime"

export HOME="$STATE_ROOT/home"
export TMPDIR="$STATE_ROOT/runtime"
export XDG_CACHE_HOME="$STATE_ROOT/cache"
export XDG_CONFIG_HOME="$STATE_ROOT/config"
export PIP_CACHE_DIR="$STATE_ROOT/pip-cache"
export PIP_DISABLE_PIP_VERSION_CHECK=1

if [[ ! -x "$VENV/bin/python" ]]; then
  printf '==> Creating doc-tools venv: %s\n' "$VENV"
  python3 -m venv "$VENV"
fi

printf '==> Installing Python dependencies into %s\n' "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip

"$VENV/bin/python" -m pip install \
  'pypdf>=5' \
  'reportlab>=4' \
  'pdf2docx>=0.5.13' \
  'img2pdf>=0.5' \
  'weasyprint>=62' \
  'markdown>=3.5' \
  'python-docx>=1.1' \
  'pillow>=10' \
  'cryptography>=3.1'

printf '==> Verifying Python dependencies\n'
"$VENV/bin/python" - <<'PY'
import importlib
import logging
import warnings

logging.disable(logging.INFO)
warnings.filterwarnings("ignore", message="The `fitz` API is deprecated.*")

checks = {
    "pypdf": "pypdf",
    "reportlab": "reportlab",
    "pdf2docx": "pdf2docx",
    "img2pdf": "img2pdf",
    "weasyprint": "weasyprint",
    "markdown": "markdown",
    "docx": "docx",
    "PIL": "PIL",
    "cryptography": "cryptography",
}
failed = []
for label, module in checks.items():
    try:
        mod = importlib.import_module(module)
        version = getattr(mod, "__version__", "")
        print(f"  OK  {label:<12} {version}")
    except Exception as exc:
        failed.append((label, exc))
        print(f"  ERR {label:<12} {exc}")

if failed:
    raise SystemExit(1)
PY

printf '\n==> doc-tools environment ready\n'
printf '    Run: docs doctor\n'
