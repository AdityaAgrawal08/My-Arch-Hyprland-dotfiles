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
OUT = os.path.expanduser(
    os.path.join(os.environ.get("XDG_CACHE_HOME", "~/.cache"), "waybar", "style.css")
)
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

    css = PX.sub(lambda m: f"{float(m.group(1)) * ratio:.2f}px", css)

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
