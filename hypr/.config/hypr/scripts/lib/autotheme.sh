# shellcheck shell=bash
# Shared helpers for the autotheme scripts.  Sourced, never executed directly.

CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}"
CACHE_DIR="$CACHE_ROOT/autotheme"
THEME_JSON="$CACHE_DIR/theme.json"
THEME_COMPAT="$CACHE_ROOT/autotheme.json"
STATE_FILE="$CACHE_DIR/wallpaper"
ACCENTS_JSON="$CACHE_DIR/accents.json"
SEED_PNG="$CACHE_DIR/seed.png"
ROLES_JSON="$CACHE_DIR/matugen-roles.json"
LOG_FILE="$CACHE_DIR/last.log"
LOCK_FILE="$CACHE_DIR/lock"
KITTY_MODE_FILE="$CACHE_DIR/kitty-mode"
KITTY_OPAQUE="$CACHE_DIR/kitty-opaque.conf"
KITTY_TRANSPARENT="$CACHE_DIR/kitty-transparent.conf"
KITTY_ACTIVE="$CACHE_DIR/kitty.conf"
SAMPLES_DIR="$CACHE_DIR/samples"
DUNST_DROPIN="${XDG_CONFIG_HOME:-$HOME/.config}/dunst/dunstrc.d/autotheme.conf"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# Must match scene.VERSION.  Bump both when the strategy changes so cached
# themes are rebuilt instead of silently keeping an old policy.
SCENE_VERSION=1

WALLPAPER_DIR="$(realpath -m -- "${WALLPAPER_DIR:-$SCRIPT_DIR/../themes/wallpapers/assets}")"
THUMBS_DIR="$(realpath -m -- "${THUMBS_DIR:-$SCRIPT_DIR/../themes/wallpapers/thumbs}")"

IMAGE_SUFFIXES="jpg jpeg png webp gif avif bmp tiff"

cache_init() {
    mkdir -p "$CACHE_DIR" "$THUMBS_DIR" "$SAMPLES_DIR" "$(dirname "$DUNST_DROPIN")"
}

log_line() {
    printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG_FILE"
}

warn() {
    log_line "warning: $*"
    printf 'autotheme: %s\n' "$*" >&2
}

die() {
    log_line "error: $*"
    printf 'autotheme: %s\n' "$*" >&2
    exit 1
}

acquire_lock() {
    exec 9>"$LOCK_FILE"
    if ! flock -w 20 9; then
        die "another wallpaper operation is still running"
    fi
}

stat_mtime() {
    stat -c %Y -- "$1" 2>/dev/null || echo 0
}

sha1_text() {
    printf '%s' "$1" | sha1sum | cut -d' ' -f1
}

thumb_path_for() {
    local file="$1" hash
    hash="$(sha1_text "$(realpath -m -- "$file"):$(stat_mtime "$file")")"
    printf '%s/%s.jpg' "$THUMBS_DIR" "$hash"
}

suffix_of() {
    local value="${1##*.}"
    printf '%s' "${value,,}"
}

is_supported() {
    local suffix
    suffix="$(suffix_of "$1")"
    [[ " $IMAGE_SUFFIXES " == *" $suffix "* ]]
}

extract_middle_frame() {
    local file="$1" output="$2" duration mid
    duration="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$file" 2>/dev/null || echo 0)"
    if ! [[ "$duration" =~ ^[0-9]+([.][0-9]+)?$ ]] || ! awk -v d="$duration" 'BEGIN { exit !(d > 0.05) }'; then
        duration=2
    fi
    mid="$(awk -v d="$duration" 'BEGIN { printf "%.3f", d / 2 }')"
    mkdir -p "$(dirname "$output")"
    if ffmpeg -v error -ss "$mid" -i "$file" -frames:v 1 -y "$output" >/dev/null 2>&1 \
        && [[ -s "$output" ]]; then
        return 0
    fi
    # Very short GIFs can have no frame at their midpoint; fall back to frame 0.
    if ffmpeg -v error -ss 0 -i "$file" -frames:v 1 -y "$output" >/dev/null 2>&1 \
        && [[ -s "$output" ]]; then
        return 0
    fi
    ffmpeg -v error -i "$file" -frames:v 1 -y "$output" >/dev/null 2>&1
    [[ -s "$output" ]]
}

