# Productivity Dashboard

**Status:** Implemented for the reference deployment (Hyprland 0.56, Waybar 0.15, PySide6 6.12).

## Purpose

A three-section desktop dashboard (Todo, Calendar, Events) opened by clicking
the Waybar date/time module. It is a normal always-on-top Qt window, not a
layer-shell overlay or a terminal UI.

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
│   ├── models.py    # Todo, Subtask, Event, CalendarSelection, DashboardState
│   ├── store.py     # locked, atomic JSON persistence
│   ├── calendar_logic.py
│   ├── events.py    # deadline completion + notification dedupe
│   ├── notifier.py
│   └── hypr_integration.py
└── ui/
    ├── theme.py     # centralized colors/QSS/animation helpers
    ├── widgets.py   # cards, headers, buttons, custom dialogs
    ├── window.py    # frameless shell + panel layout
    └── <section>.py # todo, calendar, events
```

## State

Todo rows show only the task name; clicking a name opens the edit form. A task
can hold subtasks that can be added, edited, deleted and struck through inside
that form. When every subtask is struck, the parent task is struck automatically
and the active count drops. Events can be edited or deleted from the event row.

All data lives in `~/.local/share/productivity-dashboard/state.json`.
Writes are atomic (temp file + `os.replace`) and guarded by an advisory
`flock`. A missing or corrupt file falls back to an empty state.

## Usage

- Click the Waybar clock/date to open the dashboard; click it again to close.
- `Escape` or a click outside the card also closes it.
- Event notifications fire at the **exact configured second** via a transient
  systemd timer (`systemd-run --user --on-calendar=...`) armed whenever an
  event is saved or snoozed. A persistent minutely timer remains as a reboot /
  catch-up fallback.
- The notification is a real always-on-top popup with two **clickable buttons**:
  **Snooze · 5 min** (default — ignoring or closing the popup also snoozes it)
  and **Dismiss** (no further reminder). The title is
  `{Name} - {Event time (dd-MM-yyyy HH:mm)}`.
- A snooze that would land at or past the event time is dropped from the
  schedule entirely.

## Verification

```bash
python3 -m compileall -q ~/.config/hypr/scripts/dashboard
bash -n ~/.local/bin/productivity-dashboard
~/.local/bin/productivity-dashboard --check-notifications
systemctl --user status productivity-dashboard-notify.timer
```
