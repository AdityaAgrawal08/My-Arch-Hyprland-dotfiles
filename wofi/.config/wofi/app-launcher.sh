#!/usr/bin/env bash
# App launcher: pick an application with wofi and open it on a new workspace.
#
# wofi prints the selected .desktop entry's expanded Exec line
# (drun-print_command) instead of executing it, so we can create and
# focus a fresh workspace first, then spawn the app pinned to it.
# The workspace-switch animation and the window pop-in animation play
# back to back.

set -u

cmd="$(wofi --show drun --define=drun-print_command=true)"
[ -n "$cmd" ] || exit 0

# New workspace = highest existing workspace ID + 1
# (same rule as increase_workspace.sh).
max="$(hyprctl workspaces -j | jq '.[].id' | sort -n | tail -n 1)"
[ -n "$max" ] || max=0
new=$((max + 1))

# Escape backslashes and double quotes for the Lua string literal below.
cmd="${cmd//\\/\\\\}"
cmd="${cmd//\"/\\\"}"

# 1) Create and focus the new workspace (plays the workspace animation).
hyprctl dispatch "hl.dsp.focus({ workspace = \"$new\" })"

# 2) Launch the app pinned to the new workspace (plays the pop-in animation).
hyprctl dispatch "hl.dsp.exec_cmd(\"$cmd\", { workspace = $new })"
