# Autotheme and Wallpaper Engine

**Status:** Verified for image and GIF switching, scene-aware strategy
selection, palette generation, fallbacks, Kitty modes,
Waybar/Wofi/GTK/Dunst reloads, Hyprland border updates, and Neovim colorscheme
application. Hyprlock’s visual override was not exercised.

## Purpose

Provides a single wallpaper-driven theme pipeline for the desktop. A wallpaper
switch generates one canonical Material You dark palette and renders every
supported surface from it:

- Waybar
- Wofi
- Kitty
- Neovim
- Dunst
- GTK 3/4
- Hyprlock
- Hyprland window borders

No fixed theme set is used. Every switch derives surfaces, accents, terminal
colors, and editor highlights from the selected wallpaper. A Pillow-only scene
analyser weights the colour clusters by visual attention and region, chooses a
scheme type and mood adjustments, and gives Matugen a scene-selected seed
colour. There is no semantic model and no fixed palette list.

The engine deliberately targets this machine’s stack; it does not implement
Quickshell, Ghostty, Limine, SDDM Maya, GRUB, or video wallpapers.

## Scope

In scope:

- Wallpaper backends `awww` and `hyprpaper`.
- Static images and animated GIFs.
- Pillow-only scene heuristics: attention map, region priors, tags, strategy.
- Palette extraction, Matugen integration, fallback palettes.
- Theme rendering, live reloads, picker, thumbnails, state.
- Kitty opaque/transparent variants.
- Per-surface integration.

Out of scope:

- Semantic segmentation, object masks, or vision-language models.
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
   ├─ scene.py (Pillow)
   │    ├─ 64x64 attention map
   │    ├─ tone/colour/structure metrics
   │    └─ tags + palette strategy
   ├─ vibrant.py
   │    ├─ attention- and region-weighted clusters
   │    ├─ accents.json (seed, accents, ANSI, scene)
   │    └─ seed.png (64x64 solid seed)
   ├─ matugen (dark, strategy scheme, seed or wallpaper)
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

The pipeline is one-shot. No daemon watches the wallpaper. Applications with
live reload support are signaled; Neovim polls `theme.json` every two seconds
and reapplies its highlight groups.

## Components and files

### Scripts

| Path | Role |
| --- | --- |
| `hypr/.config/hypr/scripts/autotheme.conf` | Runtime preferences |
| `hypr/.config/hypr/scripts/wallpaper_switch.sh` | CLI and pipeline orchestration |
| `hypr/.config/hypr/scripts/wallpaper_picker.sh` | Wofi thumbnail picker |
| `hypr/.config/hypr/scripts/lib/autotheme.sh` | Backend, reload, thumbnail, JSON, state helpers |
| `hypr/.config/hypr/scripts/lib/scene.py` | Pillow-only attention map, metrics, tags, strategy |
| `hypr/.config/hypr/scripts/lib/vibrant.py` | Scene-weighted accent/seed/ANSI extraction |
| `hypr/.config/hypr/scripts/lib/build_theme.py` | Theme construction, hue alignment, contrast enforcement |
| `hypr/.config/hypr/scripts/lib/render.py` | Template renderer |
| `hypr/.config/hypr/scripts/waybar-scale.py` | Waybar scaling and palette injection |
| `tests/test_scene.py` | Scene regression tests |

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
| `~/.cache/autotheme/accents.json` | Extracted seed, accents, ANSI, scene document |
| `~/.cache/autotheme/seed.png` | 64×64 solid seed for Matugen |
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
| `AUTOTHEME_SCENE` | `auto` | `off`, `heuristic`, `auto`; `auto` resolves to heuristic |
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
wallpaper_switch.sh scene
wallpaper_switch.sh explain
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
| `scene` | Print the last scene document as JSON |
| `explain` | Print a human-readable scene summary |
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
- The sample is passed to `vibrant.py`. Matugen receives the scene seed in
  scene mode, or the sample when scene mode is off or the seed is unavailable.

