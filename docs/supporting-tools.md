# Supporting Tools

**Status:** Source verified. Lid scripts are not installed by the repository.

## Purpose

Documents small tools that are not part of the main desktop surfaces:

- Lid open/close helpers.
- Wallpaper generator scripts.
- htop configuration.

## Scope

In scope:

- `lid-sounds/`
- `scripts/generate_wallpaper.py`
- `scripts/process_wallpaper.py`
- `htop/.config/htop/htoprc`

Out of scope:

- Main desktop components.
- Trash, Neovim, OpenCode, autotheme, and PDF tools.

## Lid helpers

### Files

| File | Purpose |
| --- | --- |
| `lid-sounds/lid-action.sh` | Handle `open`/`close` events |
| `lid-sounds/unlock-hook.sh` | Lock, then play the open sound |

Neither script is installed, started, or referenced by another repository
component. They are standalone helpers.

### Behavior

`lid-action.sh` accepts `open` or `close`:

- `open`: if `hyprlock` is not running, play the open sound with `mpv`.
- `close`: if `hyprlock` is not running, start `hyprlock`.

`unlock-hook.sh` starts `hyprlock`, then plays the open sound after it exits.

Hardcoded assumptions:

- User `aditya`
- UID 1000
- `wayland-1`
- Fixed runtime, home, and sound paths

`hypridle` does not call these scripts; it calls `hyprlock` directly.

### Reproduction

There is no service or lid hook in the repository. Wire the scripts manually to
a logind/lid event source or invoke them directly:

```bash
./lid-sounds/lid-action.sh close
./lid-sounds/lid-action.sh open
```

Dependencies: `hyprlock`, `mpv`, `pgrep`, `su`, a valid Wayland session, and the
sound file.

## Wallpaper generators

### `scripts/generate_wallpaper.py`

Generates a 1920×1080 Everforest-style abstract wallpaper with Cairo.

Behavior:

- Background `#2b3339`.
- Top-left polygon `#323c41` at 0.4 opacity.
- Bottom-right polygon `#3d484d` at 0.3 opacity.
- Center-left circle `#7fbbb3` at 0.06 opacity, 1.5 px line.
- Two intersecting lines `#a7c080` at 0.08 opacity, 1.2 px.
- Writes a PNG under `~/Pictures`.

Dependency: Python 3 + `pycairo`.

Limitations:

- Output is outside the autotheme wallpaper library, so it does not appear in
  the wallpaper picker automatically.
- No CLI options.
- Fixed Everforest palette.

### `scripts/process_wallpaper.py`

Processes a landscape image into a 1920×1080 wallpaper with a 40 px black top
strip reserved for Waybar.

Behavior:

- Resize to 1920×1040.
- Brightness 0.72.
- Saturation 0.60.
- Composite a 15% Everforest overlay `(43, 51, 57, 38)`.
- Paste onto a 1920×1080 black canvas at y=40.
- Write to the autotheme wallpaper assets directory.

Dependency: Pillow.

Limitations:

- Source image path is hardcoded in the script.
- Overwrites the tracked wallpaper asset.
- Assumes the 40 px top strip matches Waybar.
- No CLI options.

Neither generator is called by the autotheme engine.

## htop

`htop/.config/htop/htoprc` is a generated htop 3.5.1 configuration.

Key settings:

```ini
color_scheme=0
hide_kernel_threads=1
show_program_path=1
highlight_deleted_exe=1
highlight_megabytes=1
highlight_threads=1
delay=15
header_layout=two_50_50
column_meters_0=LeftCPUs2 Memory Swap
column_meter_modes_0=1 1 1
column_meters_1=RightCPUs2 Tasks LoadAverage Uptime
column_meter_modes_1=1 2 2 2
sort_key=46
```

Screens:

- `Main`: PID USER PRIORITY NICE M_VIRT M_RESIDENT M_PRIV STATE PERCENT_CPU
  PERCENT_MEM TIME Command
- `I/O`: PID USER IO_PRIORITY IO_RATE IO_READ_RATE IO_WRITE_RATE
  PERCENT_SWAP_DELAY PERCENT_IO_DELAY Command

htop rewrites the file when settings change. It is not autothemed. On the
reference deployment, `~/.config/htop/htoprc` is a real copy rather than a Stow
symlink.

## Dependencies

| Tool | Packages |
| --- | --- |
| Lid helpers | `hyprlock`, `mpv` |
| Wallpaper generators | `python`, `python-pillow`, `python-cairo` |
| htop | `htop` |

## Reproduction

Lid helpers:

```bash
mkdir -p ~/Downloads
```

Wallpaper generators:

```bash
python3 scripts/generate_wallpaper.py
python3 scripts/process_wallpaper.py
```

htop:

```bash
cd ~/dotfiles
stow --target="$HOME" --no-folding htop
```

## Verification

- Lid scripts were inspected; they are not installed or referenced.
- Wallpaper generator source was inspected.
- htop configuration was inspected.

## Known limitations

- Lid scripts hardcode user, UID, display, and sound paths.
- `generate_wallpaper.py` writes outside the picker library.
- `process_wallpaper.py` has a hardcoded input path and overwrites the tracked
  wallpaper asset.
- Neither generator accepts CLI options.
- htop is not autothemed.

## Related documentation

- [system-overview.md](system-overview.md)
- [document-and-file-utilities.md](document-and-file-utilities.md)
- [installation-and-package-management.md](installation-and-package-management.md)
