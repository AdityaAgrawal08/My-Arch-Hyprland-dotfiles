#!/usr/bin/env python3
"""Heuristic scene analysis for wallpaper-derived themes.

The analyser is deliberately small: it uses Pillow only, runs in the existing
``vibrant.py`` process, and keeps no state.  It produces an attention map, a
set of tone/colour/structure metrics, descriptive tags, and a palette strategy.

There is no semantic segmentation model and no external service.  The tags are
statistical descriptions of the image, not object classes.
"""

from __future__ import annotations

import colorsys
import math

from PIL import Image, ImageChops, ImageFilter, ImageOps

VERSION = 3
ATTENTION_SIZE = 64
METRIC_SIZE = 128


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def pixels(image: Image.Image) -> list:
    """Return pixel values without the Pillow 14 ``getdata`` deprecation."""
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())  # pragma: no cover - older Pillow


def _center_prior(size: int = ATTENTION_SIZE) -> Image.Image:
    center = (size - 1) / 2.0
    data = bytearray(size * size)
    for y in range(size):
        for x in range(size):
            dx = (x - center) / center
            dy = (y - center) / center
            data[y * size + x] = max(0, 255 - int(math.hypot(dx, dy) * 170))
    return Image.frombytes("L", (size, size), bytes(data))


CENTER_PRIOR = _center_prior()


def build_attention(image: Image.Image) -> list[int]:
    """Build a small centre-weighted colour/contrast attention map.

    A large solid subject can have little high-frequency detail inside it, so
    the map combines a coarse colour centre-surround term with a grayscale
    high-pass term.  Both are cheap Pillow filters.
    """
    if image.mode != "RGB":
        image = image.convert("RGB")
    small = image.resize((ATTENTION_SIZE, ATTENTION_SIZE), Image.Resampling.BILINEAR)

    surround = small.filter(ImageFilter.GaussianBlur(6))
    difference = ImageChops.difference(small, surround)
    red, green, blue = difference.split()
    colour = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    colour = colour.filter(ImageFilter.GaussianBlur(2))

    gray = small.convert("L")
    local = ImageChops.difference(gray, gray.filter(ImageFilter.GaussianBlur(2)))
    local = local.filter(ImageFilter.GaussianBlur(1))

    attention = ImageChops.add(colour, local)
    attention = ImageChops.multiply(attention, CENTER_PRIOR)
    attention = ImageOps.autocontrast(attention)

    values = pixels(attention)
    if max(values, default=0) == 0:
        return [128] * (ATTENTION_SIZE * ATTENTION_SIZE)
    return values


def _percentile(histogram: list[int], total: int, fraction: float) -> int:
    target = total * fraction
    running = 0
    for index, count in enumerate(histogram):
        running += count
        if running >= target:
            return index
    return len(histogram) - 1


def _is_skin(red: int, green: int, blue: int) -> bool:
    return (
        red > 95
        and green > 40
        and blue > 20
        and max(red, green, blue) - min(red, green, blue) > 15
        and abs(red - green) > 15
        and red > green
        and red > blue
    )


def _attention_metrics(attention: list[int]) -> tuple[float, float, float]:
    total = sum(attention)
    if total <= 0:
        return 0.0, 0.0, 0.0
    mean = total / len(attention)
    variance = sum((value - mean) ** 2 for value in attention) / len(attention)
    deviation = math.sqrt(variance)
    subject = sum(1 for value in attention if value > mean + deviation)

    centre_start = ATTENTION_SIZE // 4
    centre_end = ATTENTION_SIZE - centre_start
    centre_sum = 0
    for y in range(ATTENTION_SIZE):
        if not centre_start <= y < centre_end:
            continue
        row = y * ATTENTION_SIZE
        centre_sum += sum(attention[row + centre_start : row + centre_end])

    return mean / 255.0, subject / len(attention), centre_sum / total