## Current-theme shortcut

`theme_is_current(file)` checks:

- `theme.json.wallpaper == realpath(file)`
- `theme.json.mtime == stat -c %Y file`
- When `AUTOTHEME_SCENE` is not `off`: `theme.json.scene.version ==
  SCENE_VERSION`
- When `AUTOTHEME_SCENE=off`: `theme.json` has no `scene` block

If they match and `AUTOTHEME_FORCE != 1`, palette generation is skipped. The
wallpaper is still repainted and the generated surfaces are still re-rendered
and reapplied. An in-place file edit that preserves mtime is not detected.

## Accent extraction

`vibrant.py` produces `accents.json`.

### Output schema

```json
{
  "wallpaper": "/…/<wallpaper>.jpg",
  "grayscale": false,
  "seed": "#cc7050",
  "accent": "#d17e61",
  "accent_soft": "#5c96c1",
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
  "scene": {
    "version": 3,
    "confidence": 1.0,
    "degraded": false,
    "tags": [
      { "name": "sky-water", "confidence": 1.0 },
      { "name": "vivid", "confidence": 0.8 },
      { "name": "low-key", "confidence": 0.55 }
    ],
    "metrics": { "lumaMedian": 0.2118, "satP90": 0.7193, "...": "..." },
    "strategy": {
      "scheme": "scheme-fidelity",
      "contrast": 0.103,
      "lightnessDark": -0.011,
      "ansiSaturation": 1.08,
      "surfaceTint": 0.7,
      "borderContrast": 0.8
    }
  },
  "meta": {
    "mean_saturation": 0.3882,
    "mean_value": 0.5697,
    "vivid_weight": 15760.5313,
    "clusters": 2,
    "scene_mode": "heuristic",
    "scene": true
  }
}
```

Values shown are examples, not constants. The full metric set is documented
in [scene-aware-theming.md](scene-aware-theming.md).

### Algorithm

1. Open with Pillow; apply `draft("RGB", 512x512)` for JPEG speed; convert to
   RGB; thumbnail to 256×256 with Lanczos.
2. If scene mode is enabled:
   - Build a 64×64 attention map from a colour centre-surround term, a
     grayscale high-pass term, and a radial centre prior.
   - Compute tone, colour, structure, region, and attention metrics at
     128×128.
   - Derive tags and a palette strategy.
   - If this step fails, log a warning and continue with the statistical
     palette.
3. Compute HSV for every pixel. Accumulate mean saturation and mean value.
4. Skip pixels with saturation `< 0.28`, value `< 0.10`, or value `> 0.985`.
5. Weight = `saturation^1.6 * value`.
   In scene mode multiply by
   `(0.05 + 0.95 * attention) * row_prior * column_prior`.
6. Accumulate 36 hue bins of 10°; each stores weighted RGB sums and weight.
7. Sort bins by weight. A cluster is eligible when weight ≥
   `max(total_weight * 0.004, 0.05)`.
8. Primary cluster: highest-weight eligible cluster. In scene mode a leading
   sky-like cluster is demoted when the image is not overwhelmingly cool and a
   meaningful alternative family exists. Sunsets prefer the aggregated warm
   family; nature scenes prefer the green family; a genuinely blue-dominant
   image keeps its blue cluster. Details are in
   [scene-aware-theming.md](scene-aware-theming.md).
9. Seed: clamp the primary cluster to HSL lightness `[0.50, 0.62]` and
   saturation `[0.55, 0.80]`. The seed is written to `seed.png` for Matugen.
10. Accent: clamp the primary cluster to HSL lightness `[0.60, 0.80]` and
    saturation `[0.55, 0.95]`.
