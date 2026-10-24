# Autotheme and Wallpaper Engine

**Status:** Verified on the reference deployment for image and GIF switching,
palette generation, fallbacks, Kitty modes, Waybar/Wofi/GTK/Dunst reloads, and
Hyprland border updates. Hyprlock’s visual override was not exercised.

## Purpose

Provides a single wallpaper-driven theme pipeline for the desktop. A wallpaper
switch generates one canonical Material You dark palette and renders every
supported surface from it:

- Waybar
- Wofi
- Kitty
- Dunst
- GTK 3/4
- Hyprlock
- Hyprland window borders

The engine deliberately targets this machine’s stack. It does not implement
Quickshell, Ghostty, Limine, SDDM Maya, GRUB, or video wallpapers.

## Scope

In scope:

- Wallpaper backends `awww` and `hyprpaper`.
- Static images and animated GIFs.
- Palette extraction, Matugen integration, fallback palettes.
- Theme rendering, live reloads, picker, thumbnails, state.
- Kitty opaque/transparent variants.
- Per-surface integration.

Out of scope:

- Video wallpapers (`mpvpaper`).
- SDDM/GRUB theming.
- Quickshell or Ghostty integration.
- Per-monitor independent wallpapers.
- Persisting Matugen output per wallpaper.

## Architecture

```text
wallpaper file
   │
   ├─ awww / hyprpaper paints wallpaper
   ├─ GIF middle-frame extraction (ffmpeg)
   ├─ vibrant.py
   │    ├─ accents.json
   │    └─ grayscale flag
   ├─ matugen (dark, tonal-spot)
   │    └─ matugen-roles.json
   ├─ build_theme.py
   │    └─ theme.json + autotheme.json
   ├─ render.py
   │    ├─ kitty variants
   │    ├─ waybar palette
   │    ├─ wofi styles
   │    ├─ gtk palette
   │    ├─ hyprlock input-field colors
   │    └─ dunst drop-in
   └─ apply_live
        ├─ Hyprland border colors
        ├─ Waybar reload
        ├─ Kitty set-colors
        └─ Dunst reload
```

The pipeline is one-shot. No daemon watches the wallpaper or the palette after
the switch.

## Components and files

### Scripts

| Path | Role |
| --- | --- |
| `hypr/.config/hypr/scripts/autotheme.conf` | Runtime preferences |
| `hypr/.config/hypr/scripts/wallpaper_switch.sh` | CLI and pipeline orchestration |
| `hypr/.config/hypr/scripts/wallpaper_picker.sh` | Wofi thumbnail picker |
| `hypr/.config/hypr/scripts/lib/autotheme.sh` | Backend, reload, thumbnail, JSON, state helpers |
| `hypr/.config/hypr/scripts/lib/vibrant.py` | Accent and ANSI extraction |
| `hypr/.config/hypr/scripts/lib/build_theme.py` | Theme construction and contrast enforcement |
| `hypr/.config/hypr/scripts/lib/render.py` | Template renderer |
| `hypr/.config/hypr/scripts/waybar-scale.py` | Waybar scaling and palette injection |

### Templates

| Path | Output |
| --- | --- |
| `templates/matugen-roles.json` | `~/.cache/autotheme/matugen-roles.json` |
| `templates/kitty-opaque.conf` | `~/.cache/autotheme/kitty-opaque.conf` |
| `templates/kitty-transparent.conf` | `~/.cache/autotheme/kitty-transparent.conf` |
| `templates/waybar.css` | `~/.cache/autotheme/waybar.css` |
| `templates/wofi.css` | `~/.cache/autotheme/wofi.css` |
| `templates/wofi-confirm.css` | `~/.cache/autotheme/wofi-confirm.css` |
| `templates/gtk.css` | `~/.cache/autotheme/gtk.css` |
| `templates/hyprlock-colors.conf` | `~/.cache/autotheme/hyprlock-colors.conf` |
| `templates/dunst-colors.conf` | `~/.config/dunst/dunstrc.d/autotheme.conf` |

