from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import calendar_logic
from ..core.models import DashboardState
from ..core.store import save as save_state
from .widgets import IconButton, SectionHeader


class CalendarPanel(QWidget):
    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.state = state
        selection = state.calendar
        self.year = selection.year or date.today().year
        self.month = selection.month or date.today().month
        self.selected = calendar_logic.from_key(selection.selected) or date.today()

        self._prev = IconButton("‹", "Previous month")
        self._next = IconButton("›", "Next month")
        self.header = SectionHeader("▦", "", None, (self._prev, self._next))
        self.header.set_title(self._month_title())

        weekdays = QHBoxLayout()
        weekdays.setContentsMargins(0, 0, 0, 0)
        for name in calendar_logic.WEEKDAYS:
            label = QLabel(name)
            label.setObjectName("day-label")
            label.setAlignment(Qt.AlignCenter)
            weekdays.addWidget(label)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(2)
        self._day_buttons: list[QPushButton] = []
        for index in range(42):
            button = QPushButton()
            button.setObjectName("day")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self._on_day(i))
            self._grid.addWidget(button, index // 7, index % 7)
            self._day_buttons.append(button)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText("dd-mm-yyyy")
        self._entry.setMaximumWidth(130)
        self._entry.returnPressed.connect(self._on_jump)
        self._go = QPushButton("Go")
        self._go.setObjectName("go")
        self._go.clicked.connect(self._on_jump)

        entry_row = QHBoxLayout()
        entry_row.setContentsMargins(0, 6, 0, 0)
        entry_row.setSpacing(8)
        entry_row.addWidget(self._entry)
        entry_row.addWidget(self._go)
        entry_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.header)
        layout.addLayout(weekdays)
        layout.addLayout(self._grid, 1)
        layout.addLayout(entry_row)

        self._prev.clicked.connect(lambda: self._change_month(-1))
        self._next.clicked.connect(lambda: self._change_month(1))
        self._render()

    def set_state(self, state: DashboardState) -> None:
        self.state = state
        selection = state.calendar
        self.year = selection.year or self.year
        self.month = selection.month or self.month
        parsed = calendar_logic.from_key(selection.selected)
        if parsed is not None:
            self.selected = parsed
        self._render()

    def _month_title(self) -> str:
        return date(self.year, self.month, 1).strftime("%B %Y")

    def _render(self) -> None:
        self.header.set_title(self._month_title())
        today = date.today()
        weeks = calendar_logic.month_grid(self.year, self.month)
        for index, button in enumerate(self._day_buttons):
            week = weeks[index // 7] if index // 7 < len(weeks) else []
            day = week[index % 7] if index % 7 < len(week) else today
            button.setText(str(day.day))
            button.setProperty("adjacent", day.month != self.month)
            button.setProperty("today", day == today)
            button.setProperty("selected", day == self.selected)
            button.setToolTip(day.strftime("%A, %d %B %Y"))
            button.style().polish(button)

    def _persist(self) -> None:
        self.state.calendar.year = self.year
        self.state.calendar.month = self.month
        self.state.calendar.selected = calendar_logic.date_key(self.selected)
        save_state(self.state)

    def _on_day(self, index: int) -> None:
        week = calendar_logic.month_grid(self.year, self.month)[index // 7]
        day = week[index % 7]
        if day.month != self.month:
            self.year, self.month = day.year, day.month
        self.selected = day
        self._persist()
        self._render()

    def _change_month(self, delta: int) -> None:
        self.year, self.month = calendar_logic.shift_month(self.year, self.month, delta)
        self._persist()
        self._render()

    def _on_jump(self) -> None:
        parsed = calendar_logic.parse_date(self._entry.text())
        if parsed is None:
            self._entry.setText("")
            self._entry.setPlaceholderText("Invalid — use dd-mm-yyyy")
            return
        self.year, self.month = parsed.year, parsed.month
        self.selected = parsed
        self._entry.clear()
        self._entry.setPlaceholderText("dd-mm-yyyy")
        self._persist()
        self._render()
