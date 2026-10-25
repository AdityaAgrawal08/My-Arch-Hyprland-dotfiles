# Hyprland Automation Scripts

**Status:** Verified for syntax and selected runtime paths; individual scripts
are noted below.

## Purpose

Describes the helper scripts in `hypr/.config/hypr/scripts/` that provide
battery notifications, adaptive terminal sizing, UI scaling, Waybar scaling,
workspace management, power control, close confirmation, and night-light
control.

## Scope

In scope:

- `battery-notify.sh`, `battery-notify.c`, compiled `battery-notify`
- `adaptive-font.py`
- `ui-scale.py`
- `waybar-scale.py`
- `switch_workspace.sh`
- `circular_workspace.sh`
- `increase_workspace.sh`
- `delete_and_shift_workspaces.sh`
- `power-menu.sh`
- `confirm_close.sh`
- `night_light_toggle.sh`
- `compile_flags.txt` and `__pycache__/`

Out of scope:

- Wallpaper/autotheme scripts (see
  [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)).
- Hyprland compositor configuration (see
  [hyprland-configuration.md](hyprland-configuration.md)).

## Script inventory

| File | Runtime | Purpose |
| --- | --- | --- |
| `battery-notify.sh` | Bash | Compile and run the C notifier |
| `battery-notify.c` | C | UPower D-Bus threshold notifications |
| `battery-notify` | Binary | Tracked but Stow-ignored; rebuilt on demand |
| `adaptive-font.py` | Python | Resize Kitty font/padding based on window size |
| `ui-scale.py` | Python | Change focused monitor scale |
| `waybar-scale.py` | Python | Scale and theme Waybar CSS |
| `switch_workspace.sh` | Bash | Previous/next populated workspace |
| `circular_workspace.sh` | Bash | Cycle populated workspaces |
| `increase_workspace.sh` | Bash | Focus max workspace ID + 1 |
| `delete_and_shift_workspaces.sh` | Bash | Compact workspace IDs |
| `power-menu.sh` | Bash | Wofi power menu |
| `confirm_close.sh` | Bash | Confirmation for busy terminals |
| `night_light_toggle.sh` | Bash | Toggle `hyprsunset -t 3000` |
| `compile_flags.txt` | Text | clangd flags for the C notifier |
| `__pycache__/` | Runtime | Python bytecode cache |

## Battery notifier

### `battery-notify.sh`

```bash
SCRIPT_DIR="$HOME/.config/hypr/scripts"
SRC="$SCRIPT_DIR/battery-notify.c"
BIN="$SCRIPT_DIR/battery-notify"

if [[ ! -f "$BIN" ]] || [[ "$SRC" -nt "$BIN" ]]; then
    gcc -O2 "$SRC" -o "$BIN" $(pkg-config --cflags --libs gio-2.0)
fi
exec "$BIN"
```

The script compiles the C source when the binary is missing or older than the
source, then replaces itself with the binary. The binary is tracked in the
repository but is excluded from Stow by `install.sh`
(`--ignore='battery-notify$'`).

Dependencies: `gcc`, `pkg-config`, GLib/GIO, UPower, a notification daemon.

### `battery-notify.c`

Behavior:

- Acquires a single-instance write lock at
  `$XDG_RUNTIME_DIR/battery-notify.lock`, falling back to `/tmp`.
- Connects to the session and system D-Bus.
- Finds a UPower device whose object path contains `battery_`.
- Reads initial `OnBattery` and `Percentage`.
- Subscribes to UPower `PropertiesChanged`.
- Low-battery thresholds: **25%, 15%, 10%, 5%**.
  - Each threshold fires once per discharge.
  - It re-arms when the percentage rises above the threshold.
  - If several thresholds are crossed at once, lower thresholds are marked as
    notified without separate notifications.
- High threshold: **95%** while charging.
  - Fires once per charging session.
  - Starting plugged in at or above 95% marks it as already notified.
- Sends notifications with app name `Battery Monitor`, urgency byte `1`, and a
  20-second timeout.
- Writes timestamped status lines to stdout.

Limitations:

- No systemd unit; started by Hyprland autostart.
- Exits with an error if UPower or a battery device is unavailable.
- The tracked binary can be stale; the wrapper rebuilds it when the source is
  newer.

## Adaptive terminal font

`adaptive-font.py` keeps Kitty font size and padding proportional to the tiled
window size.

Tuning:

| Setting | Value |
| --- | --- |
| Base font | 10.0 |
| Minimum font | 7.0 |
| Maximum font | 14.0 |
| Scale padding | true |
| Base padding | 12.0 |
| Minimum padding | 6.0 |
| Maximum padding | 12.0 |
| Debounce | 0.3 s |
| Fallback base area | 1276 × 674 |
| Fallback base scale | 1.5 |

Algorithm:

