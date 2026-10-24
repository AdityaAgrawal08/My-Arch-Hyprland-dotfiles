# Notifications, GTK, and Lock Screen

**Status:** Dunst, GTK, and Hyprlock configuration verified. Hyprlock visual
override not exercised. SDDM/GRUB documented as observed, not integrated.

## Purpose

Defines the desktop surfaces that consume the autotheme palette through native
inclusion mechanisms:

- Dunst through a drop-in file.
- GTK 3/4 through CSS `@import`.
- Hyprlock through `source`.
- Observed SDDM Maya and GRUB state.

## Scope

In scope:

- `dunst/.config/dunst/dunstrc`
- `dunst` generated drop-in
- `gtk/.config/gtk-3.0/` and `gtk-4.0/`
- `hyprlock.conf` and generated lock colors
- SDDM Maya and GRUB as installed system components

Out of scope:

- Dunst upstream features beyond the configured options.
- GTK theme development.
- SDDM/GRUB deployment automation; none exists in this repository.

## Dunst

### Files and paths

| Path | Role |
| --- | --- |
| `dunst/.config/dunst/dunstrc` | Base configuration |
| `hypr/.config/hypr/scripts/templates/dunst-colors.conf` | Generated color template |
| `~/.config/dunst/dunstrc.d/autotheme.conf` | Generated drop-in |
| `/usr/lib/systemd/user/dunst.service` | Packaged D-Bus service |
| `~/.cache/autotheme/theme.json` | Palette source |

### Service

The Arch package provides a D-Bus-activated user service:

```ini
[Unit]
Description=Dunst notification daemon
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=dbus
BusName=org.freedesktop.Notifications
ExecStart=/usr/bin/dunst
ExecReload=/usr/bin/dunstctl reload
```

On the reference deployment, `dunst.service` is `static` and active.

### Base configuration

Key global settings:

```ini
[global]
    monitor = 0
    follow = none
    width = 300
    height = (0, 300)
    origin = top-right
    offset = (10, 50)
    scale = 0
    notification_limit = 20
    progress_bar = true
    separator_height = 2
    padding = 8
    horizontal_padding = 8
    frame_width = 1
    frame_color = "#3d484d"
    gap_size = 0
    separator_color = frame
    sort = yes
    font = Adwaita Sans 11
    markup = full
    format = "<b>%s</b>\n%b"
    alignment = left
    vertical_alignment = center
    ellipsize = middle
    icon_theme = Adwaita
    icon_position = left
    min_icon_size = 32
    max_icon_size = 128
    history_length = 20
    corner_radius = 10
    mouse_left_click = close_current
    mouse_middle_click = do_action, close_current
    mouse_right_click = close_all
```

Base urgency colors:

| Section | Background | Foreground | Frame | Timeout |
| --- | --- | --- | --- | --- |
| `urgency_low` | `#2b3339` | `#859289` | `#3d484d` | 10 |
| `urgency_normal` | `#2b3339` | `#d3c6aa` | `#a7c080` | 10 |
| `urgency_critical` | `#2b3339` | `#d3c6aa` | `#e67e80` | 0 |

There is a `[battery-notify]` rule:

```ini
[battery-notify]
    appname = "Battery Monitor"
    show_age_threshold = -1
```

`show_age_threshold` is a global setting. Dunst logs:

```text
WARNING: Setting show_age_threshold is in the wrong section (battery-notify, should be global)
```

on reload. The intended per-application behavior is not fully applied.

### Generated drop-in

`render.py` writes:

```ini
[global]
    frame_color = "<border>"
    highlight = "<accent>"

[urgency_low]
    background = "<bg>"
    foreground = "<muted>"
    frame_color = "<border>"

[urgency_normal]
    background = "<bg>"
    foreground = "<fg>"
    frame_color = "<accent>"

[urgency_critical]
    background = "<bg>"
    foreground = "<fg>"
    frame_color = "<critical>"
```

Load order:

1. `~/.config/dunst/dunstrc`
2. `~/.config/dunst/dunstrc.d/*.conf` in lexical order

The drop-in overrides only color keys. `wallpaper_switch.sh` calls
`dunstctl reload`. Dunst’s message “Reloading settings (with the old files)”
means it reloads the same paths, including the drop-in.

If `AUTOTHEME_DUNST=0`, `render_all()` removes the drop-in and reload still
occurs when Dunst is running.

### Reproduction

```bash
sudo pacman -S --needed dunst libnotify
cd ~/dotfiles
stow --target="$HOME" --no-folding dunst
~/.config/hypr/scripts/wallpaper_switch.sh init
dunstctl reload
notify-send "Theme test" "This should use the wallpaper colors."
```

### Verification

- `dunstctl reload` returns 0.
- The generated drop-in exists.
- `journalctl --user -u dunst` shows no color/parse errors beyond the
  pre-existing `show_age_threshold` warning.
- Visual colors were not confirmed under controlled conditions.

### Known limitations

