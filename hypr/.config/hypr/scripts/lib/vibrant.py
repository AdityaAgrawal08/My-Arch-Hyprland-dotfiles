#!/usr/bin/env python3
"""Extract vivid accent colours and a terminal ANSI palette from a wallpaper.

The Material You roles produced by matugen are intentionally pastel.  This
module finds the wallpaper's own most saturated colour clusters so accents can
stay punchy while the surfaces continue to come from matugen.

Only Pillow is required.  The output is a small JSON document consumed by
build_theme.py.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - handled by the shell wrapper
    Image = None


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


def load_pixels(path: Path) -> tuple[list[tuple[int, int, int]], float, float]:
    if Image is None:
        raise RuntimeError("Pillow is not installed (install python-pillow)")

    with Image.open(path) as source:
        # JPEGs can be decoded at a reduced size without loading the full image.
        try:
            source.draft("RGB", (512, 512))
        except Exception:
            pass
        image = source.convert("RGB")
        image.thumbnail((256, 256), Image.Resampling.LANCZOS)
        if hasattr(image, "get_flattened_data"):
            pixels = list(image.get_flattened_data())  # Pillow 13+
        else:
            pixels = list(image.getdata())

    if not pixels:
        raise RuntimeError("the image contains no pixels")

    saturations: list[float] = []
    values: list[float] = []
    for r, g, b in pixels:
        _, saturation, value = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        saturations.append(saturation)
        values.append(value)
    return pixels, sum(saturations) / len(saturations), sum(values) / len(values)


def cluster_colours(pixels: list[tuple[int, int, int]]) -> tuple[list[dict], float]:
    """Return weighted hue clusters and the total vivid weight."""
    bins: list[dict] = [
        {"hue": index * 10.0 + 5.0, "weight": 0.0, "r": 0.0, "g": 0.0, "b": 0.0}
        for index in range(36)
    ]
    total = 0.0

    for r, g, b in pixels:
        hue, saturation, value = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        if saturation < MIN_SATURATION or value < MIN_VALUE or value > MAX_VALUE:
            continue
        weight = (saturation**1.6) * value
        if weight <= 0.0:
            continue
        slot = bins[int((hue * 360.0) // 10.0) % 36]
        slot["weight"] += weight
        slot["r"] += r * weight
        slot["g"] += g * weight
        slot["b"] += b * weight
        total += weight

    clusters: list[dict] = []
    for slot in bins:
        weight = slot["weight"]
        if weight <= 0.0:
            continue
        clusters.append(
            {
                "hue": slot["hue"],
                "weight": weight,
                "rgb": (slot["r"] / weight, slot["g"] / weight, slot["b"] / weight),
            }
        )
    clusters.sort(key=lambda item: item["weight"], reverse=True)
    return clusters, total


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


def ansi_palette(
    clusters: list[dict],
    total_weight: float,
    accent: tuple[float, float, float],
) -> dict[str, str]:
    _, accent_lightness, accent_saturation = hls(accent)
    palette: dict[str, str] = {}
    minimum_weight = max(total_weight * MIN_CLUSTER_FRACTION, 0.05)

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
            lightness = clamp(0.58 + accent_lightness * 0.12, 0.58, 0.72)
            base = from_hls(canonical_hue / 360.0, lightness, saturation)

        normal = tune_for_dark(
            base,
            min_lightness=0.55,
            max_lightness=0.78,
            min_saturation=0.28,
            max_saturation=0.86,
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


def extract(path: Path) -> dict:
    pixels, mean_saturation, mean_value = load_pixels(path)
    clusters, total_weight = cluster_colours(pixels)

    minimum_weight = max(total_weight * MIN_CLUSTER_FRACTION, 0.05)
    # A truly gray image has no pixels passing the saturation filter.  Do not
    # use mean saturation here: a night scene with one vivid light is still a
    # colourful wallpaper.
    grayscale = total_weight <= 0.05 or not clusters
    primary = (
        pick_cluster(clusters, minimum_weight=minimum_weight) if not grayscale else None
    )

    if grayscale or primary is None:
        accent = (216, 216, 216)
        accent_soft = (184, 184, 184)
        ansi = neutral_palette()
        grayscale = True
    else:
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
        ansi = ansi_palette(clusters, total_weight, accent)

    return {
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
        },
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="wallpaper or extracted frame")
    parser.add_argument("-o", "--output", type=Path, required=True, help="accents JSON")
    args = parser.parse_args(argv)

    try:
        result = extract(args.image)
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
