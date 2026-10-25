# Waybar Status Bar

**Status:** Verified for configuration, generated CSS parsing, and live startup.

## Purpose

Provides the top status bar: Hyprland workspaces, clock/date, battery, audio,
backlight, keyboard state, MPD, and system tray. It is also a primary consumer
of the autotheme palette.

## Scope

In scope:

- `config.jsonc`
- `style.css`
- `bluetooth.sh`
- `waybar-scale.py`
- Generated Waybar CSS.

Out of scope:

- Waybar upstream behavior.
- Other bar implementations.
- Autotheme palette generation (see
  [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)).

## Architecture

Waybar is not launched directly. It is launched by:

```bash
~/.config/hypr/scripts/waybar-scale.py start
```

The script:

1. Reads the focused monitor scale from `hyprctl -j monitors`.
2. Scales every `Npx` value in `~/.config/waybar/style.css` by
   `1.5 / current_scale`.
3. Prepends the generated palette from `~/.cache/autotheme/waybar.css`.
4. Writes `~/.cache/waybar/style.css`.
5. Executes `waybar -s ~/.cache/waybar/style.css`.

`waybar-scale.py apply` performs the same generation and sends `SIGUSR2`.

## Files and paths

| Path | Role |
| --- | --- |
| `waybar/.config/waybar/config.jsonc` | Module layout and options |
| `waybar/.config/waybar/style.css` | Tokenized GTK CSS |
| `waybar/.config/waybar/bluetooth.sh` | Bluetooth JSON provider |
| `hypr/.config/hypr/scripts/waybar-scale.py` | Scaling, palette injection, reload |
| `hypr/.config/hypr/scripts/templates/waybar.css` | Generated color block template |
| `~/.cache/autotheme/waybar.css` | Generated `@define-color` block |
| `~/.cache/waybar/style.css` | Generated scaled stylesheet |

## Module layout

```jsonc
{
  "height": 2,
  "spacing": 4,
  "modules-left": [
    "hyprland/workspaces",
    "sway/mode",
    "sway/scratchpad",
    "custom/media"
  ],
  "modules-center": ["clock", "battery"],
  "modules-right": [
    "mpd",
    //"idle_inhibitor",
    "pulseaudio",
    "backlight",
    "keyboard-state",
    "sway/language",
    "tray"
  ]
}
```

### Active modules

| Module | Behavior |
| --- | --- |
| `hyprland/workspaces` | All outputs, no scroll; format `{name}: {icon}`, focused `{name}: `, urgent `{name}: ` |
| `clock` | `HH:MM  |  DD-MM-YYYY`; calendar tooltip |
| `battery` | Capacity/icons; charging/plugged/full variants; states good 80, warning 30, critical 20 |
| `mpd` | Now-playing status with consume/random/repeat/single icons; 5 s interval |
| `pulseaudio` | Volume/mic, Bluetooth and muted variants; click opens `pavucontrol` |
| `backlight` | Percent and icon |
| `keyboard-state` | Num Lock and Caps Lock indicators |
| `sway/language` | Configured keyboard-layout module; expected to be inert on Hyprland |
| `tray` | System tray with 10 px spacing |
| `custom/media` | Configured, but its `exec` script is missing |
| `sway/mode` | Configured; expected to be inert on Hyprland |
| `sway/scratchpad` | Configured; expected to be inert on Hyprland |

### Defined but inactive modules

These keys exist in `config.jsonc` but are not referenced by any `modules-*`
array:

- `hyprland/mode`
- `battery#bat2`
- `cpu`
- `memory`
- `idle_inhibitor`
- `custom/bluetooth`

To activate a module, add its key to the relevant `modules-*` array.

## Bluetooth provider

`bluetooth.sh` outputs Waybar JSON:

```bash
if ! bluetoothctl show | grep -q "Powered: yes"; then
    echo '{"text":" off","tooltip":"Bluetooth powered off"}'
    exit 0
fi

connected_device=$(bluetoothctl devices Connected | head -n 1)
if [[ -n "$connected_device" ]]; then
    name=$(echo "$connected_device" | cut -d ' ' -f3-)
    echo "{\"text\":\" $name\",\"tooltip\":\"Bluetooth connected\"}"
    exit 0
fi

echo '{"text":"","tooltip":"Bluetooth on (no device connected)"}'
```

`custom/bluetooth` is defined but not active, so this script is not currently
executed by Waybar.

## Styling

`style.css` uses GTK color references.

