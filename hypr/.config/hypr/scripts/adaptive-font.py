#!/usr/bin/env python3
"""Adaptive font size for kitty windows on Hyprland.

Keeps every kitty window's font size (and optionally its padding) proportional
to the window's tiled size, so terminals stay consistent whether one, two or
more windows share a workspace.

Requires in kitty.conf:
    allow_remote_control yes
    listen_on unix:${XDG_RUNTIME_DIR}/kitty
"""
from __future__ import annotations

import glob
import json
import math
import os
import shutil
import socket
import subprocess
import time

# ------------------------------- tuning -------------------------------------
BASE_FONT     = 10.0   # font size when a kitty window has the full space
MIN_FONT      = 7.0    # readability floor
MAX_FONT      = 14.0   # ceiling
SCALE_PADDING = True   # also scale window padding with the size
BASE_PADDING  = 12.0   # padding at full size (window_padding_width)
MIN_PADDING   = 6.0
MAX_PADDING   = 12.0
DEBOUNCE      = 0.3    # seconds to wait after the last window event
# ----------------------------------------------------------------------------

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
KITTEN  = shutil.which("kitten") or "/usr/bin/kitten"
BASE_AREA = 1276.0 * 674.0
BASE_SCALE = 1.5

WATCHED_EVENTS = {
    "openwindow", "closewindow", "movewindow", "resizewindow",
    "changefloatingmode", "fullscreen", "monitoradded", "monitorremoved",
    "activespecial", "configreloaded",
}


def hyprctl_json(*args: str):
    out = subprocess.run(["hyprctl", "-j", *args],
                         capture_output=True, text=True).stdout
    return json.loads(out)


def baseline_area() -> float:
    """Usable area (logical px) of one full-size tiled window."""
    global BASE_SCALE
    try:
        mons = hyprctl_json("monitors")
        m = next((x for x in mons if x.get("focused")), mons[0])
        scale = float(m.get("scale", 1.0)) or 1.0
        BASE_SCALE  = scale
        w = m["width"] / scale - 4.0                # outer gaps/borders
        reserved = m.get("reserved") or [0, 0, 0, 0]
        h = m["height"] / scale - 4.0 - max(reserved)   # status bar etc.
        if w > 100 and h > 100:
            return w * h
    except Exception:
        pass
    return BASE_AREA


def target_size(area: float, monitor_scale: float):
    """Return (font_size, padding) for a window of the given pixel area."""
    scale = math.sqrt(max(area, 1.0) / BASE_AREA)
    # Keep the terminal's physical size in sync with the compositor's
    # global UI scale instead of cancelling monitor-scale changes.
    scale *= monitor_scale / BASE_SCALE
    font = round(max(MIN_FONT, min(MAX_FONT, BASE_FONT * scale)), 1)
    pad = None
    if SCALE_PADDING:
        pad = int(round(max(MIN_PADDING, min(MAX_PADDING, BASE_PADDING * scale))))
    return font, pad


def push(pid: int, font: float, pad) -> None:
    """Send the new font size (and padding) to the kitty instance owning pid."""
    addr = f"unix:{RUNTIME}/kitty-{pid}"
    try:
        subprocess.run([KITTEN, "@", "--to", addr, "set-font-size", "--all", f"{font}"],
                       capture_output=True, timeout=5)
        if pad is not None:
            subprocess.run([KITTEN, "@", "--to", addr, "set-spacing", "--all", f"padding={pad}"],
                           capture_output=True, timeout=5)
    except Exception:
        pass


def apply_all(applied: dict) -> None:
    try:
        clients = hyprctl_json("clients")
        mons = hyprctl_json("monitors")
    except Exception:
        return
    scale_by_id = {m.get("id"): float(m.get("scale") or 1.0) for m in mons}
    alive = set()
    for c in clients:
        if c.get("class") != "kitty" or not c.get("mapped"):
            continue
        pid = c.get("pid")
        if not pid:
            continue
        alive.add(pid)
        w, h = c.get("size", [0, 0])
        monitor_scale = scale_by_id.get(c.get("monitor"), 1.0)
        font, pad = target_size(max(1, w * h), monitor_scale)
        if applied.get(pid) != (font, pad):
            push(pid, font, pad)
            applied[pid] = (font, pad)
    for pid in list(applied):
        if pid not in alive:
            del applied[pid]


def event_socket():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    path = f"{RUNTIME}/hypr/{sig}/.socket2.sock"
    if sig and os.path.exists(path):
        return path
    socks = glob.glob(f"{RUNTIME}/hypr/*/.socket2.sock")
    return max(socks, key=os.path.getmtime) if socks else None


def already_running() -> bool:
    pidfile = f"{RUNTIME}/adaptive-font.pid"
    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())
        if pid != os.getpid():
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                if b"adaptive-font" in f.read():
                    return True
        raise ValueError
    except Exception:
        try:
            with open(pidfile, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass
        return False


def main() -> None:
    if already_running():
        return
    global BASE_AREA
    BASE_AREA = baseline_area()

    applied: dict = {}
    while True:
        path = event_socket()
        if not path:
            time.sleep(2)
            continue
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            sock.connect(path)
        except OSError:
            sock.close()
            time.sleep(2)
            continue

        pending_until = time.monotonic() + 0.5   # initial pass for open windows
        buf = b""
        try:
            while True:
                try:
                    data = sock.recv(4096)
                    if not data:
                        raise ConnectionError("hyprland event socket closed")
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        ev = line.decode(errors="replace").split(">>", 1)[0]
                        if ev in WATCHED_EVENTS:
                            pending_until = time.monotonic() + DEBOUNCE
                except socket.timeout:
                    pass
                if pending_until and time.monotonic() >= pending_until:
                    pending_until = 0.0
                    apply_all(applied)
        except Exception:
            time.sleep(2)
        finally:
            try:
                sock.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