- Only colors are generated.
- Geometry, fonts, timeouts, icons, and rules remain in the base config.
- `show_age_threshold` is in the wrong section.
- The base config can be a real copy on existing machines, so repository edits
  may not propagate.
- The generated drop-in uses `$XDG_CONFIG_HOME`; the base config search path is
  fixed by Dunst.

## GTK 3/4

### Files and paths

| Path | Role |
| --- | --- |
| `gtk/.config/gtk-3.0/gtk.css` | GTK3 rules and palette import |
| `gtk/.config/gtk-3.0/settings.ini` | GTK3 settings |
| `gtk/.config/gtk-4.0/gtk.css` | GTK4 rules and palette import |
| `gtk/.config/gtk-4.0/settings.ini` | GTK4 settings |
| `hypr/.config/hypr/scripts/templates/gtk.css` | Generated palette template |
| `~/.cache/autotheme/gtk.css` | Generated palette |

### Settings

Both files:

```ini
[Settings]
gtk-theme-name = Adwaita-dark
gtk-icon-theme-name = Adwaita
gtk-font-name = Adwaita Sans 11
gtk-application-prefer-dark-theme = true
```

The CSS overrides colors on top of Adwaita-dark.

### CSS import

Both files begin with:

```css
@import url("file:///home/aditya/.cache/autotheme/gtk.css");

selection {
    background-color: @accent_color;
    color: @accent_fg_color;
}
```

Generated definitions:

```css
@define-color bg_color ...;
@define-color surface_color ...;
@define-color border_color ...;
@define-color fg_color ...;
@define-color muted_color ...;
@define-color selected_bg_color ...;
@define-color selected_fg_color ...;
@define-color accent_color ...;
@define-color accent_fg_color ...;
@define-color error_color ...;
@define-color warning_color ...;
```

`selected_bg_color` is the theme hover color; `accent_color` is the vivid
accent.

### Rules

GTK3:

- `window`, `menu`, `.menu`, `.popup`: `@bg_color`, `@fg_color`,
  `@border_color`, radius 10, padding 4, shadow.
- `menuitem`, `.menuitem`, `modelbutton`: padding 6×12, margin 2×4, radius 6,
  `@fg_color`, 0.15 s transition.
- Hover/active menu items: `@selected_bg_color`.
- `check`, `radio`: 14×14, border, transparent.
- Checked/radio: `@accent_color` background, `@accent_fg_color` mark.
- `tooltip`: `@surface_color`, `@fg_color`, `@border_color`, radius 8.

GTK4:

- `window`, `popover`, `.popover`, `.popup`: same base styling.
- `button.menuitem`, `modelbutton`: padding/margin/radius, `@fg_color`.
- Hover: `@selected_bg_color`.
- `check`/`radio` and checked state: same accent treatment.
- No tooltip rule.

### Deployed state

On the reference deployment, `~/.config/gtk-3.0/gtk.css` and
`~/.config/gtk-4.0/gtk.css` are real files, not Stow symlinks. Repository edits
do not propagate until the files are recopied or Stow adopts them.

### Reproduction

```bash
sudo pacman -S --needed gtk3 gtk4 adwaita-icon-theme adwaita-fonts
cd ~/dotfiles
stow --target="$HOME" --no-folding gtk
~/.config/hypr/scripts/wallpaper_switch.sh init
```

Restart GTK applications after generation.

### Verification

Both active files and the generated palette loaded through GTK’s CSS provider:

```python
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
p = Gtk.CssProvider()
p.load_from_path("/home/aditya/.config/gtk-3.0/gtk.css")
```

and the equivalent GTK4 call.

### Known limitations

- Changes apply on application restart.
- Import path is absolute and assumes
  `/home/aditya/.cache/autotheme/gtk.css`.
- Custom `XDG_CACHE_HOME` breaks the path.
- Live files are copies on the reference deployment.
- A different GTK theme may override or conflict.

## Hyprlock

### Files and paths

| Path | Role |
| --- | --- |
| `hypr/.config/hypr/hyprlock.conf` | Layout and static colors |
| `hypr/.config/hypr/scripts/templates/hyprlock-colors.conf` | Generated input-field colors |
| `~/.cache/autotheme/hyprlock-colors.conf` | Generated source file |
| `hypr/.config/hypr/hypridle.conf` | Lock triggers |

### Layout

- General grace: 1 second; cursor hidden; fades enabled; empty input ignored.
- Background: screenshot, 2 blur passes, blur size 6, brightness 0.65,
  contrast 0.90, vibrancy 0.15, vibrancy_darkness 0.10.
- Clock: 80 px JetBrains Mono, 5000 ms update, top center, y −60.
- Date: 13 px sans, 600000 ms update, top center, y −190.
- Prompt: “ENTER PASSWORD”, 10 px, bottom center, y 150.
- Input field: 280×48, bottom center, y 90, radius 10, outline 1, dots 0.22.
- Caps Lock indicator: 10 px, bottom center, y 50, amber.
- Static input colors: white outer/inner, green check, red fail.