### Wallpaper library

Place image or GIF files, or other supported image formats, in
`~/.config/hypr/themes/wallpapers/assets/`. They are detected automatically,
appear in the wallpaper picker on the next open, and can be selected to change
the desktop background. The `thumbs/` directory is generated automatically and
is not tracked.

### Generated state

| Path | Purpose |
| --- | --- |
| `~/.cache/autotheme/theme.json` | Canonical palette |
| `~/.cache/autotheme.json` | Legacy copy |
| `~/.cache/autotheme/accents.json` | Extracted accents and ANSI |
| `~/.cache/autotheme/matugen-roles.json` | Raw M3 roles |
| `~/.cache/autotheme/kitty-opaque.conf` | Opaque Kitty colors |
| `~/.cache/autotheme/kitty-transparent.conf` | Transparent Kitty colors |
| `~/.cache/autotheme/kitty.conf` | Symlink to active variant |
| `~/.cache/autotheme/kitty-mode` | Last explicit global Kitty mode |
| `~/.cache/autotheme/waybar.css` | Waybar color block |
| `~/.cache/autotheme/wofi.css` | Wofi stylesheet |
| `~/.cache/autotheme/wofi-confirm.css` | Confirmation stylesheet |
| `~/.cache/autotheme/gtk.css` | GTK color definitions |
| `~/.cache/autotheme/hyprlock-colors.conf` | Lock input-field colors |
| `~/.cache/autotheme/samples/` | GIF frame samples |
| `~/.cache/autotheme/wallpaper` | Current wallpaper path |
| `~/.cache/wallpaper_state` | Legacy current-wallpaper path |
| `~/.cache/autotheme/last.log` | Runtime log |
| `~/.cache/autotheme/lock` | `flock` lock |
| `~/.cache/waybar/style.css` | Scaled, themed Waybar CSS |
| `~/.config/dunst/dunstrc.d/autotheme.conf` | Dunst drop-in |

## Runtime preferences

`autotheme.conf` uses environment-overridable defaults.

| Variable | Default | Meaning |
| --- | --- | --- |
| `WALLPAPER_BACKEND` | `auto` | `auto`, `awww`, or `hyprpaper` |
| `WALLPAPER_DIR` | `<scripts>/../themes/wallpapers/assets` | Wallpaper library |
| `THUMBS_DIR` | `<scripts>/../themes/wallpapers/thumbs` | Thumbnail cache |
| `WALLPAPER_TRANSITION` | `random` | `random`, `wave`, `wipe`, `none`, or another awww transition |
| `AUTOTHEME_MATUGEN` | `auto` | `auto`, `always`, `never`; only `never` disables Matugen |
| `AUTOTHEME_DUNST` | `1` | Render and reload Dunst colors |
| `AUTOTHEME_NOTIFY` | `0` | Send a notification after a switch |
| `AUTOTHEME_VIDEO` | `0` | Reserved; unused |

Additional variables:

- `AUTOTHEME_FORCE=1` forces palette regeneration.
- `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`, `XDG_RUNTIME_DIR`.

## Command-line interface

```bash
wallpaper_switch.sh apply <file> [transition]
wallpaper_switch.sh restore
wallpaper_switch.sh regenerate
wallpaper_switch.sh pick
wallpaper_switch.sh borders
wallpaper_switch.sh kitty-mode [--pid PID] <opaque|transparent|auto>
wallpaper_switch.sh list-json
wallpaper_switch.sh ensure-thumbs
wallpaper_switch.sh init
wallpaper_switch.sh doctor
```

