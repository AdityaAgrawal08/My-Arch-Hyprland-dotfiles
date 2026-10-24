#!/usr/bin/env bash
# Wofi wallpaper picker with cached thumbnails.
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"

# shellcheck source=autotheme.conf
if [[ -f "$SCRIPT_DIR/autotheme.conf" ]]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/autotheme.conf"
fi
# shellcheck source=lib/autotheme.sh
source "$SCRIPT_DIR/lib/autotheme.sh"

main() {
    local json lines choice index path

    cache_init

    ensure_thumbs
    json="$(list_json)"

    if [[ "$(jq 'length' <<<"$json")" -eq 0 ]]; then
        if command -v notify-send >/dev/null 2>&1; then
            notify-send -a autotheme "Wallpaper" "No wallpapers found in $WALLPAPER_DIR"
        fi
        exit 0
    fi

    lines="$(jq -r 'to_entries[] | "img:\(.value.thumb):text:\(.key + 1). \(.value.name | gsub(":"; "-"))"' <<<"$json")"
    choice="$(printf '%s\n' "$lines" | wofi --dmenu \
        --allow-images \
        --insensitive \
        --prompt "Wallpaper" \
        --define=image_size=48 \
        --define=parse_action=true \
        --matching=contains)"
    [[ -n "$choice" ]] || exit 0

    # parse_action normally strips the escape prefix; handle both forms.
    choice="${choice#*:text:}"
    index="$(sed -nE 's/^([0-9]+)\..*/\1/p' <<<"$choice" | head -n1)"
    if [[ -n "$index" ]]; then
        path="$(jq -r --argjson index "$index" '.[$index - 1].path // empty' <<<"$json")"
    else
        path="$(jq -r --arg name "$choice" '.[] | select(.name == $name) | .path' <<<"$json" | head -n1)"
    fi

    [[ -n "$path" && -f "$path" ]] || exit 0
    exec "$SCRIPT_DIR/wallpaper_switch.sh" apply "$path"
}

main "$@"
