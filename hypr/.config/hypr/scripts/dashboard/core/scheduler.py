from __future__ import annotations

import math
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .models import DashboardState, Event

LAUNCHER = str(Path.home() / ".local/bin/productivity-dashboard")


def _unit(event_id: str) -> str:
    return f"productivity-dashboard-{event_id[:12]}"


def cancel(event_id: str) -> None:
    if not shutil.which("systemctl"):
        return
    subprocess.run(
        ["systemctl", "--user", "stop", f"{_unit(event_id)}.timer"],
        check=False,
        capture_output=True,
        timeout=5,
    )


def arm(event: Event) -> None:
    """Schedule a one-shot systemd timer at the exact notification second."""
    cancel(event.id)
    if not event.notify_at or event.notified or event.dismissed:
        return
    if not shutil.which("systemd-run") or not shutil.which("systemctl"):
        return
    # systemd calendar timers fire on whole seconds; round up so the event is
    # never considered "not yet due" when the timer fires.
    when = datetime.fromtimestamp(math.ceil(event.notify_at)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    subprocess.run(
        [
            "systemd-run",
            "--user",
            "--unit",
            _unit(event.id),
            "--on-calendar",
            when,
            # systemd's default AccuracySec is 1 minute, which makes an
            # exact-time notification arrive visibly late.
            "--timer-property=AccuracySec=100ms",
            "--collect",
            LAUNCHER,
            "--check-notifications",
        ],
        check=False,
        capture_output=True,
        timeout=10,
    )


def arm_all(state: DashboardState) -> None:
    for event in state.events:
        if not event.notified and not event.dismissed and event.notify_at:
            arm(event)
