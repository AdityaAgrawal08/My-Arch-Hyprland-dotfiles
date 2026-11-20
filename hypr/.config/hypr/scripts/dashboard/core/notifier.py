from __future__ import annotations

import shutil
import subprocess


def available() -> bool:
    return shutil.which("notify-send") is not None


def send(summary: str, body: str = "", timeout_ms: int = 10000) -> bool:
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
