"""Tests for the productivity dashboard (dashboard-only)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DASHBOARD_ROOT = Path(__file__).resolve().parents[2] / "hypr/.config/hypr/scripts"
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))
