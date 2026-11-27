#!/usr/bin/env python3
"""Static integration checks for dashboard wiring."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "hypr/.config/hypr/scripts/dashboard"


class IntegrationTests(unittest.TestCase):
    def test_waybar_clock_on_click(self) -> None:
        text = (REPO / "waybar/.config/waybar/config.jsonc").read_text()
        clock = re.search(r'"clock"\s*:\s*\{(.*?)\n\s*\}', text, re.S)
        self.assertIsNotNone(clock)
        self.assertIn("productivity-dashboard", clock.group(1))

    def test_hyprland_window_rules(self) -> None:
        text = (REPO / "hypr/.config/hypr/hyprland.lua").read_text()
        self.assertIn('title = "^Productivity Dashboard$"', text)
        self.assertIn('title = "^Event Notification$"', text)

    def test_no_stale_desktop_hardcoding_in_dashboard(self) -> None:
        for path in DASH.rglob("*.py"):
            text = path.read_text()
            self.assertNotIn("/home/aditya", text, path.name)

    def test_notification_timer_units(self) -> None:
        service = DASH / "systemd/productivity-dashboard-notify.service"
        timer = DASH / "systemd/productivity-dashboard-notify.timer"
        self.assertIn("--check-notifications", service.read_text())
        self.assertIn("Persistent=true", timer.read_text())

    def test_state_schema_has_no_notes_or_wallpapers(self) -> None:
        from dashboard.core.models import DashboardState

        keys = set(DashboardState().to_dict())
        self.assertEqual(keys, {"version", "todos", "events", "calendar"})


if __name__ == "__main__":
    unittest.main()
