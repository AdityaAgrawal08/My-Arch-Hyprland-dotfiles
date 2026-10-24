#!/usr/bin/env bash
# One-pass wallpaper + autotheme pipeline for Hyprland.
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

usage() {
    cat <<'EOF'
usage: wallpaper_switch.sh <command> [args]

  apply <file> [transition]   Set a wallpaper and regenerate the theme
  restore                     Restore the last wallpaper/theme (used at login)
  regenerate                  Rebuild the theme from the current wallpaper
  pick                        Open the Wofi wallpaper picker
  borders                     Re-apply Hyprland border colours
  kitty-mode [--pid PID] MODE Switch Kitty between opaque|transparent|auto
  list-json                   List supported wallpapers as JSON
  ensure-thumbs               Generate missing wallpaper thumbnails
  init                        Seed generated files without touching the session
  doctor                      Print dependency and state diagnostics
EOF
}

random_transition() {
    local -a choices=(wave wipe)
    printf '%s\n' "${choices[RANDOM % ${#choices[@]}]}"
}

sample_for() {
    local file="$1" suffix sample hash
    suffix="$(suffix_of "$file")"
    case "$suffix" in
        gif)
            hash="$(sha1_text "$(realpath -m -- "$file"):$(stat_mtime "$file")")"
            sample="$SAMPLES_DIR/frame-$hash.png"
            if [[ ! -s "$sample" ]]; then
                extract_middle_frame "$file" "$sample" || return 1
            fi
            printf '%s\n' "$sample"
            ;;
        *)
            printf '%s\n' "$file"
            ;;
    esac
}

apply_wallpaper() {
    local file="$1" transition="$2" sample
    cache_init

    if [[ "$transition" == random ]]; then
        transition="$(random_transition)"
    fi

    paint_wallpaper "$file" "$transition" || warn "the wallpaper backend failed; continuing with theming"

    printf '%s\n' "$file" >"$STATE_FILE"
    printf '%s\n' "$file" >"$CACHE_ROOT/wallpaper_state"

    if ! sample="$(sample_for "$file")" || [[ -z "$sample" ]]; then
        sample="$file"
        warn "could not extract a middle frame; sampling the whole file"
    fi

    if theme_is_current "$file" && [[ "${AUTOTHEME_FORCE:-0}" != 1 ]]; then
        log_line "palette unchanged for $file; skipping matugen"
    else
        if generate_theme "$file" "$sample"; then
            log_line "generated palette for $file"
        else
            warn "theme generation failed; keeping the previous palette"
        fi
    fi

    if render_all; then
        log_line "rendered autotheme outputs"
    else
        warn "template rendering failed"
    fi

    apply_live
    notify_wallpaper "$file"
}

cmd_apply() {
    local file="${1:-}" transition="${2:-${WALLPAPER_TRANSITION:-random}}"
    [[ -n "$file" ]] || die "apply needs a wallpaper path"
    file="$(realpath -m -- "$file")"
    [[ -f "$file" ]] || die "not a file: $file"
    is_supported "$file" || die "unsupported wallpaper type: ${file##*.}"

    cache_init
    acquire_lock
    ensure_backend
    apply_wallpaper "$file" "$transition"
}

cmd_restore() {
    local file
    cache_init
    acquire_lock
    ensure_backend

    file="$(default_wallpaper || true)"
    [[ -n "$file" ]] || die "no wallpaper found in $WALLPAPER_DIR"

    printf '%s\n' "$file" >"$STATE_FILE"
    printf '%s\n' "$file" >"$CACHE_ROOT/wallpaper_state"

    if theme_is_current "$file"; then
        render_all || warn "could not render the cached theme"
        paint_wallpaper "$file" none || warn "could not restore the wallpaper"
        apply_live
        log_line "restored $file"
    else
        apply_wallpaper "$file" none
    fi
}

cmd_regenerate() {
    local file sample
    cache_init
    acquire_lock
    file="$(default_wallpaper || true)"
    [[ -n "$file" ]] || die "no wallpaper found in $WALLPAPER_DIR"
    sample="$(sample_for "$file" || printf '%s' "$file")"
    generate_theme "$file" "$sample" || die "theme generation failed"
    render_all || die "template rendering failed"
    apply_live
    log_line "regenerated theme for $file"
}

cmd_kitty_mode() {
    local pid="" mode
    if [[ "${1:-}" == --pid ]]; then
        pid="${2:-}"
        shift 2 || true
    fi
    mode="${1:-auto}"
    [[ "$mode" =~ ^(opaque|transparent|auto)$ ]] || die "kitty-mode expects opaque, transparent or auto"
    cache_init
    set_kitty_active "$mode" || die "Kitty colour files are missing; run wallpaper_switch.sh init"
    reload_kitty "$mode" "$pid"

    if [[ "$mode" != auto ]]; then
        if [[ -n "$pid" ]]; then
            printf '%s\n' "$mode" >"$RUNTIME_DIR/kitty-mode-$pid"
        else
            while IFS= read -r -d '' sock; do
                [[ -S "$sock" ]] || continue
                printf '%s\n' "$mode" >"$RUNTIME_DIR/kitty-mode-${sock##*-}"
            done < <(find "$RUNTIME_DIR" -maxdepth 1 -type s -name 'kitty-*' -print0 2>/dev/null)
        fi
    fi

    log_line "kitty mode: $mode${pid:+ (pid $pid)}"
}

cmd_init() {
    local file sample
    cache_init

    if [[ ! -f "$THEME_JSON" ]]; then
        file="$(default_wallpaper || true)"
        if [[ -n "$file" ]]; then
            sample="$(sample_for "$file" || printf '%s' "$file")"
            generate_theme "$file" "$sample" || die "could not create the initial theme"
        else
            python3 "$SCRIPT_DIR/lib/build_theme.py" --fallback dark \
                --wallpaper "" --mtime 0 -o "$THEME_JSON" --compat "$THEME_COMPAT" \
                || die "could not create the fallback theme"
        fi
    fi

    if [[ -z "$(default_wallpaper 2>/dev/null || true)" ]]; then
        warn "no wallpaper found in $WALLPAPER_DIR"
    elif [[ ! -f "$STATE_FILE" ]]; then
        file="$(default_wallpaper)"
        printf '%s\n' "$file" >"$STATE_FILE"
        printf '%s\n' "$file" >"$CACHE_ROOT/wallpaper_state"
    fi

    render_all || die "could not render the initial theme"
    set_kitty_active auto || true
    log_line "initialized autotheme"
}

cmd_list_json() {
    cache_init
    list_json
}

cmd_ensure_thumbs() {
    cache_init
    ensure_thumbs
}

cmd_doctor() {
    cache_init
    doctor
}

main() {
    local command="${1:-}"
    shift || true
    case "$command" in
        apply)
            cmd_apply "$@"
            ;;
        restore)
            cmd_restore
            ;;
        regenerate)
            cmd_regenerate
            ;;
        pick)
            exec "$SCRIPT_DIR/wallpaper_picker.sh" "$@"
            ;;
        borders)
            cache_init
            apply_borders
            ;;
        kitty-mode)
            cmd_kitty_mode "$@"
            ;;
        list-json)
            cmd_list_json
            ;;
        ensure-thumbs)
            cmd_ensure_thumbs
            ;;
        init)
            cmd_init
            ;;
        doctor)
            cmd_doctor
            ;;
        help|-h|--help|"")
            usage
            ;;
        *)
            usage >&2
            die "unknown command: $command"
            ;;
    esac
}

main "$@"
