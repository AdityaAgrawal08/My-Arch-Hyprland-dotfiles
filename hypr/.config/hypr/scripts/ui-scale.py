#!/usr/bin/env python3
"""Change the focused monitor's Hyprland scale (global UI size)."""

from __future__ import annotations

import json
import subprocess
import sys
import time

# Candidate scales. Values that do not produce whole logical pixels
# for the current monitor mode are filtered out below.
CANDIDATES = (
    1.0, 1.1, 1.2, 1.25, 1.3, 1.4, 1.5, 1.6,
    1.7, 1.75, 1.8, 1.875, 2.0, 2.25, 2.4, 2.5,
)


def hyprctl_json(*args: str):
    out = subprocess.check_output(["hyprctl", "-j", *args], text=True)
    return json.loads(out)


def notify(summary: str, body: str) -> None:
    try:
        subprocess.run(
            [
                "notify-send",
                "-a", "Hyprland",
                "-h", "string:x-canonical-private-synchronous:ui-scale",
                summary,
                body,
            ],
            check=False,
        )
    except FileNotFoundError:
        pass


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"up", "down"}:
        print(f"usage: {sys.argv[0]} up|down", file=sys.stderr)
        return 2

    direction = sys.argv[1]
    monitors = hyprctl_json("monitors")
    if not monitors:
        return 1

    monitor = next((m for m in monitors if m.get("focused")), monitors[0])
    width = int(monitor["width"])
    height = int(monitor["height"])
    current = float(monitor["scale"])

    # Hyprland requires the logical resolution to be whole pixels.
    scales = sorted(
        s for s in CANDIDATES
        if abs(width / s - round(width / s)) < 1e-6
        and abs(height / s - round(height / s)) < 1e-6
    )
    if not scales:
        notify("UI scale", "No valid scale for this mode")
        return 1

    if direction == "up":
        new_scale = next((s for s in scales if s > current + 1e-6), None)
    else:
        new_scale = next((s for s in reversed(scales) if s < current - 1e-6), None)

    if new_scale is None:
        notify("UI scale", f"{current:g}× (limit)")
        return 0

    refresh = float(monitor["refreshRate"])
    mode = f"{width}x{height}@{refresh:g}"
    position = f"{monitor['x']}x{monitor['y']}"

    lua = 'hl.monitor({ output = "%s", mode = "%s", position = "%s", scale = %s })' % (
        monitor["name"], mode, position, f"{new_scale:g}"
    )

    try:
        subprocess.run(
            ["hyprctl", "eval", lua],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        notify("UI scale", (exc.stderr or "Failed to apply scale").strip())
        return 1

    # hyprctl can exit 0 without applying the change, so verify it.
    applied = False
    for _ in range(10):
        after = hyprctl_json("monitors")
        actual = next((m for m in after if m.get("name") == monitor["name"]), None)
        if actual and abs(float(actual.get("scale") or 0.0) - new_scale) < 1e-3:
            applied = True
            break
        time.sleep(0.05)

    if not applied:
        notify("UI scale", "Hyprland did not apply the scale")
        return 1

    logical = f"{round(width / new_scale)}×{round(height / new_scale)}"
    notify("UI scale", f"{new_scale:g}× ({logical} logical)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
