# Scene-Aware Theming

**Status:** Verified on the reference deployment for heuristic analysis, seed
selection, strategy selection, seed-based Matugen generation, and regression
against scene mode disabled.

## Purpose

Explains the lightweight scene layer that sits between the wallpaper and the
palette engine. It makes the theme react to what the image contains
structurally — a bright sky, a dark low-key scene, a green landscape, a muted
minimal composition — instead of relying only on whole-image colour
statistics.

The layer is deliberately small:

- Pillow only. No NumPy, OpenCV, ONNX, or model download.
- Runs inside the existing `vibrant.py` process.
- No daemon, no watcher, no persistent RAM.
- One analysis per wallpaper change, then it exits.

It is not a semantic segmentation system. It does not identify people, sky,
water, or objects as classes. It derives statistical descriptions and region
priors that are strong enough to stop a large smooth background from
dominating the accent.

## Scope

In scope:

- `hypr/.config/hypr/scripts/lib/scene.py`
- The scene section of `hypr/.config/hypr/scripts/lib/vibrant.py`
- Strategy consumption in `hypr/.config/hypr/scripts/lib/build_theme.py`
- Matugen invocation changes in `hypr/.config/hypr/scripts/lib/autotheme.sh`
- `AUTOTHEME_SCENE` in `hypr/.config/hypr/scripts/autotheme.conf`
- `scene` and `explain` commands in `wallpaper_switch.sh`
- `tests/test_scene.py`

Out of scope:

- Semantic segmentation (SegFormer, DeepLab, or similar).
- Vision-language models or image captioning.
- Per-object masks, face detection, or portrait-specific palettes.
- Any background service or model server.

## How it works

### Attention map

`scene.build_attention()` downsamples the wallpaper to 64×64 and combines two
cheap Pillow signals:

1. **Colour centre-surround** — the difference between each pixel and a
   Gaussian-blurred version of the image, reduced to the maximum channel
   difference. This catches large solid subjects that have little internal
   texture.
2. **Grayscale high-pass** — the difference between luma and a blurred luma.
   This catches edges and fine detail.

The combined map is multiplied by a radial centre prior and normalized with
`ImageOps.autocontrast`. If the result is completely flat, a neutral map of
128 is returned so the weighting falls back to region priors rather than
zeroing every pixel.

### Metrics

Metrics are computed on a 128×128 copy:

| Group | Metrics |
| --- | --- |
| Tone | `lumaMean`, `lumaMedian`, `lumaP10`, `lumaP90`, `contrast`, `entropy` |
| Colour | `satMean`, `satP90`, `chromaFraction`, `colorfulness`, `warmFraction`, `coolFraction` |
| Structure | `edgeDensity`, `flatFraction`, `topLuma`, `bottomLuma`, `centreLuma` |
| Regions | `skyFraction`, `groundFraction`, `greenFraction`, `blueFraction` |
| Attention | `attentionMean`, `subjectFraction`, `centreMass` |
| Diagnostic | `skinFraction` |

`skyFraction` is the fraction of the top 40% that is blue-ish or bright neutral
with low edge energy. `groundFraction` is the fraction of the bottom 25% that
is low-edge and either dark or low-saturation. Both are heuristics, not
segmentation masks.

`skinFraction` uses a classic RGB skin rule. It is recorded for diagnostics
only. On a salmon-toned reference wallpaper it reports 0.25 even though there
is no person, so it must not drive seed selection.

### Tags

Tags are emitted only when their confidence is at least 0.35.

| Tag | Signal |
| --- | --- |
| `monochrome` | low chromatic fraction or low 90th-percentile saturation |
| `low-key` | median luma below 0.30 |
| `high-key` | median luma above 0.62 |
| `vivid` | high saturation and high Hasler–Süsstrunk colorfulness |
| `muted` | low 90th-percentile saturation |
| `minimal` | low edge density and high flat fraction |
| `busy` | high edge density |
| `warm` | warm hue fraction above 0.55 |
| `cool` | cool hue fraction above 0.55 |
| `nature` | green pixel fraction above 0.10 |
| `sky-water` | blue or sky-like fraction above 0.18 |
| `sunset` | warm fraction above 0.08 and a sky-like top band above 0.25 |
| `urban` | high edge density, low green fraction, some chroma |

Tags are descriptive. They do not name objects. A sunset can carry both
`cool` and `sunset`: the sky is cool, the horizon is warm. The seed policy
gives the warm family priority.

### Cluster weighting

`vibrant.py` keeps its 36 hue bins. In scene mode each pixel's weight becomes:

