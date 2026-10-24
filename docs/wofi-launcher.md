# Wofi Launcher

**Status:** Verified for configuration, generated CSS parsing, and launcher
startup. Picker selection and confirmation dialog were inspected but not driven
end-to-end.

## Purpose

Defines the Wofi-based application launcher, browser picker, wallpaper picker,
power menu, and terminal close-confirmation dialog.

## Scope

In scope:

- Main Wofi configuration.
- Generated and static stylesheets.
- `browser-launcher.sh`.
- `power-menu.sh`.
- `confirm_close.sh`.
- Wallpaper picker integration.

Out of scope:

- Wofi upstream behavior.
- Application `.desktop` file maintenance.
- Theme palette generation (see
  [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)).

## Files and paths

| Path | Role |
| --- | --- |
| `wofi/.config/wofi/config` | Main config |
| `wofi/.config/wofi/style.css` | Static fallback stylesheet |
| `wofi/.config/wofi/confirm.css` | Static fallback confirmation stylesheet |
| `wofi/.config/wofi/browser-launcher.sh` | Zen/Brave/Firefox picker |
| `hypr/.config/hypr/scripts/templates/wofi.css` | Generated main stylesheet template |
| `hypr/.config/hypr/scripts/templates/wofi-confirm.css` | Generated confirmation template |
| `hypr/.config/hypr/scripts/wallpaper_picker.sh` | Wallpaper picker |
| `hypr/.config/hypr/scripts/power-menu.sh` | Power menu |
| `hypr/.config/hypr/scripts/confirm_close.sh` | Close confirmation |
| `~/.cache/autotheme/wofi.css` | Generated main stylesheet |
| `~/.cache/autotheme/wofi-confirm.css` | Generated confirmation stylesheet |

## Main configuration

```ini
width=800 height=600 location=center show=drun prompt=Search... allow_markup=true no_actions=true halign=fill orientation=vertical content_halign=fill
no_sort=true
matching=none
style=/home/aditya/.cache/autotheme/wofi.css
```

Behavior:

- Default mode: `drun`.
- `matching=none` disables filtering unless a command overrides it.
- `no_sort=true`; callers control ordering.
- `style=` points to the generated autotheme stylesheet.
- `allow_markup=true` enables Pango markup.

## Generated versus static styles

The tracked `wofi/style.css` and `wofi/confirm.css` are Everforest fallbacks.
They are not loaded while the generated files exist.

- Main Wofi loads `~/.cache/autotheme/wofi.css`.
- `confirm_close.sh` passes
  `-s "$HOME/.cache/autotheme/wofi-confirm.css"`.

### Generated main stylesheet

| Selector | Styling |
| --- | --- |
| `window` | `@border`, `@bg`, radius 10 |
| `#outer-box` | 6 px margin, 10 px padding, transparent |
| `#input` | 8 px margin, 6 px padding, 1 px `@border`, `@surface`, `@fg`, radius 8 |
| `#entry` | 4×6 px padding, radius 6, transparent |
| `#text` | 4 px margin, `@fg` |
| `#entry:selected` | `@accent` background |
| `#text:selected` | `@onAccent`, bold |
| scrollbar slider | `@surfaceHigh`, radius 4 |

### Generated confirmation stylesheet

| Selector | Styling |
| --- | --- |
| `*` | Adwaita Sans/Noto Sans, 12 px, `@fg` |
| `window` | `@border`, `@bg`, radius 12 |
| `#input` | `@surface`, `@fg`, bold 13 px, no caret |
| `#entry` | `@surface`, `@border`, radius 7 |
| `#text` | 12 px bold `@fg` |
| first button (NO) | `@critical` background/border, `@onCritical` text |
| last button (YES) | `@accent` background/border, `@onAccent` text |
| `#entry:selected` | 2 px `@bright` ring |
| scrollbar | transparent |

## Application launcher

`SUPER+R` executes:

```bash
wofi --show drun
```

Uses the main configuration and generated stylesheet.

## Browser picker

