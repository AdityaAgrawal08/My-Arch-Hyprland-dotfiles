from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import DashboardState, Note, new_id
from ..core.store import save as save_state
from .theme import COLORS, fade_swap
from .widgets import FieldDialog, IconButton, RowActionButton, SectionHeader


class NoteRow(QFrame):
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, note: Note) -> None:
        super().__init__()
        self.setObjectName("note-row")
        self.setFixedHeight(38)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 6, 2)
        row.setSpacing(10)

        bullet = QLabel("•")
        bullet.setAlignment(Qt.AlignCenter)
        bullet.setStyleSheet(f"color: {COLORS['accent']}; font-size: 18px;")
        bullet.setFixedWidth(14)
        row.addWidget(bullet)

        text = QLabel(note.text or "Empty note")
        row.addWidget(text, 1)

        edit = RowActionButton("✎", "Edit note")
        edit.clicked.connect(lambda: self.edit_requested.emit(note.id))
        row.addWidget(edit)

        remove = RowActionButton("×", "Delete note", danger=True)
        remove.clicked.connect(lambda: self.delete_requested.emit(note.id))
        row.addWidget(remove)

        self.setToolTip("Double-click to edit")


class NotesPanel(QWidget):
    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.state = state
        self._add_button = IconButton("+", "Add note")
        self.header = SectionHeader("", "Notes", None, (self._add_button,))

        self._list = QListWidget()
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self._list.itemDoubleClicked.connect(
            lambda item: self._edit(str(item.data(Qt.UserRole)))
        )
        self._empty = QLabel("No notes yet — press + to add one.")
        self._empty.setObjectName("subtext")
        self._empty.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.header)
        layout.addWidget(self._empty)
        layout.addWidget(self._list, 1)

        self._add_button.clicked.connect(self._add)
        self._reload(animate=False)

    def set_state(self, state: DashboardState) -> None:
        self.state = state
        self._reload(animate=False)

    def _reload(self, animate: bool = True) -> None:
        def build() -> None:
            self._list.clear()
            for note in self.state.notes:
                item = QListWidgetItem()
                item.setSizeHint(QSize(200, 38))
                item.setData(Qt.UserRole, note.id)
                row = NoteRow(note)
                row.edit_requested.connect(self._edit)
                row.delete_requested.connect(self._delete)
                self._list.addItem(item)
                self._list.setItemWidget(item, row)

        if animate:
            fade_swap(self._list, build)
        else:
            build()
        self._empty.setVisible(not self.state.notes)

    def _find(self, note_id: str) -> Note | None:
        return next((note for note in self.state.notes if note.id == note_id), None)

    def _form(self, note: Note | None) -> str | None:
        dialog = FieldDialog(
            self,
            "Edit note" if note else "New note",
            [
                {
                    "key": "text",
                    "label": "Note",
                    "kind": "textarea",
                    "value": note.text if note else "",
                }
            ],
        )
        if dialog.exec() != FieldDialog.Accepted:
            return None
        text = dialog.values()["text"].strip()
        return text or None

    def _add(self) -> None:
        text = self._form(None)
        if text is None:
            return
        self.state.notes.append(Note(id=new_id(), text=text))
        save_state(self.state)
        self._reload()

    def _edit(self, note_id: str) -> None:
        note = self._find(note_id)
        if note is None:
            return
        text = self._form(note)
        if text is None:
            return
        note.text = text
        save_state(self.state)
        self._reload()

    def _delete(self, note_id: str) -> None:
        self.state.notes = [note for note in self.state.notes if note.id != note_id]
        save_state(self.state)
        self._reload()
