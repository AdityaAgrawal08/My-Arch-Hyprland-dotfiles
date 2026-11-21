from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

from .theme import COLORS


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")


class SectionHeader(QWidget):
    def __init__(
        self,
        icon: str,
        title: str,
        count: int | None = None,
        actions: Iterable[QWidget] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 4, 4)
        row.setSpacing(8)

        bar = QFrame()
        bar.setObjectName("section-bar")
        bar.setFixedSize(3, 24)
        row.addWidget(bar)

        icon_label = QLabel(icon)
        icon_label.setObjectName("section-icon")
        row.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setObjectName("section-title")
        self._title_label = title_label
        row.addWidget(title_label)

        self._count_label: QLabel | None = None
        if count is not None:
            self._count_label = QLabel(f"({count})")
            self._count_label.setObjectName("count")
            row.addWidget(self._count_label)

        row.addStretch(1)
        for action in actions:
            row.addWidget(action)

    def set_count(self, count: int) -> None:
        if self._count_label is not None:
            self._count_label.setText(f"({count})")

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)


class EmptyState(QFrame):
    """Centered empty-state with an optional outline icon and two text lines."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        glyph: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addStretch(1)

        if glyph:
            box = QFrame()
            box.setObjectName("empty-icon")
            box.setFixedSize(52, 52)
            icon = QLabel(glyph)
            icon.setObjectName("empty-glyph")
            icon.setAlignment(Qt.AlignCenter)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            box_layout.addWidget(icon)
            wrapper = QHBoxLayout()
            wrapper.addStretch(1)
            wrapper.addWidget(box)
            wrapper.addStretch(1)
            layout.addLayout(wrapper)
            layout.addSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("empty-title")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        sub_label = QLabel(subtitle)
        sub_label.setObjectName("empty-sub")
        sub_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub_label)
        layout.addStretch(1)


class IconButton(QPushButton):
    def __init__(
        self,
        text: str,
        tooltip: str = "",
        checkable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("icon-btn")
        self.setToolTip(tooltip)
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)


class RowActionButton(QPushButton):
    def __init__(self, text: str, tooltip: str, danger: bool = False) -> None:
        super().__init__(text)
        self.setObjectName("row-action")
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        if danger:
            self.setProperty("danger", True)


class RoundCheckBox(QCheckBox):
    """Checkbox drawn as a rounded square with a hand-picked check mark."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1.5, 1.5, 15.0, 15.0)

        painter.setPen(QPen(QColor(COLORS["border"]), 1.5))
        painter.setBrush(QBrush(QColor(COLORS["card_alt"])))
        painter.drawRoundedRect(rect, 4, 4)

        if self.isChecked():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(COLORS["accent"])))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(
                QPen(
                    QColor(COLORS["on_accent"]),
                    2.0,
                    Qt.SolidLine,
                    Qt.RoundCap,
                    Qt.RoundJoin,
                )
            )
            painter.drawLine(QPointF(5.0, 9.0), QPointF(8.0, 12.0))
            painter.drawLine(QPointF(8.0, 12.0), QPointF(13.0, 6.0))


class FieldDialog(QDialog):
    """Small frameless form used by every add/edit action."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        fields: list[dict[str, Any]],
        ok_label: str = "Save",
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self._widgets: dict[str, Any] = {}

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
        inner.setContentsMargins(22, 20, 22, 18)
        inner.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("dialog-title")
        inner.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        for field in fields:
            key = field["key"]
            label = QLabel(field["label"])
            label.setObjectName("field-label")
            kind = field.get("kind", "text")
            value = field.get("value", "")

            if kind == "textarea":
                widget: Any = QPlainTextEdit()
                widget.setPlainText(str(value or ""))
            elif kind == "datetime":
                widget = QDateTimeEdit()
                widget.setCalendarPopup(True)
                widget.setDisplayFormat("dd-MM-yyyy HH:mm")
                widget.setDateTime(value)
            else:
                widget = QLineEdit(str(value or ""))
                widget.setPlaceholderText(field.get("placeholder", ""))

            self._widgets[key] = widget
            form.addRow(label, widget)

        inner.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        save = QPushButton(ok_label)
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        buttons.addWidget(save)

        inner.addLayout(buttons)
        QTimer.singleShot(0, self._center)

    def _center(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        origin = parent.mapToGlobal(QPoint(0, 0))
        self.move(
            origin.x() + (parent.width() - self.width()) // 2,
            origin.y() + (parent.height() - self.height()) // 2,
        )

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QPlainTextEdit):
                result[key] = widget.toPlainText().strip()
            elif isinstance(widget, QDateTimeEdit):
                result[key] = widget.dateTime()
            else:
                result[key] = widget.text().strip()
        return result

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
