from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QGridLayout, QVBoxLayout, QWidget

from ..core import hypr_integration, store
from ..core.models import DashboardState
from .calendar_widget import CalendarPanel
from .events_widget import EventsPanel
from .notes_widget import NotesPanel
from .theme import apply_theme
from .todo import TodoPanel
from .wallpapers_widget import WallpaperPanel
from .widgets import Card


class DashboardWindow(QWidget):
    closed = Signal()

    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.state = state
        self.setObjectName("dashboard-root")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("Productivity Dashboard")
        self._raised = False

        x, y, win_w, win_h, card_max_w = hypr_integration.dashboard_geometry()
        self.setGeometry(x, y, win_w, win_h)

        card_h = min(650, win_h - 26)
        card_top = 14
        self.card = Card(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            max(12, (win_w - card_max_w) // 2),
            card_top,
            max(12, (win_w - card_max_w) // 2),
            max(12, win_h - card_top - card_h),
        )
        outer.addWidget(self.card, 0, Qt.AlignCenter)
        self.card.setFixedSize(card_max_w, card_h)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 12, 20, 12)
        card_layout.setSpacing(8)

        self.todo = TodoPanel(state)
        self.calendar = CalendarPanel(state)
        self.wallpapers = WallpaperPanel(state)
        self.notes = NotesPanel(state)
        self.events = EventsPanel(state)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.addWidget(self.todo, 0, 0)
        grid.addWidget(self.calendar, 0, 1)
        grid.addWidget(self.wallpapers, 1, 0, 1, 2)
        grid.addWidget(self.notes, 2, 0)
        grid.addWidget(self.events, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 5)
        grid.setRowStretch(1, 4)
        grid.setRowStretch(2, 4)
        grid.setRowMinimumHeight(0, 300)
        grid.setRowMinimumHeight(1, 160)
        grid.setRowMinimumHeight(2, 140)
        card_layout.addLayout(grid)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._raised = False
        QTimer.singleShot(180, self._place)
        QTimer.singleShot(700, self._place)
        # No opacity effect on the card: with a translucent top-level window
        # Qt would cache the wallpaper behind it and show it through panels.

    def _place(self) -> None:
        x, y, win_w, win_h, _ = hypr_integration.dashboard_geometry()
        address = hypr_integration.window_address()
        hypr_integration.place_window(address, x, y, win_w, win_h)
        if not self._raised and address:
            hypr_integration.raise_window(address)
            self._raised = True

    def reload_state(self) -> None:
        in_session_calendar = self.state.calendar
        self.state = store.load()
        # Keep whatever month/day the user navigated to during this session.
        self.state.calendar = in_session_calendar
        self.todo.set_state(self.state)
        self.calendar.set_state(self.state)
        self.wallpapers.set_state(self.state)
        self.notes.set_state(self.state)
        self.events.set_state(self.state)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self.card.geometry().contains(event.position().toPoint()):
            self.close()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.closed.emit()
        super().closeEvent(event)

    @staticmethod
    def apply_theme(app: QApplication) -> None:
        apply_theme(app)
