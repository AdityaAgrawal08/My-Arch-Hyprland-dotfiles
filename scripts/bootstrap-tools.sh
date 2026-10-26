#!/usr/bin/env bash
# Bootstrap/refresh the document and PDF toolkit environment.
#
# This is a convenience wrapper for the same setup used by install.sh.  The
# toolkit source is in local/.local/share/doctools; the venv lives in
# ~/.local/share/doctools/venv and runtime state in ~/.local/state/doctools.
set -euo pipefail

DOTFILES_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

exec "$DOTFILES_DIR/local/.local/share/doctools/setup.sh"
