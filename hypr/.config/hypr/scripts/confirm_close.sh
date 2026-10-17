#!/usr/bin/env bash

# The confirmation question - also identifies our dialog below.
PROMPT="Do you want to close this window?"

# Only one confirmation dialog at a time: if a previous press was never
# answered, its dialog is still out there holding the lock. Dismiss it so
# this press always acts on the window that is focused right now.
LOCK_FILE="/tmp/confirm_close.lock"

if [ -f "$LOCK_FILE" ]; then
    OLD_PID=$(tr -cd "0-9" < "$LOCK_FILE")

    # Only trust a lock held by a real instance of this script. A stale lock
    # whose PID was reused by some unrelated process is simply cleared.
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null && grep -q confirm_close.sh "/proc/$OLD_PID/cmdline" 2>/dev/null; then
        # Its dialog is what keeps it alive: close that first, then wait for
        # the old instance to exit so its EXIT trap cannot remove the lock we
        # are about to write.
        pkill -f -- "--prompt $PROMPT" 2>/dev/null
        for _ in {1..20}; do
            kill -0 "$OLD_PID" 2>/dev/null || break
            sleep 0.05
        done
        # Belt and braces: force it if it somehow survived
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill "$OLD_PID" 2>/dev/null
            for _ in {1..20}; do
                kill -0 "$OLD_PID" 2>/dev/null || break
                sleep 0.05
            done
        fi
    fi

    # Also catch an orphaned dialog whose script already died.
    pkill -f -- "--prompt $PROMPT" 2>/dev/null
    rm -f "$LOCK_FILE"
fi

# Store the current script PID in the lock file
echo "$$" > "$LOCK_FILE"

# Clean up lock file on exit
cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Get active window info in JSON format
WINDOW_JSON=$(hyprctl activewindow -j)
WINDOW_ADDRESS=$(echo "$WINDOW_JSON" | jq -r '.address')
WINDOW_CLASS=$(echo "$WINDOW_JSON" | jq -r '.class')
WINDOW_PID=$(echo "$WINDOW_JSON" | jq -r '.pid')

# Exit if no window is active
if [ -z "$WINDOW_ADDRESS" ] || [ "$WINDOW_ADDRESS" = "null" ] || [ "$WINDOW_ADDRESS" = "0x" ]; then
    exit 0
fi

close_window() {
    hyprctl dispatch "hl.dsp.window.close({ window = \"address:$WINDOW_ADDRESS\" })"
}

# Bypass confirmation for utility/overlay windows
if [[ "$WINDOW_CLASS" =~ ^(wofi)$ ]]; then
    close_window
    exit 0
fi

# Terminal emulator window classes (as reported by Hyprland)
TERMINAL_CLASSES='^(kitty|Alacritty|foot|ghostty|com\.mitchellh\.ghostty|wezterm|org\.wez\.wezterm|gnome-terminal|konsole|xterm|XTerm|st)$'

# Things that are fine to kill without asking: idle shells and kitty's own
# helper processes (kitten __atexit__, kitten __watch_conf__, ...)
IDLE_OK_NAMES='fish|bash|zsh|sh|dash|ksh|nu|elvish|kitten|kitty'

# A terminal is "busy" when:
#   - one of its direct children has children of its own (a shell running a
#     command: foreground, background or suspended), or
#   - a direct child is neither a shell nor a kitty helper (e.g. kitty -e btop)
terminal_has_running_command() {
    local child child_name
    while IFS= read -r child; do
        [ -n "$child" ] || continue
        if pgrep -P "$child" >/dev/null 2>&1; then
            return 0
        fi
        child_name=$(cat /proc/"$child"/comm 2>/dev/null)
        [ -n "$child_name" ] || continue
        [[ "$child_name" =~ ^($IDLE_OK_NAMES)$ ]] || return 0
    done < <(pgrep -P "$1" 2>/dev/null)
    return 1
}

# Non-terminals close instantly, no dialog
if [[ ! "$WINDOW_CLASS" =~ $TERMINAL_CLASSES ]]; then
    close_window
    exit 0
fi

# Terminals with nothing running close instantly, no dialog
if [ -z "$WINDOW_PID" ] || [ "$WINDOW_PID" = "null" ] || [ "$WINDOW_PID" = "0" ] \
    || ! terminal_has_running_command "$WINDOW_PID"; then
    close_window
    exit 0
fi

# A command is running: ask before killing it
CHOICE=$(printf "NO\nYES" | wofi --dmenu \
    --prompt "$PROMPT" \
    --width 350 \
    --height 105 \
    --columns 2 \
    -k /dev/null \
    -n \
    -D use_search_box=false \
    -D content_halign=center \
    -D single_click=true \
    -s ~/.config/wofi/confirm.css)

# If choice is yes, close the window by its address
if [ "$CHOICE" = "YES" ]; then
    close_window
fi