| Command | Behavior |
| --- | --- |
| `apply` | Validate, lock, ensure backend, paint, write state, sample, generate if needed, render, apply live |
| `restore` | Use state or default wallpaper; repaint without transition and reapply surfaces |
| `regenerate` | Regenerate from the current wallpaper |
| `pick` | Execute the Wofi picker |
| `borders` | Reapply Hyprland border colors only |
| `kitty-mode` | Switch Kitty color variant without changing opacity |
| `list-json` | Emit supported assets as JSON |
| `ensure-thumbs` | Generate missing thumbnails |
| `init` | Create initial theme and generated files without touching the session |
| `doctor` | Print paths, backend, theme state, and command availability |

## Wallpaper painting

`apply_wallpaper()` paints before generating the palette.

### awww backend

```bash
awww img -a "$file" \
  --resize crop \
  --transition-type <wave|wipe|none|...> \
  --transition-duration 0.8 \
  --transition-fps 60
```

- `-a` applies to all awww daemon instances.
- `random` selects `wave` or `wipe`.
- Supports static images and animated GIFs.
- On failure, attempts Hyprpaper if installed.

### Hyprpaper fallback

- Enumerates monitors with `hyprctl -j monitors | jq -r '.[].name'`.
- Runs `hyprctl hyprpaper wallpaper "<monitor>,<file>,cover"`.
- Converts GIFs to a middle frame because Hyprpaper cannot animate.
- Starts Hyprpaper from `~/.config/hypr/hyprpaper.conf` if necessary.

### Backend selection

- `auto` prefers `awww` + `awww-daemon`.
- Starting awww terminates Hyprpaper.
- Starting Hyprpaper terminates awww.
- Daemons are started with `nohup ... 9>&- &` so they do not inherit the
  wallpaper lock file descriptor.
- If awww fails during painting, the script can switch to Hyprpaper and repaint.

## State and sampling

After painting:

```bash
printf '%s\n' "$file" > ~/.cache/autotheme/wallpaper
printf '%s\n' "$file" > ~/.cache/wallpaper_state
```

Sampling:

- Static image: use the file directly.
- GIF: extract a middle frame.
  - `ffprobe` reads `format=duration`.
  - Invalid or ≤0.05 s duration uses 2 s.
  - `ffmpeg -ss <duration/2> -frames:v 1` writes
    `~/.cache/autotheme/samples/frame-<sha1>.png`.
  - If the midpoint yields no frame, retry at 0, then without `-ss`.
- The sample is passed to `vibrant.py` and Matugen.

## Current-theme shortcut

`theme_is_current(file)` checks only:

- `theme.json.wallpaper == realpath(file)`
- `theme.json.mtime == stat -c %Y file`

If both match and `AUTOTHEME_FORCE != 1`, palette generation is skipped. The
wallpaper is still repainted and the generated surfaces are still re-rendered
and reapplied.

## Accent extraction

`vibrant.py` produces `accents.json`.

### Output schema

```json
{
  "grayscale": false,
  "accent": "#d19b61",
  "accent_soft": "#a7ce82",
  "on_accent": "#0c0c0c",
  "on_accent_soft": "#0c0c0c",
  "ansi": {
    "red": "#c18b8b",
    "bright_red": "#d3acac",
    "yellow": "#c1c18b",
    "bright_yellow": "#d3d3ac",
    "green": "#8bc18b",
    "bright_green": "#acd3ac",
    "cyan": "#8bc1c1",
    "bright_cyan": "#acd3d3",
    "blue": "#8b8bc1",
    "bright_blue": "#acacd3",
    "magenta": "#c18bc1",
    "bright_magenta": "#d3acd3"
  },
  "meta": {
    "mean_saturation": 0.1758,
    "mean_value": 0.1919,
    "vivid_weight": 63.7986,
    "clusters": 3
  }
}
```

Values shown are examples, not constants.

### Algorithm

1. Open with Pillow; apply `draft("RGB", 512x512)` for JPEG speed; convert to
   RGB; thumbnail to 256×256 with Lanczos.
