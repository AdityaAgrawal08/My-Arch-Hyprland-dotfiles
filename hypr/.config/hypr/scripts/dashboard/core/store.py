from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import DashboardState

DATA_HOME = Path(os.path.expanduser(os.environ.get("XDG_DATA_HOME", "~/.local/share")))
STATE_DIR = DATA_HOME / "productivity-dashboard"
STATE_FILE = STATE_DIR / "state.json"
LOCK_FILE = STATE_DIR / "state.lock"


@contextmanager
def locked() -> Iterator[None]:
    """Serialize all readers and writers with an advisory file lock."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def load() -> DashboardState:
    with locked():
        try:
            raw = STATE_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("state root is not an object")
            return DashboardState.from_dict(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return DashboardState()


def save(state: DashboardState) -> bool:
    """Atomically write the state. Returns True on success."""
    with locked():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=STATE_DIR, prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state.to_dict(), handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, STATE_FILE)
            return True
        except (OSError, TypeError, ValueError):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            return False


def reset() -> bool:
    with locked():
        try:
            STATE_FILE.unlink(missing_ok=True)
            return True
        except OSError:
            return False