| Token | Meaning |
| --- | --- |
| `@bg` | Bar background |
| `@surface` | Module card background |
| `@surface_high` | Defined but unused |
| `@border` | Card/bar border |
| `@fg` | Main text |
| `@muted` | Inactive workspace text |
| `@hover` | Hover surface |
| `@accent` | Active workspace background |
| `@accent_soft` | Defined but unused |
| `@on_accent` | Active workspace text |
| `@critical` | Urgent workspace background |
| `@on_critical` | Urgent workspace text |
| `@bright` | Hover text |

Key rules:

- Global font: `Adwaita Sans`, `Noto Sans`, sans-serif; 11 px; `@fg`.
- Bar: `@bg`; bottom border `@border`.
- Module cards: `@surface`, 1 px `@border`, radius 8, padding 2×12, margin 4.
- Inactive workspace: `@muted`.
- Workspace hover: `@fg` on `@hover`.
- Active workspace: `@on_accent` on `@accent`.
- Urgent workspace: `@on_critical` on `@critical`.
- Clock/battery form a joined center pill.
- Module hover: `@hover` background, `@bright` text.

Generated palette block:

```css
@define-color bg ...;
@define-color surface ...;
@define-color surface_high ...;
@define-color border ...;
@define-color fg ...;
@define-color muted ...;
@define-color hover ...;
@define-color accent ...;
@define-color accent_soft ...;
@define-color on_accent ...;
@define-color critical ...;
@define-color on_critical ...;
@define-color bright ...;
```

Fallback palette used when `waybar.css` is missing:

```css
@define-color bg #101010;
@define-color surface #1a1a1a;
@define-color surface_high #242424;
@define-color border #3a3a3a;
@define-color fg #e6e6e6;
@define-color muted #9a9a9a;
@define-color hover #242424;
@define-color accent #d0d0d0;
@define-color accent_soft #a8a8a8;
@define-color on_accent #111111;
@define-color critical #ff6b6b;
@define-color on_critical #111111;
@define-color bright #ffffff;
```

## Scaling

- Base scale: `1.5`.
- Ratio: `1.5 / focused_monitor_scale`.
- Every `Npx` in the source stylesheet is multiplied by the ratio and written
  with two decimals.
- At scale 1.5, output matches source sizes.
- At scale 1.0, values grow 1.5× physically.
- At scale 2.0, values shrink.

`ui-scale.py` changes the monitor scale and calls `waybar-scale.py apply`.

## Dependencies

- `waybar`
- `hyprctl` (Hyprland)
- `jq` for module/script helpers
- `bluetoothctl` for the Bluetooth provider
- `pavucontrol` for pulseaudio click action
- `playerctl`/MPD for the MPD module
- Nerd Fonts: `ttf-jetbrains-mono-nerd`, `ttf-firacode-nerd`,
  `woff2-font-awesome`
- `Adwaita Sans` and `Noto Sans`

## Reproduction

```bash
sudo pacman -S --needed waybar jq playerctl pavucontrol bluez-utils

cd ~/dotfiles
stow --target="$HOME" --no-folding waybar
stow --target="$HOME" --no-folding hypr

~/.config/hypr/scripts/wallpaper_switch.sh init
~/.config/hypr/scripts/waybar-scale.py start
```

Do not start plain `waybar`; the source stylesheet contains undefined `@`
tokens unless the generated palette is prepended.

## Verification

```bash
pgrep -a waybar
head -20 ~/.cache/waybar/style.css

python3 - <<'PY'
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
p = Gtk.CssProvider()
p.load_from_path("/home/aditya/.cache/waybar/style.css")
print("waybar css ok")
PY
```

Verified on the reference deployment:

- Waybar remains running after `SIGUSR2`.
- Generated CSS parses through GTK3.
- The cache begins with the generated `@define-color` block.

## Known limitations

- `custom/media` references
  `$HOME/.config/waybar/mediaplayer.py`, which is absent.
- `custom/bluetooth` is not active.
- `sway/mode`, `sway/scratchpad`, and `sway/language` are Sway-oriented and
  expected to be inert on Hyprland; `hyprland/language` is the appropriate
  keyboard-layout module.
- `hyprland/mode`, `battery#bat2`, `cpu`, `memory`, and `idle_inhibitor` are
  inactive configuration.
- Bar CSS is valid only when launched through `waybar-scale.py`.
- `waybar-scale.py` requires a live Hyprland session.
- Layout is tuned for 1920×1080 at scale 1.5.

## Related documentation

- [hyprland-configuration.md](hyprland-configuration.md)
- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [hyprland-automation-scripts.md](hyprland-automation-scripts.md)