ensure_thumb() {
    local asset thumb suffix tmp magick_bin
    asset="$(realpath -m -- "$1")"
    [[ -f "$asset" ]] || return 1
    thumb="$(thumb_path_for "$asset")"
    [[ -f "$thumb" ]] && return 0
    mkdir -p "$THUMBS_DIR"

    suffix="$(suffix_of "$asset")"
    magick_bin="$(command -v magick || command -v convert || true)"
    if [[ -z "$magick_bin" && "$suffix" != gif ]]; then
        warn "ImageMagick is missing; cannot create a thumbnail for $(basename "$asset")"
        return 1
    fi

    tmp="$(mktemp "$SAMPLES_DIR/thumb.XXXXXX.png")"
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN

    if [[ "$suffix" == gif ]]; then
        if ! extract_middle_frame "$asset" "$tmp"; then
            warn "could not extract a frame from $(basename "$asset")"
            return 1
        fi
        if [[ -n "$magick_bin" ]]; then
            "$magick_bin" "$tmp" -thumbnail '512x512^' -gravity center -extent 512x512 -quality 82 "$thumb" >/dev/null 2>&1 || return 1
        else
            ffmpeg -v error -i "$tmp" -vf "scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=#111111" -frames:v 1 -q:v 3 -y "$thumb" >/dev/null 2>&1 || return 1
        fi
    else
        "$magick_bin" "$asset" -thumbnail '512x512^' -gravity center -extent 512x512 -quality 82 "$thumb" >/dev/null 2>&1 || return 1
    fi
    [[ -s "$thumb" ]]
}

ensure_thumbs() {
    local file
    [[ -d "$WALLPAPER_DIR" ]] || return 0
    while IFS= read -r -d '' file; do
        ensure_thumb "$file" || true
    done < <(find "$WALLPAPER_DIR" -maxdepth 1 -type f -print0)
}

list_json() {
    python3 - "$WALLPAPER_DIR" "$THUMBS_DIR" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
thumbs = Path(sys.argv[2])
kinds = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".gif": "gif",
    ".avif": "image",
    ".bmp": "image",
    ".tiff": "image",
}
items = []
if root.is_dir():
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        kind = kinds.get(path.suffix.lower())
        if not kind:
            continue
        mtime = int(path.stat().st_mtime)
        digest = hashlib.sha1(f"{path.resolve()}:{mtime}".encode()).hexdigest()
        thumb = thumbs / f"{digest}.jpg"
        items.append(
            {
                "name": path.name,
                "path": str(path.resolve()),
                "type": kind,
                "thumb": str(thumb if thumb.is_file() else path.resolve()),
            }
        )
print(json.dumps(items, indent=2))
PY
}

read_pref_mode() {
    local pref="$HOME/.local/state/kitty-opacity" value
    if [[ -r "$pref" ]]; then
        value="$(<"$pref")"
        if [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
            if awk -v v="$value" 'BEGIN { exit !(v >= 0.6) }'; then
                printf 'opaque\n'
            else
                printf 'transparent\n'
            fi
            return
        fi
    fi
    printf 'opaque\n'
}

kitty_mode_for_pid() {
    local pid="$1" mode_file="$RUNTIME_DIR/kitty-mode-$1" value
    if [[ -r "$mode_file" ]]; then
        value="$(<"$mode_file")"
        if [[ "$value" == opaque || "$value" == transparent ]]; then
            printf '%s\n' "$value"
            return
        fi
    fi
    read_pref_mode
}

set_kitty_active() {
    local mode="${1:-auto}" variant
    [[ -f "$KITTY_OPAQUE" && -f "$KITTY_TRANSPARENT" ]] || return 1
    if [[ "$mode" == auto ]]; then
        # The opacity preference is what a freshly opened terminal will use,
        # so it is the right default for the include file.
        mode="$(read_pref_mode)"
    fi
    [[ "$mode" == transparent ]] || mode=opaque
    if [[ "$mode" == transparent ]]; then
        variant="$KITTY_TRANSPARENT"
    else
        variant="$KITTY_OPAQUE"
    fi
    ln -sfn "$variant" "$KITTY_ACTIVE"
    printf '%s\n' "$mode" >"$KITTY_MODE_FILE"
}

reload_kitty() {
    local requested="${1:-auto}" only_pid="${2:-}" sock pid mode variant
    command -v kitten >/dev/null 2>&1 || return 0
    [[ -d "$RUNTIME_DIR" ]] || return 0

    while IFS= read -r -d '' sock; do
        [[ -S "$sock" ]] || continue
        pid="${sock##*-}"
        [[ -n "$only_pid" && "$pid" != "$only_pid" ]] && continue
        mode="$requested"
        if [[ "$mode" == auto ]]; then
            mode="$(kitty_mode_for_pid "$pid")"
        fi
        if [[ "$mode" == transparent ]]; then
            variant="$KITTY_TRANSPARENT"
        else
            variant="$KITTY_OPAQUE"
        fi
        [[ -f "$variant" ]] || continue
        if ! kitten @ --to "unix:$sock" set-colors --all --configured "$variant" >/dev/null 2>&1; then
            warn "could not update Kitty colours for socket $sock"
        fi
    done < <(find "$RUNTIME_DIR" -maxdepth 1 -type s -name 'kitty-*' -print0 2>/dev/null)
}

ACTIVE_BACKEND=""

backend_name() {
    if [[ -n "$ACTIVE_BACKEND" ]]; then
        printf '%s\n' "$ACTIVE_BACKEND"
        return 0
    fi
    case "${WALLPAPER_BACKEND:-auto}" in
        awww)
            printf 'awww\n'
            ;;
        hyprpaper)
            printf 'hyprpaper\n'
            ;;
        auto)
            if command -v awww >/dev/null 2>&1 && command -v awww-daemon >/dev/null 2>&1; then
                printf 'awww\n'
            elif command -v hyprpaper >/dev/null 2>&1; then
                printf 'hyprpaper\n'
            else
                printf 'none\n'
            fi
            ;;
        *)
            printf 'none\n'
            ;;
    esac
}

