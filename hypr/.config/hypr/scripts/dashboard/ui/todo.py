from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import DashboardState, Subtask, Todo, new_id
from ..core.store import save as save_state
from .theme import COLORS, fade_swap
from .widgets import Card, IconButton, RoundCheckBox, RowActionButton, SectionHeader

MIME = "application/x-dashboard-todo-id"


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.clicked.emit()


class SubtaskRow(QFrame):
    removed = Signal(QListWidgetItem)

    def __init__(
        self, subtask: Subtask | None = None, item: QListWidgetItem | None = None
    ) -> None:
        super().__init__()
        self.setObjectName("task-row")
        self.setFixedHeight(34)
        self._item = item
        self.id = subtask.id if subtask else ""

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 6, 0)
        row.setSpacing(10)

        check = RoundCheckBox()
        check.setChecked(bool(subtask and subtask.completed))
        row.addWidget(check)

        self._name = QLineEdit(subtask.name if subtask else "")
        self._name.setPlaceholderText("Subtask name")
        self._name.setStyleSheet("border: none; background: transparent; padding: 0;")

        def apply_strike(checked: bool) -> None:
            font = QFont(self._name.font())
            font.setStrikeOut(checked)
            self._name.setFont(font)
            self._name.setStyleSheet(
                "border: none; background: transparent; padding: 0; color: "
                + (COLORS["muted"] if checked else COLORS["text"])
                + ";"
            )

        check.toggled.connect(apply_strike)
        apply_strike(check.isChecked())
        row.addWidget(self._name, 1)

        remove = RowActionButton("×", "Delete subtask", danger=True)
        remove.clicked.connect(lambda: self.removed.emit(self._item))  # type: ignore[arg-type]
        row.addWidget(remove)

        self._check = check

    @property
    def name(self) -> str:
        return self._name.text().strip()

    @property
    def completed(self) -> bool:
        return self._check.isChecked()


class TaskDialog(QDialog):
    """Add/edit form: name, optional description and a subtask editor."""

    def __init__(self, parent: QWidget, todo: Todo | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self._rows: list[SubtaskRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        frame = Card()
        frame.setObjectName("dialog")
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(COLORS["shadow"]))
        frame.setGraphicsEffect(shadow)
        outer.addWidget(frame)

        inner = QVBoxLayout(frame)
        inner.setContentsMargins(20, 18, 20, 16)
        inner.setSpacing(10)

        heading = QLabel("Edit task" if todo else "New task")
        heading.setObjectName("dialog-title")
        inner.addWidget(heading)

        self._name = QLineEdit(todo.name if todo else "")
        self._name.setPlaceholderText("Task name")
        inner.addWidget(self._name)

        self._description = QPlainTextEdit(todo.description if todo else "")
        self._description.setPlaceholderText("Description (optional)")
        self._description.setMaximumHeight(64)
        inner.addWidget(self._description)

        sub_header = QHBoxLayout()
        label = QLabel("Subtasks")
        label.setObjectName("field-label")
        sub_header.addWidget(label)
        sub_header.addStretch(1)
        add_sub = QPushButton("+ Add")
        add_sub.setObjectName("go")
        add_sub.clicked.connect(lambda: self._add_subtask())
        sub_header.addWidget(add_sub)
        inner.addLayout(sub_header)

        self._sub_list = QListWidget()
        self._sub_list.setFrameShape(QFrame.NoFrame)
        self._sub_list.setFixedHeight(150)
        self._sub_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        inner.addWidget(self._sub_list)

        for subtask in todo.subtasks if todo else []:
            self._add_subtask(subtask)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        buttons.addWidget(save)
        inner.addLayout(buttons)

        QTimer.singleShot(0, self._center)

    def _add_subtask(self, subtask: Subtask | None = None) -> None:
        item = QListWidgetItem()
        item.setSizeHint(QSize(200, 34))
        row = SubtaskRow(subtask, item)
        row.removed.connect(self._remove_subtask)
        self._sub_list.addItem(item)
        self._sub_list.setItemWidget(item, row)
        self._rows.append(row)
        if subtask is None:
            row._name.setFocus()

    def _remove_subtask(self, item: QListWidgetItem) -> None:
        row = self._sub_list.itemWidget(item)
        if row in self._rows:
            self._rows.remove(row)
        self._sub_list.takeItem(self._sub_list.row(item))

    def _center(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        origin = parent.mapToGlobal(QPoint(0, 0))
        self.move(
            origin.x() + (parent.width() - self.width()) // 2,
            origin.y() + (parent.height() - self.height()) // 2,
        )

    def values(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "description": self._description.toPlainText().strip(),
            "subtasks": [
                {"id": row.id or new_id(), "name": row.name, "completed": row.completed}
                for row in self._rows
                if row.name
            ],
        }

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


class TaskRow(QFrame):
    toggled = Signal(str, bool)
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, todo: Todo, manage: bool = False) -> None:
        super().__init__()
        self.setObjectName("task-row")
        self.setFixedHeight(42)

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

        name = ClickableLabel(todo.name or "Untitled task")
        if todo.completed:
            name.setObjectName("struck")
        name.setToolTip("Click to edit task and subtasks")
        name.clicked.connect(lambda: self.edit_requested.emit(todo.id))
        row.addWidget(name, 1)

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
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
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
                item.setSizeHint(QSize(200, 42))
                item.setData(Qt.UserRole, todo.id)
                row = TaskRow(todo, manage=self._manage)
                row.toggled.connect(self._toggle)
                row.edit_requested.connect(self._edit)
                row.delete_requested.connect(self._delete)
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

    def _form(self, todo: Todo | None) -> Todo | None:
        dialog = TaskDialog(self, todo)
        if dialog.exec() != QDialog.Accepted:
            return None
        values = dialog.values()
        name = values["name"]
        if not name:
            return None

        subtasks = [
            Subtask(
                id=item["id"],
                name=item["name"],
                completed=bool(item["completed"]),
            )
            for item in values["subtasks"]
        ]

        if todo is None:
            todo = Todo(id=new_id(), name=name)
        todo.name = name
        todo.description = values["description"]
        todo.subtasks = subtasks
        if subtasks:
            todo.sync_completion()
        return todo

    def _toggle(self, todo_id: str, completed: bool) -> None:
        todo = self._find(todo_id)
        if todo is None:
            return
        todo.completed = completed
        if todo.subtasks:
            for subtask in todo.subtasks:
                subtask.completed = completed
        self._persist()
        self._reload()

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
        if self._form(todo) is None:
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
