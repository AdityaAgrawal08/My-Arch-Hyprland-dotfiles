from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import scheduler
from ..core.models import DashboardState, Event, new_id
from ..core.store import save as save_state
from .theme import fade_swap
from .widgets import (
    EmptyState,
    FieldDialog,
    IconButton,
    RowActionButton,
    SectionHeader,
)


def _format_moment(timestamp: float) -> str:
    if not timestamp:
        return "No date"
    return datetime.fromtimestamp(timestamp).strftime("%a, %d %b · %H:%M")


class EventRow(QFrame):
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, event: Event) -> None:
        super().__init__()
        self.setObjectName("event-row")
        self.setFixedHeight(48)

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(12)

        bar = QFrame()
        bar.setObjectName(
            "event-bar-completed" if event.completed else "event-bar-upcoming"
        )
        bar.setFixedSize(4, 34)
        row.addWidget(bar)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)

        name = QLabel(event.name or "Untitled event")
        if event.completed:
            name.setObjectName("struck")
        text_column.addWidget(name)

        moment_text = _format_moment(event.end_at)
        if event.dismissed:
            moment_text += "  •  Dismissed"
        elif event.snoozed and not event.completed:
            moment_text += "  •  Snoozed 5m"
        moment = QLabel(moment_text)
        moment.setObjectName("subtext")
        text_column.addWidget(moment)

        if event.description:
            description = QLabel(event.description)
            description.setObjectName("subtext")
            text_column.addWidget(description)

        row.addLayout(text_column, 1)

        edit = RowActionButton("✎", "Edit event")
        edit.clicked.connect(lambda: self.edit_requested.emit(event.id))
        row.addWidget(edit)

        remove = RowActionButton("×", "Delete event", danger=True)
        remove.setProperty("always", True)
        remove.clicked.connect(lambda: self.delete_requested.emit(event.id))
        row.addWidget(remove)

        self.setToolTip("Double-click to edit")


class EventsPanel(QWidget):
    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.setObjectName("panel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.state = state
        self._add_button = IconButton("+", "Add event")
        self.header = SectionHeader(
            "", "Events", len(state.events), (self._add_button,)
        )

        self._list = QListWidget()
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self._list.itemDoubleClicked.connect(
            lambda item: self._edit(str(item.data(Qt.UserRole)))
        )
        self._empty = EmptyState("No events yet", "Press + to add one.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(4)
        layout.addWidget(self.header)
        layout.addWidget(self._empty)
        layout.addWidget(self._list, 1)

        self._add_button.clicked.connect(self._add)
        self._reload(animate=False)

    def set_state(self, state: DashboardState) -> None:
        self.state = state
        self._reload(animate=False)

    def _ordered(self) -> list[Event]:
        return sorted(
            self.state.events,
            key=lambda event: (event.completed, event.end_at or float("inf")),
        )

    def _reload(self, animate: bool = True) -> None:
        def build() -> None:
            self._list.clear()
            for event in self._ordered():
                item = QListWidgetItem()
                item.setSizeHint(QSize(200, 48))
                item.setData(Qt.UserRole, event.id)
                row = EventRow(event)
                row.edit_requested.connect(self._edit)
                row.delete_requested.connect(self._delete)
                self._list.addItem(item)
                self._list.setItemWidget(item, row)

        if animate:
            fade_swap(self._list, build)
        else:
            build()
        self._empty.setVisible(not self.state.events)
        self.header.set_count(len(self.state.events))

    def _find(self, event_id: str) -> Event | None:
        return next(
            (event for event in self.state.events if event.id == event_id), None
        )

    def _form(self, event: Event | None) -> Event | None:
        default_end = QDateTime.currentDateTime().addSecs(86400)
        if event is not None and event.end_at:
            end_default = QDateTime.fromSecsSinceEpoch(int(event.end_at))
        else:
            end_default = default_end
        if event is not None and event.notify_at:
            notify_default = QDateTime.fromSecsSinceEpoch(int(event.notify_at))
        else:
            # By default the reminder fires exactly when the event time is
            # reached. The user may still set an earlier time explicitly.
            notify_default = end_default

        dialog = FieldDialog(
            self,
            "Edit event" if event else "New event",
            [
                {"key": "name", "label": "Name", "value": event.name if event else ""},
                {
                    "key": "description",
                    "label": "Description",
                    "kind": "textarea",
                    "value": event.description if event else "",
                },
                {
                    "key": "end_at",
                    "label": "End date & time",
                    "kind": "datetime",
                    "value": end_default,
                },
                {
                    "key": "notify_at",
                    "label": "Notification date & time",
                    "kind": "datetime",
                    "value": notify_default,
                },
            ],
        )
        # Keep the reminder glued to the event time until the user explicitly
        # edits the notification field.
        end_widget = dialog._widgets["end_at"]
        notify_widget = dialog._widgets["notify_at"]
        notify_edited = False

        def on_notify_changed(_dt=None) -> None:
            nonlocal notify_edited
            notify_edited = True

        def on_end_changed(dt) -> None:
            if not notify_edited:
                notify_widget.blockSignals(True)
                notify_widget.setDateTime(dt)
                notify_widget.blockSignals(False)

        notify_widget.dateTimeChanged.connect(on_notify_changed)
        end_widget.dateTimeChanged.connect(on_end_changed)

        if dialog.exec() != FieldDialog.Accepted:
            return None
        values = dialog.values()
        name = values["name"].strip()
        if not name:
            return None
        end_at = float(values["end_at"].toSecsSinceEpoch())
        notify_at = float(values["notify_at"].toSecsSinceEpoch())
        if end_at <= 0 or notify_at <= 0:
            return None
        # A reminder must never be scheduled past the event itself.
        if notify_at > end_at:
            notify_at = end_at

        previous_notify = event.notify_at if event is not None else 0.0
        if event is None:
            event = Event(id=new_id(), name=name)
        event.name = name
        event.description = values["description"]
        event.end_at = end_at
        event.notify_at = notify_at
        # Only a genuine schedule change re-arms the notification, so editing
        # an unrelated field never fires the same notification twice.
        if notify_at != previous_notify:
            event.notified = False
            event.snoozed = False
            event.dismissed = False
        return event

    def _delete(self, event_id: str) -> None:
        scheduler.cancel(event_id)
        self.state.events = [
            event for event in self.state.events if event.id != event_id
        ]
        save_state(self.state)
        self._reload()

    def _add(self) -> None:
        event = self._form(None)
        if event is None:
            return
        self.state.events.append(event)
        save_state(self.state)
        scheduler.arm(event)
        self._reload()

    def _edit(self, event_id: str) -> None:
        event = self._find(event_id)
        if event is None:
            return
        if self._form(event) is None:
            return
        save_state(self.state)
        scheduler.arm(event)
        self._reload()
