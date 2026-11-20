from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QParallelAnimationGroup
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

COLORS: dict[str, str] = {
    "card": "#1a1512",
    "card_alt": "#221a16",
    "card_hover": "#2a201b",
    "border": "#3b2c24",
    "border_soft": "#2d231e",
    "text": "#f4eae2",
    "muted": "#a08d80",
    "faint": "#6f5e53",
    "accent": "#e8a06a",
    "accent_hover": "#f4b98d",
    "accent_dark": "#b97047",
    "accent_soft": "rgba(232,160,106,0.15)",
    "on_accent": "#1a1009",
    "danger": "#ec6b62",
    "danger_soft": "rgba(236,107,98,0.14)",
    "ok": "#7fc99a",
    "info": "#7aa7e8",
    "shadow": "rgba(0,0,0,160)",
}

FONT = '"Inter", "Adwaita Sans", "Noto Sans", sans-serif'

STYLESHEET = """
* {
    font-family: %(font)s;
    color: %(text)s;
    outline: none;
}

QWidget#dashboard-root { background: transparent; }

QFrame#card {
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 14px;
}

QLabel#section-icon {
    font-size: 20px;
    color: %(accent)s;
    min-width: 24px;
}

QLabel#section-title {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.2px;
}

QLabel#count {
    font-size: 16px;
    font-weight: 700;
    color: %(accent)s;
    margin-left: 2px;
}

QLabel#subtext {
    font-size: 12px;
    color: %(muted)s;
}

QLabel#struck {
    font-size: 13px;
    color: %(muted)s;
    text-decoration: line-through;
}

QLabel#day-label {
    font-size: 13px;
    font-weight: 600;
    color: %(muted)s;
}

QPushButton#icon-btn {
    background: %(card_alt)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    min-width: 30px;
    max-width: 30px;
    min-height: 28px;
    max-height: 28px;
    font-size: 14px;
    color: %(muted)s;
}
QPushButton#icon-btn:hover {
    background: %(accent_soft)s;
    border-color: %(accent)s;
    color: %(accent)s;
}
QPushButton#icon-btn:checked {
    background: %(accent)s;
    border-color: %(accent)s;
    color: %(on_accent)s;
}
QPushButton#icon-btn[active="true"] {
    background: %(accent)s;
    border-color: %(accent)s;
    color: %(on_accent)s;
}

QPushButton#primary {
    background: %(accent)s;
    color: %(on_accent)s;
    border: none;
    border-radius: 8px;
    padding: 7px 18px;
    font-weight: 700;
}
QPushButton#primary:hover { background: %(accent_hover)s; }
QPushButton#primary:disabled { background: %(border)s; color: %(muted)s; }

QPushButton#ghost {
    background: transparent;
    color: %(muted)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 7px 16px;
}
QPushButton#ghost:hover { background: %(card_hover)s; color: %(text)s; }

QPushButton#day {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    font-size: 12px;
    font-weight: 600;
    min-height: 24px;
}
QPushButton#day:hover { background: %(card_hover)s; }
QPushButton#day[adjacent="true"] { color: %(faint)s; }
QPushButton#day[today="true"] { border: 1px solid %(accent_dark)s; }
QPushButton#day[selected="true"] {
    background: %(accent)s;
    color: %(on_accent)s;
    border: 1px solid %(accent)s;
}
QPushButton#day[selected="true"]:hover { background: %(accent_hover)s; }

QPushButton#go {
    background: %(accent_soft)s;
    color: %(accent)s;
    border: 1px solid %(accent_dark)s;
    border-radius: 8px;
    padding: 6px 14px;
    font-weight: 700;
}
QPushButton#go:hover { background: %(accent)s; color: %(on_accent)s; }

QLineEdit, QDateTimeEdit, QPlainTextEdit {
    background: %(card_alt)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: %(accent_dark)s;
}
QLineEdit:focus, QDateTimeEdit:focus, QPlainTextEdit:focus {
    border: 1px solid %(accent)s;
}
QPlainTextEdit { min-height: 64px; }

QListWidget {
    background: transparent;
    border: none;
    padding: 0;
}
QListWidget::item { background: transparent; border: none; }
QListWidget::item:selected { background: transparent; }
QListWidget::item:hover { background: transparent; }

QFrame#task-row, QFrame#note-row, QFrame#event-row {
    background: transparent;
    border: none;
    border-bottom: 1px solid %(border_soft)s;
}
QFrame#task-row:hover, QFrame#note-row:hover, QFrame#event-row:hover {
    background: %(card_hover)s;
    border-radius: 6px;
}

QPushButton#row-action {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: %(faint)s;
    font-size: 14px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
}
QPushButton#row-action { color: transparent; }
QPushButton#row-action[always="true"] { color: %(faint)s; }
QFrame#task-row:hover QPushButton#row-action,
QFrame#note-row:hover QPushButton#row-action,
QFrame#event-row:hover QPushButton#row-action { color: %(faint)s; }
QPushButton#row-action:hover { background: %(accent_soft)s; color: %(accent)s; }
QPushButton#row-action[danger="true"]:hover {
    background: %(danger_soft)s;
    color: %(danger)s;
}

QLabel#handle {
    color: %(faint)s;
    font-size: 15px;
    min-width: 16px;
    max-width: 16px;
}

QFrame#event-bar-upcoming { background: %(danger)s; border-radius: 2px; }
QFrame#event-bar-completed { background: %(info)s; border-radius: 2px; }

QFrame#dialog {
    background: %(card)s;
    border: 1px solid %(accent_dark)s;
    border-radius: 14px;
}

QLabel#dialog-title {
    font-size: 16px;
    font-weight: 700;
    color: %(text)s;
}

QLabel#field-label {
    font-size: 12px;
    font-weight: 600;
    color: %(muted)s;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px 0 2px 0;
}
QScrollBar::handle:vertical {
    background: %(border)s;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: %(accent_dark)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0 2px 0 2px;
}
QScrollBar::handle:horizontal {
    background: %(border)s;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
""" % {**COLORS, "font": FONT}


def apply_theme(app: Any) -> None:
    app.setStyleSheet(STYLESHEET)


def fade_in(widget: QWidget, duration: int = 200, start: float = 0.0) -> None:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.start()
    widget._fade_animation = animation  # keep a reference alive
    widget._fade_effect = effect


def fade_swap(widget: QWidget, callback) -> None:
    """Fade out, run callback (which rebuilds content), then fade back in."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    group = QParallelAnimationGroup(widget)

    out = QPropertyAnimation(effect, b"opacity", widget)
    out.setDuration(90)
    out.setStartValue(1.0)
    out.setEndValue(0.25)

    inn = QPropertyAnimation(effect, b"opacity", widget)
    inn.setDuration(140)
    inn.setStartValue(0.25)
    inn.setEndValue(1.0)
    inn.setEasingCurve(QEasingCurve.OutCubic)

    group.addAnimation(out)
    group.addAnimation(inn)

    def on_finished() -> None:
        widget.setGraphicsEffect(None)
        widget._swap_group = None

    inn.finished.connect(on_finished)
    widget._swap_group = group

    def on_out_finished() -> None:
        callback()
        inn.start()

    out.finished.connect(on_out_finished)
    out.start()
