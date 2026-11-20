from __future__ import annotations

import json
import re
import subprocess
from typing import Any

WINDOW_CLASS = "productivity-dashboard"


def _json(*args: str) -> Any:
    output = subprocess.check_output(
        ["hyprctl", "-j", *args], text=True, timeout=8, stderr=subprocess.DEVNULL
    )
    return json.loads(output)


def _raw(*args: str) -> str:
    return subprocess.check_output(
        ["hyprctl", *args], text=True, timeout=8, stderr=subprocess.DEVNULL
    )


def _waybar_bottom(fallback_y: int) -> int:
    try:
        layers = _raw("layers")
    except (OSError, subprocess.SubprocessError):
        return fallback_y + 42
    for line in layers.splitlines():
        if "namespace: waybar" not in line:
            continue
        match = re.search(r"xywh:\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", line)
        if match:
            return int(match.group(2)) + int(match.group(4))
    return fallback_y + 42


def display_geometry() -> dict[str, int | float]:
    """Logical monitor geometry plus the bottom edge of the Waybar layer."""
    try:
        monitors = _json("monitors")
        monitor = next((m for m in monitors if m.get("focused")), monitors[0])
        scale = float(monitor.get("scale") or 1.0) or 1.0
        x = int(round(float(monitor.get("x", 0)) / scale))
        y = int(round(float(monitor.get("y", 0)) / scale))
        width = int(round(float(monitor["width"]) / scale))
        height = int(round(float(monitor["height"]) / scale))
    except (
        OSError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ):
        x, y, width, height, scale = 0, 0, 1280, 720, 1.0
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "scale": scale,
        "bar_bottom": _waybar_bottom(y),
    }


def window_address() -> str:
    try:
        clients = _json("clients")
        for client in clients:
            cls = str(client.get("class") or "").lower()
            title = str(client.get("title") or "")
            if cls == WINDOW_CLASS or title == "Productivity Dashboard":
                return str(client.get("address") or "")
    except (OSError, TypeError, ValueError, subprocess.SubprocessError):
        pass
    return ""


def place_window(address: str, x: int, y: int, width: int, height: int) -> None:
    """Qt already applies the geometry; the window rule keeps it floating.

    Hyprland's Lua config makes legacy `hyprctl dispatch` strings invalid, so
    no dispatch is issued here. The parameters are kept for callers that want
    to apply additional positioning later.
    """
    return


def raise_window(address: str) -> None:
    if not address:
        return
    lua = f'hl.dsp.focus({{ window = "address:{address}" }})'
    try:
        subprocess.run(
            ["hyprctl", "eval", lua],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return


def dashboard_geometry() -> tuple[int, int, int, int, int]:
    """Return (window_x, window_y, window_w, window_h, card_max_width)."""
    geo = display_geometry()
    x = int(geo["x"])
    top = int(geo["bar_bottom"])
    width = int(geo["width"])
    height = max(320, int(geo["height"]) - top)
    return x, top, width, height, min(880, width - 96)