ensure_backend() {
    local backend attempt
    backend="$(backend_name)"
    case "$backend" in
        awww)
            if ! command -v awww >/dev/null 2>&1 || ! command -v awww-daemon >/dev/null 2>&1; then
                if command -v hyprpaper >/dev/null 2>&1; then
                    warn "awww is not installed; falling back to hyprpaper"
                    ACTIVE_BACKEND=hyprpaper
                    ensure_backend
                    return
                fi
                die "awww is not installed and no hyprpaper fallback is available"
            fi
            if ! awww query >/dev/null 2>&1; then
                nohup awww-daemon >/dev/null 2>&1 9>&- &
                for attempt in $(seq 1 50); do
                    awww query >/dev/null 2>&1 && break
                    sleep 0.1
                done
            fi
            if awww query >/dev/null 2>&1; then
                ACTIVE_BACKEND=awww
                # Do not leave a second wallpaper daemon drawing underneath.
                pkill -x hyprpaper >/dev/null 2>&1 || true
                return 0
            fi
            if command -v hyprpaper >/dev/null 2>&1; then
                warn "awww-daemon did not become ready; falling back to hyprpaper"
                ACTIVE_BACKEND=hyprpaper
                ensure_backend
                return
            fi
            die "awww-daemon did not become ready"
            ;;
        hyprpaper)
            command -v hyprpaper >/dev/null 2>&1 || die "hyprpaper is not installed"
            command -v hyprctl >/dev/null 2>&1 || die "hyprctl is not available"
            if ! hyprctl hyprpaper listactive >/dev/null 2>&1; then
                nohup hyprpaper -c "$HOME/.config/hypr/hyprpaper.conf" >/dev/null 2>&1 9>&- &
                for attempt in $(seq 1 50); do
                    hyprctl hyprpaper listactive >/dev/null 2>&1 && break
                    sleep 0.1
                done
            fi
            if hyprctl hyprpaper listactive >/dev/null 2>&1; then
                ACTIVE_BACKEND=hyprpaper
                # Remove an awww layer if one was left over from a previous run.
                pkill -x awww-daemon >/dev/null 2>&1 || true
                return 0
            fi
            die "hyprpaper did not become ready"
            ;;
        *)
            die "no supported wallpaper backend (install awww or hyprpaper)"
            ;;
    esac
}