2. Compute HSV for every pixel.
3. Skip pixels with saturation `< 0.28`, value `< 0.10`, or value `> 0.985`.
4. Weight = `saturation^1.6 * value`.
5. Accumulate 36 hue bins of 10°; each stores weighted RGB sums and weight.
6. Sort bins by weight. A cluster is eligible when weight ≥
   `max(total_weight * 0.004, 0.05)`.
7. Primary accent: highest-weight eligible cluster.
8. Clamp primary to HSL lightness `[0.60, 0.80]` and saturation
   `[0.55, 0.95]`.
9. Secondary accent: next eligible cluster at least 32° away; clamp to
   lightness `[0.56, 0.77]` and saturation `[0.45, 0.88]`.
   If none exists, rotate the primary hue by +60° at lightness 0.66 and
   saturation `clamp(primary_saturation * 0.8, 0.4, 0.8)`.
10. ANSI palette:
    - Canonical hues: red 0°, yellow 60°, green 120°, cyan 180°, blue 240°,
      magenta 300°.
    - A cluster may supply a family when its hue is within 24°.
    - Missing families are synthesized from the accent’s saturation and
      lightness:
      `saturation = clamp(accent_s * 0.55, 0.30, 0.55)`,
      `lightness = clamp(0.58 + accent_l * 0.12, 0.58, 0.72)`.
    - Normal colors clamp to lightness `[0.55, 0.78]` and saturation
      `[0.28, 0.86]`.
    - Bright colors use `lightness + 0.10`, capped at 0.86.
11. Grayscale when `total_weight <= 0.05` or no clusters.
    - Accent `#d8d8d8`, soft accent `#b8b8b8`.
    - ANSI uses low-saturation canonical hues: normal lightness 0.64 /
      saturation 0.22; bright 0.76 / 0.18.
12. `on_accent`/`on_accent_soft` choose `#0c0c0c` or `#f6f6f6` by WCAG
    contrast.

Mean saturation is recorded but is not used to decide grayscale.

## Matugen roles

`generate_theme()` writes a temporary config:

```toml
[config]
version_check = false

[templates.roles]
input_path = "<repo>/hypr/.config/hypr/scripts/templates/matugen-roles.json"
output_path = "~/.cache/autotheme/matugen-roles.json"
```

Then runs:

```bash
matugen image "$sample" -m dark -t scheme-tonal-spot \
  --source-color-index 0 -c "$CACHE_DIR/matugen.toml" -q
```

Properties:

- `--config` isolates the run from `~/.config/matugen/config.toml`.
- `version_check = false` disables update checks.
- No `[config.wallpaper]`, so Matugen does not set the wallpaper.
- `--source-color-index 0` avoids an interactive source-color prompt.
- `scheme-tonal-spot` produces harmonious dark surfaces.
- `-q` suppresses output; logs go to `last.log`.

`matugen-roles.json` extracts:

```json
{
  "surface": "{{ colors.surface.default.hex }}",
  "surface_variant": "{{ colors.surface_variant.default.hex }}",
  "on_surface": "{{ colors.on_surface.default.hex }}",
  "on_surface_variant": "{{ colors.on_surface_variant.default.hex }}",
  "outline": "{{ colors.outline.default.hex }}",
  "outline_variant": "{{ colors.outline_variant.default.hex }}",
  "primary": "{{ colors.primary.default.hex }}",
  "on_primary": "{{ colors.on_primary.default.hex }}",
  "secondary": "{{ colors.secondary.default.hex }}",
  "tertiary": "{{ colors.tertiary.default.hex }}",
  "error": "{{ colors.error.default.hex }}",
  "on_error": "{{ colors.on_error.default.hex }}",
  "source_color": "{{ colors.source_color.default.hex }}"
}
```

Matugen creates missing output directories.

## Theme construction

`build_theme.py` merges M3 roles and extracted accents.

### Derived values

Given `surface`:

