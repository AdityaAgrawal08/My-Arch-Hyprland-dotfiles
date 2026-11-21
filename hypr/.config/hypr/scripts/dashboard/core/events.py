from __future__ import annotations

import time
from datetime import datetime
from typing import Sequence

from . import notifier, scheduler, store
from .models import DashboardState, Event

SNOOZE_SECONDS = 300  # 5 minutes


def now_ts() -> float:
    return time.time()


def event_time_text(timestamp: float) -> str:
    if not timestamp:
        return "No time"
    return datetime.fromtimestamp(timestamp).strftime("%d-%m-%Y %H:%M")


def notification_title(event: Event) -> str:
    """{Name} - {Actual time when it starts}."""
    return f"{event.name or 'Event'} - {event_time_text(event.end_at)}"


def event_body(event: Event) -> str:
    return event.description or "Event reminder"


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
        if event.notify_at
        and not event.notified
        and not event.dismissed
        and event.notify_at <= now
    ]


def _snooze(event: Event) -> None:
    next_at = now_ts() + SNOOZE_SECONDS
    # Base case: a snooze that would land at or past the event time is
    # dropped from the schedule entirely — no later notification.
    if event.end_at and next_at >= event.end_at:
        event.notify_at = 0.0
        event.notified = True
        event.snoozed = False
    else:
        event.notify_at = next_at
        event.notified = False
        event.snoozed = True


def _handle_action(event: Event, action: str | None) -> None:
    if action == notifier.ACTION_DISMISS:
        event.dismissed = True
        event.notified = True
        event.snoozed = False
    elif action == notifier.SEND_FAILED:
        # Delivery failed: do not loop forever; mark it handled.
        event.notified = True
    else:
        # Explicit Snooze, or no action (expired / closed / left-clicked).
        # Snooze is the default: remind again in five minutes, unless that
        # would pass the event time (then the schedule entry is dropped).
        _snooze(event)


def check_all(send: bool = True) -> tuple[bool, list[Event]]:
    """Single source of truth used by the systemd timer (and CLI).

    Returns (state_changed, notifications_fired). When `send` is False the
    due events are only marked, never displayed.
    """
    state = store.load()
    changed = auto_complete(state)
    due = due_notifications(state)
    fired: list[Event] = []
    for event in due:
        if send:
            action = notifier.show_popup(event.id)
            _handle_action(event, action)
            if event.snoozed or action == notifier.ACTION_DISMISS:
                fired.append(event)
        else:
            event.notified = True
        changed = True
    if changed:
        store.save(state)
    # Keep exact-time timers armed for every still-pending notification.
    scheduler.arm_all(state)
    return changed, fired


def refresh_completion() -> None:
    """Reconcile overdue events without consuming notifications.

    Used by the in-app timer so the GUI never blocks on a waiting notify-send
    and never steals a notification from the systemd timer.
    """
    state = store.load()
    if auto_complete(state):
        store.save(state)


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