paint_wallpaper() {
    local file="$1" transition="${2:-none}" backend monitor target
    backend="$(backend_name)"
    case "$backend" in
        awww)
            if ! awww img -a "$file" --resize crop --transition-type "$transition" \
                --transition-duration 0.8 --transition-fps 60 >/dev/null 2>&1; then
                if command -v hyprpaper >/dev/null 2>&1; then
                    warn "awww could not set $(basename "$file"); falling back to hyprpaper"
                    ACTIVE_BACKEND=hyprpaper
                    ensure_backend
                    paint_wallpaper "$file" none
                    return
                fi
                warn "awww could not set $(basename "$file")"
                return 1
            fi
            ;;
        hyprpaper)
            target="$file"
            if [[ "$(suffix_of "$file")" == gif ]]; then
                target="$CACHE_DIR/hyprpaper-frame.png"
                if ! extract_middle_frame "$file" "$target"; then
                    warn "hyprpaper cannot animate GIFs and frame extraction failed"
                    return 1
                fi
                warn "hyprpaper is static-only; $(basename "$file") is shown as a still"
            fi
            while IFS= read -r monitor; do
                [[ -n "$monitor" ]] || continue
                if ! hyprctl hyprpaper wallpaper "$monitor,$target,cover" >/dev/null 2>&1; then
                    warn "hyprpaper could not set $monitor"
                fi
            done < <(hyprctl -j monitors 2>/dev/null | jq -r '.[].name' 2>/dev/null)
            ;;
        *)
            return 1
            ;;
    esac
}

theme_is_current() {
    local file="$1" mtime scene_mode
    [[ -f "$THEME_JSON" ]] || return 1
    mtime="$(stat_mtime "$file")"
    jq -e --arg file "$file" --argjson mtime "$mtime" \
        '.wallpaper == $file and .mtime == $mtime' "$THEME_JSON" >/dev/null 2>&1 || return 1
    scene_mode="${AUTOTHEME_SCENE:-auto}"
    if [[ "$scene_mode" != off ]]; then
        jq -e --argjson version "$SCENE_VERSION" \
            '.scene.version == $version' "$THEME_JSON" >/dev/null 2>&1 || return 1
    fi
    return 0
}

generate_theme() {
    local file="$1" sample="$2" mtime grayscale=false built=0 fallback mode
    local scene_mode="${AUTOTHEME_SCENE:-auto}"
    local matugen_source scheme contrast lightness seed matugen_ok=0
    mtime="$(stat_mtime "$file")"
    rm -f "$ROLES_JSON" "$SEED_PNG"

    local -a vibrant_args=("$sample" -o "$ACCENTS_JSON")
    if [[ "$scene_mode" == off ]]; then
        vibrant_args+=(--scene off)
    else
        vibrant_args+=(--scene "$scene_mode" --seed-out "$SEED_PNG")
    fi
    if ! python3 "$SCRIPT_DIR/lib/vibrant.py" "${vibrant_args[@]}" >>"$LOG_FILE" 2>&1; then
        warn "vibrant.py failed; using the default accent palette"
        printf '{}\n' >"$ACCENTS_JSON"
    fi
    if command -v jq >/dev/null 2>&1 && [[ -s "$ACCENTS_JSON" ]]; then
        grayscale="$(jq -r '.grayscale // false' "$ACCENTS_JSON" 2>/dev/null || echo false)"
    fi

    matugen_source="$sample"
    scheme="scheme-tonal-spot"
    contrast="0"
    lightness="0"
    if [[ "$scene_mode" != off ]] && [[ -s "$ACCENTS_JSON" ]] \
        && command -v jq >/dev/null 2>&1; then
        seed="$(jq -r '.seed // empty' "$ACCENTS_JSON" 2>/dev/null || true)"
        scheme="$(jq -r '.scene.strategy.scheme // "scheme-tonal-spot"' "$ACCENTS_JSON" 2>/dev/null || echo scheme-tonal-spot)"
        contrast="$(jq -r '.scene.strategy.contrast // 0' "$ACCENTS_JSON" 2>/dev/null || echo 0)"
        lightness="$(jq -r '.scene.strategy.lightnessDark // 0' "$ACCENTS_JSON" 2>/dev/null || echo 0)"
        if [[ -n "$seed" && -s "$SEED_PNG" ]]; then
            matugen_source="$SEED_PNG"
        fi
    fi
    case "$scheme" in
        scheme-content|scheme-expressive|scheme-fidelity|scheme-fruit-salad|\
        scheme-monochrome|scheme-neutral|scheme-rainbow|scheme-tonal-spot|\
        scheme-vibrant|scheme-smart)
            ;;
        *)
            scheme="scheme-tonal-spot"
            ;;
    esac

    if [[ "${AUTOTHEME_MATUGEN:-auto}" != never ]] \
        && command -v matugen >/dev/null 2>&1 \
        && [[ "$grayscale" != true ]]; then
        cat >"$CACHE_DIR/matugen.toml" <<EOF
[config]
version_check = false