11. Secondary accent: next eligible cluster at least 32° away; clamp to
    lightness `[0.56, 0.77]` and saturation `[0.45, 0.88]`.
    If none exists, rotate the primary hue by +60° at lightness 0.66 and
    saturation `clamp(primary_saturation * 0.8, 0.4, 0.8)`.
12. ANSI palette:
    - Canonical hues: red 0°, yellow 60°, green 120°, cyan 180°, blue 240°,
      magenta 300°.
    - A cluster may supply a family when its hue is within 24°.
    - Missing families are synthesized from the accent’s saturation and
      lightness:
      `saturation = clamp(accent_s * 0.55, 0.30, 0.55)`,
      `lightness = clamp(0.58 + accent_l * 0.12, 0.58, 0.72)`.
    - Normal colors clamp to lightness `[0.55, 0.78]` and saturation
      `[0.28, 0.86]`, scaled by the strategy’s `ansiSaturation`.
    - Bright colors use `lightness + 0.10`, capped at 0.86.
13. Grayscale when `total_weight <= 0.05` or there are no clusters.
    - `chromaFraction` is diagnostic only. A small vivid subject in an
      otherwise monochrome image still produces an accent (selective colour).
    - Accent `#d8d8d8`, soft accent `#b8b8b8`.
    - ANSI uses low-saturation canonical hues: normal lightness 0.64 /
      saturation 0.22; bright 0.76 / 0.18.
14. `on_accent`/`on_accent_soft` choose `#0c0c0c` or `#f6f6f6` by WCAG
    contrast.

Mean saturation is recorded but is not used to decide grayscale. With
`AUTOTHEME_SCENE=off`, steps 2 and 5 are skipped and the output matches the
pre-scene statistical palette.

## Matugen roles

`generate_theme()` writes a temporary config:

```toml
[config]
version_check = false

[templates.roles]
input_path = "<repo>/hypr/.config/hypr/scripts/templates/matugen-roles.json"
output_path = "~/.cache/autotheme/matugen-roles.json"
```

Scene mode runs:

```bash
matugen image "$SEED_PNG" -m dark -t "$scheme" \
  --source-color-index 0 --contrast "$contrast" \
  --lightness-dark "$lightness" \
  -c "$CACHE_DIR/matugen.toml" -q
```

With `AUTOTHEME_SCENE=off` it keeps the original form:

```bash
matugen image "$sample" -m dark -t scheme-tonal-spot \
  --source-color-index 0 -c "$CACHE_DIR/matugen.toml" -q
```

Properties:

- `--config` isolates the run from `~/.config/matugen/config.toml`.
- `version_check = false` disables update checks.
- No `[config.wallpaper]`, so Matugen does not set the wallpaper.
- `--source-color-index 0` is required even for a solid seed; without it
  Matugen reports multiple source colors and refuses to run non-interactively.
- In scene mode the source is `seed.png`, a 64×64 solid image built from the
  attention/region-weighted cluster. This prevents a dominant sky from
  choosing the hue.
- `scheme`, `contrast`, and `lightnessDark` come from
  `accents.json.scene.strategy`; values are clamped by the scene analyser.
- `--lightness-dark` is limited to `[-0.02, 0.02]` because larger negative
  values move the black point and clip shadows to black.
- If Matugen rejects the seed, the shell retries once with `$sample` and the
  same scheme. If that fails, the static fallback is used.
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

Given Matugen `surface` and the scene seed:

```text
surface     = align_hue(surface, seed, surfaceTint * 0.5)
card        = mix(surface, #ffffff, 0.055)
card_high   = mix(surface, #ffffff, 0.095)
hover       = mix(surface, #ffffff, 0.13)
border      = ensure_contrast(
                mix(outline_variant, surface, 0.52),
                surface,
                1.25 + 0.55 * borderContrast)
bright      = lighten(accent, 0.10)
transparent = mix(surface, accent, 0.10)
```

`align_hue` changes only the hue; it preserves the surface lightness and
saturation. It keeps the surfaces coherent when Matugen was run on a fallback
image instead of the seed.

