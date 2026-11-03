#!/usr/bin/env python3
"""Entry point for Hyprland Task Manager & System Explorer (taskmgr / sysmon)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

# Ensure package imports resolve regardless of working directory
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from backend.doctor import SystemDoctor
from ui.window import PAGES_SPEC, TaskManagerWindow


class TaskManagerApp(Gtk.Application):
    def __init__(
        self,
        initial_page: str = "processes",
        smoke_test: bool = False,
        lifecycle_test: bool = False,
        power_test: bool = False,
    ) -> None:
        super().__init__(application_id="com.aditya.taskmgr")
        self.initial_page = initial_page
        self.smoke_test = smoke_test
        self.lifecycle_test = lifecycle_test
        self.power_test = power_test
        self.win: TaskManagerWindow | None = None

    def do_activate(self) -> None:
        if self.win is None:
            self.win = TaskManagerWindow(self, initial_page=self.initial_page)
        self.win.present()

        if self.power_test and self.win is not None:
            self._run_power_test()
        elif self.lifecycle_test and self.win is not None:
            self._run_lifecycle_test()
        elif self.smoke_test and self.win is not None:
            self._run_smoke_test()

    def _run_power_test(self) -> None:
        """Click each real power-profile button and verify the daemon state."""
        assert self.win is not None
        from backend.power_profiles import PowerProfileController

        if not PowerProfileController.is_available():
            print("POWER_TEST_UNAVAILABLE", flush=True)
            self.quit()
            return
        original = PowerProfileController.get_current()
        print(f"POWER_ORIGINAL: {original}", flush=True)
        results: list[tuple[str, str | None]] = []
        try:
            for profile, button in self.win.profile_buttons.items():
                button.emit("clicked")
                actual = PowerProfileController.get_current()
                results.append((profile, actual))
                print(
                    f"POWER_BUTTON {profile}: requested={profile} actual={actual}",
                    flush=True,
                )
        finally:
            if original:
                PowerProfileController.set_profile(original)
            print(
                f"POWER_RESTORED: {PowerProfileController.get_current()}",
                flush=True,
            )
        passed = all(actual == requested for requested, actual in results)
        print("POWER_TEST_PASS" if passed else "POWER_TEST_FAIL", flush=True)
        self.quit()

    def _run_smoke_test(self) -> None:
        assert self.win is not None
        page_ids = [p[0] for p in PAGES_SPEC]

        def step(idx: int) -> bool:
            if self.win is None:
                return False
            if idx < len(page_ids):
                pid = page_ids[idx]
                self.win._select_page(pid)
                self.win._refresh_all()
                print(f"SMOKE_TEST_PAGE_OK: {pid}", flush=True)
                if pid == "ports":
                    hpol, vpol = self.win.port_scroll.get_policy()
                    h_ok = hpol == Gtk.PolicyType.ALWAYS
                    v_ok = vpol == Gtk.PolicyType.ALWAYS
                    print(
                        f"SMOKE_TEST_PORTS_SCROLL: horizontal={h_ok} vertical={v_ok}",
                        flush=True,
                    )
                    if not (h_ok and v_ok):
                        print(
                            "SMOKE_TEST_FAIL: Ports scrollbars are not both enabled",
                            flush=True,
                        )
                        self.quit()
                        return False
                if pid == "processes":
                    rows = len(self.win.proc_store)
                    print(f"SMOKE_TEST_PROCESS_ROWS: {rows}", flush=True)
                    if rows == 0:
                        print(
                            "SMOKE_TEST_FAIL: process table is empty after refresh",
                            flush=True,
                        )
                        self.quit()
                        return False
                    probe = os.environ.get("TASKMGR_SMOKE_PROBE_PID")
                    if probe and probe.isdigit():
                        found = any(
                            int(row[0]) == int(probe) for row in self.win.proc_store
                        )
                        print(
                            f"SMOKE_TEST_PROBE_PID {probe}: "
                            f"{'FOUND' if found else 'MISSING'}",
                            flush=True,
                        )
                        if not found:
                            print(
                                "SMOKE_TEST_FAIL: newly launched probe process "
                                "is missing from the GUI store",
                                flush=True,
                            )
                            self.quit()
                            return False
                GLib.timeout_add(120, lambda: step(idx + 1))
            else:
                print("SMOKE_TEST_COMPLETE: ALL_9_PAGES_VERIFIED", flush=True)
                refresh_handled = self.win._on_capture_key(
                    None,
                    Gdk.KEY_r,
                    0,
                    Gdk.ModifierType.CONTROL_MASK,
                )
                print(
                    f"SMOKE_TEST_CTRL_R_HANDLED: {refresh_handled}",
                    flush=True,
                )
                if not refresh_handled:
                    print(
                        "SMOKE_TEST_FAIL: Ctrl+R was not handled",
                        flush=True,
                    )
                handled = self.win._on_capture_key(
                    None, Gdk.KEY_Escape, 0, Gdk.ModifierType(0)
                )
                print(f"SMOKE_TEST_ESCAPE_HANDLED: {handled}", flush=True)
                if not handled:
                    print("SMOKE_TEST_FAIL: Escape was not handled", flush=True)
                self.quit()
            return False

        GLib.timeout_add(150, lambda: step(0))

    def _run_lifecycle_test(self) -> None:
        """Spawn a real process, prove it appears in the GUI store, kill it,
        and prove it disappears after the next refresh."""
        assert self.win is not None
        proc = subprocess.Popen(
            ["bash", "-c", "exec -a taskmgr_lifecycle_probe sleep 30"]
        )
        print(f"LIFECYCLE_PROBE_PID: {proc.pid}", flush=True)
        state = {"found": False}

        def phase_found() -> bool:
            if self.win is None:
                return False
            self.win._select_page("processes")
            self.win._refresh_all()
            state["found"] = any(int(row[0]) == proc.pid for row in self.win.proc_store)
            print(f"LIFECYCLE_FOUND_IN_GUI: {state['found']}", flush=True)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            GLib.timeout_add(700, phase_removed)
            return False

        def phase_removed() -> bool:
            if self.win is None:
                return False
            self.win._refresh_all()
            gone = not any(int(row[0]) == proc.pid for row in self.win.proc_store)
            print(f"LIFECYCLE_REMOVED_FROM_GUI: {gone}", flush=True)
            if state["found"] and gone:
                print("LIFECYCLE_TEST_PASS", flush=True)
            else:
                print("LIFECYCLE_TEST_FAIL", flush=True)
            self.quit()
            return False

        GLib.timeout_add(1200, phase_found)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="taskmgr",
        description="Windows-style Task Manager & Full System Diagnostic Explorer for Arch Linux + Hyprland",
    )
    parser.add_argument(
        "--page",
        "-p",
        choices=[p[0] for p in PAGES_SPEC],
        default="processes",
        help="Initial page to display on launch",
    )
    parser.add_argument(
        "--doctor-json",
        action="store_true",
        help="Run the full 'Working vs. Not Working' audit and print JSON to stdout without opening the GUI",
    )
    parser.add_argument(
        "--verify-truth",
        action="store_true",
        help="Cross-check displayed values against independent kernel sources and exit",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Launch the GTK4 window, cycle through all 9 pages to verify live rendering, and exit",
    )
    parser.add_argument(
        "--lifecycle-test",
        action="store_true",
        help="Spawn a real process, prove it appears in the GUI store, kill it, and prove it disappears",
    )
    parser.add_argument(
        "--power-test",
        action="store_true",
        help="Click each real power-profile button, verify the daemon state, and restore the original profile",
    )
    args, gtk_args = parser.parse_known_args()

    if args.doctor_json:
        print(json.dumps(SystemDoctor.run_full_audit(), indent=2))
        return 0

    if args.verify_truth:
        from backend.verification import run_truth_audit

        results = run_truth_audit()
        print(f"{'CHECK':<38} {'PASS':<5} {'EXPECTED':<22} {'COLLECTOR':<22} NOTE")
        print("-" * 118)
        failed = 0
        for r in results:
            status = "OK" if r["pass"] else "FAIL"
            if not r["pass"]:
                failed += 1
            print(
                f"{r['check']:<38} {status:<5} {str(r['expected']):<22} "
                f"{str(r['collector_value']):<22} {r['note']}"
            )
        print("-" * 118)
        print(
            f"{len(results) - failed}/{len(results)} independent cross-checks passed."
        )
        return 0 if failed == 0 else 1

    app = TaskManagerApp(
        initial_page=args.page,
        smoke_test=args.smoke_test,
        lifecycle_test=args.lifecycle_test,
        power_test=args.power_test,
    )
    # Install our own SIGINT handler before Gio.run() installs its fallback.
    # Without this, Gio re-raises the default KeyboardInterrupt after the main
    # loop and can leave the GTK window alive in some Python/GTK combinations.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    try:
        return app.run([sys.argv[0], *gtk_args])
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