[templates.roles]
input_path = "$SCRIPT_DIR/templates/matugen-roles.json"
output_path = "$ROLES_JSON"
EOF
        local -a matugen_args=(
            image "$matugen_source" -m dark -t "$scheme"
            --source-color-index 0 -c "$CACHE_DIR/matugen.toml" -q
        )
        if awk -v value="$contrast" 'BEGIN { exit !(value != 0) }'; then
            matugen_args+=(--contrast "$contrast")
        fi
        if awk -v value="$lightness" 'BEGIN { exit !(value != 0) }'; then
            matugen_args+=(--lightness-dark "$lightness")
        fi

        if matugen "${matugen_args[@]}" >>"$LOG_FILE" 2>&1 \
            && [[ -s "$ROLES_JSON" ]] \
            && jq -e . "$ROLES_JSON" >/dev/null 2>&1; then
            matugen_ok=1
        elif [[ "$matugen_source" != "$sample" ]]; then
            warn "matugen rejected the scene seed; retrying with the wallpaper"
            rm -f "$ROLES_JSON"
            local -a retry_args=("${matugen_args[@]}")
            retry_args[1]="$sample"
            if matugen "${retry_args[@]}" >>"$LOG_FILE" 2>&1 \
                && [[ -s "$ROLES_JSON" ]] \
                && jq -e . "$ROLES_JSON" >/dev/null 2>&1; then
                matugen_ok=1
            fi
        fi

        if [[ "$matugen_ok" -eq 1 ]]; then
            if python3 "$SCRIPT_DIR/lib/build_theme.py" \
                --wallpaper "$file" --mtime "$mtime" \
                --roles "$ROLES_JSON" --accents "$ACCENTS_JSON" \
                -o "$THEME_JSON" --compat "$THEME_COMPAT" >>"$LOG_FILE" 2>&1; then
                built=1
            fi
        else
            warn "matugen failed; using the static dark fallback"
        fi
    fi

    if [[ "$built" -eq 0 ]]; then
        mode=dark
        [[ "$grayscale" == true ]] && mode=neutral
        if ! python3 "$SCRIPT_DIR/lib/build_theme.py" \
            --wallpaper "$file" --mtime "$mtime" \
            --accents "$ACCENTS_JSON" --fallback "$mode" \
            -o "$THEME_JSON" --compat "$THEME_COMPAT" >>"$LOG_FILE" 2>&1; then
            warn "could not build a theme document"
            return 1
        fi
    fi

    if [[ "$built" -eq 1 && "$scene_mode" != off ]] \
        && command -v jq >/dev/null 2>&1; then
        log_line "scene scheme=$scheme tags=$(jq -r '(.scene.tags // []) | map(.name) | join(",")' "$ACCENTS_JSON" 2>/dev/null || true)"
    fi

    jq -e '.bg and .accent and .fg' "$THEME_JSON" >/dev/null 2>&1 || {
        warn "generated theme.json is incomplete"
        return 1
    }
}

render_all() {
    python3 "$SCRIPT_DIR/lib/render.py" --theme "$THEME_JSON" >>"$LOG_FILE" 2>&1 || return 1
    if [[ "${AUTOTHEME_DUNST:-1}" != 1 ]]; then
        rm -f "$DUNST_DROPIN"
    fi
}

apply_borders() {
    local accent border current desired
    command -v hyprctl >/dev/null 2>&1 || return 0
    [[ -f "$THEME_JSON" ]] || return 0
    accent="$(jq -r '.accent // empty' "$THEME_JSON" 2>/dev/null || true)"
    border="$(jq -r '.border // empty' "$THEME_JSON" 2>/dev/null || true)"
    [[ -n "$accent" && -n "$border" ]] || return 0

    current="$(hyprctl getoption general:col.active_border -j 2>/dev/null | jq -r '.gradient // empty' 2>/dev/null || true)"
    desired="ff${accent#\#} 0deg"
    if [[ "$current" == "$desired" ]]; then
        current="$(hyprctl getoption general:col.inactive_border -j 2>/dev/null | jq -r '.gradient // empty' 2>/dev/null || true)"
        [[ "$current" == "ff${border#\#} 0deg" ]] && return 0
    fi

    # Hyprland 0.56 uses the Lua parser: keywords are unreachable, so use
    # hl.config through hyprctl eval.
    hyprctl eval "hl.config({ general = { [\"col.active_border\"] = \"rgba(${accent#\#}ff)\", [\"col.inactive_border\"] = \"rgba(${border#\#}ff)\" } })" >/dev/null 2>&1 || true
}