1. Use `$XDG_RUNTIME_DIR/adaptive-font.pid` to enforce one instance.
2. Compute the focused monitor’s usable logical area from
   `hyprctl -j monitors`, subtracting gaps/borders and the reserved bar area.
3. Connect to Hyprland’s `.socket2.sock`, discovered from
   `HYPRLAND_INSTANCE_SIGNATURE` or the newest `$XDG_RUNTIME_DIR/hypr/*`.
4. Watch `openwindow`, `closewindow`, `movewindow`, `resizewindow`,
   `changefloatingmode`, `fullscreen`, `monitoradded`, `monitorremoved`,
   `activespecial`, and `configreloaded`.
5. After debounce, read `hyprctl -j clients` and `-j monitors`.
6. For mapped clients of class `kitty`:
   ```text
   scale = sqrt(window_area / BASE_AREA) * monitor_scale / BASE_SCALE
   font  = clamp(BASE_FONT * scale, MIN_FONT, MAX_FONT)
   pad   = clamp(BASE_PADDING * scale, MIN_PADDING, MAX_PADDING)
   ```
7. Send:
   ```bash
   kitten @ --to unix:$XDG_RUNTIME_DIR/kitty-<pid> set-font-size --all <font>
   kitten @ --to unix:$XDG_RUNTIME_DIR/kitty-<pid> set-spacing --all padding=<pad>
   ```
8. Remember the last applied values per PID and remove stale PIDs.

Dependencies: Kitty remote control, `kitten`, `hyprctl`, Hyprland event socket.

Limitations:

- PID reuse is detected only by checking `/proc/<pid>/cmdline` for
  `adaptive-font`.
- Only class `kitty` is handled.
- The baseline is recomputed on each start; no configuration is persisted.
- Retries every 2 seconds if the event socket is unavailable.

## UI scaling

`ui-scale.py` changes the focused monitor’s Hyprland scale.

Usage:

```bash
ui-scale.py up
ui-scale.py down
```

Behavior:

- Candidate scales:
  `1.0, 1.1, 1.2, 1.25, 1.3, 1.4, 1.5, 1.6, 1.7, 1.75, 1.8, 1.875, 2.0,
  2.25, 2.4, 2.5`.
- Filters candidates that produce whole-pixel logical dimensions.
- Selects the next valid scale.
- Applies it with `hyprctl eval`:
  ```lua
  hl.monitor({ output = "<name>", mode = "<W>x<H>@<R>",
               position = "<X>x<Y>", scale = <scale> })
  ```
- Verifies the change by polling `hyprctl -j monitors` for up to 10 × 50 ms.
- Calls `waybar-scale.py apply`.
- Sends a notification with the new scale and logical resolution.

Limitations:

- Runtime-only; a config reload or login restores `1.5`.
- Only the focused monitor is changed.
- Some monitor modes have no valid whole-pixel scale candidates.

## Waybar scaling

`waybar-scale.py` scales Waybar CSS and prepends the autotheme palette.

Inputs:

- `~/.config/waybar/style.css`
- `~/.cache/autotheme/waybar.css`
- `~/.cache/waybar/style.css` (output)

Behavior:

1. Read the focused monitor scale.
2. Compute `ratio = 1.5 / current_scale`.
3. Scale every `Npx` value in `style.css` by `ratio`.
4. Read the generated palette; use the built-in neutral fallback if missing.
5. Write the palette plus scaled CSS to the cache.
6. `start` executes `waybar -s ~/.cache/waybar/style.css`.
7. `apply` sends `SIGUSR2` to Waybar.

Limitations:

- Plain `waybar` without `-s ~/.cache/waybar/style.css` leaves `@` tokens
  undefined.
- Requires a running Hyprland.
- Output write is not atomic, but reload occurs after the process exits.
- Fallback palette is not wallpaper-derived.

## Workspace scripts

All scripts dispatch Lua code strings to `hyprctl`.

### `switch_workspace.sh next|prev`

- Reads `hyprctl -j activeworkspace` and `-j workspaces`.
- Keeps positive workspace IDs with `windows > 0`.
- `next`: next higher ID, wrapping to the first.
- `prev`: next lower ID, wrapping to the last.
- Dispatches:
  ```bash
  hyprctl dispatch "hl.dsp.focus({ workspace = <id> })"
  ```

### `circular_workspace.sh`

- Parses text output from `hyprctl activeworkspace` and `hyprctl workspaces`.
- Keeps numeric workspace IDs.
- Selects the next higher ID, wrapping to the lowest.
- Writes `hyprctl` output to `/tmp/hypr_silent`.

### `increase_workspace.sh`

- Reads the maximum existing workspace ID with `jq`.
- Focuses `max + 1`, creating it.

### `delete_and_shift_workspaces.sh`

- Requires `jq`.
- Maps existing sorted workspace IDs to `1..N`.
- Moves every client to its mapped workspace.
- Refocuses the mapped current workspace.
- Sends `SIGUSR1` to Waybar.

