#!/usr/bin/env python3
"""Entry point for Hyprland Task Manager & System Explorer (taskmgr / sysmon)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
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
from backend.ebpf import PROBES
from ui.window import PAGES_SPEC, TaskManagerWindow


class TaskManagerApp(Gtk.Application):
    def __init__(
        self,
        initial_page: str = "processes",
        smoke_test: bool = False,
        lifecycle_test: bool = False,
        power_test: bool = False,
        async_test: bool = False,
        responsive_test: bool = False,
    ) -> None:
        super().__init__(application_id="com.aditya.taskmgr")
        self.initial_page = initial_page
        self.smoke_test = smoke_test
        self.lifecycle_test = lifecycle_test
        self.power_test = power_test
        self.async_test = async_test
        self.responsive_test = responsive_test
        self.win: TaskManagerWindow | None = None

    def do_activate(self) -> None:
        if self.win is None:
            self.win = TaskManagerWindow(self, initial_page=self.initial_page)
        self.win.present()

        if self.power_test and self.win is not None:
            self._run_power_test()
        elif self.responsive_test and self.win is not None:
            self._run_responsive_test()
        elif self.async_test and self.win is not None:
            self._run_async_test()
        elif self.lifecycle_test and self.win is not None:
            self._run_lifecycle_test()
        elif self.smoke_test and self.win is not None:
            self._run_smoke_test()

    def _run_responsive_test(self) -> None:
        """Force compact mode, resize to 900x600, and verify the result."""
        assert self.win is not None
        # Simulate a 960x540 logical monitor to exercise the automatic path.
        self.win._monitor_logical_size = lambda: (960.0, 540.0)
        self.win._auto_compact_checked = False
        self.win._maybe_auto_compact()
        print(
            f"RESPONSIVE_AUTO_COMPACT: {self.win._compact_mode}",
            flush=True,
        )
        print(
            f"RESPONSIVE_AUTO_DEFAULT_SIZE: {self.win.get_default_size()}",
            flush=True,
        )
        self.win._apply_compact_mode(True)
        min_width = self.win.measure(Gtk.Orientation.HORIZONTAL, -1).minimum
        hidden = 0
        visible = 0
        for view, _kind in self.win._context_views:
            for column in view.get_columns():
                if column.get_visible():
                    visible += 1
                else:
                    hidden += 1
        print(f"RESPONSIVE_COMPACT_MIN_WIDTH: {min_width}", flush=True)
        print(
            f"RESPONSIVE_SIDEBAR_VISIBLE: {self.win.sidebar_box.get_visible()}",
            flush=True,
        )
        print(
            f"RESPONSIVE_COLUMNS: visible={visible} hidden={hidden}",
            flush=True,
        )
        print(
            f"RESPONSIVE_DROPDOWN_VISIBLE: {self.win.compact_page_dropdown.get_visible()}",
            flush=True,
        )
        self.win.set_default_size(900, 600)

        def resize_window() -> bool:
            subprocess.Popen(
                [
                    "hyprctl",
                    "dispatch",
                    'hl.dsp.window.resize({ x = 900, y = 600, window = "class:com.aditya.taskmgr" })',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            GLib.timeout_add(900, check)
            return False

        def check() -> bool:
            if self.win is None:
                return False
            width, height = self.win.get_width(), self.win.get_height()
            print(f"RESPONSIVE_RESIZED: {width}x{height}", flush=True)
            passed = width <= 950 and not self.win.sidebar_box.get_visible()
            print(
                "RESPONSIVE_TEST_PASS" if passed else "RESPONSIVE_TEST_FAIL",
                flush=True,
            )
            self.quit()
            return False

        GLib.timeout_add(400, resize_window)

    def _run_async_test(self) -> None:
        """Verify the background sampler populates the process table."""
        assert self.win is not None
        self.win._sync_sampling = False
        self.win._select_page("processes")
        self.win._refresh_all()

        def check() -> bool:
            if self.win is None:
                return False
            rows = len(self.win.proc_store)
            print(f"ASYNC_TEST_PROCESS_ROWS: {rows}", flush=True)
            print(
                "ASYNC_TEST_PASS" if rows > 0 else "ASYNC_TEST_FAIL",
                flush=True,
            )
            self.quit()
            return False

        GLib.timeout_add(1500, check)

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
        self.win._sync_sampling = True
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
                if pid == "services":
                    svc_rows = len(self.win.svc_store)
                    io_rows = sum(
                        1 for row in self.win.svc_store if row[9] != "-"
                    )
                    print(f"SMOKE_TEST_SERVICE_ROWS: {svc_rows}", flush=True)
                    print(
                        f"SMOKE_TEST_SERVICE_IO_ROWS: {io_rows}",
                        flush=True,
                    )
                    print(
                        "SMOKE_TEST_SERVICE_PRIV_BUTTON: "
                        f"{self.win.svc_privileged_btn.get_sensitive()}",
                        flush=True,
                    )
                    if svc_rows == 0:
                        print(
                            "SMOKE_TEST_FAIL: service table is empty",
                            flush=True,
                        )
                        self.quit()
                        return False
                if pid == "power":
                    print(
                        f"SMOKE_TEST_RAPL_LABEL: {self.win.rapl_lbl.get_text()}",
                        flush=True,
                    )
                    print(
                        "SMOKE_TEST_RAPL_PRIV_BUTTON: "
                        f"{self.win.rapl_privileged_btn.get_sensitive()}",
                        flush=True,
                    )
                if pid == "hardware":
                    print(
                        f"SMOKE_TEST_CAPABILITIES: {len(self.win.cap_store)}",
                        flush=True,
                    )
                    print(
                        f"SMOKE_TEST_STORAGE_HEALTH_ROWS: {len(self.win.smart_store)}",
                        flush=True,
                    )
                    print(
                        f"SMOKE_TEST_EBPF_PROBES: {len(PROBES)}",
                        flush=True,
                    )
                    print(
                        f"SMOKE_TEST_FAN_CONTROLS: {len(self.win.fan_devices)}",
                        flush=True,
                    )
                    print(
                        "SMOKE_TEST_FAN_APPLY_SENSITIVE: "
                        f"{self.win.fan_apply_btn.get_sensitive()}",
                        flush=True,
                    )
                    print(
                        "SMOKE_TEST_BATTERY_THRESHOLD_CONTROLS: "
                        f"{len(self.win.battery_devices)}",
                        flush=True,
                    )
                    print(
                        "SMOKE_TEST_BATTERY_APPLY_SENSITIVE: "
                        f"{self.win.battery_apply_btn.get_sensitive()}",
                        flush=True,
                    )
                    ebpf_info = self.win.ebpf_runner.detect()
                    priv = self.win.privileged_client
                    print(
                        "SMOKE_TEST_EBPF_GATE: "
                        f"can_run={ebpf_info['can_run']} "
                        f"root={ebpf_info['root']} btf={ebpf_info['btf']} "
                        f"bpftrace={bool(ebpf_info['bpftrace'])} "
                        f"pkexec_helper={priv.available}",
                        flush=True,
                    )
                    print(
                        "SMOKE_TEST_PRIVILEGED_HELPER: "
                        f"available={priv.available} "
                        f"installed={priv.installed_helper} "
                        f"pkexec={bool(priv.pkexec)} "
                        f"helper={priv.helper}",
                        flush=True,
                    )
                    print(
                        "SMOKE_TEST_EBPF_START_SENSITIVE: "
                        f"{self.win.ebpf_start_btn.get_sensitive()}",
                        flush=True,
                    )
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
                    self.win._switch_proc_mode("tree")
                    self.win._refresh_all()
                    tree_rows = len(self.win.proc_tree_store)
                    print(f"SMOKE_TEST_TREE_ROWS: {tree_rows}", flush=True)
                    if tree_rows == 0:
                        print(
                            "SMOKE_TEST_FAIL: process tree is empty",
                            flush=True,
                        )
                        self.quit()
                        return False
                    self.win._switch_proc_mode("flat")
                    self.win._refresh_all()
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
                print(
                    f"SMOKE_TEST_CONTEXT_VIEWS: {self.win._context_view_count}",
                    flush=True,
                )
                total_targets = (
                    self.win._context_view_count
                    + self.win._context_target_count
                )
                print(
                    f"SMOKE_TEST_CONTEXT_TARGETS: {total_targets}",
                    flush=True,
                )
                if self.win._context_view_count == 0:
                    print(
                        "SMOKE_TEST_FAIL: no table context menus were installed",
                        flush=True,
                    )
                self.win._show_context_menu(
                    self.win.proc_view,
                    20,
                    20,
                    "Smoke-test Details",
                    "echo smoke-test",
                )
                menu_open = self.win.context_menu.get_visible()
                self.win._hide_context_menu()
                menu_closed = not self.win.context_menu.get_visible()
                print(
                    f"SMOKE_TEST_CONTEXT_MENU: open={menu_open} closed={menu_closed}",
                    flush=True,
                )
                if not (menu_open and menu_closed):
                    print(
                        "SMOKE_TEST_FAIL: in-window context menu did not open/close",
                        flush=True,
                    )
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
        self.win._sync_sampling = True
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
    parser.add_argument(
        "--async-test",
        action="store_true",
        help="Verify the background sampler populates the process table without blocking",
    )
    parser.add_argument(
        "--responsive-test",
        action="store_true",
        help="Force compact mode, resize the window to 900x600, and verify it fits",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Write a JSON/Markdown/CSV diagnostic report and append a history snapshot",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Destination directory for --report (default: ~/.local/state/taskmgr/reports/<timestamp>)",
    )
    parser.add_argument(
        "--waybar-json",
        action="store_true",
        help="Print one Waybar custom-module JSON object and exit",
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

    if args.report:
        from backend.report import write_report

        paths = write_report(args.report_dir)
        print(json.dumps(paths, indent=2))
        return 0

    if args.waybar_json:
        from backend.performance import PerformanceCollector

        collector = PerformanceCollector()
        time.sleep(0.5)
        perf = collector.sample()
        battery = perf.get("battery", {})
        text = f"CPU {perf['cpu_total']:.0f}%  RAM {perf['mem'].percent:.0f}%"
        if battery.get("present"):
            text += f"  BAT {battery['percent']}%"
        tooltip = (
            f"CPU: {perf['cpu_total']:.1f}%\n"
            f"RAM: {perf['mem'].percent:.1f}%\n"
            f"GPU: {perf['gpu'].busy_pct:.1f}%\n"
            f"Network: ↓{perf['down_kbs']:.1f} ↑{perf['up_kbs']:.1f} KB/s\n"
            f"Disk: R {perf['read_mbs']:.2f} W {perf['write_mbs']:.2f} MB/s"
        )
        if battery.get("present"):
            tooltip += (
                f"\nBattery: {battery['percent']}% "
                f"({battery['watts']:.1f} W, {battery['remaining_str']})"
            )
        css_class = "normal"
        if perf["cpu_total"] >= 80 or perf["mem"].percent >= 90:
            css_class = "critical"
        elif perf["cpu_total"] >= 50 or perf["mem"].percent >= 75:
            css_class = "warning"
        print(json.dumps({"text": text, "tooltip": tooltip, "class": css_class}))
        return 0

    app = TaskManagerApp(
        initial_page=args.page,
        smoke_test=args.smoke_test,
        lifecycle_test=args.lifecycle_test,
        power_test=args.power_test,
        async_test=args.async_test,
        responsive_test=args.responsive_test,
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
