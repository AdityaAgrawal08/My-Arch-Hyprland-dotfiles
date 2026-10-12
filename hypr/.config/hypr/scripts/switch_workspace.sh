#!/bin/bash

# Switch to the previous / next workspace that has windows.
# This wraps around (like circular_workspace.sh for ALT + TAB):
# at the last workspace "next" jumps to the first one, and at the
# first workspace "prev" jumps to the last one.
#
# Usage: switch_workspace.sh next|prev

direction="${1:-next}"

current=$(hyprctl -j activeworkspace 2>/dev/null | jq -r '.id')
if ! [[ "$current" =~ ^-?[0-9]+$ ]]; then
    exit 0
fi

# Real workspaces only: positive IDs (skips special:magic) that have windows.
mapfile -t workspaces < <(
    hyprctl -j workspaces 2>/dev/null \
        | jq -r '.[] | select(.id > 0 and .windows > 0) | .id' \
        | sort -n
)

if [ ${#workspaces[@]} -eq 0 ]; then
    exit 0
fi

target=""

case "$direction" in
    next)
        for ws in "${workspaces[@]}"; do
            if (( ws > current )); then
                target="$ws"
                break
            fi
        done
        # Wrap around: nothing to the right -> first workspace.
        [ -n "$target" ] || target="${workspaces[0]}"
        ;;
    prev)
        for (( i = ${#workspaces[@]} - 1; i >= 0; i-- )); do
            if (( workspaces[i] < current )); then
                target="${workspaces[i]}"
                break
            fi
        done
        # Wrap around: nothing to the left -> last workspace.
        [ -n "$target" ] || target="${workspaces[${#workspaces[@]} - 1]}"
        ;;
esac

# Safety net: no workspace to switch to (only the current one has windows).
[ -n "$target" ] || exit 0

hyprctl dispatch "hl.dsp.focus({ workspace = $target })" >/dev/null 2>&1
