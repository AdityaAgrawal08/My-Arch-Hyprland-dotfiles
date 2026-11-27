#!/usr/bin/env python3
"""Core logic tests: models, persistence, events, calendar, IPC."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard.core import (
    calendar_logic,
    events,
    ipc,
    models,
    notifier,
    scheduler,
    store,
)


class ModelsTests(unittest.TestCase):
    def test_from_dict_is_defensive(self) -> None:
        state = models.DashboardState.from_dict(
            {"todos": [{"name": "x", "subtasks": [{"name": "s"}]}], "unknown": 1}
        )
        self.assertEqual(len(state.todos), 1)
        self.assertEqual(state.todos[0].name, "x")
        self.assertEqual(state.todos[0].subtasks[0].name, "s")
        self.assertEqual(len(state.events), 0)

    def test_invalid_fields_fall_back(self) -> None:
        todo = models.Todo.from_dict({"completed": "yes", "subtasks": "bad"})
        self.assertTrue(todo.completed)
        self.assertEqual(todo.subtasks, [])
        event = models.Event.from_dict({"end_at": "oops", "notify_at": None})
        self.assertEqual(event.end_at, 0.0)
        self.assertEqual(event.notify_at, 0.0)

    def test_active_count_and_auto_strike(self) -> None:
        state = models.DashboardState()
        state.todos.append(
            models.Todo(
                name="A",
                subtasks=[
                    models.Subtask(name="1", completed=True),
                    models.Subtask(name="2", completed=True),
                ],
            )
        )
        self.assertEqual(state.active_todos, 1)
        state.todos[0].sync_completion()
        self.assertTrue(state.todos[0].completed)
        self.assertEqual(state.active_todos, 0)
        state.todos[0].subtasks[1].completed = False
        state.todos[0].sync_completion()
        self.assertFalse(state.todos[0].completed)
        self.assertEqual(state.active_todos, 1)

    def test_completed_items_are_never_dropped(self) -> None:
        state = models.DashboardState.from_dict(
            {
                "todos": [{"name": "done", "completed": True}],
                "events": [{"name": "past", "completed": True, "end_at": 1}],
            }
        )
        again = models.DashboardState.from_dict(state.to_dict())
        self.assertEqual(len(again.todos), 1)
        self.assertEqual(len(again.events), 1)
        self.assertTrue(again.todos[0].completed)
        self.assertTrue(again.events[0].completed)


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="dash-store-")
        self.patch = patch.dict(os.environ, {"XDG_DATA_HOME": self.temp.name})
        self.patch.start()
        import importlib

        importlib.reload(store)

    def tearDown(self) -> None:
        self.patch.stop()
        self.temp.cleanup()

    def test_missing_and_corrupt_state(self) -> None:
        self.assertEqual(store.load().todos, [])
        store.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        store.STATE_FILE.write_text("not json")
        self.assertEqual(store.load().events, [])

    def test_atomic_roundtrip(self) -> None:
        state = models.DashboardState()
        state.todos.append(models.Todo(name="task"))
        state.events.append(models.Event(name="event", end_at=10, notify_at=5))
        self.assertTrue(store.save(state))
        loaded = store.load()
        self.assertEqual(loaded.todos[0].name, "task")
        self.assertEqual(loaded.events[0].end_at, 10)
        self.assertTrue(store.LOCK_FILE.exists())
        self.assertFalse(any(store.STATE_DIR.glob(".state-*.tmp")))

    def test_reset(self) -> None:
        store.save(models.DashboardState())
        self.assertTrue(store.reset())
        self.assertFalse(store.STATE_FILE.exists())


class EventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="dash-events-")
        self.patch = patch.dict(os.environ, {"XDG_DATA_HOME": self.temp.name})
        self.patch.start()
        import importlib

        importlib.reload(store)
        importlib.reload(events)

    def tearDown(self) -> None:
        self.patch.stop()
        self.temp.cleanup()

    def _due(self, end_offset=600):
        state = models.DashboardState()
        state.events.append(
            models.Event(
                name="Exam",
                end_at=time.time() + end_offset,
                notify_at=time.time() - 5,
            )
        )
        store.save(state)
        return state

    def test_auto_complete_keeps_event(self) -> None:
        state = models.DashboardState()
        state.events.append(
            models.Event(name="Past", end_at=time.time() - 10, notify_at=0)
        )
        self.assertTrue(events.auto_complete(state))
        self.assertTrue(state.events[0].completed)
        self.assertEqual(len(state.events), 1)

    def test_due_notifications_respect_dismissed(self) -> None:
        state = self._due()
        self.assertEqual(len(events.due_notifications(state)), 1)
        state.events[0].dismissed = True
        self.assertEqual(events.due_notifications(state), [])

    def test_snooze_and_base_case(self) -> None:
        self._due()
        with (
            patch.object(notifier, "show_popup", return_value="snooze"),
            patch.object(scheduler, "arm_all"),
        ):
            events.check_all(send=True)
        event = store.load().events[0]
        self.assertTrue(event.snoozed)
        self.assertFalse(event.notified)
        self.assertLess(event.notify_at, event.end_at)

        self._due(end_offset=100)
        with (
            patch.object(notifier, "show_popup", return_value="snooze"),
            patch.object(scheduler, "arm_all"),
        ):
            events.check_all(send=True)
        event = store.load().events[0]
        self.assertEqual(event.notify_at, 0.0)
        self.assertTrue(event.notified)
        self.assertFalse(event.snoozed)

    def test_default_snooze_and_dismiss(self) -> None:
        self._due()
        with (
            patch.object(notifier, "show_popup", return_value=None),
            patch.object(scheduler, "arm_all"),
        ):
            events.check_all(send=True)
        self.assertTrue(store.load().events[0].snoozed)

        self._due()
        with (
            patch.object(notifier, "show_popup", return_value="dismiss"),
            patch.object(scheduler, "arm_all"),
        ):
            events.check_all(send=True)
        self.assertTrue(store.load().events[0].dismissed)

    def test_send_failure_marks_handled(self) -> None:
        self._due()
        with (
            patch.object(notifier, "show_popup", return_value=notifier.SEND_FAILED),
            patch.object(scheduler, "arm_all"),
        ):
            events.check_all(send=True)
        event = store.load().events[0]
        self.assertTrue(event.notified)
        self.assertFalse(event.snoozed)

    def test_title_format(self) -> None:
        event = models.Event(name="CT Exam", end_at=1795337365.0)
        self.assertEqual(events.notification_title(event), "CT Exam - 22-11-2026 14:19")

    def test_refresh_completion_does_not_consume_notifications(self) -> None:
        self._due()
        events.refresh_completion()
        self.assertFalse(store.load().events[0].notified)


class CalendarTests(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(str(calendar_logic.parse_date("15-03-2027")), "2027-03-15")
        self.assertEqual(str(calendar_logic.parse_date("15/03/2027")), "2027-03-15")
        self.assertEqual(str(calendar_logic.parse_date("2027-03-15")), "2027-03-15")
        self.assertIsNone(calendar_logic.parse_date("garbage"))

    def test_grid_always_6x7_with_adjacent_months(self) -> None:
        grid = calendar_logic.month_grid(2026, 11)
        self.assertEqual(len(grid), 6)
        self.assertTrue(all(len(week) == 7 for week in grid))
        self.assertEqual(grid[0][0].month, 10)
        self.assertEqual(grid[-1][-1].month, 12)

    def test_shift_month(self) -> None:
        self.assertEqual(calendar_logic.shift_month(2026, 1, -1), (2025, 12))
        self.assertEqual(calendar_logic.shift_month(2026, 12, 1), (2027, 1))


class IPCTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="dash-ipc-")
        self.patch = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name})
        self.patch.start()
        import importlib

        importlib.reload(ipc)

    def tearDown(self) -> None:
        self.patch.stop()
        self.temp.cleanup()

    def test_request_clear(self) -> None:
        self.assertFalse(ipc.close_requested())
        ipc.request_close()
        self.assertTrue(ipc.close_requested())
        ipc.clear_close_request()
        self.assertFalse(ipc.close_requested())
        self.assertFalse(ipc.CLOSE_FILE.exists())


if __name__ == "__main__":
    unittest.main()
