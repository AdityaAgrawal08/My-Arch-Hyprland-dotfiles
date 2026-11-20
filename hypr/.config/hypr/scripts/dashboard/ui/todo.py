from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import DashboardState, Todo, new_id
from ..core.store import save as save_state
from .theme import fade_swap
from .widgets import (
    FieldDialog,
    IconButton,
    RoundCheckBox,
    RowActionButton,
    SectionHeader,
)

MIME = "application/x-dashboard-todo-id"


class TaskRow(QFrame):
    toggled = Signal(str, bool)
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, todo: Todo, manage: bool = False) -> None:
        super().__init__()
        self.setObjectName("task-row")
        self.setFixedHeight(46)

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(10)

        handle = QLabel("⠿")
        handle.setObjectName("handle")
        handle.setToolTip("Drag to reorder")
        row.addWidget(handle)

        check = RoundCheckBox()
        check.setChecked(todo.completed)
        check.toggled.connect(lambda checked: self.toggled.emit(todo.id, checked))
        row.addWidget(check)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)

        name = QLabel(todo.name or "Untitled task")
        if todo.completed:
            name.setObjectName("struck")
        text_column.addWidget(name)

        if todo.description:
            description = QLabel(todo.description)
            description.setObjectName("subtext")
            text_column.addWidget(description)

        row.addLayout(text_column, 1)

        edit = RowActionButton("✎", "Edit task")
        edit.clicked.connect(lambda: self.edit_requested.emit(todo.id))
        row.addWidget(edit)

        remove = RowActionButton("×", "Delete task", danger=True)
        remove.clicked.connect(lambda: self.delete_requested.emit(todo.id))
        row.addWidget(remove)

        for button in (edit, remove):
            button.setVisible(manage)


class TodoList(QListWidget):
    reorder_requested = Signal(str, int)

    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setFrameShape(QFrame.NoFrame)
        self.setSpacing(0)

    def mimeTypes(self) -> list[str]:
        return [MIME, *super().mimeTypes()]

    def mimeData(self, items: list[QListWidgetItem]) -> QMimeData:
        mime = QMimeData()
        if items:
            mime.setData(MIME, QByteArray(str(items[0].data(Qt.UserRole)).encode()))
        return mime

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasFormat(MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasFormat(MIME):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not event.mimeData().hasFormat(MIME):
            super().dropEvent(event)
            return
        raw = bytes(event.mimeData().data(MIME)).decode("utf-8", "replace")
        index = self.indexAt(event.position().toPoint())
        target = index.row() if index.isValid() else self.count()
        event.acceptProposedAction()
        self.reorder_requested.emit(raw, target)


class TodoPanel(QWidget):
    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.state = state
        self._manage = False

        self._add_button = IconButton("+", "Add task")
        self._manage_button = IconButton("⋯", "Show task actions")
        self._manage_button.setCheckable(True)

        self.header = SectionHeader(
            "☑",
            "Todo",
            state.active_todos,
            (self._add_button, self._manage_button),
        )

        self._list = TodoList()
        self._empty = QLabel("No tasks yet — press + to add one.")
        self._empty.setObjectName("subtext")
        self._empty.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.header)
        layout.addWidget(self._empty)
        layout.addWidget(self._list, 1)

        self._add_button.clicked.connect(self._add)
        self._manage_button.toggled.connect(self._set_manage)
        self._list.reorder_requested.connect(self._reorder)
        self._reload(animate=False)

    def set_state(self, state: DashboardState) -> None:
        self.state = state
        self._reload(animate=False)

    def _set_manage(self, enabled: bool) -> None:
        self._manage = enabled
        self._manage_button.setToolTip(
            "Hide task actions" if enabled else "Show task actions"
        )
        self._reload(animate=False)

    def _reload(self, animate: bool = True) -> None:
        def build() -> None:
            self._list.clear()
            for todo in self.state.todos:
                item = QListWidgetItem()
                item.setSizeHint(QSize(200, 46))
                row = TaskRow(todo, manage=self._manage)
                row.toggled.connect(self._toggle)
                row.edit_requested.connect(self._edit)
                row.delete_requested.connect(self._delete)
                item.setData(Qt.UserRole, todo.id)
                self._list.addItem(item)
                self._list.setItemWidget(item, row)

        if animate:
            fade_swap(self._list, build)
        else:
            build()
        self._empty.setVisible(not self.state.todos)
        self.header.set_count(self.state.active_todos)

    def _find(self, todo_id: str) -> Todo | None:
        return next((todo for todo in self.state.todos if todo.id == todo_id), None)

    def _persist(self) -> None:
        save_state(self.state)

    def _toggle(self, todo_id: str, completed: bool) -> None:
        todo = self._find(todo_id)
        if todo is None:
            return
        todo.completed = completed
        self._persist()
        self._reload()

    def _form(self, todo: Todo | None) -> Todo | None:
        dialog = FieldDialog(
            self,
            "Edit task" if todo else "New task",
            [
                {"key": "name", "label": "Name", "value": todo.name if todo else ""},
                {
                    "key": "description",
                    "label": "Description",
                    "kind": "textarea",
                    "value": todo.description if todo else "",
                },
            ],
        )
        if dialog.exec() != FieldDialog.Accepted:
            return None
        values = dialog.values()
        name = values["name"].strip()
        if not name:
            return None
        if todo is None:
            todo = Todo(id=new_id(), name=name)
        todo.name = name
        todo.description = values["description"]
        return todo

    def _add(self) -> None:
        todo = self._form(None)
        if todo is None:
            return
        self.state.todos.append(todo)
        self._persist()
        self._reload()

    def _edit(self, todo_id: str) -> None:
        todo = self._find(todo_id)
        if todo is None:
            return
        updated = self._form(todo)
        if updated is None:
            return
        self._persist()
        self._reload()

    def _delete(self, todo_id: str) -> None:
        self.state.todos = [todo for todo in self.state.todos if todo.id != todo_id]
        self._persist()
        self._reload()

    def _reorder(self, todo_id: str, target: int) -> None:
        source = next(
            (i for i, todo in enumerate(self.state.todos) if todo.id == todo_id), None
        )
        if source is None:
            return
        insert_at = max(0, min(target, len(self.state.todos)))
        if source < insert_at:
            insert_at -= 1
        if source == insert_at:
            return
        todo = self.state.todos.pop(source)
        self.state.todos.insert(insert_at, todo)
        self._persist()
        self._reload()