reload_waybar() {
    if [[ -x "$SCRIPT_DIR/waybar-scale.py" ]]; then
        "$SCRIPT_DIR/waybar-scale.py" apply >>"$LOG_FILE" 2>&1 || warn "waybar-scale.py failed"
    fi
}

reload_dunst() {
    command -v dunstctl >/dev/null 2>&1 || return 0
    pgrep -x dunst >/dev/null 2>&1 || return 0
    if [[ "${AUTOTHEME_DUNST:-1}" != 1 ]]; then
        dunstctl reload >/dev/null 2>&1 || true
        return 0
    fi
    dunstctl reload >/dev/null 2>&1 || warn "dunstctl reload failed"
}

apply_live() {
    set_kitty_active auto || true
    apply_borders
    reload_waybar
    reload_kitty auto
    reload_dunst
}

default_wallpaper() {
    local candidate
    if [[ -r "$STATE_FILE" ]]; then
        candidate="$(<"$STATE_FILE")"
        if [[ -f "$candidate" ]]; then
            realpath -m -- "$candidate"
            return 0
        fi
    fi
    for candidate in \
        "$WALLPAPER_DIR/wallpaper.png" \
        "$WALLPAPER_DIR/wallpaper.jpg" \
        "$HOME/Pictures/wallpaper.png"; do
        if [[ -f "$candidate" ]]; then
            realpath -m -- "$candidate"
            return 0
        fi
    done
    candidate="$(find "$WALLPAPER_DIR" -maxdepth 1 -type f -printf '%f\t%p\n' 2>/dev/null | sort | head -n1 | cut -f2-)"
    [[ -n "$candidate" ]] && realpath -m -- "$candidate"
}

notify_wallpaper() {
    local file="$1" thumb
    [[ "${AUTOTHEME_NOTIFY:-0}" == 1 ]] || return 0
    command -v notify-send >/dev/null 2>&1 || return 0
    thumb="$(thumb_path_for "$file")"
    if [[ -f "$thumb" ]]; then
        notify-send -a autotheme -i "$thumb" "Wallpaper" "$(basename "$file")" >/dev/null 2>&1 || true
    else
        notify-send -a autotheme "Wallpaper" "$(basename "$file")" >/dev/null 2>&1 || true
    fi
}

doctor() {
    local backend
    backend="$(backend_name)"
    printf 'autotheme doctor\n'
    printf '  wallpaper dir : %s\n' "$WALLPAPER_DIR"
    printf '  thumbs dir    : %s\n' "$THUMBS_DIR"
    printf '  cache dir     : %s\n' "$CACHE_DIR"
    printf '  backend       : %s\n' "$backend"
    printf '  theme.json    : %s\n' "$([[ -f "$THEME_JSON" ]] && echo present || echo missing)"
    printf '  wallpaper     : %s\n' "$(default_wallpaper || echo missing)"
    printf '  scene mode    : %s\n' "${AUTOTHEME_SCENE:-auto}"
    for command in matugen awww awww-daemon hyprpaper hyprctl jq python3 kitten dunstctl waybar wofi magick ffmpeg; do
        if command -v "$command" >/dev/null 2>&1; then
            printf '  %-13s : %s\n' "$command" "$(command -v "$command")"
        else
            printf '  %-13s : missing\n' "$command"
        fi
    done
    if python3 -c 'import PIL' >/dev/null 2>&1; then
        printf '  pillow        : ok\n'
    else
        printf '  pillow        : missing\n'
    fi
    if [[ -f "$THEME_JSON" ]] && command -v jq >/dev/null 2>&1; then
        printf '  accent        : %s\n' "$(jq -r '.accent' "$THEME_JSON" 2>/dev/null || echo '?')"
        printf '  background    : %s\n' "$(jq -r '.bg' "$THEME_JSON" 2>/dev/null || echo '?')"
    fi
    if [[ -s "$ACCENTS_JSON" ]] && command -v jq >/dev/null 2>&1; then
        printf '  scene tags    : %s\n' "$(jq -r '(.scene.tags // []) | map(.name) | join(",")' "$ACCENTS_JSON" 2>/dev/null || true)"
        printf '  scene scheme  : %s\n' "$(jq -r '.scene.strategy.scheme // "?"' "$ACCENTS_JSON" 2>/dev/null || echo '?')"
        printf '  scene seed    : %s\n' "$(jq -r '.seed // "?"' "$ACCENTS_JSON" 2>/dev/null || echo '?')"
    fi
}
