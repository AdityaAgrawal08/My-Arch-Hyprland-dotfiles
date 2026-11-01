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
| `wofi/.config/wofi/app-launcher.sh` | Application launcher; opens the pick on a new workspace |
| `hypr/.config/hypr/scripts/templates/wofi.css` | Generated main stylesheet template |
| `hypr/.config/hypr/scripts/templates/wofi-confirm.css` | Generated confirmation template |
| `hypr/.config/hypr/scripts/wallpaper_picker.sh` | Wallpaper picker |
| `hypr/.config/hypr/scripts/power-menu.sh` | Power menu |
| `hypr/.config/hypr/scripts/confirm_close.sh` | Close confirmation |
| `~/.cache/autotheme/wofi.css` | Generated main stylesheet |
| `~/.cache/autotheme/wofi-confirm.css` | Generated confirmation stylesheet |

## Main configuration

```ini
width=800
height=600
location=center
prompt=Select an Application
allow_markup=true
no_actions=true
halign=fill
orientation=vertical
content_halign=fill
style=/home/aditya/.cache/autotheme/wofi.css
```

Behavior:

- Wofi parses exactly one `key=value` pair per line; anything after the first
  `=` on a line is consumed as that key's value.
- Default mode: `drun`, passed on the command line by the launcher.
- `prompt=Select an Application`.
- Filtering and sort order use wofi defaults (fuzzy matching). The former
  `matching=none` and `no_sort=true` entries were dropped with the line-split
  fix; add them back as separate lines if unfiltered, caller-sorted output is
  wanted.
- `style=` points to the generated autotheme stylesheet.
- `allow_markup=true` enables Pango markup.

## Generated versus static styles

The tracked `wofi/style.css` and `wofi/confirm.css` are neutral-dark fallbacks.
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
~/.config/wofi/app-launcher.sh
```

The launcher opens the selected application on a brand-new workspace:

1. `wofi --show drun --define=drun-print_command=true` runs the picker and
   prints the selected `.desktop` entry's expanded `Exec` line instead of
   launching it.
2. The script reads `hyprctl workspaces -j` and computes the next workspace as
   the highest existing workspace ID plus one.
3. `hyprctl dispatch "hl.dsp.focus({ workspace = <id> })"` creates and focuses
   that workspace, playing the workspace animation.
4. `hyprctl dispatch "hl.dsp.exec_cmd(<command>, { workspace = <id> })"`
   launches the application pinned to the new workspace, playing the window
   pop-in animation.

Properties:

- The picker uses the main configuration and generated stylesheet.
- Cancelling the picker (Escape) exits without creating a workspace.
- Requires `jq` for the workspace ID lookup and `hyprctl` for dispatching.
- Uses Hyprland's Lua dispatcher syntax (`hl.dsp.*`).
- Wofi expands `.desktop` field codes (`%U`, `%f`, ...) in the printed command.

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

~/.config/wofi/app-launcher.sh
```

## Verification

Verified:

- `wofi --show drun` starts without CSS parser errors.
- `~/.cache/autotheme/wofi.css` and `wofi-confirm.css` parse through GTK3’s
  `Gtk.CssProvider`.
- `wofi/config` points at the generated stylesheet.
- `confirm_close.sh` uses the generated confirmation stylesheet.

Not verified:

- Application launcher selection and new-workspace behaviour.
- Wallpaper picker selection through the UI.
- Power menu actions and sound playback.
- Confirmation dialog interaction.

## Known limitations

- `wofi/style.css` and `wofi/confirm.css` are inactive static fallbacks.
- The `style=` and confirmation `-s` paths hardcode `/home/aditya` and
  `$HOME/.cache/autotheme`.
- `browser-launcher.sh` has no shebang and hardcoded browser paths.
- `power-menu.sh` hardcodes sound paths and does not handle missing files.
- `app-launcher.sh` cannot open `Terminal=true` desktop entries in a terminal;
  wofi's terminal wrapper is bypassed when the command is printed.
- Already-running single-instance applications (Zen, Brave, Firefox) are
  activated instead of opened; the freshly created workspace stays empty.
- Wofi does not live-reload styles; changes appear on the next launch.

## Related documentation

- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [hyprland-automation-scripts.md](hyprland-automation-scripts.md)
- [hyprland-configuration.md](hyprland-configuration.md)