```text
saturation^1.6 · value
  · (0.05 + 0.95 · attention)
  · row_prior
  · column_prior
```

The `0.05` floor is intentional: a texture-only image should not collapse to a
single high-contrast edge.

Region priors:

| Region | Weight |
| --- | --- |
| Top 42%, when `skyFraction > 0.12` | ramps from 0.35 at the top to 1.0 |
| Bottom 28%, when `groundFraction > 0.12` | ramps from 1.0 to 0.50 |
| Outer 10% left/right | 0.65 at the edge, 1.0 inside |

### Seed selection

The highest-weight eligible cluster is the starting point. It is tuned to a
mid-lightness so Matugen's tonal generation has a stable source:

```text
seed = HSL(primary_hue, 0.50..0.62, 0.55..0.80)
```

Because a large sky can still lead a weighted histogram, the seed selection
then applies one demotion rule:

- If the leading cluster is sky-like (hue 190–265°), the image is **not**
  overwhelmingly cool (`blueFraction > 0.70`, `greenFraction < 0.05`, and
  `warmFraction < 0.10`), and a meaningful alternative family exists, the
  alternative wins.
- A **sunset** takes priority: when `warmFraction >= 0.10` and the warm hue
  family (hue below 90° or above 300°) has at least 10% of the total weight,
  the largest warm cluster becomes the seed. The warm band is often split
  across several 10° bins, so the family is aggregated before the decision.
- Otherwise, when `greenFraction >= 0.20` and the green family (70–165°) has at
  least 10% of the total weight, the largest green cluster wins. A landscape
  gets a vegetation-family theme.
- If no substantial alternative exists, or the image is overwhelmingly cool,
  the leading blue cluster is kept. A blue wallpaper therefore stays blue.

The punchy `accent` remains tuned to lightness `0.60..0.80` and saturation
`0.55..0.95`. The secondary accent remains at least 32° away in hue.

### Matugen

In scene mode, `autotheme.sh` writes a 64×64 solid PNG from the seed and runs
Matugen on that file instead of the whole wallpaper:

```bash
matugen image ~/.cache/autotheme/seed.png -m dark \
  -t <strategy.scheme> --source-color-index 0 \
  --contrast <strategy.contrast> \
  --lightness-dark <strategy.lightnessDark> \
  -c ~/.cache/autotheme/matugen.toml -q
```

This is the core fix for the "everything is blue" failure mode. Matugen's
dominant-colour selection never sees the large sky; it sees the scene-selected
seed colour. `--source-color-index 0` is still required because Matugen reports
multiple source colours even for a solid image.

If Matugen rejects the seed, the shell retries once with the original wallpaper
and the same scheme. If that also fails, the static fallback is used.

### Strategy

| Scene | Scheme | Tuning |
| --- | --- | --- |
| `monochrome` | `scheme-monochrome` | neutral ANSI; no seed |
| `nature` | `scheme-content` | strong surface tint toward the seed |
| `sky-water` | `scheme-fidelity` | preserve the seed hue; moderate surface tint |
| `muted` or `minimal` | `scheme-neutral` | softer borders, lower ANSI saturation |
| `vivid` + `busy`/`urban` | `scheme-vibrant` | higher contrast, stronger borders |
| `vivid` alone | `scheme-vibrant` | higher contrast |
| default | `scheme-tonal-spot` | current behaviour |

Additional strategy values:

- `contrast`: `-0.12..0.22`, from low-key, high-key, vivid, and muted signals.
- `lightnessDark`: `-0.02..0.02`. The range is deliberately small because
  Matugen's parameter moves the black point and clips shadows at larger
  negative values.
- `ansiSaturation`: `0.60..1.15`; `0` for monochrome.
- `surfaceTint`: how far `build_theme.py` rotates the surface hue toward the
  seed; scaled by confidence.
- `borderContrast`: raises or lowers the border's contrast against the surface.

## Resource use

Measured on the reference machine:

| Wallpaper | Peak RSS, `--scene off` | Peak RSS, `--scene heuristic` |
| --- | --- | --- |
| 2123×1195 JPEG | 33.6 MiB | 33.5 MiB |
| 3840×2160 JPEG | 73.2 MiB | 73.3 MiB |

Scene mode adds roughly 20–40 ms of CPU per wallpaper change. Wall-clock
measurements on a loaded desktop are noisy; the stable result is that peak RSS
does not increase. The numbers include Python startup and Pillow import; they
are not idle cost. Nothing remains resident after the command exits.

