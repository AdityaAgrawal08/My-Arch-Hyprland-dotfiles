from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import wallpapers as wallpaper_core
from ..core.models import DashboardState
from .widgets import IconButton, SectionHeader


class WallpaperPanel(QWidget):
    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.setObjectName("panel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.state = state
        self._items = wallpaper_core.list_wallpapers()
        self._mode = "grid"

        self._grid_button = IconButton("▦", "Grid view", checkable=True)
        self._grid_button.setChecked(True)
        self._list_button = IconButton("☰", "List view", checkable=True)
        self.header = SectionHeader(
            "◧", "Wallpapers", len(self._items), (self._grid_button, self._list_button)
        )

        self._view = QListWidget()
        self._view.setViewMode(QListView.IconMode)
        self._view.setFrameShape(QListWidget.NoFrame)
        self._view.setMovement(QListView.Static)
        self._view.setResizeMode(QListView.Adjust)
        self._view.setFlow(QListView.LeftToRight)
        self._view.setSpacing(10)
        self._view.setIconSize(QSize(175, 65))
        self._view.setGridSize(QSize(195, 112))
        self._view.itemClicked.connect(self._on_click)

        self._empty = QLabel("No wallpapers found in the theme assets directory.")
        self._empty.setObjectName("subtext")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setVisible(not self._items)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(4)
        layout.addWidget(self.header)
        layout.addWidget(self._empty)
        layout.addWidget(self._view, 1)

        self._grid_button.toggled.connect(self._set_mode)
        self._list_button.toggled.connect(self._set_mode)
        self._populate()

    def set_state(self, state: DashboardState) -> None:
        self.state = state

    def _set_mode(self, _checked: bool) -> None:
        use_grid = self._grid_button.isChecked()
        if use_grid == (self._mode == "grid"):
            return
        self._list_button.blockSignals(True)
        self._grid_button.blockSignals(True)
        self._grid_button.setChecked(use_grid)
        self._list_button.setChecked(not use_grid)
        self._list_button.blockSignals(False)
        self._grid_button.blockSignals(False)

        self._mode = "grid" if use_grid else "list"
        if use_grid:
            self._view.setViewMode(QListView.IconMode)
            self._view.setIconSize(QSize(175, 65))
            self._view.setGridSize(QSize(195, 112))
            self._view.setFlow(QListView.LeftToRight)
        else:
            self._view.setViewMode(QListView.ListMode)
            self._view.setIconSize(QSize(56, 40))
            self._view.setGridSize(QSize())
            self._view.setFlow(QListView.TopToBottom)
        self._populate()

    def _populate(self) -> None:
        self._view.clear()
        current = wallpaper_core.current_wallpaper()
        current_item = None
        for index, entry in enumerate(self._items):
            path = str(entry.get("path") or "")
            name = str(entry.get("name") or path.rsplit("/", 1)[-1])
            pixmap = QPixmap(str(entry.get("thumb") or path))
            icon = QIcon()
            if not pixmap.isNull():
                target = QSize(260, 100) if self._mode == "grid" else QSize(84, 60)
                scaled = pixmap.scaled(
                    target, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                x = max(0, (scaled.width() - target.width()) // 2)
                y = max(0, (scaled.height() - target.height()) // 2)
                icon = QIcon(scaled.copy(x, y, target.width(), target.height()))
            item = QListWidgetItem(icon, f"{index + 1}. {name}")
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self._view.addItem(item)
            if path and path == current:
                current_item = item
        if current_item is not None:
            self._view.setCurrentItem(current_item)
        self._view.scrollToTop()

    def _on_click(self, item: QListWidgetItem) -> None:
        path = str(item.data(Qt.UserRole) or "")
        if wallpaper_core.apply_wallpaper(path):
            self._view.setCurrentItem(item)
            QTimer.singleShot(2500, self._refresh_highlight)

    def _refresh_highlight(self) -> None:
        current = wallpaper_core.current_wallpaper()
        for index in range(self._view.count()):
            item = self._view.item(index)
            if str(item.data(Qt.UserRole) or "") == current:
                self._view.setCurrentItem(item)
                break
