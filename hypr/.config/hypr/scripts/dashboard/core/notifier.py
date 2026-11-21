from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ACTION_SNOOZE = "snooze"
ACTION_DISMISS = "dismiss"
SEND_FAILED = "__failed__"

NOTIFICATION_TIMEOUT_MS = 90_000
MAIN = Path(__file__).resolve().parent.parent / "main.py"


def available() -> bool:
    return shutil.which("notify-send") is not None


def send(summary: str, body: str = "", timeout_ms: int = 10000) -> bool:
    """Plain notification (no actions). Kept as a fallback."""
    if not available():
        return False
    try:
        subprocess.run(
            [
                "notify-send",
                "-a",
                "Productivity Dashboard",
                "-u",
                "normal",
                "-t",
                str(timeout_ms),
                summary,
                body,
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def show_popup(event_id: str, timeout_ms: int = NOTIFICATION_TIMEOUT_MS) -> str | None:
    """Show the clickable Snooze/Dismiss popup for an event.

    Returns the clicked action, None when it timed out/was closed, or
    SEND_FAILED when the popup could not be started.
    """
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "wayland")
    if "WAYLAND_DISPLAY" not in env:
        runtime = Path(env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        sockets = sorted(runtime.glob("wayland-*"))
        if sockets:
            env["WAYLAND_DISPLAY"] = sockets[0].name
    command = [sys.executable, str(MAIN), "--notify", event_id]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=(timeout_ms / 1000) + 12,
        )
    except (OSError, subprocess.SubprocessError):
        return SEND_FAILED
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    action = lines[-1]
    return action if action in (ACTION_SNOOZE, ACTION_DISMISS) else None