```text
card        = mix(surface, #ffffff, 0.055)
card_high   = mix(surface, #ffffff, 0.095)
hover       = mix(surface, #ffffff, 0.13)
border      = mix(outline_variant, surface, 0.52)
bright      = lighten(accent, 0.10)
transparent = mix(surface, accent, 0.10)
```

### Contrast enforcement

- `fg`: `on_surface`, lifted until contrast ≥ 7.0 against surface.
- `muted`: `on_surface_variant`, lifted until contrast ≥ 4.0.
- `accent`, `accentSoft`, `critical`: lifted until contrast ≥ 3.0.
- `onAccent`, `onAccentSoft`, `onCritical`: black `#0c0c0c` or white
  `#f6f6f6`, whichever has better contrast.
- ANSI black = card.
- ANSI bright black = outline lifted until contrast ≥ 2.4.
- ANSI white = fg.
- ANSI bright white = `#f5f5f5`.

### Output keys

```json
{
  "wallpaper": "/absolute/path",
  "mtime": 1783067533,
  "generated": 1792849016,
  "mode": "dark",
  "grayscale": false,
  "bg": "#18120b",
  "bgSolid": "#18120b",
  "surface": "#251f18",
  "surfaceHigh": "#2e2922",
  "border": "#322a21",
  "fg": "#ede0d4",
  "bright": "#d6a571",
  "muted": "#d3c4b4",
  "hover": "#36312b",
  "accent": "#d19b61",
  "accentSoft": "#a7ce82",
  "onAccent": "#0c0c0c",
  "onAccentSoft": "#0c0c0c",
  "critical": "#ffb4ab",
  "onCritical": "#0c0c0c",
  "success": "#8bc18b",
  "warning": "#c1c18b",
  "kitty_bg_opaque": "#000000",
  "kitty_bg_transparent": "#2a2014",
  "bg_rgb": "24, 18, 11",
  "surface_rgb": "37, 31, 24",
  "accent_rgb": "209, 155, 97",
  "accent_soft_rgb": "167, 206, 130",
  "fg_rgb": "237, 224, 212",
  "muted_rgb": "211, 196, 180",
  "critical_rgb": "255, 180, 171",
  "ansi": { "...": "..." },
  "ansi_black": "#251f18",
  "ansi_bright_black": "#9b8f80",
  "ansi_red": "#c18b8b",
  "...": "..."
}
```

Values are illustrative. The same document is written to
`~/.cache/autotheme/theme.json` and `~/.cache/autotheme.json`.

## Rendering

`render.py` substitutes `{{key}}` placeholders from `theme.json`. Missing keys
are fatal. Writes are atomic via a `.tmp` file and `os.replace`, mode `0644`.

Manifest:

| Template | Output |
| --- | --- |
| `kitty-opaque.conf` | `~/.cache/autotheme/kitty-opaque.conf` |
| `kitty-transparent.conf` | `~/.cache/autotheme/kitty-transparent.conf` |
| `waybar.css` | `~/.cache/autotheme/waybar.css` |
| `wofi.css` | `~/.cache/autotheme/wofi.css` |
| `wofi-confirm.css` | `~/.cache/autotheme/wofi-confirm.css` |
| `gtk.css` | `~/.cache/autotheme/gtk.css` |
| `hyprlock-colors.conf` | `~/.cache/autotheme/hyprlock-colors.conf` |
| `dunst-colors.conf` | `~/.config/dunst/dunstrc.d/autotheme.conf` |

`render_all()` removes the Dunst drop-in when `AUTOTHEME_DUNST != 1`.

## Surface integration

### Kitty

`kitty.conf` ends with:

```conf
include /home/aditya/.cache/autotheme/kitty.conf
```

The two variants share foreground, cursor, selection, tab accents, border
colors, and the 16 ANSI colors. They differ in:

- `background`
- `tab_bar_background`
- `inactive_tab_background`

