from __future__ import annotations

import time
from datetime import datetime
from typing import Sequence

from . import notifier, store
from .models import DashboardState, Event


def now_ts() -> float:
    return time.time()


def auto_complete(state: DashboardState, now: float | None = None) -> bool:
    """Mark events whose end time passed as completed. Returns True if changed."""
    now = now_ts() if now is None else now
    changed = False
    for event in state.events:
        if not event.completed and event.end_at and event.end_at <= now:
            event.completed = True
            changed = True
    return changed


def due_notifications(state: DashboardState, now: float | None = None) -> list[Event]:
    now = now_ts() if now is None else now
    return [
        event
        for event in state.events
        if event.notify_at and not event.notified and event.notify_at <= now
    ]


def event_body(event: Event) -> str:
    parts = []
    if event.description:
        parts.append(event.description)
    if event.end_at:
        parts.append(
            "Ends: "
            + datetime.fromtimestamp(event.end_at).strftime("%a, %d %b %Y · %H:%M")
        )
    return "\n".join(parts)


def check_all(send: bool = True) -> tuple[bool, list[Event]]:
    """Single source of truth used by the GUI timer and the systemd timer.

    Returns (state_changed, notifications_fired).
    """
    state = store.load()
    changed = auto_complete(state)
    due = due_notifications(state)
    fired: list[Event] = []
    for event in due:
        if send:
            if notifier.send(event.name or "Event", event_body(event)):
                event.notified = True
                fired.append(event)
                changed = True
            # If notify-send failed, leave `notified` cleared so the next
            # check retries instead of silently losing the notification.
        else:
            event.notified = True
            changed = True
    if changed:
        store.save(state)
    return changed, fired


def upcoming(events: Sequence[Event]) -> list[Event]:
    return sorted(
        (event for event in events if not event.completed),
        key=lambda event: event.end_at or float("inf"),
    )


def completed(events: Sequence[Event]) -> list[Event]:
    return sorted(
        (event for event in events if event.completed),
        key=lambda event: event.end_at or float("inf"),
    )