Waybar’s documented CSS/config reload signal is `SIGUSR2`; `SIGUSR1` is normally
a visibility toggle. The refresh behavior of this script is therefore not
guaranteed.

## Power menu

`power-menu.sh`:

- Builds a Wofi dmenu with Lock, Sleep, Restart, Shutdown.
- Logs the selection to `/tmp/power-menu.log`.
- Lock:
  - Plays `~/Downloads/close.wav` with `mpv`.
  - Starts `hyprlock`.
  - Waits 2.5 seconds.
  - Plays `~/Downloads/open.wav`.
- Sleep:
  - Plays the close sound.
  - Starts `hyprlock`.
  - Waits 0.5 seconds.
  - Runs `systemctl suspend`.
- Restart/Shutdown:
  - `systemctl reboot` / `poweroff`.

Dependencies: `wofi`, `mpv`, `hyprlock`, `systemctl`, sound files.

## Close confirmation

`confirm_close.sh` handles `SUPER+Q`.

Behavior:

1. Uses `/tmp/confirm_close.lock` to allow one dialog.
2. If a previous instance is alive and its cmdline contains
   `confirm_close.sh`, closes its Wofi prompt and waits; otherwise clears the
   stale lock.
3. Writes its PID to the lock and removes it on exit.
4. Reads `hyprctl activewindow -j`; exits if no active window.
5. Closes Wofi windows immediately.
6. For terminal classes, inspects the terminal process tree:
   - Child with its own children → busy.
   - Direct child not in `fish|bash|zsh|sh|dash|ksh|nu|elvish|kitten|kitty`
     → busy.
7. Busy terminal → Wofi two-button prompt using
   `~/.cache/autotheme/wofi-confirm.css`.
8. `YES` dispatches:
   ```bash
   hyprctl dispatch "hl.dsp.window.close({ window = \"address:<address>\" })"
   ```

Limitations:

- Stale-lock cleanup uses a prompt pattern match.
- Assumes a conventional terminal process tree.
- Does not use `set -e`; individual commands may fail.
- Uses Hyprland 0.56 Lua dispatcher syntax.

## Night light

`night_light_toggle.sh`:

```bash
if pgrep -x "hyprsunset" >/dev/null; then
    killall hyprsunset
else
    hyprsunset -t 3000
fi
```

No persisted state or notification. Bound to `SUPER+N` via an absolute
`/home/aditya` path.

## Compile flags

`compile_flags.txt`:

```text
-I/usr/include/glib-2.0
-I/usr/lib/glib-2.0/include
-I/usr/include/libmount
-I/usr/include/blkid
-I/usr/include/sysprof-6
-pthread
```

Used by clangd for `battery-notify.c`. It does not affect runtime compilation.

## Reproduction

1. Install dependencies from
   [installation-and-package-management.md](installation-and-package-management.md).
2. Stow or copy `hypr/.config/hypr`.
3. Make scripts executable:
   ```bash
   chmod +x ~/.config/hypr/scripts/*.sh ~/.config/hypr/scripts/*.py
   ```
4. Compile the battery notifier:
   ```bash
   ~/.config/hypr/scripts/battery-notify.sh
   ```
5. Start Hyprland and verify:
   ```bash
   pgrep -a battery-notify
   pgrep -af adaptive-font
   ~/.config/hypr/scripts/waybar-scale.py apply
   ~/.config/hypr/scripts/switch_workspace.sh next
   ```
6. Test the power menu and close confirmation manually.

## Verification

Validated:

- Bash syntax for shell scripts.
- Python syntax for Python scripts.
- Battery notifier source behavior.
- Adaptive font and Waybar scaling behavior in the live session.
- Workspace script logic and dispatcher syntax.
- `confirm_close.sh` process-tree logic by inspection.

Not validated:

- Battery notification delivery on hardware thresholds.
- `circular_workspace.sh` and `delete_and_shift_workspaces.sh` under all
  workspace states.
- Power menu sound playback on the reference deployment.
- Night-light toggle visual effect.

## Known limitations

- `power-menu.sh`, `night_light_toggle.sh`, and `lid-sounds/*` hardcode
  `/home/aditya` or `/run/user/1000`.
- `delete_and_shift_workspaces.sh` uses `SIGUSR1` for Waybar even though
  `SIGUSR2` is the documented reload signal.
- `increase_workspace.sh` assumes numeric workspace IDs and `jq`.
- `circular_workspace.sh` parses human-readable `hyprctl` output.
- `adaptive-font.py` and `ui-scale.py` require a live Hyprland socket.
- The battery notifier has no unit file.

## Related documentation

- [hyprland-configuration.md](hyprland-configuration.md)
- [waybar-status-bar.md](waybar-status-bar.md)
- [terminal-shell-and-prompt.md](terminal-shell-and-prompt.md)
- [notifications-gtk-and-lock-screen.md](notifications-gtk-and-lock-screen.md)
