from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


def new_id() -> str:
    return uuid.uuid4().hex


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Todo:
    id: str = field(default_factory=new_id)
    name: str = ""
    description: str = ""
    completed: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "Todo":
        data = data if isinstance(data, dict) else {}
        return cls(
            id=_as_str(data.get("id")) or new_id(),
            name=_as_str(data.get("name")),
            description=_as_str(data.get("description")),
            completed=bool(data.get("completed", False)),
        )


@dataclass
class Note:
    id: str = field(default_factory=new_id)
    text: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "Note":
        data = data if isinstance(data, dict) else {}
        return cls(
            id=_as_str(data.get("id")) or new_id(),
            text=_as_str(data.get("text")),
        )


@dataclass
class Event:
    id: str = field(default_factory=new_id)
    name: str = ""
    description: str = ""
    end_at: float = 0.0
    notify_at: float = 0.0
    completed: bool = False
    notified: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "Event":
        data = data if isinstance(data, dict) else {}
        return cls(
            id=_as_str(data.get("id")) or new_id(),
            name=_as_str(data.get("name")),
            description=_as_str(data.get("description")),
            end_at=_as_float(data.get("end_at")),
            notify_at=_as_float(data.get("notify_at")),
            completed=bool(data.get("completed", False)),
            notified=bool(data.get("notified", False)),
        )


@dataclass
class CalendarSelection:
    selected: str = ""
    year: int = 0
    month: int = 0

    @classmethod
    def from_dict(cls, data: Any) -> "CalendarSelection":
        data = data if isinstance(data, dict) else {}
        today = date.today()
        try:
            year = int(data.get("year") or today.year)
        except (TypeError, ValueError):
            year = today.year
        try:
            month = int(data.get("month") or today.month)
        except (TypeError, ValueError):
            month = today.month
        if not 1 <= month <= 12:
            month = today.month
        if not 1900 <= year <= 2200:
            year = today.year
        return cls(
            selected=_as_str(data.get("selected")) or today.isoformat(),
            year=year,
            month=month,
        )


@dataclass
class DashboardState:
    version: int = 1
    todos: list[Todo] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    calendar: CalendarSelection = field(default_factory=CalendarSelection)

    @property
    def active_todos(self) -> int:
        return sum(1 for todo in self.todos if not todo.completed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "todos": [asdict(todo) for todo in self.todos],
            "notes": [asdict(note) for note in self.notes],
            "events": [asdict(event) for event in self.events],
            "calendar": asdict(self.calendar),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "DashboardState":
        data = data if isinstance(data, dict) else {}
        return cls(
            version=int(data.get("version") or 1),
            todos=[Todo.from_dict(item) for item in _as_list(data.get("todos"))],
            notes=[Note.from_dict(item) for item in _as_list(data.get("notes"))],
            events=[Event.from_dict(item) for item in _as_list(data.get("events"))],
            calendar=CalendarSelection.from_dict(data.get("calendar")),
        )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
