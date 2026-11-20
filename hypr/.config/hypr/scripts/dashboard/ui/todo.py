from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QMouseEvent
from PySide6.QtWidgets import (
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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.models import DashboardState, Subtask, Todo, new_id
from ..core.store import save as save_state
from .theme import COLORS
from .widgets import Card, IconButton, RowActionButton, RoundCheckBox, SectionHeader

ROW_H = 42
PITCH = 44
DRAG_THRESHOLD = 5


class ClickableLabel(QLabel):
    """Emits `clicked` on a press+release in the same spot; ignores press so
    the parent TaskRow can use it to start a drag."""

    clicked = Signal()

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self._press_pos = None

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._press_pos is not None:
            moved = (event.position().toPoint() - self._press_pos).manhattanLength()
            if moved < DRAG_THRESHOLD:
                self.clicked.emit()
        self._press_pos = None
        super().mouseReleaseEvent(event)


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
        from PySide6.QtCore import QSize

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
        self.setFixedHeight(ROW_H)
        self._owner: TodoList | None = None

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
        name.setToolTip("Click to edit • drag to reorder")
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

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._owner is not None:
            self._owner._row_press(self, event)
        event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._owner is not None:
            self._owner._row_move(self, event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._owner is not None:
            self._owner._row_release(self, event)
        super().mouseReleaseEvent(event)


class TodoList(QScrollArea):
    """Animated, threshold-based drag reordering for task rows."""

    reorder_requested = Signal(str, int)

    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.viewport().setStyleSheet("background: transparent;")

        self._viewport = QWidget()
        self._viewport.setObjectName("todo-viewport")
        self._viewport.setStyleSheet("background: transparent;")
        self.setWidget(self._viewport)

        self.rows: list[TaskRow] = []
        self._source = -1
        self._target = -1
        self._drag_row: TaskRow | None = None
        self._grab_y = 0.0
        self._dragging = False
        self._animating = False
        self._animations: dict[TaskRow, QPropertyAnimation] = {}
        self._finish_animation: QPropertyAnimation | None = None

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._viewport.setFixedWidth(self.viewport().width())
        self._viewport.setFixedHeight(max(ROW_H, len(self.rows) * PITCH))
        for row in self.rows:
            row.resize(self._viewport.width(), ROW_H)

    def set_rows(self, rows: list[TaskRow]) -> None:
        self._stop_animations()
        for old in self.rows:
            old.setParent(None)
            old.deleteLater()
        self.rows = rows
        for index, row in enumerate(rows):
            row._owner = self
            row.setParent(self._viewport)
            row.move(0, index * PITCH)
            row.show()
        self._viewport.setFixedWidth(self.viewport().width())
        self._viewport.setFixedHeight(max(ROW_H, len(rows) * PITCH))
        for row in rows:
            row.resize(self._viewport.width(), ROW_H)

    def _stop_animations(self) -> None:
        for animation in self._animations.values():
            animation.stop()
        self._animations.clear()
        if self._finish_animation is not None:
            self._finish_animation.stop()
            self._finish_animation = None

    def _animate_to(self, row: TaskRow, y: int, duration: int = 170) -> None:
        previous = self._animations.get(row)
        if previous is not None:
            previous.stop()
        animation = QPropertyAnimation(row, b"pos", self)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setStartValue(row.pos())
        animation.setEndValue(QPoint(row.x(), y))
        animation.start()
        self._animations[row] = animation

    def _row_press(self, row: TaskRow, event: QMouseEvent) -> None:
        if self._animating or event.button() != Qt.LeftButton:
            return
        if row not in self.rows:
            return
        self._source = self.rows.index(row)
        self._target = self._source
        self._drag_row = row
        self._grab_y = event.position().y()
        self._dragging = False

    def _row_move(self, row: TaskRow, event: QMouseEvent) -> None:
        if row is not self._drag_row or not (event.buttons() & Qt.LeftButton):
            return
        if not self._dragging:
            if abs(event.position().y() - self._grab_y) < DRAG_THRESHOLD:
                return
            self._begin_drag()

        viewport_pos = self._viewport.mapFromGlobal(event.globalPosition().toPoint())
        top = max(
            0, min(viewport_pos.y() - int(self._grab_y), (len(self.rows) - 1) * PITCH)
        )
        self._drag_row.move(0, top)
        self._update_neighbours(top)

    def _begin_drag(self) -> None:
        self._dragging = True
        row = self._drag_row
        if row is None:
            return
        row.raise_()
        row.setStyleSheet(
            "background: #241c17; border: 1px solid #b97047; "
            "border-radius: 8px; padding: 0 6px;"
        )
        shadow = QGraphicsDropShadowEffect(row)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 170))
        row.setGraphicsEffect(shadow)

    def _update_neighbours(self, dragged_top: int) -> None:
        assert self._drag_row is not None
        source = self._source
        target = max(0, min(round(dragged_top / PITCH), len(self.rows) - 1))
        self._target = target
        for index, row in enumerate(self.rows):
            if row is self._drag_row:
                continue
            if source < target and source < index <= target:
                display = index - 1
            elif source > target and target <= index < source:
                display = index + 1
            else:
                display = index
            if row.y() != display * PITCH:
                self._animate_to(row, display * PITCH)

    def _row_release(self, row: TaskRow, event: QMouseEvent) -> None:
        if row is not self._drag_row:
            return
        self._drag_row = None
        if not self._dragging:
            self._source = -1
            return
        self._dragging = False
        self._animating = True

        row = self.rows[self._source]
        committed = self._target != self._source
        final_y = (self._target if committed else self._source) * PITCH

        animation = QPropertyAnimation(row, b"pos", self)
        animation.setDuration(300 if committed else 240)
        animation.setEasingCurve(
            QEasingCurve.OutBack if committed else QEasingCurve.OutCubic
        )
        animation.setStartValue(row.pos())
        animation.setEndValue(QPoint(row.x(), final_y))
        self._finish_animation = animation

        source_id = str(row.property("task_id") or "")
        target_index = self._target
        source_index = self._source

        def finished() -> None:
            row.setStyleSheet("")
            row.setGraphicsEffect(None)
            self._finish_animation = None
            self._animating = False
            self._animations.clear()
            if committed and source_id:
                self.reorder_requested.emit(source_id, target_index)
            elif source_index != target_index:
                # Snap-back: neighbours may be mid-flight, restore their slots.
                for index, other in enumerate(self.rows):
                    other.move(0, index * PITCH)

        animation.finished.connect(finished)
        animation.start()

    def task_id_of(self, row: TaskRow) -> str:
        return str(row.property("task_id") or "")


class TodoPanel(QWidget):
    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.state = state
        self._manage = False

        self._add_button = IconButton("+", "Add task")
        self._manage_button = IconButton("⋯", "Show task actions")
        self._manage_button.setCheckable(True)

        self.header = SectionHeader(
            "☑", "Todo", state.active_todos, (self._add_button, self._manage_button)
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
        rows: list[TaskRow] = []
        for todo in self.state.todos:
            row = TaskRow(todo, manage=self._manage)
            row.toggled.connect(self._toggle)
            row.edit_requested.connect(self._edit)
            row.delete_requested.connect(self._delete)
            row.setProperty("task_id", todo.id)
            rows.append(row)
        self._list.set_rows(rows)
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
            Subtask(id=item["id"], name=item["name"], completed=bool(item["completed"]))
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
        self._reload(animate=False)

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
        insert_at = max(0, min(target, len(self.state.todos) - 1))
        if source == insert_at:
            self._reload(animate=False)
            return
        todo = self.state.todos.pop(source)
        self.state.todos.insert(insert_at, todo)
        self._persist()
        self._reload(animate=False)
