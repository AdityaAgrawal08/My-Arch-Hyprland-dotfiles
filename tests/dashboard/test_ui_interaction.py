#!/usr/bin/env python3
"""Headless UI interaction tests for the glitch fixes."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QEventLoop, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from dashboard.core.models import DashboardState, Todo
from dashboard.ui.todo import (
    DRAG_THRESHOLD,
    ClickableLabel,
    TodoList,
    TodoPanel,
    TaskRow,
)
from dashboard.ui.theme import COLORS
from dashboard.ui.widgets import RoundCheckBox
from dashboard.ui.window import DashboardWindow


def mouse_event(kind, local, global_pos=None, buttons=Qt.NoButton):
    return QMouseEvent(
        kind,
        QPointF(local),
        QPointF(global_pos or local),
        Qt.LeftButton,
        buttons,
        Qt.NoModifier,
    )


class QAppMixin(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()


class ClickableLabelTests(QAppMixin):
    def test_click_only_on_release_in_place(self) -> None:
        label = ClickableLabel("Task")
        seen = []
        label.clicked.connect(lambda: seen.append(1))
        label.mousePressEvent(mouse_event(QEvent.MouseButtonPress, QPoint(10, 10)))
        label.mouseReleaseEvent(mouse_event(QEvent.MouseButtonRelease, QPoint(11, 10)))
        self.assertEqual(seen, [1])

        seen.clear()
        label.mousePressEvent(mouse_event(QEvent.MouseButtonPress, QPoint(10, 10)))
        label.mouseReleaseEvent(
            mouse_event(QEvent.MouseButtonRelease, QPoint(10 + DRAG_THRESHOLD + 5, 10))
        )
        self.assertEqual(seen, [])

    def test_press_is_ignored_for_drag_passthrough(self) -> None:
        label = ClickableLabel("Task")
        event = mouse_event(QEvent.MouseButtonPress, QPoint(5, 5))
        label.mousePressEvent(event)
        self.assertFalse(event.isAccepted())


class WidgetPaintTests(QAppMixin):
    def test_round_checkbox_paints_without_color_errors(self) -> None:
        box = RoundCheckBox()
        box.resize(18, 18)
        box.setChecked(True)
        pixmap = __import__("PySide6.QtGui", fromlist=["QPixmap"]).QPixmap(18, 18)
        box.render(pixmap)  # raises inside paintEvent on a bad color key

    def test_all_referenced_color_keys_exist(self) -> None:
        for path in (
            Path(__file__).resolve().parents[2] / "hypr/.config/hypr/scripts/dashboard"
        ).rglob("*.py"):
            import re

            for name in re.findall(r'COLORS\["([^"]+)"\]', path.read_text()):
                self.assertIn(name, COLORS, f"{path.name}: {name}")


class WindowCloseTests(QAppMixin):
    def _window(self):
        with (
            patch(
                "dashboard.core.hypr_integration.dashboard_geometry",
                return_value=(0, 42, 1280, 678, 880),
            ),
            patch("dashboard.core.hypr_integration.window_address", return_value=""),
            patch("dashboard.core.hypr_integration.place_window"),
            patch("dashboard.core.hypr_integration.raise_window"),
        ):
            window = DashboardWindow(DashboardState())
        window.show()
        self.app.processEvents()
        window._startup_deadline = 0
        return window

    def test_inside_press_does_not_close(self) -> None:
        window = self._window()
        with patch.object(window, "close") as close:
            point = window.card.geometry().center()
            window.mousePressEvent(mouse_event(QEvent.MouseButtonPress, point))
            close.assert_not_called()

    def test_outside_press_closes(self) -> None:
        window = self._window()
        with patch.object(window, "close") as close:
            window.mousePressEvent(mouse_event(QEvent.MouseButtonPress, QPoint(2, 2)))
            close.assert_called_once()

    def test_press_during_drag_does_not_close(self) -> None:
        window = self._window()
        window.set_drag_active(True)
        with patch.object(window, "close") as close:
            window.mousePressEvent(mouse_event(QEvent.MouseButtonPress, QPoint(2, 2)))
            close.assert_not_called()
        window.mouseReleaseEvent(mouse_event(QEvent.MouseButtonRelease, QPoint(2, 2)))
        self.assertFalse(window._drag_active)

    def test_startup_grace_prevents_immediate_close(self) -> None:
        window = self._window()
        window._startup_deadline = __import__("time").monotonic() + 5
        with patch.object(window, "close") as close:
            window.mousePressEvent(mouse_event(QEvent.MouseButtonPress, QPoint(2, 2)))
            close.assert_not_called()

    def test_tab_child_press_never_closes(self) -> None:
        window = self._window()
        with (
            patch.object(window, "childAt", return_value=window.card),
            patch.object(window, "close") as close,
        ):
            window.mousePressEvent(mouse_event(QEvent.MouseButtonPress, QPoint(2, 2)))
            close.assert_not_called()


class DragListTests(QAppMixin):
    def _list(self, count=3):
        todo_list = TodoList()
        rows = []
        for index in range(count):
            row = TaskRow(Todo(name=f"T{index}"))
            row.setProperty("task_id", f"id{index}")
            rows.append(row)
        todo_list.set_rows(rows)
        return todo_list, rows

    def test_drag_threshold_commit_and_signal(self) -> None:
        todo_list, rows = self._list()
        seen = []
        todo_list.reorder_requested.connect(lambda sid, idx: seen.append((sid, idx)))

        todo_list._row_press(
            rows[0], mouse_event(QEvent.MouseButtonPress, QPoint(0, 20))
        )
        self.assertFalse(todo_list._dragging)
        todo_list._begin_drag()
        self.assertTrue(todo_list._dragging)
        todo_list._update_neighbours(20)
        self.assertEqual(todo_list._target, 0)
        todo_list._update_neighbours(30)
        self.assertEqual(todo_list._target, 1)
        todo_list._row_release(
            rows[0], mouse_event(QEvent.MouseButtonRelease, QPoint(0, 30))
        )
        self.wait(400)
        self.assertEqual(seen, [("id0", 1)])

    def test_snap_back_no_signal(self) -> None:
        todo_list, rows = self._list()
        seen = []
        todo_list.reorder_requested.connect(lambda sid, idx: seen.append((sid, idx)))
        todo_list._row_press(
            rows[1], mouse_event(QEvent.MouseButtonPress, QPoint(0, 20))
        )
        todo_list._begin_drag()
        todo_list._update_neighbours(1 * 44 + 5)
        todo_list._row_release(
            rows[1], mouse_event(QEvent.MouseButtonRelease, QPoint(0, 49))
        )
        self.wait(400)
        self.assertEqual(seen, [])

    def test_state_reset_on_animation_stop(self) -> None:
        todo_list, rows = self._list()
        todo_list._row_press(
            rows[0], mouse_event(QEvent.MouseButtonPress, QPoint(0, 20))
        )
        todo_list._begin_drag()
        todo_list._animating = True
        todo_list._stop_animations()
        self.assertFalse(todo_list._dragging)
        self.assertFalse(todo_list._animating)
        self.assertIsNone(todo_list._drag_row)
        self.assertEqual(todo_list._source, -1)
        self.assertEqual(todo_list._target, -1)

    def test_click_vs_drag_on_row(self) -> None:
        panel = TodoPanel(DashboardState())
        row = TaskRow(Todo(name="A"))
        seen = []
        row.edit_requested.connect(lambda sid: seen.append(sid))
        row.mousePressEvent(mouse_event(QEvent.MouseButtonPress, QPoint(5, 5)))
        row.mouseReleaseEvent(
            mouse_event(QEvent.MouseButtonRelease, QPoint(5 + DRAG_THRESHOLD + 5, 5))
        )
        self.assertEqual(seen, [])
        self.assertFalse(panel._list._dragging)


if __name__ == "__main__":
    unittest.main()