Opaque variant: `#000000`.

Transparent variant: `theme.kitty_bg_transparent`
(`mix(surface, accent, 0.10)`).

The active file `~/.cache/autotheme/kitty.conf` is a symlink to the chosen
variant.

Live color update:

```bash
kitten @ --to "unix:$XDG_RUNTIME_DIR/kitty-<pid>" \
  set-colors --all --configured "<variant>"
```

This preserves window opacity and font settings.

Mode model:

- `~/.local/state/kitty-opacity` stores the saved opacity (`0.2` or `1.0`).
- `$XDG_RUNTIME_DIR/kitty-mode-<pid>` stores `opaque` or `transparent` per
  Kitty instance.
- `terminal.fish` writes both and calls
  `wallpaper_switch.sh kitty-mode [--pid PID] <mode>`.
- `kitty-opacity.fish` applies saved opacity to new windows and writes the mode
  file; it does not switch the active variant.
- `set_kitty_active auto` chooses the include variant from saved opacity.
- `reload_kitty auto` chooses per-instance variants from mode files.
- `kitty-mode auto` uses saved opacity for the include and per-instance files
  for live windows.
- `kitty-mode <explicit>` applies to the requested PID or all instances and
  writes the corresponding mode files.

Neovim reads
`$XDG_RUNTIME_DIR/kitty-mode-$KITTY_PID` and switches Gruvbox transparency
accordingly.

### Waybar

`waybar/style.css` uses `@` color tokens. `waybar-scale.py`:

1. Scales every `Npx` by `1.5 / current_scale`.
2. Prepends `~/.cache/autotheme/waybar.css`.
3. Writes `~/.cache/waybar/style.css`.
4. Starts Waybar with `-s` that file, or sends `SIGUSR2` on apply.

### Wofi

`wofi/config` contains:

```ini
style=/home/aditya/.cache/autotheme/wofi.css
```

`confirm_close.sh` uses:

```bash
-s "$HOME/.cache/autotheme/wofi-confirm.css"
```

The tracked `wofi/style.css` and `wofi/confirm.css` are static fallbacks and are
not loaded while the generated files exist.

### Dunst

Generated drop-in:

```ini
[global]
    frame_color = "..."
    highlight = "..."

[urgency_low]
    background = "..."
    foreground = "..."
    frame_color = "..."

[urgency_normal]
    background = "..."
    foreground = "..."
    frame_color = "..."

[urgency_critical]
    background = "..."
    foreground = "..."
    frame_color = "..."
```

Dunst loads `~/.config/dunst/dunstrc` first, then
`~/.config/dunst/dunstrc.d/*.conf`. The drop-in overrides only color keys.
`dunstctl reload` reloads the same paths.

### GTK 3/4

Both `gtk.css` files start with:

