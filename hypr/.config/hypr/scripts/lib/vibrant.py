#!/usr/bin/env python3
"""Extract vivid accent colours and a terminal ANSI palette from a wallpaper.

The Material You roles produced by matugen are intentionally pastel.  This
module finds the wallpaper's own most saturated colour clusters so accents can
stay punchy while the surfaces continue to come from matugen.

When scene mode is enabled, clusters are weighted by a small attention map and
by region priors (sky, ground, side borders).  A large smooth sky no longer
outvotes a small saturated subject.  The analysis uses Pillow only and runs in
this process; there is no model and no daemon.

The output is a small JSON document consumed by build_theme.py and the shell
pipeline.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - handled by the shell wrapper
    Image = None
    ImageOps = None

try:
    from scene import (
        ATTENTION_SIZE,
        VERSION as SCENE_VERSION,
        analyze as analyze_scene,
        build_attention,
        column_weights,
        row_weights,
    )
except Exception as error:  # pragma: no cover - scene.py ships with this module
    print(
        f"vibrant: scene module unavailable ({error}); using statistical palette",
        file=sys.stderr,
    )
    ATTENTION_SIZE = 64
    SCENE_VERSION = 0
    analyze_scene = None
    build_attention = None
    column_weights = None
    row_weights = None


# ANSI hue families, in degrees.
ANSI_HUES = {
    "red": 0.0,
    "yellow": 60.0,
    "green": 120.0,
    "cyan": 180.0,
    "blue": 240.0,
    "magenta": 300.0,
}

# How far a cluster may be from an ANSI family's canonical hue.  Keeping this
# tight avoids using the same warm cluster for both red and yellow.
ANSI_HUE_TOLERANCE = 24.0
# Two accents must be at least this far apart in hue.
ACCENT_SEPARATION = 32.0
# Ignore very dark, very bright or washed-out pixels.
MIN_SATURATION = 0.28
MIN_VALUE = 0.10
MAX_VALUE = 0.985
# A cluster must contribute at least this fraction of the vivid weight.
MIN_CLUSTER_FRACTION = 0.004
# Low-attention regions still contribute a little so a texture-only image does
# not collapse to its single most contrasty edge.
ATTENTION_FLOOR = 0.05


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[float, float, float] | tuple[int, int, int]) -> str:
    r, g, b = (int(round(clamp(float(c), 0, 255))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    amount: float,
) -> tuple[float, float, float]:
    amount = clamp(amount, 0.0, 1.0)
    return tuple(a + (b - a) * amount for a, b in zip(first, second))  # type: ignore[return-value]


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        value = value / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    a = relative_luminance(first)
    b = relative_luminance(second)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def choose_foreground(rgb: tuple[int, int, int]) -> str:
    """Return black or white, whichever contrasts better with *rgb*."""
    black = (12, 12, 12)
    white = (246, 246, 246)
    return rgb_to_hex(
        black if contrast_ratio(rgb, black) >= contrast_ratio(rgb, white) else white
    )


def hls(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (clamp(c, 0, 255) / 255.0 for c in rgb)
    return colorsys.rgb_to_hls(r, g, b)


def from_hls(
    hue: float, lightness: float, saturation: float
) -> tuple[float, float, float]:
    r, g, b = colorsys.hls_to_rgb(
        hue % 1.0, clamp(lightness, 0, 1), clamp(saturation, 0, 1)
    )
    return (r * 255.0, g * 255.0, b * 255.0)


def tune_for_dark(
    rgb: tuple[float, float, float],
    *,
    min_lightness: float,
    max_lightness: float,
    min_saturation: float,
    max_saturation: float,
) -> tuple[int, int, int]:
    hue, lightness, saturation = hls(rgb)
    lightness = clamp(lightness, min_lightness, max_lightness)
    saturation = clamp(saturation, min_saturation, max_saturation)
    return tuple(int(round(c)) for c in from_hls(hue, lightness, saturation))  # type: ignore[return-value]


def hue_distance(first: float, second: float) -> float:
    delta = abs(first - second) % 360.0
    return min(delta, 360.0 - delta)


def load_image(path: Path) -> Image.Image:
    if Image is None:
        raise RuntimeError("Pillow is not installed (install python-pillow)")

    with Image.open(path) as source:
        # JPEGs can be decoded at a reduced size without loading the full image.
        try:
            source.draft("RGB", (512, 512))
        except Exception:
            pass
        image = source.convert("RGB")
        # Shrink before applying EXIF orientation: exif_transpose returns a
        # copy, and copying a full-resolution 4K frame would double peak RSS.
        image.thumbnail((256, 256), Image.Resampling.LANCZOS)
        if ImageOps is not None:
            try:
                image = ImageOps.exif_transpose(image)
            except Exception:
                pass
    return image


def image_pixels(image: Image.Image) -> list:
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())  # pragma: no cover - older Pillow


def cluster_colours(
    pixels: list[tuple[int, int, int]],
    width: int,
    height: int,
    *,
    attention: list[int] | None = None,
    metrics: dict | None = None,
) -> tuple[list[dict], float, float, float]:
    """Return weighted hue clusters, total vivid weight, and pixel means.

    With *attention* and *metrics* the histogram is weighted by visual
    attention and region priors.  Without them the function keeps the original
    whole-image weighting.
    """
    scene_weighting = bool(
        attention is not None
        and metrics
        and row_weights is not None
        and column_weights is not None
    )
    rows = row_weights(height, metrics) if scene_weighting else None
    columns = column_weights(width) if scene_weighting else None
    x_map = (
        [x * ATTENTION_SIZE // width for x in range(width)] if scene_weighting else None
    )
    y_map = (
        [y * ATTENTION_SIZE // height for y in range(height)]
        if scene_weighting
        else None
    )

    bins: list[dict] = [
        {"hue": index * 10.0 + 5.0, "weight": 0.0, "r": 0.0, "g": 0.0, "b": 0.0}
        for index in range(36)
    ]
    total = 0.0
    saturation_sum = 0.0
    value_sum = 0.0

    for index, (r, g, b) in enumerate(pixels):
        hue, saturation, value = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        saturation_sum += saturation
        value_sum += value
        if saturation < MIN_SATURATION or value < MIN_VALUE or value > MAX_VALUE:
            continue

        weight = (saturation**1.6) * value
        if scene_weighting:
            x = index % width
            y = index // width
            attention_value = (
                attention[y_map[y] * ATTENTION_SIZE + x_map[x]] / 255.0  # type: ignore[index]
            )
            weight *= (
                (ATTENTION_FLOOR + (1.0 - ATTENTION_FLOOR) * attention_value)
                * rows[y]  # type: ignore[index]
                * columns[x]  # type: ignore[index]
            )
        if weight <= 0.0:
            continue

        slot = bins[int((hue * 360.0) // 10.0) % 36]
        slot["weight"] += weight
        slot["r"] += r * weight
        slot["g"] += g * weight
        slot["b"] += b * weight
        total += weight

    count = len(pixels)
    clusters: list[dict] = []
    for slot in bins:
        weight = slot["weight"]
        if weight <= 0.0:
            continue
        clusters.append(
            {
                "hue": slot["hue"],
                "weight": weight,
                "rgb": (
                    slot["r"] / slot["weight"],
                    slot["g"] / slot["weight"],
                    slot["b"] / slot["weight"],
                ),
            }
        )
    clusters.sort(key=lambda item: item["weight"], reverse=True)
    return (
        clusters,
        total,
        saturation_sum / count if count else 0.0,
        value_sum / count if count else 0.0,
    )


def pick_cluster(
    clusters: list[dict],
    *,
    minimum_weight: float,
    excluded_hues: list[float] | None = None,
    separation: float = ACCENT_SEPARATION,
) -> dict | None:
    for cluster in clusters:
        if cluster["weight"] < minimum_weight:
            continue
        if excluded_hues and any(
            hue_distance(cluster["hue"], hue) < separation for hue in excluded_hues
        ):
            continue
        return cluster
    return None


def choose_primary_cluster(
    clusters: list[dict],
    total: float,
    metrics: dict,
) -> dict | None:
    """Pick a seed cluster, demoting a dominant sky when a scene alternative exists.

    A large blue sky can still lead the histogram even after per-pixel
    attention weighting.  When the leading cluster is sky-like, prefer a
    substantial warm family for sunsets, then a substantial green family for
    nature scenes.  If the image is overwhelmingly cool and has no meaningful
    green or warm region, keep the blue cluster so a genuinely blue wallpaper
    stays blue.
    """
    if not clusters or total <= 0:
        return None

    dominant = clusters[0]
    if not 190.0 <= dominant["hue"] <= 265.0:
        return dominant

    blue_fraction = float(metrics.get("blueFraction", 0.0))
    green_fraction = float(metrics.get("greenFraction", 0.0))
    warm_fraction = float(metrics.get("warmFraction", 0.0))
    if blue_fraction > 0.70 and green_fraction < 0.05 and warm_fraction < 0.10:
        return dominant

    minimum = total * 0.10
    warm = [
        cluster
        for cluster in clusters
        if cluster["hue"] < 90.0 or cluster["hue"] > 300.0
    ]
    if warm_fraction >= 0.10 and sum(cluster["weight"] for cluster in warm) >= minimum:
        return max(warm, key=lambda cluster: cluster["weight"])

    green = [cluster for cluster in clusters if 70.0 <= cluster["hue"] <= 165.0]
    if (
        green_fraction >= 0.20
        and sum(cluster["weight"] for cluster in green) >= minimum
    ):
        return max(green, key=lambda cluster: cluster["weight"])

    alternatives = [
        cluster
        for cluster in clusters[1:]
        if cluster["weight"] >= minimum and not 190.0 <= cluster["hue"] <= 265.0
    ]
    if alternatives:
        return max(alternatives, key=lambda cluster: cluster["weight"])
    return dominant


def ansi_palette(
    clusters: list[dict],
    total_weight: float,
    accent: tuple[float, float, float],
    *,
    saturation_scale: float = 1.0,
) -> dict[str, str]:
    _, accent_lightness, accent_saturation = hls(accent)
    palette: dict[str, str] = {}
    minimum_weight = max(total_weight * MIN_CLUSTER_FRACTION, 0.05)
    min_saturation = clamp(0.28 * saturation_scale, 0.0, 0.90)
    max_saturation = clamp(0.86 * saturation_scale, min_saturation, 0.95)

    for name, canonical_hue in ANSI_HUES.items():
        candidate = None
        for cluster in clusters:
            if cluster["weight"] < minimum_weight:
                continue
            if hue_distance(cluster["hue"], canonical_hue) <= ANSI_HUE_TOLERANCE:
                candidate = cluster
                break

        if candidate is not None:
            base = candidate["rgb"]
        else:
            # Missing hue family: keep it recognisable instead of dead grey.
            saturation = clamp(accent_saturation * 0.55, 0.30, 0.55)
            saturation *= clamp(saturation_scale, 0.6, 1.15)
            lightness = clamp(0.58 + accent_lightness * 0.12, 0.58, 0.72)
            base = from_hls(canonical_hue / 360.0, lightness, saturation)

        normal = tune_for_dark(
            base,
            min_lightness=0.55,
            max_lightness=0.78,
            min_saturation=min_saturation,
            max_saturation=max_saturation,
        )
        hue, lightness, saturation = hls(normal)
        bright = from_hls(hue, clamp(lightness + 0.10, 0, 0.86), saturation)
        palette[name] = rgb_to_hex(normal)
        palette[f"bright_{name}"] = rgb_to_hex(bright)

    return palette


def neutral_palette() -> dict[str, str]:
    """Low-saturation ANSI colours for grayscale wallpapers."""
    palette: dict[str, str] = {}
    for name, hue in ANSI_HUES.items():
        normal = from_hls(hue / 360.0, 0.64, 0.22)
        bright = from_hls(hue / 360.0, 0.76, 0.18)
        palette[name] = rgb_to_hex(normal)
        palette[f"bright_{name}"] = rgb_to_hex(bright)
    return palette


def extract_image(
    image: Image.Image,
    *,
    scene_mode: str = "heuristic",
    seed_out: Path | None = None,
    source: str = "",
) -> dict:
    if image.mode != "RGB":
        image = image.convert("RGB")
    if scene_mode == "auto":
        scene_mode = "heuristic"

    scene = None
    attention = None
    if scene_mode != "off" and analyze_scene is not None:
        try:
            attention = build_attention(image)  # type: ignore[misc]
            scene = analyze_scene(image, attention)  # type: ignore[misc]
        except Exception as error:  # noqa: BLE001 - scene analysis is optional
            print(
                f"vibrant: scene analysis failed ({error}); using statistical palette",
                file=sys.stderr,
            )
            attention = None
            scene = None

    pixels = image_pixels(image)
    if not pixels:
        raise RuntimeError("the image contains no pixels")
    width, height = image.size
    clusters, total_weight, mean_saturation, mean_value = cluster_colours(
        pixels,
        width,
        height,
        attention=attention,
        metrics=(scene or {}).get("metrics"),
    )

    strategy = (scene or {}).get("strategy") or {}
    try:
        ansi_saturation = float(strategy.get("ansiSaturation", 1.0))
    except (TypeError, ValueError):
        ansi_saturation = 1.0
    if not math.isfinite(ansi_saturation):
        ansi_saturation = 1.0

    minimum_weight = max(total_weight * MIN_CLUSTER_FRACTION, 0.05)
    grayscale = total_weight <= 0.05 or not clusters

    if grayscale:
        primary = None
    elif scene is not None:
        primary = choose_primary_cluster(clusters, total_weight, scene["metrics"])
    else:
        primary = pick_cluster(clusters, minimum_weight=minimum_weight)
    seed_rgb: tuple[int, int, int] | None = None

    if grayscale or primary is None:
        accent = (216, 216, 216)
        accent_soft = (184, 184, 184)
        ansi = neutral_palette()
        grayscale = True
    else:
        seed_rgb = tune_for_dark(
            primary["rgb"],
            min_lightness=0.50,
            max_lightness=0.62,
            min_saturation=0.55,
            max_saturation=0.80,
        )
        accent = tune_for_dark(
            primary["rgb"],
            min_lightness=0.60,
            max_lightness=0.80,
            min_saturation=0.55,
            max_saturation=0.95,
        )
        secondary = pick_cluster(
            clusters,
            minimum_weight=minimum_weight,
            excluded_hues=[primary["hue"]],
        )
        if secondary is not None:
            accent_soft = tune_for_dark(
                secondary["rgb"],
                min_lightness=0.56,
                max_lightness=0.77,
                min_saturation=0.45,
                max_saturation=0.88,
            )
        else:
            hue, _, saturation = hls(accent)
            accent_soft = tuple(  # type: ignore[assignment]
                int(round(channel))
                for channel in from_hls(
                    hue + (60.0 / 360.0), 0.66, clamp(saturation * 0.8, 0.4, 0.8)
                )
            )
        ansi = ansi_palette(
            clusters,
            total_weight,
            accent,
            saturation_scale=ansi_saturation,
        )

    if scene is not None and seed_out is not None and seed_rgb is not None:
        seed_out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 64), seed_rgb).save(seed_out)

    result: dict = {
        "wallpaper": source,
        "grayscale": grayscale,
        "accent": rgb_to_hex(accent),
        "accent_soft": rgb_to_hex(accent_soft),
        "on_accent": choose_foreground(accent),
        "on_accent_soft": choose_foreground(accent_soft),
        "ansi": ansi,
        "meta": {
            "mean_saturation": round(mean_saturation, 4),
            "mean_value": round(mean_value, 4),
            "vivid_weight": round(total_weight, 4),
            "clusters": len(clusters),
            "scene_mode": scene_mode,
            "scene": scene is not None,
        },
    }
    if scene is not None:
        if seed_rgb is not None:
            result["seed"] = rgb_to_hex(seed_rgb)
        result["scene"] = scene
    elif scene_mode != "off" and SCENE_VERSION:
        # Keep a versioned marker so theme_is_current does not regenerate the
        # same failed image on every restore.
        result["scene"] = {
            "version": SCENE_VERSION,
            "mode": "degraded",
            "confidence": 0.0,
            "degraded": True,
            "tags": [],
            "metrics": {},
            "strategy": {},
        }
    return result


def extract(
    path: Path,
    *,
    scene_mode: str = "heuristic",
    seed_out: Path | None = None,
) -> dict:
    return extract_image(
        load_image(path),
        scene_mode=scene_mode,
        seed_out=seed_out,
        source=str(path),
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="wallpaper or extracted frame")
    parser.add_argument("-o", "--output", type=Path, required=True, help="accents JSON")
    parser.add_argument(
        "--scene",
        choices=["off", "heuristic", "auto"],
        default="heuristic",
        help="scene weighting mode (default: heuristic)",
    )
    parser.add_argument(
        "--seed-out",
        type=Path,
        help="write a 64x64 solid seed PNG for matugen",
    )
    args = parser.parse_args(argv)

    try:
        result = extract(
            args.image,
            scene_mode=args.scene,
            seed_out=args.seed_out,
        )
    except Exception as error:  # noqa: BLE001 - shell wrapper needs a clean failure
        print(f"vibrant: {error}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