### Contrast enforcement

- `fg`: `on_surface`, lifted until contrast ≥ 7.0 against surface.
- `muted`: `on_surface_variant`, lifted until contrast ≥ 4.5.
- `accent`: lifted until contrast ≥ 4.5.
- `accentSoft`: lifted until contrast ≥ 4.0.
- `critical`: lifted until contrast ≥ 3.0.
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
  "...": "...",
  "scene": {
    "mode": "heuristic",
    "version": 3,
    "confidence": 1.0,
    "degraded": false,
    "tags": [{ "name": "sky-water", "confidence": 1.0 }],
    "strategy": { "scheme": "scheme-fidelity", "...": "..." },
    "seed": "#cc7050"
  }
}
```

Values are illustrative. The same document is written to
`~/.cache/autotheme/theme.json` and `~/.cache/autotheme.json`. The `scene`
block is omitted when `AUTOTHEME_SCENE=off`; `theme_is_current` then requires
the block to be absent, so switching between `off` and `auto` invalidates the
cache.

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

### Neovim

`nvim/.config/nvim/lua/core/autotheme.lua` reads
`~/.cache/autotheme/theme.json` at startup, defines Neovim highlight groups from
the palette, and polls the file every two seconds for updates. It also reads
`$XDG_RUNTIME_DIR/kitty-mode-$KITTY_PID` to switch between a transparent and a
solid background. There is no predefined Neovim colorscheme.

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
Kitty’s generated `color0`–`color15`. Neovim uses the generated palette through
`core/autotheme.lua`.

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
| surface | `#121212` |
| outline | `#8a8a8a` |
| outline_variant | `#3a3a3a` |
| on_surface | `#e6e6e6` |
| on_surface_variant | `#a8a8a8` |
| error | `#ffb4ab` |
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

### Scene analysis failure

If `scene.py` raises an exception, `vibrant.py` logs
`scene analysis failed` and continues with the unweighted statistical palette.
`accents.json` then carries a scene marker with `degraded: true`, an empty tag
list, and no `seed`; the shell keeps the original Matugen invocation
(`$sample`, `scheme-tonal-spot`). The marker keeps the scene version valid, so
the same image is not re-analysed on every restore. Scene failure is never
fatal.

If `scene.py` is missing, the shell disables scene mode before calling
`vibrant.py`; `doctor` reports `scene.py : missing`. If the module exists but
cannot be imported, `vibrant.py` logs `scene module unavailable` and falls back
the same way.

If the seed image is missing or Matugen rejects it, the shell retries once with
the original wallpaper and the same scheme. If that fails, the static fallback
is used.

If `theme.json` has no `scene.version` or its version does not equal
`SCENE_VERSION`, `theme_is_current` treats the cached theme as stale and
regenerates it. With `AUTOTHEME_SCENE=off`, a theme that still has a `scene`
block is also treated as stale.

### Vibrant/Pillow failure

`accents.json` is written as `{}`. `build_theme.py` uses `DEFAULT_ACCENTS`:

| Key | Value |
| --- | --- |
| accent | `#d0d0d0` |
| accent_soft | `#a8a8a8` |
| ANSI | `#b78f8f #cdb7b7 #b7b78f #cdcdb7 #8fb78f #b7cdb7 #8fb7b7 #b7cdcd #8f8fb7 #b7b7cd #b78fb7 #cdb7cd` |

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
| Neovim | Polls `theme.json` every two seconds and reapplies highlights |
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
- `python-pillow` is required by `vibrant.py` and `scene.py`.
- The scene layer adds no package, model, service, or daemon. It is Pillow
  only.
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
5. Run the scene tests:
   ```bash
   python3 -m unittest discover \
     -s tests -p 'test_*.py' -v
   ```
6. Apply:
   ```bash
   ~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file>
   ```

## Verification