def analyze(image: Image.Image, attention: list[int] | None = None) -> dict:
    """Return metrics, tags, and a palette strategy for *image*."""
    if image.mode != "RGB":
        image = image.convert("RGB")
    if attention is None:
        attention = build_attention(image)

    small = image.resize((METRIC_SIZE, METRIC_SIZE), Image.Resampling.BILINEAR)
    sample = pixels(small)
    count = len(sample)
    if count == 0:
        raise RuntimeError("the image contains no pixels")

    luma_image = small.convert("L")
    histogram = luma_image.histogram()
    total = sum(histogram)
    luma_mean = sum(index * value for index, value in enumerate(histogram)) / total
    variance = (
        sum((index - luma_mean) ** 2 * value for index, value in enumerate(histogram))
        / total
    )
    luma_median = _percentile(histogram, total, 0.50) / 255.0
    luma_p10 = _percentile(histogram, total, 0.10) / 255.0
    luma_p90 = _percentile(histogram, total, 0.90) / 255.0
    contrast = math.sqrt(variance) / 255.0
    entropy = -sum(
        (value / total) * math.log2(value / total) for value in histogram if value
    )
    entropy = clamp(entropy / 8.0)

    edge_image = luma_image.filter(ImageFilter.FIND_EDGES)
    edges = pixels(edge_image)
    edge_density = sum(edges) / (count * 255.0)
    flat_fraction = sum(1 for value in edges if value < 8) / count

    saturations: list[float] = []
    saturation_sum = 0.0
    value_sum = 0.0
    chromatic = 0
    green_pixels = 0
    blue_pixels = 0
    warm = 0
    cool = 0
    skin = 0
    sky = 0
    ground = 0
    top_limit = int(count * 0.40)
    bottom_start = int(count * 0.75)
    bottom_count = count - bottom_start
    red_green_sum = 0.0
    yellow_blue_sum = 0.0
    red_green_square = 0.0
    yellow_blue_square = 0.0

    for index, (red, green, blue) in enumerate(sample):
        hue, saturation, value = colorsys.rgb_to_hsv(
            red / 255.0, green / 255.0, blue / 255.0
        )
        saturation_sum += saturation
        value_sum += value
        saturations.append(saturation)

        is_chromatic = saturation > 0.25 and value > 0.08
        if is_chromatic:
            chromatic += 1
            if hue < 90.0 / 360.0 or hue > 300.0 / 360.0:
                warm += 1
            elif 180.0 / 360.0 <= hue <= 270.0 / 360.0:
                cool += 1

        if saturation > 0.18 and 70.0 / 360.0 <= hue <= 165.0 / 360.0:
            green_pixels += 1
        if saturation > 0.18 and 190.0 / 360.0 <= hue <= 265.0 / 360.0:
            blue_pixels += 1
        if _is_skin(red, green, blue):
            skin += 1

        edge = edges[index]
        if index < top_limit:
            sky_like = (
                saturation > 0.10 and 190.0 / 360.0 <= hue <= 265.0 / 360.0
            ) or (saturation < 0.15 and value > 0.60)
            if edge < 12 and sky_like:
                sky += 1
        elif index >= bottom_start:
            if edge < 10 and (saturation < 0.30 or value < 0.35):
                ground += 1

        red_green = red - green
        yellow_blue = 0.5 * (red + green) - blue
        red_green_sum += red_green
        yellow_blue_sum += yellow_blue
        red_green_square += red_green * red_green
        yellow_blue_square += yellow_blue * yellow_blue

    mean_saturation = saturation_sum / count
    mean_value = value_sum / count
    saturations.sort()
    sat_p90 = saturations[min(count - 1, int(count * 0.90))]
    chroma_fraction = chromatic / count

    red_green_mean = red_green_sum / count
    yellow_blue_mean = yellow_blue_sum / count
    red_green_std = (
        max(0.0, red_green_square / count - red_green_mean * red_green_mean) ** 0.5
    )
    yellow_blue_std = (
        max(0.0, yellow_blue_square / count - yellow_blue_mean * yellow_blue_mean)
        ** 0.5
    )
    colorfulness = math.hypot(red_green_std, yellow_blue_std) + 0.3 * math.hypot(
        red_green_mean, yellow_blue_mean
    )

    green_fraction = green_pixels / count
    blue_fraction = blue_pixels / count
    warm_fraction = warm / chromatic if chromatic else 0.0
    cool_fraction = cool / chromatic if chromatic else 0.0
    skin_fraction = skin / count
    sky_fraction = sky / top_limit if top_limit else 0.0
    ground_fraction = ground / bottom_count if bottom_count else 0.0

    top_luma = (
        sum(
            index * value
            for index, value in enumerate(
                small.crop((0, 0, METRIC_SIZE, int(METRIC_SIZE * 0.40)))
                .convert("L")
                .histogram()
            )
        )
        / (METRIC_SIZE * int(METRIC_SIZE * 0.40))
        / 255.0
    )
    bottom_luma = (
        sum(
            index * value
            for index, value in enumerate(
                small.crop((0, int(METRIC_SIZE * 0.75), METRIC_SIZE, METRIC_SIZE))
                .convert("L")
                .histogram()
            )
        )
        / (METRIC_SIZE * (METRIC_SIZE - int(METRIC_SIZE * 0.75)))
        / 255.0
    )
    centre_luma = (
        sum(
            index * value
            for index, value in enumerate(
                small.crop(
                    (
                        int(METRIC_SIZE * 0.25),
                        int(METRIC_SIZE * 0.25),
                        int(METRIC_SIZE * 0.75),
                        int(METRIC_SIZE * 0.75),
                    )
                )
                .convert("L")
                .histogram()
            )
        )
        / (int(METRIC_SIZE * 0.5) ** 2)
        / 255.0
    )

    attention_mean, subject_fraction, centre_mass = _attention_metrics(attention)

    tags: list[dict] = []

    def add_tag(name: str, score: float) -> None:
        score = clamp(score)
        if score >= 0.35:
            tags.append({"name": name, "confidence": round(score, 2)})

    monochrome_score = max(
        clamp((0.06 - chroma_fraction) / 0.06),
        clamp((0.12 - sat_p90) / 0.12),
    )
    add_tag("monochrome", monochrome_score)
    add_tag("low-key", (0.30 - luma_median) / 0.16)
    add_tag("high-key", (luma_median - 0.62) / 0.16)
    vivid_score = (
        0.0
        if monochrome_score >= 0.5
        else ((sat_p90 - 0.45) / 0.30) * 0.6 + ((colorfulness - 25.0) / 40.0) * 0.4
    )
    add_tag("vivid", vivid_score)
    muted_score = 0.0 if monochrome_score >= 0.5 else (0.38 - sat_p90) / 0.20
    add_tag("muted", muted_score)
    add_tag(
        "minimal",
        ((0.12 - edge_density) / 0.08) * 0.6 + ((flat_fraction - 0.45) / 0.35) * 0.4,
    )
    add_tag("busy", (edge_density - 0.15) / 0.15)
    add_tag("warm", (warm_fraction - 0.55) / 0.30)
    add_tag("cool", (cool_fraction - 0.55) / 0.30)
    add_tag("nature", (green_fraction - 0.10) / 0.30)
    add_tag(
        "sky-water",
        (max(sky_fraction, blue_fraction) - 0.18) / 0.35,
    )
    add_tag(
        "sunset",
        clamp((warm_fraction - 0.10) / 0.15) * clamp((sky_fraction - 0.25) / 0.35),
    )
    add_tag(
        "urban",
        clamp((edge_density - 0.12) / 0.16)
        * clamp((0.12 - green_fraction) / 0.12)
        * clamp((chroma_fraction - 0.08) / 0.20),
    )

    tags.sort(key=lambda item: item["confidence"], reverse=True)
    confidence = max((item["confidence"] for item in tags), default=0.0)
    degraded = confidence < 0.45
    by_name = {item["name"]: item["confidence"] for item in tags}

    scheme = "scheme-tonal-spot"
    if by_name.get("monochrome", 0.0) >= 0.5:
        scheme = "scheme-monochrome"
    elif by_name.get("nature", 0.0) >= 0.5:
        scheme = "scheme-content"
    elif by_name.get("sky-water", 0.0) >= 0.5:
        scheme = "scheme-fidelity"
    elif by_name.get("muted", 0.0) >= 0.5 or by_name.get("minimal", 0.0) >= 0.6:
        scheme = "scheme-neutral"
    elif by_name.get("vivid", 0.0) >= 0.5 and (
        by_name.get("busy", 0.0) >= 0.35 or by_name.get("urban", 0.0) >= 0.35
    ):
        scheme = "scheme-vibrant"
    elif by_name.get("vivid", 0.0) >= 0.70:
        scheme = "scheme-vibrant"

    contrast = clamp(
        0.10 * by_name.get("low-key", 0.0)
        - 0.04 * by_name.get("high-key", 0.0)
        + 0.06 * by_name.get("vivid", 0.0)
        - 0.03 * by_name.get("muted", 0.0),
        -0.12,
        0.22,
    )
    if scheme == "scheme-monochrome":
        lightness_dark = 0.0
    else:
        # Matugen's --lightness-dark moves the black point, so large negative
        # values clip shadows to pure black.  Keep the nudge deliberately small.
        lightness_dark = clamp(
            -0.02 * by_name.get("low-key", 0.0) + 0.01 * by_name.get("high-key", 0.0),
            -0.02,
            0.02,
        )

    ansi_saturation = (
        0.0
        if scheme == "scheme-monochrome"
        else clamp(
            1.0 + 0.10 * by_name.get("vivid", 0.0) - 0.20 * by_name.get("muted", 0.0),
            0.60,
            1.15,
        )
    )

    if by_name.get("nature", 0.0) >= 0.5:
        surface_tint = 0.85
    elif by_name.get("sky-water", 0.0) >= 0.5:
        surface_tint = 0.70
    elif by_name.get("urban", 0.0) >= 0.5:
        surface_tint = 0.65
    elif by_name.get("minimal", 0.0) >= 0.5:
        surface_tint = 0.50
    else:
        surface_tint = 0.70
    surface_tint *= 0.5 + 0.5 * confidence

    if by_name.get("busy", 0.0) >= 0.5:
        border_contrast = 1.0
    elif by_name.get("minimal", 0.0) >= 0.5:
        border_contrast = 0.60
    else:
        border_contrast = 0.80

    metrics = {
        "lumaMean": round(luma_mean / 255.0, 4),
        "lumaMedian": round(luma_median, 4),
        "lumaP10": round(luma_p10, 4),
        "lumaP90": round(luma_p90, 4),
        "contrast": round(contrast, 4),
        "entropy": round(entropy, 4),
        "satMean": round(mean_saturation, 4),
        "satP90": round(sat_p90, 4),
        "chromaFraction": round(chroma_fraction, 4),
        "colorfulness": round(colorfulness, 2),
        "edgeDensity": round(edge_density, 4),
        "flatFraction": round(flat_fraction, 4),
        "warmFraction": round(warm_fraction, 4),
        "coolFraction": round(cool_fraction, 4),
        "greenFraction": round(green_fraction, 4),
        "blueFraction": round(blue_fraction, 4),
        "skyFraction": round(sky_fraction, 4),
        "groundFraction": round(ground_fraction, 4),
        "topLuma": round(top_luma, 4),
        "bottomLuma": round(bottom_luma, 4),
        "centreLuma": round(centre_luma, 4),
        "skinFraction": round(skin_fraction, 4),
        "attentionMean": round(attention_mean, 4),
        "subjectFraction": round(subject_fraction, 4),
        "centreMass": round(centre_mass, 4),
    }

    return {
        "version": VERSION,
        "confidence": round(confidence, 2),
        "degraded": degraded,
        "tags": tags,
        "metrics": metrics,
        "strategy": {
            "scheme": scheme,
            "contrast": round(contrast, 4),
            "lightnessDark": round(lightness_dark, 4),
            "ansiSaturation": round(ansi_saturation, 4),
            "surfaceTint": round(surface_tint, 4),
            "borderContrast": round(border_contrast, 4),
        },
    }


def row_weights(height: int, metrics: dict) -> list[float]:
    """Vertical region priors used while weighting colour clusters."""
    sky = float(metrics.get("skyFraction", 0.0)) > 0.12
    ground = float(metrics.get("groundFraction", 0.0)) > 0.12
    weights: list[float] = []
    for y in range(height):
        position = y / (height - 1) if height > 1 else 0.0
        weight = 1.0
        if sky and position < 0.42:
            weight *= 1.0 - 0.65 * (1.0 - position / 0.42)
        if ground and position > 0.72:
            weight *= 1.0 - 0.50 * ((position - 0.72) / 0.28)
        weights.append(weight)
    return weights


def column_weights(width: int) -> list[float]:
    """Side-border prior used while weighting colour clusters."""
    weights: list[float] = []
    for x in range(width):
        position = x / (width - 1) if width > 1 else 0.5
        edge = min(position, 1.0 - position)
        weights.append(0.65 + 0.35 * clamp(edge / 0.10))
    return weights
