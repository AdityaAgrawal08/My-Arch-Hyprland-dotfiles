#!/usr/bin/env bash
# Launch a GUI app on the "magic" special workspace (secret screen, SUPER+S)
# so agent-opened windows never appear in the current workspace.
set -euo pipefail
if [[ $# -eq 0 ]]; then
  printf 'Usage: %s <command> [args...]\n' "$(basename "$0")" >&2
  exit 1
fi
# Quote every argument so the command survives Hyprland's exec re-parsing.
cmd=$(printf '%q ' "$@")
hyprctl dispatch exec -- "[workspace special:magic silent] ${cmd}"