`browser-launcher.sh`:

```bash
ZEN="/opt/zen-browser-bin/zen-bin"
BRAVE="/usr/bin/brave"
FIREFOX="/usr/bin/firefox"

choice=$(printf "Zen\nBrave\nFirefox" | wofi --dmenu --prompt="Choose browser: ")

case "$choice" in
    Zen) "$ZEN" & ;;
    Brave) "$BRAVE" & ;;
    Firefox) "$FIREFOX" & ;;
esac
```

Bound to `SUPER+B`.

Properties:

- No shebang; Hyprland executes it through a shell. Direct `execve` use may
  fail.
- Browser paths are hardcoded.
- Empty selection does nothing.

## Power menu

`power-menu.sh`:

- Options: Lock, Sleep, Restart, Shutdown.
- Runs:
  ```bash
  wofi --dmenu --prompt "Power Menu" --no-sort --matching=none
  ```
- Logs the selection to `/tmp/power-menu.log`.
- Lock: close sound, `hyprlock`, wait 2.5 s, open sound.
- Sleep: close sound, `hyprlock`, wait 0.5 s, `systemctl suspend`.
- Restart/Shutdown: `systemctl reboot` / `poweroff`.
- Runs `pkill wofi` before acting.

Sound files are expected at:

```text
/home/aditya/Downloads/close.wav
/home/aditya/Downloads/open.wav
```

## Close confirmation

`confirm_close.sh` uses Wofi for busy terminals:

```bash
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
    -s "$HOME/.cache/autotheme/wofi-confirm.css")
```

Behavior:

- Two columns.
- No search box.
- Single click.
- Normal window (`-n`).
- No cache (`-k /dev/null`).
- Uses the generated confirmation stylesheet.
- `YES` closes the active window via Hyprland’s Lua dispatcher.

The full process-tree and lock logic is documented in
[hyprland-automation-scripts.md](hyprland-automation-scripts.md).

## Wallpaper picker

`wallpaper_picker.sh` runs:

```bash
wofi --dmenu \
  --allow-images \
  --insensitive \
  --prompt "Wallpaper" \
  --define=image_size=48 \
  --define=parse_action=true \
  --matching=contains
```

Entries are:

```text
img:<thumb>:text:<index>. <name>
```

The picker maps the numeric index back to the source path and executes
`wallpaper_switch.sh apply <path>`. Details are in
[autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md).

## Dependencies

- `wofi`
- `bash`/`sh`
- GTK3
- `jq` for the wallpaper picker
- `hyprctl` for power/confirmation actions
- `mpv`, `hyprlock`, `systemctl` for the power menu
- `notify-send` for the empty-library notice

## Reproduction

```bash
sudo pacman -S --needed wofi jq

cd ~/dotfiles
stow --target="$HOME" --no-folding wofi
~/.config/hypr/scripts/wallpaper_switch.sh init

wofi --show drun
```

## Verification

Verified:

- `wofi --show drun` starts without CSS parser errors.
- `~/.cache/autotheme/wofi.css` and `wofi-confirm.css` parse through GTK3’s
  `Gtk.CssProvider`.
- `wofi/config` points at the generated stylesheet.
- `confirm_close.sh` uses the generated confirmation stylesheet.

Not verified:

- Wallpaper picker selection through the UI.
- Power menu actions and sound playback.
- Confirmation dialog interaction.

## Known limitations

- `wofi/style.css` and `wofi/confirm.css` are inactive static fallbacks.
- The `style=` and confirmation `-s` paths hardcode `/home/aditya` and
  `$HOME/.cache/autotheme`.
- `browser-launcher.sh` has no shebang and hardcoded browser paths.
- `power-menu.sh` hardcodes sound paths and does not handle missing files.
- `matching=none` disables filtering in the default launcher unless overridden.
- Wofi does not live-reload styles; changes appear on the next launch.

## Related documentation

- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [hyprland-automation-scripts.md](hyprland-automation-scripts.md)
- [hyprland-configuration.md](hyprland-configuration.md)
