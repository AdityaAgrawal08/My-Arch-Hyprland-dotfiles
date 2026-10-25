#!/usr/bin/env python3
"""Keep Waybar at a constant physical size while Hyprland scale changes."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

BASE_SCALE = 1.5
SRC = os.path.expanduser("~/.config/waybar/style.css")
CACHE = os.path.expanduser(os.environ.get("XDG_CACHE_HOME", "~/.cache"))
OUT = os.path.join(CACHE, "waybar", "style.css")
THEME = os.path.join(CACHE, "autotheme", "waybar.css")
FALLBACK_THEME = """\
@define-color bg #101010;
@define-color surface #1a1a1a;
@define-color surface_high #242424;
@define-color border #3a3a3a;
@define-color fg #e6e6e6;
@define-color muted #9a9a9a;
@define-color hover #242424;
@define-color accent #d0d0d0;
@define-color accent_soft #a8a8a8;
@define-color on_accent #111111;
@define-color critical #ff6b6b;
@define-color on_critical #111111;
@define-color bright #ffffff;
"""
PX = re.compile(r"(\d+(?:\.\d+)?)px")


def focused_scale() -> float:
    out = subprocess.check_output(["hyprctl", "-j", "monitors"], text=True)
    monitors = json.loads(out)
    monitor = next((m for m in monitors if m.get("focused")), monitors[0])
    return float(monitor.get("scale") or 1.0)


def generate() -> None:
    scale = focused_scale()
    ratio = BASE_SCALE / scale

    with open(SRC, encoding="utf-8") as f:
        css = f.read()

    try:
        with open(THEME, encoding="utf-8") as f:
            theme = f.read()
    except OSError:
        theme = FALLBACK_THEME

    css = PX.sub(lambda m: f"{float(m.group(1)) * ratio:.2f}px", css)
    css = theme.rstrip() + "\n\n" + css

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(css)


def reload_waybar() -> None:
    subprocess.run(["pkill", "-USR2", "-x", "waybar"], check=False)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "apply"
    if mode not in {"start", "apply"}:
        print(f"usage: {sys.argv[0]} start|apply", file=sys.stderr)
        return 2

    generate()

    if mode == "start":
        os.execvp("waybar", ["waybar", "-s", OUT])
    else:
        reload_waybar()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
