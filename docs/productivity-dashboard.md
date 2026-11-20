# Productivity Dashboard

**Status:** Implemented for the reference deployment (Hyprland 0.56, Waybar 0.15, PySide6 6.12).

## Purpose

A five-section desktop dashboard (Todo, Calendar, Wallpapers, Notes, Events)
opened by clicking the Waybar date/time module. It is a normal always-on-top
Qt window, not a layer-shell overlay or a terminal UI.

## Files

| Path | Role |
| --- | --- |
| `hypr/.config/hypr/scripts/dashboard/` | Application package (core + UI). |
| `hypr/.config/hypr/scripts/dashboard/systemd/` | User timer units. |
| `local/.local/bin/productivity-dashboard` | Toggle launcher / timer entry point. |
| `waybar/.config/waybar/config.jsonc` | Clock `on-click` hook. |
| `hypr/.config/hypr/hyprland.lua` | Floating window rule for the dashboard (matched by window title). |

## Architecture

```
dashboard/
├── main.py          # GUI and --check-notifications entry points
├── app.py           # QApplication, periodic event check, SIGTERM handling
├── core/
│   ├── models.py    # Todo, Note, Event, CalendarSelection, DashboardState
│   ├── store.py     # locked, atomic JSON persistence
│   ├── calendar_logic.py
│   ├── events.py    # deadline completion + notification dedupe
│   ├── wallpapers.py
│   ├── notifier.py
│   └── hypr_integration.py
└── ui/
    ├── theme.py     # centralized colors/QSS/animation helpers
    ├── widgets.py   # cards, headers, buttons, custom dialogs
    ├── window.py    # frameless shell + panel layout
    └── <section>.py # todo, calendar, wallpapers, notes, events
```

## State

All data lives in `~/.local/share/productivity-dashboard/state.json`.
Writes are atomic (temp file + `os.replace`) and guarded by an advisory
`flock`. A missing or corrupt file falls back to an empty state.

## Usage

- Click the Waybar clock/date to open the dashboard; click it again to close.
- `Escape` or a click outside the card also closes it.
- Wallpaper tiles apply the wallpaper through
  `wallpaper_switch.sh apply <path>` — the same result as the SUPER+T picker.
  The SUPER+T binding is unchanged.
- Event notifications are checked by a user systemd timer every minute,
  even when the dashboard is closed, and survive reboots.

## Verification

```bash
python3 -m compileall -q ~/.config/hypr/scripts/dashboard
bash -n ~/.local/bin/productivity-dashboard
~/.local/bin/productivity-dashboard --check-notifications
systemctl --user status productivity-dashboard-notify.timer
```
