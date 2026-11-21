#!/usr/bin/env python3
"""Entry point for the productivity dashboard.

GUI mode (default) is launched by the Waybar clock or by the shell launcher.
--check-notifications is a headless mode used by the systemd user timer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Productivity dashboard")
    parser.add_argument(
        "--check-notifications",
        action="store_true",
        help="Check event deadlines/notifications once and exit (timer mode)",
    )
    parser.add_argument(
        "--notify",
        metavar="EVENT_ID",
        help="Show the clickable notification popup for one event",
    )
    args = parser.parse_args()

    if args.notify:
        from dashboard.core import store
        from dashboard.core.events import event_body, notification_title
        from dashboard.ui.notification import show

        state = store.load()
        event = next((item for item in state.events if item.id == args.notify), None)
        if event is None:
            return 1
        action = show(notification_title(event), event_body(event))
        if action:
            print(action)
        return 0

    if args.check_notifications:
        from dashboard.core import events

        _changed, fired = events.check_all(send=True)
        print(f"notification check complete: {len(fired)} sent")
        return 0

    from dashboard.app import DashboardApp

    return DashboardApp().run()


if __name__ == "__main__":
    raise SystemExit(main())
