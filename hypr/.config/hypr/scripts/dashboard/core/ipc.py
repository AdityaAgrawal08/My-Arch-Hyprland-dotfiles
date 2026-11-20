from __future__ import annotations

import os
from pathlib import Path

RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
PID_FILE = RUNTIME_DIR / "productivity-dashboard.pid"
CLOSE_FILE = RUNTIME_DIR / "productivity-dashboard.close"


def request_close() -> None:
    try:
        CLOSE_FILE.touch()
    except OSError:
        pass


def close_requested() -> bool:
    return CLOSE_FILE.exists()


def clear_close_request() -> None:
    try:
        CLOSE_FILE.unlink(missing_ok=True)
    except OSError:
        pass
