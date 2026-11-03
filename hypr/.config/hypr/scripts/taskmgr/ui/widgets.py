#!/usr/bin/env python3
"""Reusable Cairo graphs, per-core meters, and GTK4 table helpers."""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango


def hex_to_rgb(
    h: str, default: tuple[float, float, float] = (0.82, 0.61, 0.38)
) -> tuple[float, float, float]:
    h = (h or "").strip().lstrip("#")
    if len(h) == 6:
        try:
            return (
                int(h[0:2], 16) / 255.0,
                int(h[2:4], 16) / 255.0,
                int(h[4:6], 16) / 255.0,
            )
        except ValueError:
            pass
    return default


class SparklineAreaChart(Gtk.DrawingArea):
    """Windows 11 Task Manager / tanksManager style 60-second area chart with optional secondary trace."""

    def __init__(
        self,
        title: str,
        fixed_max: float | None = 100.0,
        height: int = 128,
    ) -> None:
        super().__init__()
        self.title = title
        self.fixed_max = fixed_max
        self.primary_values: list[float] = []
        self.secondary_values: list[float] = []
        self.right_label: str = ""
        self.sub_label: str = ""
        self.accent_rgb: tuple[float, float, float] = (0.82, 0.61, 0.38)
        self.secondary_rgb: tuple[float, float, float] = (0.95, 0.42, 0.42)
        self.bg_rgb: tuple[float, float, float] = (0.11, 0.10, 0.10)
        self.set_content_height(height)
        self.set_hexpand(True)
        self.set_draw_func(self._on_draw)

    def update_chart(
        self,
        primary: list[float],
        right_label: str,
        sub_label: str = "",
        secondary: list[float] | None = None,
        accent_rgb: tuple[float, float, float] | None = None,
        bg_rgb: tuple[float, float, float] | None = None,
        title: str | None = None,
    ) -> None:
        self.primary_values = list(primary)
        self.right_label = right_label
        self.sub_label = sub_label
        self.secondary_values = list(secondary) if secondary else []
        if title is not None:
            self.title = title
        if accent_rgb is not None:
            self.accent_rgb = accent_rgb
        if bg_rgb is not None:
            self.bg_rgb = bg_rgb
        self.queue_draw()

    def _on_draw(
        self, _area: Gtk.DrawingArea, cr: cairo.Context, width: int, height: int
    ) -> None:
        br, bg, bb = self.bg_rgb
        cr.set_source_rgba(br, bg, bb, 0.92)
        cr.paint()

        # Subtle grid lines
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.06)
        cr.set_line_width(1.0)
        top_pad = 30.0
        plot_h = max(height - top_pad - 6.0, 10.0)
        for i in range(1, 4):
            y = top_pad + (plot_h * i / 4.0)
            cr.move_to(0, y)
            cr.line_to(width, y)
        for i in range(1, 6):
            x = width * i / 6.0
            cr.move_to(x, top_pad)
            cr.line_to(x, height)
        cr.stroke()

        vals = self.primary_values
        if len(vals) >= 2:
            peak = max(vals)
            if self.secondary_values:
                peak = max(peak, max(self.secondary_values))
            max_v = (
                self.fixed_max if self.fixed_max is not None else max(peak * 1.15, 1.0)
            )
            n = len(vals)
            step_x = width / float(n - 1)

            # Draw primary area + line
            r, g, b = self.accent_rgb
            cr.move_to(0, height)
            for idx, v in enumerate(vals):
                x = idx * step_x
                y = height - min(max(v / max_v, 0.0), 1.0) * plot_h
                cr.line_to(x, y)
            cr.line_to(width, height)
            cr.close_path()
            cr.set_source_rgba(r, g, b, 0.24)
            cr.fill()

            for idx, v in enumerate(vals):
                x = idx * step_x
                y = height - min(max(v / max_v, 0.0), 1.0) * plot_h
                if idx == 0:
                    cr.move_to(x, y)
                else:
                    cr.line_to(x, y)
            cr.set_source_rgba(r, g, b, 0.95)
            cr.set_line_width(2.0)
            cr.stroke()

            # Optional secondary trace (e.g., Kernel time or Upload / Write rate)
            if len(self.secondary_values) == n:
                sr, sg, sb = self.secondary_rgb
                for idx, v in enumerate(self.secondary_values):
                    x = idx * step_x
                    y = height - min(max(v / max_v, 0.0), 1.0) * plot_h
                    if idx == 0:
                        cr.move_to(x, y)
                    else:
                        cr.line_to(x, y)
                cr.set_source_rgba(sr, sg, sb, 0.85)
                cr.set_line_width(1.5)
                cr.stroke()

        # Header text overlay
        cr.select_font_face(
            "Adwaita Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
        )
        cr.set_font_size(12.0)
        cr.set_source_rgba(0.95, 0.94, 0.92, 0.96)
        cr.move_to(10, 18)
        cr.show_text(self.title)

        if self.right_label:
            ext = cr.text_extents(self.right_label)
            cr.move_to(max(width - ext.width - 12, 140), 18)
            cr.show_text(self.right_label)

        if self.sub_label:
            cr.select_font_face(
                "Adwaita Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL
            )
            cr.set_font_size(10.5)
            cr.set_source_rgba(0.75, 0.73, 0.70, 0.90)
            cr.move_to(10, 31)
            cr.show_text(self.sub_label)


def build_tree_view(
    store: Gtk.ListStore,
    columns: list[tuple[str, int, int, int]],
    max_total_width: int = 1300,
) -> tuple[Gtk.TreeView, Gtk.TreeModelFilter, Gtk.TreeModelSort, Gtk.ScrolledWindow]:
    """Create a sortable, filterable Gtk.TreeView wrapped in a Gtk.ScrolledWindow.

    columns format: [(title, text_col_idx, sort_col_idx, min_width), ...]
    Column widths are scaled down so a table never forces the window wider
    than the monitor; the ScrolledWindow provides horizontal scrolling and
    every column remains user-resizable.
    """
    model_filter = store.filter_new()
    model_sort = Gtk.TreeModelSort(model=model_filter)
    view = Gtk.TreeView(model=model_sort)
    view.set_headers_clickable(True)
    view.set_enable_search(False)

    requested_total = sum(c[3] for c in columns) or 1
    scale = min(1.0, float(max_total_width) / requested_total)

    for title, text_col, sort_col, min_w in columns:
        width = max(55, int(min_w * scale))
        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn(title, renderer, text=text_col)
        col.set_sort_column_id(sort_col)
        col.set_resizable(True)
        col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col.set_fixed_width(width)
        col.set_min_width(width)
        view.append_column(col)

    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_hexpand(True)
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.set_propagate_natural_width(False)
    scroll.set_propagate_natural_height(False)
    scroll.set_child(view)
    return view, model_filter, model_sort, scroll