### Generated source

```conf
# Autotheme: generated input-field colours (keeps the label colours static).
source = /home/aditya/.cache/autotheme/hyprlock-colors.conf
```

Generated:

```conf
input-field {
    outer_color       = rgba(<accent_rgb>, 0.90)
    inner_color       = rgba(<surface_rgb>, 0.35)
    check_color       = rgba(<accent_rgb>, 0.90)
    fail_color        = rgba(<critical_rgb>, 0.90)
    font_color        = rgba(<fg_rgb>, 0.92)
    placeholder_color = rgba(<muted_rgb>, 0.35)
}
```

Hyprlock parses `source` inline. The generated block appears after the original
`input-field`, so it overrides the color keys while preserving size, position,
rounding, dots, and font. Label colors remain static.

### Reproduction

1. Install `hyprlock`.
2. Ensure the `source` line is present.
3. Run:
   ```bash
   ~/.config/hypr/scripts/wallpaper_switch.sh init
   ```
4. Lock with `hyprlock` or `hypridle`.

### Verification

- Hyprlock 0.9.6 installed.
- Generated file exists with valid `rgba(r, g, b, a)` syntax.
- Hyprlock source/binary strings confirm `source` support.
- Visual lock-screen override was **not** exercised.

### Known limitations

- Only `input-field` colors are generated.
- `source` path is absolute `/home/aditya`.
- Missing generated file logs a source error and leaves static colors.
- A switch while locked does not update the current lock screen.
- Visual behavior is unverified.

## SDDM Maya and GRUB

### SDDM

Observed:

- `/etc/sddm.conf.d/theme.conf`:
  ```ini
  [Theme]
  Current=maya
  ```
- `/usr/share/sddm/themes/maya/theme.conf` is the empty template:
  ```ini
  [General]
  primaryShade=
  primaryLight=
  primaryDark=

  primaryHue1=
  primaryHue2=
  primaryHue3=

  accentShade=
  accentLight=

  accentHue1=
  accentHue2=
  accentHue3=

  normalText=

  successText=
  failureText=
  warningText=

  rebootColor=
  powerColor=
  ```
- Maya QML falls back to its own blue/pink defaults.
- No `sddm-deploy` script, sudoers rule, or autotheme template exists.
- The autotheme engine does not deploy SDDM colors.

A future integration would map:

| Maya key | Palette role |
| --- | --- |
| `primaryDark`, `primaryShade` | Surfaces |
| `primaryHue1..3` | Surface variants |
| `accentShade`, `accentHue1..3` | Accent and accent soft |
| `normalText` | `fg` |
| `successText` | `success` |
| `warningText` | `warning` |
| `failureText` | `critical` |
| `rebootColor` | Accent |
| `powerColor` | `critical` |

Writing `/usr/share/sddm/themes/maya/theme.conf` requires root.

### GRUB

Observed `/etc/default/grub`:

```ini
GRUB_DEFAULT="0"
GRUB_TIMEOUT="60"
GRUB_TIMEOUT_STYLE="menu"
```

No `GRUB_THEME` or `GRUB_BACKGROUND`. No GRUB theme is generated. Per-wallpaper
GRUB theming would require root and `grub-mkconfig` on each switch and is out of
scope.

## Dependencies

- `dunst`, `libnotify`
- `gtk3`, `gtk4`, `adwaita-icon-theme`, `adwaita-fonts`
- `hyprlock`
- `hypridle` if lock triggers are required

## Reproduction

1. Install packages and stow/copy `dunst`, `gtk`, and `hypr/.config/hypr`.
2. Generate the palette:
   ```bash
   ~/.config/hypr/scripts/wallpaper_switch.sh init
   ```
3. Dunst:
   ```bash
   dunstctl reload
   notify-send "Theme test" "This should use the current palette."
   ```
4. Restart GTK applications to load the CSS import.
5. Lock with `hyprlock` or let `hypridle` lock.

Component-specific commands remain under each section above.

## Verification

- Dunst reload returns 0 and the drop-in exists.
- GTK3/GTK4 CSS files load through `Gtk.CssProvider`.
- Hyprlock source file exists and uses valid `rgba()` syntax.
- Hyprlock visual override was not exercised.
- SDDM Maya deployment is not implemented.

## Known limitations

- Dunst generates colors only; geometry, fonts, timeouts, and rules remain in
  the base config.
- The base Dunst `[battery-notify]` section has `show_age_threshold` in the
  wrong section.
- GTK changes apply on application restart.
- GTK import paths and the Hyprlock source path are absolute and hardcode
  `/home/aditya`.
- Live GTK files may be real copies rather than Stow symlinks.
- Hyprlock only themes the input field.
- SDDM Maya and GRUB are not integrated with the palette.

## Related documentation

- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [hyprland-configuration.md](hyprland-configuration.md)
- [terminal-shell-and-prompt.md](terminal-shell-and-prompt.md)
