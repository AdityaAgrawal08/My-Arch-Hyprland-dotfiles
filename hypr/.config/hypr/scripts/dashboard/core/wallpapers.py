from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SWITCH_SCRIPT = Path.home() / ".config/hypr/scripts/wallpaper_switch.sh"
CURRENT_FILE = (
    Path(os.path.expanduser(os.environ.get("XDG_CACHE_HOME", "~/.cache")))
    / "autotheme/wallpaper"
)


def list_wallpapers() -> list[dict[str, Any]]:
    if not SWITCH_SCRIPT.is_file():
        return []
    try:
        output = subprocess.check_output(
            [str(SWITCH_SCRIPT), "list-json"],
            text=True,
            timeout=20,
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(output)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def current_wallpaper() -> str:
    try:
        return CURRENT_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def apply_wallpaper(path: str) -> bool:
    if not path or not Path(path).is_file() or not SWITCH_SCRIPT.is_file():
        return False
    try:
        subprocess.Popen(
            [str(SWITCH_SCRIPT), "apply", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def picker_available() -> bool:
    return shutil.which("wofi") is not None