Persistent disk addition: `~/.cache/autotheme/seed.png`, about 12 KB. Scene
metrics and tags live inside the existing `accents.json`; no separate scene
cache is created.

## Configuration

`autotheme.conf`:

```bash
# off | heuristic | auto
AUTOTHEME_SCENE="${AUTOTHEME_SCENE:-auto}"
```

- `auto` resolves to the heuristic analyser.
- `off` restores the pre-scene statistical palette and the original Matugen
  invocation.
- `heuristic` is explicit and useful for testing.

Environment overrides apply per command, for example:

```bash
AUTOTHEME_SCENE=off ~/.config/hypr/scripts/wallpaper_switch.sh regenerate
```

## Commands

```bash
wallpaper_switch.sh scene
wallpaper_switch.sh explain
```

`scene` prints the last scene document as JSON. `explain` prints a compact
human-readable summary.

Both read the current `~/.cache/autotheme/accents.json`. Run `regenerate` after
changing the wallpaper or the analyser.

## Reproduction

1. Confirm Pillow is installed:

   ```bash
   python3 -c 'import PIL; print(PIL.__version__)'
   ```

2. Run the unit tests:

   ```bash
   python3 -m unittest discover \
     -s tests -p 'test_*.py' -v
   ```

3. Regenerate the current theme and inspect the scene document:

   ```bash
   ~/.config/hypr/scripts/wallpaper_switch.sh regenerate
   ~/.config/hypr/scripts/wallpaper_switch.sh scene | jq '{tags, strategy, seed}'
   ```

4. Compare scene on and off:

   ```bash
   AUTOTHEME_SCENE=off ~/.config/hypr/scripts/wallpaper_switch.sh regenerate
   jq '{accent, bg, scene}' ~/.cache/autotheme/theme.json
   ~/.config/hypr/scripts/wallpaper_switch.sh regenerate
   ```

5. Measure the cost:

   ```bash
   python3 - <<'PY'
   import resource, subprocess, time
   for mode in ("off", "heuristic"):
       start = time.perf_counter()
       subprocess.run([
           "python3", "hypr/.config/hypr/scripts/lib/vibrant.py",
           "<wallpaper-file>",
           "-o", "/tmp/accents.json", "--scene", mode,
       ], check=True)
       print(mode, round((time.perf_counter() - start) * 1000, 1), "ms")
   print("peak", resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024, "MiB")
   PY
   ```

## Verification

- Unit tests cover sky-versus-subject seed selection, sunset warm-seed
  selection, landscape sky demotion, blue-dominant retention, `scene off`
  regression, nature, monochrome, low-key, high-key, seed PNG output, region
  weights, flat-image attention, surface hue alignment, and contrast floors.
- A synthetic sky-blue image with an orange subject produces an orange seed,
  not a blue one. The same image with `--scene off` produces the old blue
  accent.
- A salmon-toned wallpaper produces a salmon seed `#cc7050`, a salmon accent
  `#d17e61`, and a warm background `#150f0c`.
- A blue-dominant wallpaper produces a blue seed `#3977c6`, consistent with
  its content.
- `wallpaper_switch.sh scene` and `explain` read the generated document.
- `AUTOTHEME_SCENE=off` emits no `scene` or `seed` keys and keeps the original
  Matugen invocation.
- `theme_is_current` rejects cached themes whose scene version is missing or
  stale.
- Hyprland border, Kitty include, Waybar CSS, Wofi CSS, Dunst reload, and
  Neovim highlight verification still pass after regeneration.

## Known limitations

- No semantic masks. `sky-water`, `nature`, and `urban` are pixel-statistics
  proxies, not object classes.
- `skinFraction` is unreliable for warm-toned images and is not used.
- The attention map is a high-pass/centre-surround heuristic. It can miss a
  very large subject whose interior matches its surroundings, and it can favor
  high-contrast text or edges. Region priors and cluster minimums limit the
  damage but do not eliminate it.
- Seed-based Matugen produces surfaces from one selected colour. This is more
  predictable than whole-image extraction, but less tonally rich than a
  multi-colour image analysis.
- The strategy thresholds were calibrated on a small wallpaper library. They
  are versioned; changing them requires bumping `scene.VERSION` and
  `SCENE_VERSION` in `autotheme.sh`.
- `AUTOTHEME_SCENE=auto` currently behaves exactly like `heuristic`.
- No VLM or on-demand captioning. Abstract concepts such as "cyberpunk" are
  outside the scope.

## Related documentation

- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [terminal-shell-and-prompt.md](terminal-shell-and-prompt.md)
- [reproduction-and-verification.md](reproduction-and-verification.md)
