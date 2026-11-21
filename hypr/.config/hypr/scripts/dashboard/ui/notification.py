from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import hypr_integration
from .theme import apply_theme

POPUP_WIDTH = 380
POPUP_HEIGHT = 122


class NotificationWindow(QWidget):
    """A real, clickable notification with Snooze / Dismiss buttons."""

    def __init__(self, title: str, body: str, timeout_ms: int = 90_000) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("Event Notification")
        self.setFixedSize(POPUP_WIDTH, POPUP_HEIGHT)
        self.chosen: str | None = None

        geo = hypr_integration.display_geometry()
        x = int(geo["x"]) + int(geo["width"]) - POPUP_WIDTH - 16
        y = int(geo["bar_bottom"]) + 12
        self.move(x, y)

        root = QFrame(self)
        root.setObjectName("card")
        root.setGeometry(0, 0, POPUP_WIDTH, POPUP_HEIGHT)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        heading = QLabel(title)
        heading.setObjectName("empty-title")
        heading.setWordWrap(True)
        heading.setStyleSheet("font-size: 13px; font-weight: 700;")
        layout.addWidget(heading)

        detail = QLabel(body or "Event reminder")
        detail.setObjectName("empty-sub")
        detail.setWordWrap(True)
        layout.addWidget(detail, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        dismiss = QPushButton("Dismiss")
        dismiss.setObjectName("ghost")
        dismiss.clicked.connect(lambda: self._choose("dismiss"))
        buttons.addWidget(dismiss)

        snooze = QPushButton("Snooze · 5 min")
        snooze.setObjectName("primary")
        snooze.clicked.connect(lambda: self._choose("snooze"))
        buttons.addWidget(snooze)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close)
        self._timer.start(timeout_ms)

    def _choose(self, action: str) -> None:
        self.chosen = action
        self.close()


def show(title: str, body: str, timeout_ms: int = 90_000) -> str | None:
    """Display the popup and return the clicked action (or None on timeout)."""
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    window = NotificationWindow(title, body, timeout_ms)
    window.show()
    app.exec()
    return window.chosen
