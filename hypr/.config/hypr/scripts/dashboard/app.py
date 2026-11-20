from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .core import events, ipc
from .core.hypr_integration import WINDOW_CLASS
from .core.store import load
from .ui.theme import apply_theme
from .ui.window import DashboardWindow


class DashboardApp:
    """Owns the Qt application, the window and the periodic event check."""

    def __init__(self) -> None:
        self.qapp = QApplication.instance() or QApplication(sys.argv)
        self.qapp.setApplicationName(WINDOW_CLASS)
        self.qapp.setApplicationDisplayName("Productivity Dashboard")
        self.qapp.setDesktopFileName(WINDOW_CLASS)
        self.qapp.setOrganizationName("aditya")
        self.qapp.setQuitOnLastWindowClosed(True)
        apply_theme(self.qapp)

        # Catch up on missed events/notifications before the first paint.
        events.check_all(send=True)

        self.window = DashboardWindow(load())
        self._timer = QTimer()
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._tick)

        # The launcher signals "close" through a file: Python signal handlers
        # are unreliable while Qt owns the main thread in C++.
        ipc.clear_close_request()
        self._close_poll = QTimer()
        self._close_poll.setInterval(250)
        self._close_poll.timeout.connect(self._poll_close)

    def _tick(self) -> None:
        events.check_all(send=True)
        self.window.reload_state()

    def _poll_close(self) -> None:
        if ipc.close_requested():
            ipc.clear_close_request()
            self.qapp.quit()

    def run(self) -> int:
        self.window.show()
        self._timer.start()
        self._close_poll.start()
        signal.signal(signal.SIGTERM, self._on_terminate)
        signal.signal(signal.SIGINT, self._on_terminate)
        return self.qapp.exec()

    @staticmethod
    def _on_terminate(_signum: int, _frame: object) -> None:
        # Best-effort fallback; the file-based poll is the reliable path.
        ipc.request_close()