```bash
~/.config/hypr/scripts/wallpaper_switch.sh doctor
jq . ~/.cache/autotheme/theme.json
jq '{seed, scene}' ~/.cache/autotheme/accents.json
~/.config/hypr/scripts/wallpaper_switch.sh scene
~/.config/hypr/scripts/wallpaper_switch.sh explain
readlink ~/.cache/autotheme/kitty.conf
kitten @ ls
kitten @ --to unix:$XDG_RUNTIME_DIR/kitty-<pid> get-colors | head
awww query
hyprctl getoption general:col.active_border -j
cat ~/.config/dunst/dunstrc.d/autotheme.conf
```

Expected:

- `doctor` reports a backend, a present theme, and scene tags.
- `theme.json` contains `bg`, `accent`, `fg`, and `scene.version`.
- `accents.json` contains a `seed` and the full scene document.
- `scene` prints valid JSON; `explain` prints seed, scheme, contrast, and
  lightness.
- The active Kitty variant exists.
- `awww query` reports the current image.
- Border gradient matches the theme accent.
- Dunst drop-in exists.

Test the scene regression and the mode-switch cache:

```bash
AUTOTHEME_SCENE=off \
  ~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file> none
jq '{scene, seed}' ~/.cache/autotheme/theme.json
AUTOTHEME_SCENE=auto \
  ~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file> none
```

Expected: the off run has no scene/seed, uses the original Matugen invocation,
and regenerates even with the same wallpaper. The auto run restores the scene
theme. `theme_is_current` treats a theme with the wrong scene mode as stale.

Test fallback:

```bash
AUTOTHEME_MATUGEN=never AUTOTHEME_FORCE=1 \
  ~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file>
jq '.bg' ~/.cache/autotheme/theme.json
```

Expected: fallback surface `#121212`, complete theme.

## Known limitations

- No video wallpaper support; `AUTOTHEME_VIDEO` is unused.
- No SDDM or GRUB theming.
- No Quickshell, Ghostty, or Limine integration.
- Hardcoded `/home/aditya` paths in Kitty include, Wofi style, GTK import,
  Hyprlock source, Hyprpaper config, and Hyprland night-light bind.
- Thumbnail cache is stored inside the repository and Stow does not ignore it.
- `AUTOTHEME_MATUGEN=always` behaves like `auto`; only `never` disables
  Matugen.
- `theme_is_current` uses path, mtime, the scene version, and whether scene
  mode is off. It does not hash file contents, so an in-place edit that
  preserves mtime is not detected.
- Scene analysis is heuristic, not semantic. It has no object masks and no
  vision-language model.
- `skinFraction` is recorded for diagnostics but is not used; it
  false-positives on warm-toned images.
- The attention map can miss very large subjects whose interiors match their
  surroundings, and can favor high-contrast text or edges.
- Scene thresholds are versioned by `scene.VERSION` and `SCENE_VERSION`; both
  must be bumped when the strategy changes.
- Older Kitty instances can have mixed modes until `terminal` or
  `kitty-mode` is run for that instance.
- `kitty-opacity.fish` does not switch the active generated variant.
- Neovim applies theme changes on a two-second poll; an already-running
  Neovim process that was started before this integration must be restarted
  once.
- Hyprlock’s visual override is not verified.
- Plain `waybar` without `waybar-scale.py` has undefined `@` tokens.
- Dunst drop-in changes colors only.
- `AUTOTHEME_NOTIFY` defaults to off.

## Related documentation

- [scene-aware-theming.md](scene-aware-theming.md)
- [waybar-status-bar.md](waybar-status-bar.md)
- [wofi-launcher.md](wofi-launcher.md)
- [terminal-shell-and-prompt.md](terminal-shell-and-prompt.md)
- [notifications-gtk-and-lock-screen.md](notifications-gtk-and-lock-screen.md)
- [reproduction-and-verification.md](reproduction-and-verification.md)