```css
@import url("file:///home/aditya/.cache/autotheme/gtk.css");
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

GTK applications pick up changes on restart.

### Hyprlock

`hyprlock.conf` ends with:

```conf
source = /home/aditya/.cache/autotheme/hyprlock-colors.conf
```

Generated source:

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

Applies on the next lock. Label colors remain static.

### Hyprland borders

`apply_borders()`:

1. Reads `accent` and `border` from `theme.json`.
2. Compares `hyprctl getoption general:col.active_border -j` `.gradient` with
   `ff<accent> 0deg`.
3. If different, runs:
   ```bash
   hyprctl eval 'hl.config({ general = {
     ["col.active_border"] = "rgba(<accent>ff)",
     ["col.inactive_border"] = "rgba(<border>ff)"
   } })'
   ```
4. Repeats the check for the inactive border.

`hyprctl keyword` is invalid for Hyprland 0.56’s Lua parser.

The `config.reloaded` hook in `hyprland.lua` calls
`wallpaper_switch.sh borders`.

### Fish and Starship

No generated files. Fish and Starship use ANSI color names, so they follow
Kitty’s generated `color0`–`color15`. Nvim remains on Gruvbox.

## Picker

`wallpaper_picker.sh`:

1. Runs `cache_init` and `ensure_thumbs`.
2. Reads `list_json`.
3. Builds entries:
   ```text
   img:<thumb>:text:<index>. <name>
   ```
   Colons in names become `-`.
4. Runs:
   ```bash
   wofi --dmenu --allow-images --insensitive --prompt "Wallpaper" \
     --define=image_size=48 --define=parse_action=true --matching=contains
   ```
5. Strips an optional `:text:` prefix, extracts the numeric index, maps it to
   the JSON path, and executes `wallpaper_switch.sh apply <path>`.

Bound to `SUPER+T`.

## Thumbnails

`ensure_thumb(file)`:

- Thumbnail path:
  `THUMBS_DIR/<sha1(realpath:mtime)>.jpg`.
- Existing thumbnails are reused.
- Images:
  `magick <file> -thumbnail '512x512^' -gravity center -extent 512x512
  -quality 82 <thumb>`.
- GIFs: extract a middle frame, then apply the same crop.
- If ImageMagick is unavailable for a GIF, use `ffmpeg` scale/pad.

`list_json` uses the same hash formula and falls back to the asset path when a
thumbnail is missing. `ensure_thumbs` does not delete orphaned thumbnails.

## Fallbacks

### Matugen missing or failing

`build_theme.py --fallback dark|neutral` uses extracted accents.

`DARK_FALLBACK`:

| Role | Value |
| --- | --- |
| surface | `#141218` |
| outline | `#938f99` |
| outline_variant | `#49454f` |
| on_surface | `#e6e0e9` |
| on_surface_variant | `#cac4d0` |
| error | `#f2b8b5` |
| on_error | `#601410` |

`NEUTRAL_FALLBACK`:

| Role | Value |
| --- | --- |
| surface | `#121212` |
| outline | `#8a8a8a` |
| outline_variant | `#3a3a3a` |
| on_surface | `#e6e6e6` |
| on_surface_variant | `#a8a8a8` |
| error | `#f2b8b5` |
| on_error | `#601410` |

### Vibrant/Pillow failure

`accents.json` is written as `{}`. `build_theme.py` uses `DEFAULT_ACCENTS`:

| Key | Value |
| --- | --- |
| accent | `#d0bcff` |
| accent_soft | `#efb8c8` |
| ANSI | `#c18b8b #d3acac #c1c18b #d3d3ac #8bc18b #acd3ac #8bc1c1 #acd3d3 #8b8bc1 #acacd3 #c18bc1 #d3acd3` |

Matugen still runs unless the image was already classified as grayscale.

### Grayscale

Matugen is skipped. Neutral surfaces and neutral accents are used. ANSI keeps
low-saturation hue hints for terminal readability.

### Backend missing

- No `awww`/`awww-daemon` → Hyprpaper.
- No Hyprpaper → wallpaper paint fails; theming still runs.
- No backend at all → script exits with an error.

### Partial failure

- Palette generation failure keeps the previous theme.
- Rendering failure leaves the previous generated files in place.
- The wallpaper is painted before palette generation, so a palette failure does
  not block the wallpaper change.

## Startup and reload behavior

`hyprland.lua` autostart runs `wallpaper_switch.sh restore`.

`restore`:

1. Ensures the backend.
2. Reads `~/.cache/autotheme/wallpaper`; falls back to the built-in default
   filenames or the first asset in the wallpaper library.
3. Writes both state files.
4. If the theme is current: render, paint with `none`, apply live.
5. Otherwise: full apply with `none`.

Reload behavior by surface:

