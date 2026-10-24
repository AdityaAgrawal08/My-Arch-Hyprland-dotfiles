#!/usr/bin/env python3
"""Merge Material You roles with extracted accents into one theme document."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Static dark baseline used when matugen is unavailable.
DARK_FALLBACK = {
    "surface": "#141218",
    "outline": "#938f99",
    "outline_variant": "#49454f",
    "on_surface": "#e6e0e9",
    "on_surface_variant": "#cac4d0",
    "error": "#f2b8b5",
    "on_error": "#601410",
}

# Neutral baseline for grayscale wallpapers.  The ANSI hues stay very lightly
# tinted so diffs and listings remain readable.
NEUTRAL_FALLBACK = {
    "surface": "#121212",
    "outline": "#8a8a8a",
    "outline_variant": "#3a3a3a",
    "on_surface": "#e6e6e6",
    "on_surface_variant": "#a8a8a8",
    "error": "#f2b8b5",
    "on_error": "#601410",
}

DEFAULT_ACCENTS = {
    "grayscale": False,
    "accent": "#d0bcff",
    "accent_soft": "#efb8c8",
    "on_accent": "#1d192b",
    "on_accent_soft": "#3b1f2b",
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
        "bright_magenta": "#d3acd3",
    },
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 8:
        value = value[:6]
    if len(value) != 6:
        raise ValueError(f"invalid colour: {value!r}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[float, float, float] | tuple[int, int, int]) -> str:
    r, g, b = (int(round(clamp(float(c), 0, 255))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(first: str, second: str, amount: float) -> str:
    a = hex_to_rgb(first)
    b = hex_to_rgb(second)
    amount = clamp(amount)
    return rgb_to_hex(tuple(x + (y - x) * amount for x, y in zip(a, b)))  # type: ignore[arg-type]


def lighten(value: str, amount: float) -> str:
    return mix(value, "#ffffff", amount)


def darken(value: str, amount: float) -> str:
    return mix(value, "#000000", amount)


def relative_luminance(value: str) -> float:
    def channel(component: int) -> float:
        component = component / 255.0
        return (
            component / 12.92
            if component <= 0.04045
            else ((component + 0.055) / 1.055) ** 2.4
        )

    r, g, b = (channel(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first: str, second: str) -> float:
    a = relative_luminance(first)
    b = relative_luminance(second)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def ensure_contrast(
    foreground: str,
    background: str,
    minimum: float,
    *,
    lift: bool = True,
) -> str:
    """Nudge *foreground* until it reaches *minimum* contrast on *background*."""
    if contrast(foreground, background) >= minimum:
        return foreground
    target = "#ffffff" if lift else "#000000"
    best = foreground
    for step in range(1, 21):
        candidate = mix(foreground, target, step / 20.0)
        best = candidate
        if contrast(candidate, background) >= minimum:
            return candidate
    return best


def choose_on(value: str) -> str:
    black = "#0c0c0c"
    white = "#f6f6f6"
    return black if contrast(value, black) >= contrast(value, white) else white


def rgb_csv(value: str) -> str:
    return ", ".join(str(component) for component in hex_to_rgb(value))


def read_json(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build(args: argparse.Namespace) -> dict:
    roles = read_json(args.roles)
    accents = read_json(args.accents)
    if not accents:
        accents = DEFAULT_ACCENTS

    grayscale = bool(accents.get("grayscale")) or args.fallback == "neutral"
    fallback = NEUTRAL_FALLBACK if grayscale else DARK_FALLBACK

    def role(name: str, default: str) -> str:
        value = roles.get(name, default)
        try:
            hex_to_rgb(value)
            return value.lower()
        except (TypeError, ValueError):
            return default

    surface = role("surface", fallback["surface"])
    on_surface = role("on_surface", fallback["on_surface"])
    on_surface_variant = role("on_surface_variant", fallback["on_surface_variant"])
    outline = role("outline", fallback["outline"])
    outline_variant = role("outline_variant", fallback["outline_variant"])
    error = role("error", fallback["error"])

    # Keep the bar, launcher and terminal modules in the same low-contrast
    # family as the existing dark UI instead of using M3's much lighter
    # surface-variant for every card.
    card = mix(surface, "#ffffff", 0.055)
    card_high = mix(surface, "#ffffff", 0.095)
    hover = mix(surface, "#ffffff", 0.13)
    border = mix(outline_variant, surface, 0.52)

    accent = str(accents.get("accent") or DEFAULT_ACCENTS["accent"]).lower()
    accent_soft = str(
        accents.get("accent_soft") or DEFAULT_ACCENTS["accent_soft"]
    ).lower()
    try:
        hex_to_rgb(accent)
    except ValueError:
        accent = DEFAULT_ACCENTS["accent"]
    try:
        hex_to_rgb(accent_soft)
    except ValueError:
        accent_soft = DEFAULT_ACCENTS["accent_soft"]

    # Material dark roles are already readable on a dark surface, but a bad
    # wallpaper or a custom role should never produce an unreadable theme.
    foreground = ensure_contrast(on_surface, surface, 7.0)
    muted = ensure_contrast(on_surface_variant, surface, 4.0)
    accent = ensure_contrast(accent, surface, 3.0)
    accent_soft = ensure_contrast(accent_soft, surface, 3.0)
    critical = ensure_contrast(error, surface, 3.0)
    on_critical = choose_on(critical)
    on_accent = choose_on(accent)
    on_accent_soft = choose_on(accent_soft)
    bright = lighten(accent, 0.10)

    ansi = dict(DEFAULT_ACCENTS["ansi"])
    ansi.update(accents.get("ansi") or {})
    ansi["black"] = card
    ansi["bright_black"] = ensure_contrast(outline, surface, 2.4)
    ansi["white"] = foreground
    ansi["bright_white"] = "#f5f5f5"

    transparent = mix(surface, accent, 0.10)
    ansi_flat = {
        f"ansi_{name}": value for name, value in ansi.items() if isinstance(value, str)
    }

    return {
        "wallpaper": str(args.wallpaper) if args.wallpaper else "",
        "mtime": int(args.mtime),
        "generated": int(time.time()),
        "mode": "dark",
        "grayscale": grayscale,
        "bg": surface,
        "bgSolid": surface,
        "surface": card,
        "surfaceHigh": card_high,
        "border": border,
        "fg": foreground,
        "bright": bright,
        "muted": muted,
        "hover": hover,
        "accent": accent,
        "accentSoft": accent_soft,
        "onAccent": on_accent,
        "onAccentSoft": on_accent_soft,
        "critical": critical,
        "onCritical": on_critical,
        "success": ansi.get("green", "#a6e3a1"),
        "warning": ansi.get("yellow", "#f9e2af"),
        "kitty_bg_opaque": "#000000",
        "kitty_bg_transparent": transparent,
        # Raw components for hyprlock's rgba(r, g, b, a) syntax.
        "bg_rgb": rgb_csv(surface),
        "surface_rgb": rgb_csv(card),
        "accent_rgb": rgb_csv(accent),
        "accent_soft_rgb": rgb_csv(accent_soft),
        "fg_rgb": rgb_csv(foreground),
        "muted_rgb": rgb_csv(muted),
        "critical_rgb": rgb_csv(critical),
        "ansi": ansi,
        **ansi_flat,
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallpaper", type=Path, help="absolute wallpaper path")
    parser.add_argument(
        "--mtime", type=int, default=0, help="wallpaper modification time"
    )
    parser.add_argument("--roles", type=Path, help="matugen roles JSON")
    parser.add_argument("--accents", type=Path, help="vibrant.py accents JSON")
    parser.add_argument("--fallback", choices=["dark", "neutral"], default="dark")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument(
        "--compat", type=Path, help="optional legacy autotheme.json copy"
    )
    args = parser.parse_args(argv)

    try:
        theme = build(args)
    except Exception as error:  # noqa: BLE001 - shell wrapper needs a clean failure
        print(f"build_theme: {error}", file=sys.stderr)
        return 1

    write_json(args.output, theme)
    if args.compat:
        write_json(args.compat, theme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