| Surface | Behavior |
| --- | --- |
| Hyprland borders | Immediate via `hyprctl eval`; reapplied on `config.reloaded` |
| Waybar | Regenerated and `SIGUSR2` |
| Kitty | `kitten @ set-colors` per instance |
| Dunst | Drop-in rewritten and `dunstctl reload` |
| Wofi | Next launch |
| GTK | Next application restart |
| Hyprlock | Next lock |
| Fish/Starship | ANSI colors update in terminal output |

## Dependencies

```bash
sudo pacman -S --needed matugen awww python-pillow jq ffmpeg imagemagick
```

- `awww` and `matugen` are in `extra`.
- `python-pillow` is required by `vibrant.py`.
- `jq`, `ffmpeg`, `ffprobe`, and ImageMagick are used by shell helpers.
- `kitten` is required for live Kitty updates.
- `hyprctl` is required for borders and monitor enumeration.

## Reproduction

1. Install dependencies.
2. Stow or copy the files listed under “Components and files”.
3. Ensure:
   - Kitty ends with the generated `include`.
   - Waybar uses `waybar-scale.py`.
   - Wofi config uses the generated `style=`.
   - Confirm dialog uses the generated stylesheet.
   - GTK CSS files import the generated palette.
   - Hyprlock ends with the generated `source`.
   - Hyprland has the `SUPER+T` bind, `restore` autostart, and reload hook.
4. Seed:
   ```bash
   chmod +x ~/.config/hypr/scripts/wallpaper_switch.sh \
            ~/.config/hypr/scripts/wallpaper_picker.sh \
            ~/.config/hypr/scripts/lib/*.py
   ~/.config/hypr/scripts/wallpaper_switch.sh init
   ```
5. Apply:
   ```bash
   ~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file>
   ```

## Verification

```bash
~/.config/hypr/scripts/wallpaper_switch.sh doctor
jq . ~/.cache/autotheme/theme.json
readlink ~/.cache/autotheme/kitty.conf
kitten @ ls
kitten @ --to unix:$XDG_RUNTIME_DIR/kitty-<pid> get-colors | head
awww query
hyprctl getoption general:col.active_border -j
cat ~/.config/dunst/dunstrc.d/autotheme.conf
```

Expected:

- `doctor` reports a backend and a present theme.
- `theme.json` contains `bg`, `accent`, `fg`.
- The active Kitty variant exists.
- `awww query` reports the current image.
- Border gradient matches the theme accent.
- Dunst drop-in exists.

Test fallback:

```bash
AUTOTHEME_MATUGEN=never AUTOTHEME_FORCE=1 \
  ~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file>
jq '.bg' ~/.cache/autotheme/theme.json
```

Expected: fallback surface `#141218`, complete theme.

## Known limitations

- No video wallpaper support; `AUTOTHEME_VIDEO` is unused.
- No SDDM or GRUB theming.
- No Quickshell, Ghostty, or Limine integration.
- Hardcoded `/home/aditya` paths in Kitty include, Wofi style, GTK import,
  Hyprlock source, Hyprpaper config, and Hyprland night-light bind.
- Thumbnail cache is stored inside the repository and Stow does not ignore it.
- `AUTOTHEME_MATUGEN=always` behaves like `auto`; only `never` disables
  Matugen.
- `theme_is_current` uses path and mtime only.
- Older Kitty instances can have mixed modes until `terminal` or
  `kitty-mode` is run for that instance.
- `kitty-opacity.fish` does not switch the active generated variant.
- Hyprlock’s visual override is not verified.
- Plain `waybar` without `waybar-scale.py` has undefined `@` tokens.
- Dunst drop-in changes colors only.
- `AUTOTHEME_NOTIFY` defaults to off.

## Related documentation

- [waybar-status-bar.md](waybar-status-bar.md)
- [wofi-launcher.md](wofi-launcher.md)
- [terminal-shell-and-prompt.md](terminal-shell-and-prompt.md)
- [notifications-gtk-and-lock-screen.md](notifications-gtk-and-lock-screen.md)
- [reproduction-and-verification.md](reproduction-and-verification.md)
