#!/usr/bin/env python3
"""Main GTK4 Window implementing the 9-Page Hyprland System Explorer & Task Manager."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from backend.alerts import AlertManager
from backend.capabilities import CapabilityCollector
from backend.doctor import SystemDoctor
from backend.ebpf import PROBES, PROBES_BY_LABEL, BpftraceRunner
from backend.gpu import GpuCollector
from backend.hardware import HardwareAndMediaCollector
from backend.hardware_controls import BatteryThresholdControl, FanControl
from backend.performance import PerformanceCollector
from backend.ports import PortsCollector
from backend.power import PowerAndWakeupCollector
from backend.power_profiles import PowerProfileController
from backend.privileged_client import PrivilegedClient
from backend.rapl import RaplCollector
from backend.processes import ProcessCollector
from backend.services import ServicesCollector
from backend.storage_health import StorageHealthCollector
from ui.widgets import (
    SparklineAreaChart,
    add_tree_columns,
    build_tree_view,
    hex_to_rgb,
)

THEME_JSON = (
    Path(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")))
    / "autotheme"
    / "theme.json"
)

DATA_SOURCES_TEXT = """HYPRLAND TASK MANAGER - DATA PROVENANCE
No live value is invented. Derived and estimated values are labeled as such
at the end of this document. Missing kernel data is shown as N/A or —, never
as a plausible zero.

CPU
  /proc/stat (aggregate + per-CPU counters, ctxt, intr, procs_running)
  /proc/cpuinfo and /sys/devices/system/cpu/cpu*/cpufreq/ (MHz)
  /sys/class/hwmon/*/temp*_input (coretemp package/core temperatures)
  psutil.cpu_percent/cpu_times/cpu_freq (deltas over the sample interval)

MEMORY / SWAP
  /proc/meminfo (MemTotal, MemAvailable, Cached, Dirty, Slab, Zswap)
  /proc/swaps (per-device swap size/used/priority)
  psutil.virtual_memory() and psutil.swap_memory()

DISK / STORAGE
  /proc/diskstats via psutil.disk_io_counters() (read/write bytes, IOPS)
  lsblk -J (partitions, filesystems, mountpoints, FSUSED, FSUSE%)
  /sys/class/hwmon/*/temp*_input (NVMe composite/sensor temperatures)
  /proc/mounts (gocryptfs vault mount state)

NETWORK
  /proc/net/dev via psutil.net_io_counters(pernic=True) for the active
      default-route interface (RX/TX bytes, errors, drops)
  /proc/net/route (default interface and gateway)
  /etc/resolv.conf (DNS servers)
  nmcli -t -f ACTIVE,SSID,SIGNAL,RATE dev wifi (Wi-Fi SSID/signal/rate)
  psutil.net_if_addrs() (local IPv4 address)

BATTERY / POWER
  /sys/class/power_supply/BAT*/{capacity,status,power_now,voltage_now,
      energy_now,energy_full,energy_full_design,cycle_count}
  upower -i /org/freedesktop/UPower/devices/battery_BAT* (energy-rate when
      the HP ACPI EC does not expose power_now)
  /sys/class/power_supply/ucsi*/ (USB-C PD voltage/current)
  /sys/firmware/acpi/platform_profile (ACPI platform profile; separate from power-profiles-daemon)

GPU (Intel i915 / xe, AMD amdgpu)
  /sys/class/drm/card*/device/{vendor,device,driver}
  /sys/class/drm/card*/gt_act_freq_mhz, gt_max_freq_mhz (live/max MHz)
  /proc/<pid>/fdinfo/<fd> drm-engine-* (per-engine busy nanoseconds)
  /proc/<pid>/fdinfo/<fd> drm-total-*/drm-resident-* (client GPU memory)
  /sys/class/drm/card*/gt/gt0/rc6_residency_ms (deep-idle residency)
  /sys/class/drm/card*/device/hwmon/*/temp1_input (GPU temperature)
  Per-process GPU % is the busiest visible engine (3D, Copy, Video,
  etc.), capped at 100%; it is not a sum across engines.

PROCESSES
  /proc/<pid>/{stat,status,io,cgroup,cmdline,comm} via psutil
  /proc/<pid>/task/<tid>/{comm,stat} (thread name, state, CPU time, core)
  /proc/<pid>/fd/* (open files, pipes, device nodes)
  /proc/<pid>/environ (environment variables; secrets redacted by name)
  psutil.Process.cpu_percent() (interval delta), memory_info().rss

PORTS / NETWORK CONNECTIONS
  psutil.net_connections(kind="inet") (kernel socket table)
  /proc/<pid>/cgroup (systemd unit for the owning process)
  systemctl show --property=Id,MainPID,ExecMainPID (PID -> unit mapping)
  Unprivileged users cannot see the inode/PID of root-owned sockets; those
  rows explicitly say "(owner hidden)" instead of guessing.

SERVICES / TIMERS / AUTOSTART
  systemctl list-units --type=service --all --output=json
  systemctl list-timers --all --output=json
  ~/.config/systemd/user/*.timer (disabled user timers included)
  ~/.config/hypr/hyprland.lua hl.exec_cmd("...") entries (parsed literally)
  psutil process scan (live PID/RAM matched to each autostart target)
  hyprctl -j clients (open windows)

POWER DIAGNOSTICS
  /proc/interrupts (per-IRQ cumulative counters; rates are deltas)
  /sys/devices/system/cpu/cpu*/cpuidle/state*/{name,time} (C-state time)
  /proc/sys/kernel/nmi_watchdog
  /proc/sys/vm/dirty_writeback_centisecs
  /sys/module/snd_hda_intel/parameters/power_save
  /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference
  /sys/bus/pci/devices/*/power/control (runtime PM policy)

AUDIO / CAMERA / BLUETOOTH
  wpctl status (PipeWire sinks, sources, active links, volumes)
  /sys/class/video4linux/video* (camera name)
  /proc/<pid>/fd/* -> /dev/video* (which process currently captures)
  rfkill -J (soft/hard block state)

HARDWARE / SENSORS / MODULES / LOGS
  /sys/bus/pci/devices/*/{vendor,device,driver,power/runtime_status}
  /usr/share/hwdata/pci.ids (device names; no lspci wakeups)
  lsusb (USB peripheral inventory)
  /sys/class/hwmon/* (temperatures, fan RPM, voltages)
  /proc/modules (loaded kernel modules, size, refcount, dependencies)
  journalctl -b -p 0..3 / -k (boot errors and kernel/ACPI warnings)
  coredumpctl list (application crash history)
  Hyprland session log (hyprland.log for the live instance)

DERIVED / ESTIMATED VALUES
  The "Battery Impact (Est.)" column is a transparent heuristic built ONLY
  from measured counters: CPU %, GPU %, context switches/sec, and disk I/O.
  It is labeled "(Est.)" and is not presented as a wattage measurement.
  Remaining battery time is computed from energy_now / energy-rate, or is
  taken directly from UPower when available.
"""

PAGES_SPEC = [
    ("doctor", "🩺  1. System Doctor"),
    ("performance", "📊  2. Performance"),
    ("processes", "⚙️  3. Processes & Threads"),
    ("ports", "🌐  4. Ports & Network"),
    ("services", "🔧  5. Services & Startup"),
    ("power", "⚡  6. Power & Tunables"),
    ("audio", "🔊  7. Audio, Camera & BT"),
    ("hardware", "🔌  8. Hardware & Sensors"),
    ("logs", "📜  9. Logs & Crashes"),
]

COMPACT_WIDTH = 1150
COMPACT_TITLES: dict[str, set[str]] = {
    "process": {"PID", "Process", "CPU %", "Memory", "State"},
    "thread": {
        "Thread ID (TID)",
        "Thread Name (/proc/task/comm)",
        "State",
        "Thread CPU %",
    },
    "port": {"Proto", "Port", "Local Address", "State", "Process"},
    "service": {"Systemd Unit", "Scope", "Active", "Memory", "CPU Time"},
    "timer": {"Timer Unit", "State", "Next Elapse"},
    "autostart": {
        "hyprland.lua Autostart Command",
        "Target Daemon",
        "Live Status",
    },
    "window": {"Workspace", "Window Class", "Window Title"},
    "doctor": {"State", "Subsystem", "Component", "Live Finding"},
    "irq": {"IRQ #", "Interrupts / sec", "Hardware / Driver Subsystem"},
    "tunable": {"State", "Power Tunable", "Current"},
    "audio": {"Type", "ID", "Device / Stream / Radio Name", "Volume / State"},
    "pci": {"PCI Slot", "Hardware Device Name (pci.ids)", "Bound Kernel Driver"},
    "usb": {"USB Bus / Device", "Connected USB Peripheral"},
    "sensor": {"Sensor Chip (hwmon)", "Channel / Zone", "Live Reading"},
    "smart": {"Device", "SMART Health", "Temperature"},
    "block": {"Device / Partition", "Size", "Mountpoint / Model"},
    "module": {"Kernel Module", "Memory Size"},
    "log": {"Timestamp", "Severity", "Message"},
    "ebpf": {"Time", "Probe", "Event"},
    "capability": {"Feature", "Status"},
    "generic": set(),
}

PROCESS_COLUMNS = [
    ("PID", 0, 0, 68),
    ("Process", 2, 2, 195),
    ("CPU %", 5, 4, 72),
    ("GPU %", 7, 6, 72),
    ("Memory", 9, 8, 120),
    ("Disk I/O", 11, 10, 88),
    ("Ctx Sw/s", 13, 12, 85),
    ("Impact (Est.)", 15, 14, 120),
    ("Threads", 16, 16, 68),
    ("State", 17, 17, 65),
    ("Listen Ports", 18, 18, 115),
    ("Unit", 19, 19, 145),
    ("User", 3, 3, 75),
    ("Command", 20, 20, 260),
]
PROCESS_TYPES = (
    int,
    int,
    str,
    str,
    float,
    str,
    float,
    str,
    float,
    str,
    float,
    str,
    float,
    str,
    float,
    str,
    int,
    str,
    str,
    str,
    str,
)


class TaskManagerWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, initial_page: str = "processes") -> None:
        super().__init__(
            application=app, title="Hyprland Task Manager & System Explorer"
        )
        self.set_default_size(1150, 660)

        # Backends
        self.gpu_collector = GpuCollector()
        self.perf_collector = PerformanceCollector(gpu_collector=self.gpu_collector)
        self.proc_collector = ProcessCollector(gpu_collector=self.gpu_collector)
        self.ports_collector = PortsCollector()
        self.power_collector = PowerAndWakeupCollector()
        self.rapl_collector = RaplCollector()
        self.alerts = AlertManager()
        self.ebpf_runner = BpftraceRunner()
        self._ebpf_probe_commands: dict[str, str] = {}
        self._svc_io_sources: dict[tuple[str, str], str] = {}
        self._svc_control_groups: dict[tuple[str, str], str] = {}
        self.privileged_client = PrivilegedClient()
        self._privileged_rapl_text: str | None = None
        self._privileged_rapl_ts = 0.0
        self.fan_control = FanControl()
        self.battery_control = BatteryThresholdControl()
        self.fan_devices: list[dict] = []
        self.battery_devices: list[dict] = []

        # State
        self._theme_mtime = 0.0
        self._accent_rgb = (0.82, 0.61, 0.38)
        self._bg_rgb = (0.10, 0.09, 0.09)
        self._refresh_interval_ms = 1000
        self._timer_id: int | None = None
        self._doctor_timer_id: int | None = None
        self._mapped_once = False
        self._compact_mode = False
        self._updating_compact = False
        self._context_views: list[tuple[Gtk.TreeView, str]] = []
        self._context_target_count = 0
        self._context_details = ""
        self._context_command = ""
        self._auto_compact_checked = False

        self._proc_iters: dict[int, Gtk.TreeIter] = {}
        self._proc_mode = "flat"  # "flat" | "grouped" | "tree"
        self._hide_kthreads = True
        self._selected_pid: int | None = None
        self._selected_group_pids: list[int] = []
        self._group_pids_map: dict[int, list[int]] = {}

        self._proc_query = ""
        self._port_query = ""
        self._port_listen_only = False
        self._svc_query = ""
        self._hw_mod_query = ""
        self._log_query = ""
        self._log_mode = "errors"
        self._last_tunables: list[dict] = []
        self._last_profile_ts = 0.0
        self.profile_buttons: dict[str, Gtk.Button] = {}
        self._io_worker_busy = False
        self._sync_sampling = False
        self.auto_power_enabled = False
        self._auto_power_target: str | None = None
        self._layout_path = (
            Path(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")))
            / "taskmgr"
            / "layout.json"
        )
        self._column_visibility: dict[str, dict[str, bool]] = {}
        self._column_widths: dict[str, dict[str, int]] = {}
        self._tree_collapsed: set[int] = set()
        self._tree_iters: dict[int, Gtk.TreeIter] = {}
        self._restoring_tree = False
        self._load_layout()
        self.proc_columns: dict[str, Gtk.TreeViewColumn] = {}
        self.proc_tree_columns: dict[str, Gtk.TreeViewColumn] = {}

        self._load_autotheme()
        self._build_layout()
        self._setup_shortcuts()

        # Initial data population. Select the target page BEFORE the first
        # refresh so the process page is populated on the very first frame.
        self._refresh_doctor()
        self._select_page(initial_page)
        self._sync_sampling = True
        self._refresh_all()
        self._sync_sampling = False
        self._reset_timer(self._refresh_interval_ms)
        self._doctor_timer_id = GLib.timeout_add_seconds(30, self._on_doctor_tick)
        self.connect("destroy", self._on_destroy)
        self.connect("map", self._on_map)

    # ---------------- AUTOTHEME CSS ----------------
    def _load_autotheme(self) -> None:
        try:
            st = THEME_JSON.stat()
            if st.st_mtime != self._theme_mtime:
                self._theme_mtime = st.st_mtime
                data = json.loads(THEME_JSON.read_text(encoding="utf-8"))
                self._accent_rgb = hex_to_rgb(data.get("accent", "#d19b61"))
                self._bg_rgb = hex_to_rgb(
                    data.get("surface", "#1c1814"), (0.11, 0.10, 0.10)
                )
        except OSError:
            pass

        css = b"""
        .tm-topbar {
            background-color: @surface_color;
            border-bottom: 1px solid @border_color;
            padding: 6px 12px;
        }
        .tm-sidebar {
            background-color: @surface_color;
            border-right: 1px solid @border_color;
            padding: 6px;
        }
        .tm-sidebar row {
            border-radius: 8px;
            padding: 8px 10px;
            margin: 2px 0;
            font-weight: 600;
        }
        .tm-sidebar row:selected {
            background-color: @accent_color;
            color: @accent_fg_color;
        }
        .tm-context-menu {
            background-color: @theme_bg_color;
            border: 1px solid @borders;
            border-radius: 8px;
            padding: 6px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
        }
        .tm-context-menu button {
            min-width: 132px;
        }
        .tm-pill {
            background-color: @bg_color;
            border: 1px solid @border_color;
            border-radius: 8px;
            padding: 4px 10px;
            font-weight: 700;
            font-size: 11px;
        }
        .tm-pill-ok {
            background-color: @bg_color;
            border: 1px solid #8bc18b;
            color: #8bc18b;
            border-radius: 8px;
            padding: 4px 9px;
            font-weight: 700;
        }
        .tm-pill-warn {
            background-color: @bg_color;
            border: 1px solid @warning_color;
            color: @warning_color;
            border-radius: 8px;
            padding: 4px 9px;
            font-weight: 700;
        }
        .tm-pill-err {
            background-color: @bg_color;
            border: 1px solid @error_color;
            color: @error_color;
            border-radius: 8px;
            padding: 4px 9px;
            font-weight: 700;
        }
        .tm-card {
            background-color: @surface_color;
            border: 1px solid @border_color;
            border-radius: 10px;
            padding: 10px 12px;
        }
        .tm-source-text {
            font-family: "JetBrains Mono", "Adwaita Mono", monospace;
            font-size: 10px;
        }
        .tm-inspector {
            background-color: @surface_color;
            border-top: 1px solid @border_color;
            padding: 6px 10px;
        }
        button.tm-action-btn {
            background-image: none;
            background-color: @accent_color;
            color: @accent_fg_color;
            font-weight: 700;
            border-radius: 6px;
            padding: 4px 10px;
        }
        button.tm-danger-btn {
            background-image: none;
            background-color: @error_color;
            color: #111111;
            font-weight: 700;
            border-radius: 6px;
            padding: 4px 10px;
        }
        button.tm-secondary-btn {
            background-image: none;
            background-color: @bg_color;
            color: @fg_color;
            border: 1px solid @border_color;
            font-weight: 600;
            border-radius: 6px;
            padding: 4px 10px;
        }
        button.tm-secondary-btn.tm-profile-active {
            background-image: none;
            background-color: @accent_color;
            color: @accent_fg_color;
            border: 1px solid @accent_color;
            font-weight: 700;
            border-radius: 6px;
            padding: 4px 10px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _setup_shortcuts(self) -> None:
        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(ctrl)

        # Escape must close the window even when a search entry has focus.
        # A capture-phase controller sees the key before the focused child.
        esc = Gtk.EventControllerKey()
        esc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        esc.connect("key-pressed", self._on_capture_key)
        self.add_controller(esc)

    def _on_capture_key(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            if self.context_menu.get_visible():
                self._hide_context_menu()
                return True
            self.close()
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval in (
            Gdk.KEY_r,
            Gdk.KEY_R,
        ):
            self._refresh_current_page()
            self._set_status("Refreshed current page (Ctrl+R).")
            return True
        return False

    def _on_map(self, _widget: Gtk.Widget) -> None:
        if not self._mapped_once:
            self._mapped_once = True
            self._refresh_all()

    def _on_doctor_tick(self) -> bool:
        if self._doctor_timer_id is None:
            return False
        self._refresh_doctor()
        return True

    def _on_destroy(self, _widget: Gtk.Widget) -> None:
        self.ebpf_runner.stop()
        self._save_layout()
        if self._doctor_timer_id is not None:
            GLib.source_remove(self._doctor_timer_id)
            self._doctor_timer_id = None
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _load_layout(self) -> None:
        try:
            data = json.loads(self._layout_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                vis = data.get("visibility", {})
                widths = data.get("widths", {})
                if isinstance(vis, dict):
                    self._column_visibility = {
                        str(k): {str(t): bool(v) for t, v in values.items()}
                        for k, values in vis.items()
                        if isinstance(values, dict)
                    }
                if isinstance(widths, dict):
                    self._column_widths = {
                        str(k): {str(t): int(v) for t, v in values.items()}
                        for k, values in widths.items()
                        if isinstance(values, dict)
                    }
                collapsed = data.get("tree_collapsed", [])
                if isinstance(collapsed, list):
                    self._tree_collapsed = {
                        int(v) for v in collapsed if str(v).isdigit()
                    }
        except (OSError, ValueError, TypeError):
            pass

    def _save_layout(self) -> None:
        if not self.proc_columns:
            return
        visibility = dict(self._column_visibility.get("process", {}))
        for title in self.proc_columns:
            visibility.setdefault(title, True)
        widths = {
            title: int(column.get_width())
            for title, column in self.proc_columns.items()
            if column.get_width() > 0
        }
        self._column_visibility["process"] = visibility
        self._column_widths["process"] = widths
        try:
            self._layout_path.parent.mkdir(parents=True, exist_ok=True)
            self._layout_path.write_text(
                json.dumps(
                    {
                        "visibility": self._column_visibility,
                        "widths": self._column_widths,
                        "tree_collapsed": sorted(self._tree_collapsed),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _apply_saved_process_layout(self) -> None:
        visible = self._column_visibility.get("process", {})
        widths = self._column_widths.get("process", {})
        for columns in (self.proc_columns, self.proc_tree_columns):
            for title, column in columns.items():
                if title in visible:
                    column.set_visible(visible[title])
                if title in widths:
                    column.set_fixed_width(max(40, widths[title]))

    def _open_columns_dialog(self, _btn: Gtk.Button) -> None:
        win = Gtk.Window(
            transient_for=self,
            modal=True,
            title="Process Columns",
        )
        win.set_default_size(420, 520)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)

        title = Gtk.Label(
            label="Choose visible columns. Layout is saved in ~/.config/taskmgr/layout.json.",
            xalign=0.0,
        )
        title.set_wrap(True)
        box.append(title)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for col_title, column in self.proc_columns.items():
            check = Gtk.CheckButton(label=col_title)
            check.set_active(column.get_visible())
            check.connect(
                "toggled",
                lambda c, t=col_title, col=column: self._on_column_toggled(
                    t, col, c.get_active()
                ),
            )
            list_box.append(check)
        scroller.set_child(list_box)
        box.append(scroller)

        close = Gtk.Button(label="Close")
        close.add_css_class("tm-secondary-btn")
        close.connect("clicked", lambda _: win.close())
        box.append(close)
        win.set_child(box)
        win.present()

    def _on_column_toggled(
        self, title: str, column: Gtk.TreeViewColumn, active: bool
    ) -> None:
        column.set_visible(active)
        other = self.proc_tree_columns.get(title)
        if other is not None:
            other.set_visible(active)
        self._column_visibility.setdefault("process", {})[title] = active
        self._save_layout()

    def _on_key_pressed(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            if self.context_menu.get_visible():
                self._hide_context_menu()
                return True
            self.close()
            return True
        if keyval == Gdk.KEY_F5:
            self._refresh_current_page()
            self._set_status("Refreshed current page (F5).")
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval in (
            Gdk.KEY_r,
            Gdk.KEY_R,
        ):
            self._refresh_current_page()
            self._set_status("Refreshed current page (Ctrl+R).")
            return True
        if (
            keyval == Gdk.KEY_Delete
            and self.stack.get_visible_child_name() == "processes"
        ):
            focus = self.get_focus()
            if focus is not None and hasattr(focus, "get_text"):
                # Let the search entry consume Delete while the user is typing.
                return False
            self._signal_selected(signal.SIGTERM)
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval == Gdk.KEY_f:
            self._select_page("processes")
            self.proc_search.grab_focus()
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval == Gdk.KEY_q:
            self.close()
            return True
        return False

    def _reset_timer(self, interval_ms: int) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        self._refresh_interval_ms = interval_ms
        if interval_ms > 0:
            self._timer_id = GLib.timeout_add(interval_ms, self._on_tick)

    def _set_status(self, msg: str) -> None:
        self.status_banner.set_text(msg)
        if hasattr(self, "compact_status_lbl"):
            self.compact_status_lbl.set_text(msg)

    def _show_data_sources(self, _btn: Gtk.Button) -> None:
        win = Gtk.Window(
            transient_for=self,
            modal=True,
            title="Data Sources & Provenance",
        )
        win.set_default_size(820, 680)

        esc = Gtk.EventControllerKey()
        esc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        esc.connect(
            "key-pressed",
            lambda _c, k, _kc, _s: (
                (win.close(), True)[1] if k == Gdk.KEY_Escape else False
            ),
        )
        win.add_controller(esc)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(10)
        box.set_margin_end(10)

        title = Gtk.Label(
            label="Every value is read live from the kernel or the owning service. "
            "Derived values are labeled as estimates.",
            xalign=0.0,
        )
        title.set_wrap(True)
        box.append(title)

        label = Gtk.Label(label=DATA_SOURCES_TEXT, xalign=0.0, yalign=0.0)
        label.set_selectable(True)
        label.set_wrap(True)
        label.add_css_class("tm-source-text")
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(label)
        box.append(scroll)

        close = Gtk.Button(label="Close")
        close.add_css_class("tm-secondary-btn")
        close.connect("clicked", lambda _: win.close())
        box.append(close)

        win.set_child(box)
        win.present()

    # ---------------- MASTER LAYOUT ----------------
    def _build_layout(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(outer)
        self.set_child(self.overlay)

        # In-window right-click menu. A Gtk.Popover would create a second
        # Wayland surface and can trigger GTK frame-timing / CSS-node warnings;
        # this menu lives in the same surface as the main window.
        self.context_fixed = Gtk.Fixed()
        self.context_fixed.set_hexpand(True)
        self.context_fixed.set_vexpand(True)
        self.context_fixed.set_can_target(False)
        self.overlay.add_overlay(self.context_fixed)

        self.context_menu = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4
        )
        self.context_menu.add_css_class("tm-context-menu")
        self.context_menu.set_visible(False)
        self.context_details_btn = Gtk.Button(label="Details")
        self.context_details_btn.add_css_class("tm-secondary-btn")
        self.context_details_btn.connect(
            "clicked", self._on_context_details_clicked
        )
        self.context_command_btn = Gtk.Button(label="Command")
        self.context_command_btn.add_css_class("tm-secondary-btn")
        self.context_command_btn.connect(
            "clicked", self._on_context_command_clicked
        )
        self.context_menu.append(self.context_details_btn)
        self.context_menu.append(self.context_command_btn)
        self.context_fixed.put(self.context_menu, 0, 0)

        dismiss = Gtk.GestureClick()
        dismiss.set_button(0)
        dismiss.connect("pressed", self._on_context_backdrop_pressed)
        self.context_fixed.add_controller(dismiss)

        # 1. Top At-a-Glance Health Bar. A FlowBox wraps the pills and
        # controls instead of forcing the window wider than the monitor.
        topbar = Gtk.FlowBox()
        topbar.set_selection_mode(Gtk.SelectionMode.NONE)
        topbar.set_max_children_per_line(6)
        topbar.set_row_spacing(4)
        topbar.set_column_spacing(6)
        topbar.set_homogeneous(False)
        topbar.add_css_class("tm-topbar")

        self.compact_page_dropdown = Gtk.DropDown.new_from_strings(
            [page[1] for page in PAGES_SPEC]
        )
        self.compact_page_dropdown.set_visible(False)
        self.compact_page_dropdown.connect(
            "notify::selected", self._on_compact_page_selected
        )
        topbar.append(self.compact_page_dropdown)

        self.compact_sources_btn = Gtk.Button(label="ℹ️ Data Sources")
        self.compact_sources_btn.add_css_class("tm-secondary-btn")
        self.compact_sources_btn.set_visible(False)
        self.compact_sources_btn.connect("clicked", self._show_data_sources)
        topbar.append(self.compact_sources_btn)

        self.compact_status_lbl = Gtk.Label(label="", xalign=0.0)
        self.compact_status_lbl.set_visible(False)
        self.compact_status_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        topbar.append(self.compact_status_lbl)

        self.compact_toggle = Gtk.ToggleButton(label="Compact")
        self.compact_toggle.add_css_class("tm-secondary-btn")
        self.compact_toggle.connect("toggled", self._on_compact_toggle)
        topbar.append(self.compact_toggle)

        self.btn_doc_ok = Gtk.Button(label="✅ -- Working")
        self.btn_doc_ok.add_css_class("tm-pill-ok")
        self.btn_doc_ok.connect("clicked", lambda _: self._select_page("doctor"))
        topbar.append(self.btn_doc_ok)

        self.btn_doc_warn = Gtk.Button(label="⚠️ -- Warnings")
        self.btn_doc_warn.add_css_class("tm-pill-warn")
        self.btn_doc_warn.connect("clicked", lambda _: self._select_page("doctor"))
        topbar.append(self.btn_doc_warn)

        self.btn_doc_err = Gtk.Button(label="❌ -- Failing")
        self.btn_doc_err.add_css_class("tm-pill-err")
        self.btn_doc_err.connect("clicked", lambda _: self._select_page("doctor"))
        topbar.append(self.btn_doc_err)

        for button, label in (
            (self.btn_doc_ok, "Working"),
            (self.btn_doc_warn, "Warnings"),
            (self.btn_doc_err, "Failing"),
        ):
            self._attach_widget_context(
                button,
                f"System Doctor summary count for {label} checks. Clicking the "
                "button opens the Doctor page with the full finding and fix.",
                "taskmgr --doctor-json | jq 'group_by(.status) | "
                "map({status: .[0].status, count: length})'",
            )

        self.pill_cpu = Gtk.Label(label="CPU: --")
        self.pill_cpu.add_css_class("tm-pill")
        topbar.append(self.pill_cpu)

        self.pill_gpu = Gtk.Label(label="GPU: --")
        self.pill_gpu.add_css_class("tm-pill")
        topbar.append(self.pill_gpu)

        self.pill_ram = Gtk.Label(label="RAM: --")
        self.pill_ram.add_css_class("tm-pill")
        topbar.append(self.pill_ram)

        self.pill_io = Gtk.Label(label="I/O: --")
        self.pill_io.add_css_class("tm-pill")
        topbar.append(self.pill_io)

        self.pill_bat = Gtk.Label(label="BAT: --")
        self.pill_bat.add_css_class("tm-pill")
        topbar.append(self.pill_bat)

        for pill, details, command in (
            (
                self.pill_cpu,
                "Current total CPU load, average clock and package temperature.",
                "top",
            ),
            (
                self.pill_gpu,
                "Visible DRM client GPU utilization, clock and client count.",
                "intel_gpu_top",
            ),
            (
                self.pill_ram,
                "Current used/total physical memory and percentage.",
                "free -h",
            ),
            (
                self.pill_io,
                "Current active-interface network throughput and aggregate disk throughput.",
                "vmstat 1",
            ),
            (
                self.pill_bat,
                "Battery capacity, live power and remaining time from UPower.",
                'upower -i "$(upower -e | grep -m1 battery)"',
            ),
        ):
            self._attach_widget_context(pill, details, command)

        for lbl, ms in (("0.5s", 500), ("1s", 1000), ("2s", 2000), ("Pause", 0)):
            b = Gtk.Button(label=lbl)
            b.add_css_class("tm-secondary-btn")
            b.connect(
                "clicked",
                lambda _, m=ms, l=lbl: (
                    self._reset_timer(m),
                    self._set_status(f"Refresh interval: {l}"),
                ),
            )
            topbar.append(b)

        outer.append(topbar)

        # 2. Main Horizontal Split: Left Sidebar + Right Stack
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        body.set_vexpand(True)

        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar_box.add_css_class("tm-sidebar")
        sidebar_box.set_size_request(190, -1)
        self.sidebar_box = sidebar_box

        self.sidebar_list = Gtk.ListBox()
        self.sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._page_rows: dict[str, Gtk.ListBoxRow] = {}
        for page_id, page_title in PAGES_SPEC:
            row = Gtk.ListBoxRow()
            row._page_id = page_id  # type: ignore[attr-defined]
            lbl = Gtk.Label(label=page_title, xalign=0.0)
            row.set_child(lbl)
            self.sidebar_list.append(row)
            self._page_rows[page_id] = row
            self._attach_widget_context(
                row,
                f"This sidebar entry opens {page_title}. It shows only data "
                "collected from /proc, /sys, kernel commands, or a system service.",
                f"taskmgr --page {page_id}",
            )

        self.sidebar_list.connect("row-selected", self._on_sidebar_row_selected)
        sidebar_box.append(self.sidebar_list)

        side_spacer = Gtk.Box()
        side_spacer.set_vexpand(True)
        sidebar_box.append(side_spacer)

        btn_sources = Gtk.Button(label="ℹ️ Data Sources")
        btn_sources.add_css_class("tm-secondary-btn")
        btn_sources.connect("clicked", self._show_data_sources)
        sidebar_box.append(btn_sources)

        self.status_banner = Gtk.Label(
            label="Ready (F5 / Ctrl+R refresh, Ctrl+F search)", xalign=0.0
        )
        self.status_banner.set_wrap(True)
        self.status_banner.set_margin_start(6)
        self.status_banner.set_margin_bottom(4)
        sidebar_box.append(self.status_banner)

        body.append(sidebar_box)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        body.append(self.stack)

        outer.append(body)

        # Build all 9 pages
        self._build_page_doctor()
        self._build_page_performance()
        self._build_page_processes()
        self._build_page_ports()
        self._build_page_services()
        self._build_page_power()
        self._build_page_audio()
        self._build_page_hardware()
        self._build_page_logs()
        self._install_context_menus()
        self._maybe_auto_compact()

    def _select_page(self, page_id: str) -> None:
        row = self._page_rows.get(page_id) or self._page_rows["processes"]
        self.sidebar_list.select_row(row)
        self.stack.set_visible_child_name(row._page_id)  # type: ignore[attr-defined]
        if row._page_id in ("services", "power", "hardware"):
            self._refresh_privileged_controls()
        if row._page_id == "hardware" and hasattr(self, "ebpf_runner"):
            self._refresh_ebpf_status()
            self._refresh_hardware_controls()
        try:
            index = [p[0] for p in PAGES_SPEC].index(row._page_id)  # type: ignore[attr-defined]
            self._updating_compact = True
            self.compact_page_dropdown.set_selected(index)
            self._updating_compact = False
        except (ValueError, AttributeError):
            pass

    def _on_compact_page_selected(self, dropdown: Gtk.DropDown, _pspec) -> None:
        if self._updating_compact:
            return
        index = dropdown.get_selected()
        if 0 <= index < len(PAGES_SPEC):
            self._select_page(PAGES_SPEC[index][0])

    def _on_compact_toggle(self, button: Gtk.ToggleButton) -> None:
        if self._updating_compact:
            return
        self._apply_compact_mode(button.get_active())

    def _monitor_logical_size(self) -> tuple[float, float]:
        try:
            out = subprocess.check_output(
                ["hyprctl", "-j", "monitors"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.5,
            )
            monitors = json.loads(out)
            monitor = next(
                (m for m in monitors if m.get("focused")),
                monitors[0] if monitors else None,
            )
            if monitor:
                scale = float(monitor["scale"] or 1.0)
                return (
                    float(monitor["width"]) / scale,
                    float(monitor["height"]) / scale,
                )
        except Exception:
            pass
        return float(self.get_width() or 1280), float(self.get_height() or 720)

    def _monitor_logical_width(self) -> float:
        return self._monitor_logical_size()[0]

    def _apply_compact_mode(self, compact: bool) -> None:
        self._compact_mode = compact
        if self.sidebar_box is not None:
            self.sidebar_box.set_visible(not compact)
        self.compact_page_dropdown.set_visible(compact)
        self.compact_sources_btn.set_visible(compact)
        self.compact_status_lbl.set_visible(compact)
        self.compact_toggle.set_label("Full" if compact else "Compact")
        self._updating_compact = True
        self.compact_toggle.set_active(compact)
        self._updating_compact = False

        for view, kind in self._context_views:
            allowed = COMPACT_TITLES.get(kind, set())
            saved = self._column_visibility.get(kind, {})
            for column in view.get_columns():
                title = column.get_title() or ""
                if compact:
                    visible = (not allowed) or title in allowed
                else:
                    visible = saved.get(title, True)
                column.set_visible(visible)
        self._set_notebook_scrollable(self, compact)

    def _set_notebook_scrollable(self, widget: Gtk.Widget, _compact: bool) -> None:
        # Tab bars are always scrollable: tab labels must never force the
        # window wider than the tables or the monitor.
        if isinstance(widget, Gtk.Notebook):
            widget.set_scrollable(True)
        child = widget.get_first_child()
        while child is not None:
            self._set_notebook_scrollable(child, _compact)
            child = child.get_next_sibling()

    def _maybe_auto_compact(self) -> None:
        if self._auto_compact_checked:
            return
        self._auto_compact_checked = True
        logical_w, logical_h = self._monitor_logical_size()
        compact = logical_w < COMPACT_WIDTH
        self._apply_compact_mode(compact)
        if compact:
            width = max(860, min(900, int(logical_w) - 40))
            height = max(520, min(600, int(logical_h) - 80))
            self.set_default_size(width, height)

    def _on_sidebar_row_selected(
        self, _box: Gtk.ListBox, row: Gtk.ListBoxRow | None
    ) -> None:
        if row is not None:
            page_id = getattr(row, "_page_id", "processes")
            self.stack.set_visible_child_name(page_id)
            # Populate the newly visible page immediately instead of waiting
            # for the next timer tick.
            GLib.idle_add(self._on_page_activated, page_id)

    def _on_page_activated(self, page_id: str) -> bool:
        if self.stack.get_visible_child_name() != page_id:
            return False
        if page_id == "doctor":
            self._refresh_doctor()
        elif page_id == "hardware":
            self._refresh_hardware_static()
        elif page_id == "logs":
            self._refresh_logs()
        self._refresh_all()
        return False

    # =========================================================================
    # PAGE 1: SYSTEM DOCTOR ("WORKING VS. NOT WORKING")
    # =========================================================================
    def _build_page_doctor(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)

        bar = Gtk.FlowBox()
        bar.set_selection_mode(Gtk.SelectionMode.NONE)
        bar.set_max_children_per_line(3)
        bar.set_row_spacing(4)
        bar.set_column_spacing(8)
        bar.set_homogeneous(False)
        title = Gtk.Label(
            label="🩺 Full PC & Dotfiles Diagnostic Audit (Working vs. Not Working)",
            xalign=0.0,
        )
        bar.append(title)

        btn_rescan = Gtk.Button(label="Re-Run Full Audit")
        btn_rescan.add_css_class("tm-secondary-btn")
        btn_rescan.connect("clicked", lambda _: self._refresh_doctor())
        bar.append(btn_rescan)

        btn_fix = Gtk.Button(label="Execute Fix for Selected Row")
        btn_fix.add_css_class("tm-action-btn")
        btn_fix.connect("clicked", self._on_doctor_execute_fix)
        bar.append(btn_fix)

        btn_tune = Gtk.Button(label="Optimize All Kernel Power Tunables")
        btn_tune.add_css_class("tm-action-btn")
        btn_tune.connect("clicked", lambda _: self._run_doctor_fix_id("tune_all_power"))
        bar.append(btn_tune)

        btn_report = Gtk.Button(label="Export Diagnostic Report")
        btn_report.add_css_class("tm-secondary-btn")
        btn_report.connect("clicked", self._export_report)
        bar.append(btn_report)

        self.alerts_btn = Gtk.ToggleButton(
            label="Alerts: On" if self.alerts.enabled else "Alerts: Off"
        )
        self.alerts_btn.set_active(self.alerts.enabled)
        self.alerts_btn.add_css_class("tm-secondary-btn")
        self.alerts_btn.connect("toggled", self._on_alerts_toggled)
        bar.append(self.alerts_btn)

        box.append(bar)

        # 0:Status, 1:Category, 2:Component, 3:Summary, 4:Details, 5:FixActionLabel, 6:FixID
        self.doc_store = Gtk.ListStore(str, str, str, str, str, str, str)
        self.doc_view, _, _, doc_scroll = build_tree_view(
            self.doc_store,
            [
                ("State", 0, 0, 110),
                ("Subsystem", 1, 1, 155),
                ("Component", 2, 2, 210),
                ("Live Finding", 3, 3, 280),
                ("Diagnostic Details", 4, 4, 310),
                ("Available One-Click Fix", 5, 5, 170),
            ],
        )
        box.append(doc_scroll)
        self.stack.add_named(box, "doctor")

    def _refresh_doctor(self) -> None:
        checks = SystemDoctor.run_full_audit()
        self.doc_store.clear()
        ok_n = warn_n = err_n = 0
        for c in checks:
            st = c["status"]
            if st == "WORKING":
                ok_n += 1
                badge = "✅ WORKING"
            elif st == "WARNING":
                warn_n += 1
                badge = "⚠️ WARNING"
            else:
                err_n += 1
                badge = "❌ BROKEN"
            self.doc_store.append(
                [
                    badge,
                    c["category"],
                    c["component"],
                    c["summary"],
                    c["details"],
                    c["fix_label"] or "-",
                    c["fix_id"] or "",
                ]
            )
        self.btn_doc_ok.set_label(f"✅ {ok_n} Working")
        self.btn_doc_warn.set_label(f"⚠️ {warn_n} Warnings")
        self.btn_doc_err.set_label(f"❌ {err_n} Failing")
        self.alerts.check_doctor(checks)

    def _on_doctor_execute_fix(self, _btn: Gtk.Button) -> None:
        model, it = self.doc_view.get_selection().get_selected()
        if it is not None:
            fix_id = model[it][6]
            if fix_id:
                self._run_doctor_fix_id(fix_id)
            else:
                self._set_status(
                    "Selected row is already healthy or requires manual inspection."
                )

    def _run_doctor_fix_id(self, fix_id: str) -> None:
        ok, msg = SystemDoctor.execute_fix(fix_id)
        self._set_status(msg)
        GLib.timeout_add(900, lambda: (self._refresh_doctor(), False)[1])

    def _export_report(self, _btn: Gtk.Button) -> None:
        self._set_status("Writing diagnostic report...")
        try:
            from backend.report import write_report

            paths = write_report()
            self._set_status(f"Report written: {paths['json']}")
        except Exception as exc:
            self._set_status(f"Report failed: {exc}")

    def _on_alerts_toggled(self, button: Gtk.ToggleButton) -> None:
        self.alerts.enabled = button.get_active()
        button.set_label("Alerts: On" if self.alerts.enabled else "Alerts: Off")
        self._set_status(
            f"Desktop alerts {'enabled' if self.alerts.enabled else 'disabled'}."
        )

    # =========================================================================
    # PAGE 2: PERFORMANCE (WINDOWS 11 TASK MANAGER GRAPHS + MULTI-ENGINE)
    # =========================================================================
    def _build_page_performance(self) -> None:
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        scroll.set_child(box)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_column_homogeneous(True)

        self.chart_cpu = SparklineAreaChart("CPU Total & Kernel Split (%)", 100.0, 130)
        self.chart_mem = SparklineAreaChart("Memory & Swap Usage (%)", 100.0, 130)
        self.chart_gpu = SparklineAreaChart("GPU Utilization (%)", 100.0, 130)
        self.chart_disk = SparklineAreaChart("Disk Read / Write (MB/s)", None, 130)
        self.chart_net = SparklineAreaChart(
            "Network Throughput Down / Up (KB/s)", None, 130
        )
        self.chart_pwr = SparklineAreaChart("Battery Power (Watts)", None, 130)

        grid.attach(self.chart_cpu, 0, 0, 1, 1)
        grid.attach(self.chart_mem, 1, 0, 1, 1)
        grid.attach(self.chart_gpu, 0, 1, 1, 1)
        grid.attach(self.chart_pwr, 1, 1, 1, 1)
        grid.attach(self.chart_disk, 0, 2, 1, 1)
        grid.attach(self.chart_net, 1, 2, 1, 1)
        box.append(grid)

        for chart, details, command in (
            (
                self.chart_cpu,
                "Live total CPU utilization, user/kernel split, per-core MHz and load. "
                "Source: /proc/stat, per-CPU cpufreq and psutil.",
                "top",
            ),
            (
                self.chart_mem,
                "Live physical memory, cache, available memory and swap. "
                "Source: /proc/meminfo and psutil.",
                "free -h",
            ),
            (
                self.chart_gpu,
                "Live Intel GPU utilization, per-engine DRM fdinfo activity, "
                "frequency and RC6 residency.",
                "intel_gpu_top",
            ),
            (
                self.chart_pwr,
                "Live battery charge/discharge power and capacity from UPower "
                "and /sys/class/power_supply.",
                'upower -i "$(upower -e | grep -m1 battery)"',
            ),
            (
                self.chart_disk,
                "Live aggregate disk read/write throughput and IOPS from /proc/diskstats.",
                "vmstat 1",
            ),
            (
                self.chart_net,
                "Live throughput for the active default-route interface from /proc/net/dev.",
                "ip -s link",
            ),
        ):
            self._attach_widget_context(chart, details, command)

        # Per-core live MHz & load card
        self.perf_cores_lbl = Gtk.Label(xalign=0.0)
        self.perf_cores_lbl.add_css_class("tm-card")
        self.perf_cores_lbl.set_wrap(True)
        box.append(self.perf_cores_lbl)
        self._attach_widget_context(
            self.perf_cores_lbl,
            "Per-core CPU clock, utilization and package temperature. Source: "
            "/proc/stat, cpufreq sysfs and hwmon.",
            "lscpu -e=CPU,MAXMHZ,MINMHZ,MHZ",
        )

        # GPU Per-Engine Breakdown + Memory/Swap/Zswap/Vault readouts
        self.perf_gpu_lbl = Gtk.Label(xalign=0.0)
        self.perf_gpu_lbl.add_css_class("tm-card")
        self.perf_gpu_lbl.set_wrap(True)
        box.append(self.perf_gpu_lbl)
        self._attach_widget_context(
            self.perf_gpu_lbl,
            "GPU busy percentage, per-engine activity, frequency, RC6 sleep "
            "residency and client memory from DRM fdinfo and sysfs.",
            "intel_gpu_top",
        )

        self.perf_sys_lbl = Gtk.Label(xalign=0.0)
        self.perf_sys_lbl.add_css_class("tm-card")
        self.perf_sys_lbl.set_wrap(True)
        box.append(self.perf_sys_lbl)
        self._attach_widget_context(
            self.perf_sys_lbl,
            "Kernel context switches, interrupts, runnable/blocked processes, "
            "dirty pages, slab, zswap, vault state and PSI stall pressure.",
            "vmstat 1",
        )

        self.stack.add_named(scroll, "performance")

    # =========================================================================
    # PAGE 3: PROCESSES, APP GROUPS, TREE & DEEP THREAD/FD INSPECTOR
    # =========================================================================
    def _build_page_processes(self) -> None:
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.set_position(450)

        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        top.set_margin_top(8)
        top.set_margin_start(10)
        top.set_margin_end(10)

        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.proc_search = Gtk.SearchEntry(
            placeholder_text="Search process name, PID, user, systemd unit, or port (Ctrl+F)..."
        )
        self.proc_search.set_hexpand(True)
        self.proc_search.connect(
            "search-changed", lambda e: self._on_proc_search(e.get_text())
        )
        search_row.append(self.proc_search)
        top.append(search_row)

        bar = Gtk.FlowBox()
        bar.set_selection_mode(Gtk.SelectionMode.NONE)
        bar.set_max_children_per_line(5)
        bar.set_row_spacing(4)
        bar.set_column_spacing(6)
        bar.set_homogeneous(False)

        for mode_id, lbl in (
            ("flat", "All Processes"),
            ("grouped", "Group by App"),
            ("tree", "Process Tree"),
        ):
            b = Gtk.Button(label=lbl)
            b.add_css_class("tm-secondary-btn")
            b.connect("clicked", lambda _, m=mode_id: self._switch_proc_mode(m))
            bar.append(b)

        chk_k = Gtk.CheckButton(label="Hide Kernel Threads")
        chk_k.set_active(True)
        chk_k.connect("toggled", lambda c: self._toggle_kthreads(c.get_active()))
        bar.append(chk_k)

        btn_end = Gtk.Button(label="End Task")
        btn_end.add_css_class("tm-action-btn")
        btn_end.connect("clicked", lambda _: self._signal_selected(signal.SIGTERM))
        bar.append(btn_end)

        btn_kill = Gtk.Button(label="Force Kill")
        btn_kill.add_css_class("tm-danger-btn")
        btn_kill.connect("clicked", lambda _: self._signal_selected(signal.SIGKILL))
        bar.append(btn_kill)

        btn_freeze = Gtk.Button(label="Freeze (SIGSTOP)")
        btn_freeze.add_css_class("tm-secondary-btn")
        btn_freeze.connect("clicked", lambda _: self._signal_selected(signal.SIGSTOP))
        bar.append(btn_freeze)

        btn_resume = Gtk.Button(label="Resume (SIGCONT)")
        btn_resume.add_css_class("tm-secondary-btn")
        btn_resume.connect("clicked", lambda _: self._signal_selected(signal.SIGCONT))
        bar.append(btn_resume)

        btn_refresh_proc = Gtk.Button(label="Refresh Now")
        btn_refresh_proc.add_css_class("tm-secondary-btn")
        btn_refresh_proc.connect(
            "clicked",
            lambda _: (
                self._refresh_all(),
                self._set_status("Process list refreshed."),
            ),
        )
        bar.append(btn_refresh_proc)

        btn_columns = Gtk.Button(label="Columns")
        btn_columns.add_css_class("tm-secondary-btn")
        btn_columns.connect("clicked", self._open_columns_dialog)
        bar.append(btn_columns)

        top.append(bar)

        # Columns:
        # 0:PID(int), 1:PPID(int), 2:Name(str), 3:User(str),
        # 4:CPU(float), 5:CPU_str(str), 6:GPU(float), 7:GPU_str(str),
        # 8:MemMB(float), 9:Mem_str(str), 10:DiskKBs(float), 11:Disk_str(str),
        # 12:Wakeups(float), 13:Wakeups_str(str), 14:ImpactScore(float), 15:Impact(str),
        # 16:Threads(int), 17:State(str), 18:Ports(str), 19:Unit(str), 20:Cmd(str)
        self.proc_store = Gtk.ListStore(*PROCESS_TYPES)
        self.proc_view, self.proc_filter, self.proc_sort, proc_scroll = build_tree_view(
            self.proc_store,
            PROCESS_COLUMNS,
        )
        self.proc_filter.set_visible_func(self._proc_visible_func)
        self.proc_sort.set_sort_column_id(4, Gtk.SortType.DESCENDING)
        self.proc_view.get_selection().connect(
            "changed", self._on_proc_selection_changed
        )
        self.proc_columns = {
            (column.get_title() or ""): column
            for column in self.proc_view.get_columns()
        }
        self._apply_saved_process_layout()

        self.proc_tree_store = Gtk.TreeStore(*PROCESS_TYPES)
        self.proc_tree_view = Gtk.TreeView(model=self.proc_tree_store)
        self.proc_tree_view.set_headers_clickable(True)
        add_tree_columns(self.proc_tree_view, PROCESS_COLUMNS)
        self.proc_tree_view.get_selection().connect(
            "changed", self._on_proc_selection_changed
        )
        self.proc_tree_view.connect("row-expanded", self._on_process_tree_expanded)
        self.proc_tree_view.connect("row-collapsed", self._on_process_tree_collapsed)
        self.proc_tree_columns = {
            (column.get_title() or ""): column
            for column in self.proc_tree_view.get_columns()
        }
        self._apply_saved_process_layout()
        self.proc_tree_scroll = Gtk.ScrolledWindow()
        self.proc_tree_scroll.set_vexpand(True)
        self.proc_tree_scroll.set_hexpand(True)
        self.proc_tree_scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )
        self.proc_tree_scroll.set_propagate_natural_width(False)
        self.proc_tree_scroll.set_propagate_natural_height(False)
        self.proc_tree_scroll.set_child(self.proc_tree_view)

        self.proc_stack = Gtk.Stack()
        self.proc_stack.add_named(proc_scroll, "list")
        self.proc_stack.add_named(self.proc_tree_scroll, "tree")
        self.proc_stack.set_visible_child_name("list")
        self.proc_stack.set_vexpand(True)
        top.append(self.proc_stack)
        paned.set_start_child(top)

        # Bottom Deep Inspector (4 Sub-Tabs: Threads, Network Sockets, Open FDs, Environment)
        insp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        insp.add_css_class("tm-inspector")

        self.insp_header = Gtk.Label(
            label="Click any process above to inspect its live threads (TID, CPU%, core), sockets, open files, and environment.",
            xalign=0.0,
        )
        self.insp_header.set_ellipsize(Pango.EllipsizeMode.END)
        insp.append(self.insp_header)

        insp_nb = Gtk.Notebook()
        insp_nb.set_vexpand(True)

        # Sub-tab 1: Threads
        self.thread_store = Gtk.ListStore(
            int, str, str, float, str, int, str, str, float
        )
        _, _, t_sort, t_scroll = build_tree_view(
            self.thread_store,
            [
                ("Thread ID (TID)", 0, 0, 105),
                ("Thread Name (/proc/task/comm)", 1, 1, 210),
                ("State", 2, 2, 65),
                ("Thread CPU %", 4, 3, 105),
                ("CPU Core #", 5, 5, 90),
                ("User CPU Time", 6, 8, 115),
                ("Kernel CPU Time", 7, 8, 115),
            ],
        )
        t_sort.set_sort_column_id(3, Gtk.SortType.DESCENDING)
        insp_nb.append_page(t_scroll, Gtk.Label(label="Threads (TID)"))

        # Sub-tab 2: Process Sockets
        self.pconn_store = Gtk.ListStore(int, str, str, str, str)
        _, _, _, pc_scroll = build_tree_view(
            self.pconn_store,
            [
                ("FD", 0, 0, 60),
                ("Protocol", 1, 1, 80),
                ("Local Address", 2, 2, 220),
                ("Remote Address", 3, 3, 220),
                ("Socket State", 4, 4, 120),
            ],
        )
        insp_nb.append_page(pc_scroll, Gtk.Label(label="Open Sockets"))

        # Sub-tab 3: Open File Descriptors
        self.pfd_store = Gtk.ListStore(int, str)
        _, _, _, pfd_scroll = build_tree_view(
            self.pfd_store,
            [
                ("FD #", 0, 0, 75),
                ("Target File / Pipe / Device Node (/proc/pid/fd)", 1, 1, 650),
            ],
        )
        insp_nb.append_page(pfd_scroll, Gtk.Label(label="Open Files (fd)"))

        # Sub-tab 4: Environment & Cgroup
        self.penv_store = Gtk.ListStore(str, str)
        _, _, _, penv_scroll = build_tree_view(
            self.penv_store,
            [
                ("Variable / Property", 0, 0, 220),
                ("Value", 1, 1, 650),
            ],
        )
        insp_nb.append_page(penv_scroll, Gtk.Label(label="Environment & Metadata"))

        insp.append(insp_nb)
        paned.set_end_child(insp)
        self.stack.add_named(paned, "processes")

    def _switch_proc_mode(self, mode: str) -> None:
        self._proc_mode = mode
        self._proc_iters.clear()
        self.proc_store.clear()
        self.proc_tree_store.clear()
        self._tree_iters.clear()
        if mode == "tree":
            self.proc_stack.set_visible_child_name("tree")
            self.proc_sort.set_sort_column_id(
                Gtk.TREE_SORTABLE_UNSORTED_SORT_COLUMN_ID, Gtk.SortType.ASCENDING
            )
        else:
            self.proc_stack.set_visible_child_name("list")
            self.proc_sort.set_sort_column_id(4, Gtk.SortType.DESCENDING)
        self._refresh_all()

    def _toggle_kthreads(self, hide: bool) -> None:
        self._hide_kthreads = hide
        self._proc_iters.clear()
        self.proc_store.clear()
        self.proc_tree_store.clear()
        self._tree_iters.clear()
        self._refresh_all()

    def _on_proc_search(self, text: str) -> None:
        self._proc_query = text.strip().lower()
        self.proc_filter.refilter()
        if self._proc_mode == "tree":
            # The tree has no TreeModelFilter; rebuild it with matching
            # nodes and their ancestors so search works in tree mode too.
            self._refresh_all()

    @staticmethod
    def _proc_matches(proc: dict, query: str) -> bool:
        return any(
            query in str(proc.get(key, "")).lower()
            for key in ("pid", "name", "user", "ports", "unit", "cmd")
        )

    def _proc_visible_func(
        self, model: Gtk.TreeModel, it: Gtk.TreeIter, _data: object
    ) -> bool:
        if not self._proc_query:
            return True
        q = self._proc_query
        return any(q in str(model[it][col]).lower() for col in (0, 2, 3, 18, 19, 20))

    def _on_proc_selection_changed(self, sel: Gtk.TreeSelection) -> None:
        model, it = sel.get_selected()
        if it is not None:
            pid = int(model[it][0])
            self._selected_pid = pid
            self._selected_group_pids = self._group_pids_map.get(pid, [pid])
            self._refresh_process_inspector(pid)

    def _signal_selected(self, sig: signal.Signals) -> None:
        pids = (
            self._selected_group_pids
            if (self._proc_mode == "grouped" and self._selected_group_pids)
            else ([self._selected_pid] if self._selected_pid else [])
        )
        if not pids:
            self._set_status("Select a process row first.")
            return
        ok, msg = self.proc_collector.send_signal_to_pids(pids, int(sig))
        self._set_status(msg)
        GLib.timeout_add(350, lambda: (self._refresh_all(), False)[1])

    # =========================================================================
    # PAGE 4: PORTS & NETWORK CONNECTIONS
    # =========================================================================
    def _build_page_ports(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_start(10)
        box.set_margin_end(10)

        self.net_summary_lbl = Gtk.Label(xalign=0.0)
        self.net_summary_lbl.add_css_class("tm-card")
        self.net_summary_lbl.set_wrap(True)
        self.net_summary_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        box.append(self.net_summary_lbl)
        self._attach_widget_context(
            self.net_summary_lbl,
            "Active default-route interface, local IP, gateway, DNS, Wi-Fi "
            "SSID/signal, and RX/TX totals with errors and drops.",
            "ip -s link",
        )

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search = Gtk.SearchEntry(
            placeholder_text="Filter by port (e.g. 6379, 22, 8080), process, systemd unit, or IP..."
        )
        search.set_hexpand(True)
        search.connect("search-changed", lambda e: self._on_port_search(e.get_text()))
        bar.append(search)

        chk_listen = Gtk.CheckButton(label="Listening Ports Only (LISTEN / UNCONN)")
        chk_listen.connect(
            "toggled", lambda c: self._on_port_listen_toggle(c.get_active())
        )
        bar.append(chk_listen)

        btn_kill = Gtk.Button(label="Kill Process Using Selected Port")
        btn_kill.add_css_class("tm-danger-btn")
        btn_kill.connect("clicked", self._on_kill_port_proc)
        bar.append(btn_kill)
        box.append(bar)

        # 0:Proto, 1:Port(int), 2:Local, 3:Remote, 4:State, 5:PID(int), 6:Process, 7:Unit, 8:Purpose, 9:IsListening(bool)
        self.port_store = Gtk.ListStore(
            str, int, str, str, str, int, str, str, str, bool
        )
        self.port_view, self.port_filter, _, port_scroll = build_tree_view(
            self.port_store,
            [
                ("Proto", 0, 0, 65),
                ("Port", 1, 1, 75),
                ("Local Address", 2, 2, 155),
                ("Remote Address", 3, 3, 155),
                ("State", 4, 4, 95),
                ("PID", 5, 5, 70),
                ("Process", 6, 6, 140),
                ("Systemd Unit", 7, 7, 165),
                ("Service / Command Line Purpose", 8, 8, 300),
            ],
        )
        self.port_filter.set_visible_func(self._port_visible_func)
        # Ports has nine wide columns; keep both scrollbars visible so the
        # table can always be panned left/right and up/down inside the window.
        port_scroll.set_policy(Gtk.PolicyType.ALWAYS, Gtk.PolicyType.ALWAYS)
        self.port_scroll = port_scroll
        box.append(port_scroll)
        self.stack.add_named(box, "ports")

    def _on_port_search(self, text: str) -> None:
        self._port_query = text.strip().lower()
        self.port_filter.refilter()

    def _on_port_listen_toggle(self, active: bool) -> None:
        self._port_listen_only = active
        self.port_filter.refilter()

    def _port_visible_func(
        self, model: Gtk.TreeModel, it: Gtk.TreeIter, _data: object
    ) -> bool:
        if self._port_listen_only and not bool(model[it][9]):
            return False
        if not self._port_query:
            return True
        q = self._port_query
        return any(q in str(model[it][i]).lower() for i in range(9))

    def _on_kill_port_proc(self, _btn: Gtk.Button) -> None:
        model, it = self.port_view.get_selection().get_selected()
        if it is not None:
            pid = int(model[it][5])
            port = int(model[it][1])
            if pid > 0:
                _, msg = self.proc_collector.send_signal_to_pids([pid], signal.SIGTERM)
                self._set_status(f"Port {port}: {msg}")
            else:
                self._set_status(
                    f"Port {port} is owned by a system/root service ({model[it][7]}). Stop it in Services tab."
                )

    # =========================================================================
    # PAGE 5: SERVICES, TIMERS, AUTOSTART & HYPRLAND WINDOWS
    # =========================================================================
    def _build_page_services(self) -> None:
        nb = Gtk.Notebook()
        nb.set_margin_top(8)
        nb.set_margin_start(10)
        nb.set_margin_end(10)
        nb.set_margin_bottom(8)

        # Sub-tab A: System & User Services
        svc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        svc_box.set_margin_top(6)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        s_entry = Gtk.SearchEntry(
            placeholder_text="Filter systemd services (valkey, warp, bluetooth, pipewire, dunst)..."
        )
        s_entry.set_hexpand(True)
        s_entry.connect("search-changed", lambda e: self._on_svc_search(e.get_text()))
        bar.append(s_entry)

        for action, cls in (
            ("start", "tm-action-btn"),
            ("stop", "tm-danger-btn"),
            ("restart", "tm-secondary-btn"),
        ):
            b = Gtk.Button(label=action.capitalize())
            b.add_css_class(cls)
            b.connect("clicked", lambda _, a=action: self._on_service_action(a))
            bar.append(b)

        self.svc_privileged_btn = Gtk.Button(label="Authorize System I/O")
        self.svc_privileged_btn.add_css_class("tm-secondary-btn")
        self.svc_privileged_btn.set_tooltip_text(
            "Uses the root-owned PolicyKit helper to read /proc/<pid>/io for "
            "system services hidden by hidepid."
        )
        self.svc_privileged_btn.connect(
            "clicked", self._on_authorize_system_io
        )
        if not self.privileged_client.available:
            self.svc_privileged_btn.set_sensitive(False)
            self.svc_privileged_btn.set_tooltip_text(
                self.privileged_client.status_text()
            )
        self._attach_widget_context(
            self.svc_privileged_btn,
            "Requests PolicyKit authorization to read system-service I/O with "
            "the root-owned helper. The helper only accepts cgroup paths and "
            "returns per-service read/write byte sums.",
            "pkexec /usr/local/libexec/taskmgr-privileged service-io "
            "/system.slice/NetworkManager.service",
        )
        bar.append(self.svc_privileged_btn)
        svc_box.append(bar)

        self.svc_store = Gtk.ListStore(
            str, str, str, str, str, float, str, float, str, str, str
        )
        self.svc_view, self.svc_filter, _, svc_scroll = build_tree_view(
            self.svc_store,
            [
                ("Systemd Unit", 0, 0, 250),
                ("Scope", 1, 1, 75),
                ("Load", 2, 2, 85),
                ("Active", 3, 3, 85),
                ("SubState", 4, 4, 95),
                ("Memory", 6, 5, 95),
                ("CPU Time", 8, 7, 95),
                ("IO R/W", 9, 9, 120),
                ("Description", 10, 10, 340),
            ],
        )
        self.svc_filter.set_visible_func(self._svc_visible_func)
        svc_box.append(svc_scroll)
        nb.append_page(svc_box, Gtk.Label(label="System & User Services"))

        # Sub-tab B: System & User Timers
        self.timer_store = Gtk.ListStore(str, str, str, str, str, str)
        _, _, _, timer_scroll = build_tree_view(
            self.timer_store,
            [
                ("Timer Unit", 0, 0, 240),
                ("Activates Service", 1, 1, 240),
                ("Scope", 2, 2, 75),
                ("State", 5, 5, 95),
                ("Next Elapse", 3, 3, 210),
                ("Last Triggered", 4, 4, 210),
            ],
        )
        nb.append_page(timer_scroll, Gtk.Label(label="Scheduled Timers"))

        # Sub-tab C: Hyprland Autostart Tracker (hyprland.lua)
        self.auto_store = Gtk.ListStore(str, str, str, str, float, str)
        _, _, _, auto_scroll = build_tree_view(
            self.auto_store,
            [
                ("hyprland.lua Autostart Command", 0, 0, 380),
                ("Target Daemon", 1, 1, 150),
                ("Live Status", 2, 2, 180),
                ("Running PID(s)", 3, 3, 130),
                ("RAM Used", 5, 4, 110),
            ],
        )
        nb.append_page(auto_scroll, Gtk.Label(label="Hyprland Autostart Status"))

        # Sub-tab D: Hyprland Open Windows (hyprctl clients)
        win_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        win_box.set_margin_top(6)
        wbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_focus_w = Gtk.Button(label="Focus Selected Window")
        btn_focus_w.add_css_class("tm-action-btn")
        btn_focus_w.connect("clicked", self._on_focus_hypr_win)
        wbar.append(btn_focus_w)

        btn_close_w = Gtk.Button(label="Close Selected Window")
        btn_close_w.add_css_class("tm-danger-btn")
        btn_close_w.connect("clicked", self._on_close_hypr_win)
        wbar.append(btn_close_w)
        win_box.append(wbar)

        self.hypr_store = Gtk.ListStore(
            str, str, str, int, float, str, float, str, str, str, str
        )
        self.hypr_view, _, _, hypr_scroll = build_tree_view(
            self.hypr_store,
            [
                ("Workspace", 0, 0, 85),
                ("Window Class", 1, 1, 165),
                ("Window Title", 2, 2, 310),
                ("PID", 3, 3, 75),
                ("CPU %", 5, 4, 80),
                ("Memory", 7, 6, 100),
                ("Protocol", 8, 8, 95),
                ("Layout", 9, 9, 85),
            ],
        )
        win_box.append(hypr_scroll)
        nb.append_page(win_box, Gtk.Label(label="Hyprland Open Windows"))

        self.stack.add_named(nb, "services")

    def _on_svc_search(self, text: str) -> None:
        self._svc_query = text.strip().lower()
        self.svc_filter.refilter()

    def _svc_visible_func(
        self, model: Gtk.TreeModel, it: Gtk.TreeIter, _data: object
    ) -> bool:
        if not self._svc_query:
            return True
        q = self._svc_query
        return any(q in str(model[it][i]).lower() for i in range(11))

    def _on_service_action(self, action: str) -> None:
        model, it = self.svc_view.get_selection().get_selected()
        if it is not None:
            unit, scope = model[it][0], model[it][1]
            _, msg = ServicesCollector.control_service(unit, scope, action)
            self._set_status(msg)
            GLib.timeout_add(900, lambda: (self._refresh_services_tab(), False)[1])

    def _on_authorize_system_io(self, _btn: Gtk.Button) -> None:
        if not self.privileged_client.available:
            self._set_status(self.privileged_client.status_text())
            return
        cgroups = sorted(
            {
                cg
                for (scope, _unit), cg in self._svc_control_groups.items()
                if scope == "system" and cg
            }
        )
        if not cgroups:
            self._set_status("No system service cgroups are available to query.")
            return
        self.svc_privileged_btn.set_sensitive(False)
        self._set_status(
            "Waiting for PolicyKit authorization to read system-service I/O..."
        )

        def worker() -> None:
            data, error = self.privileged_client.service_io(cgroups)
            GLib.idle_add(self._finish_privileged_service_io, data, error)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_privileged_service_io(
        self, data: dict | None, error: str
    ) -> bool:
        if not self.privileged_client.available:
            self.svc_privileged_btn.set_sensitive(False)
        else:
            self.svc_privileged_btn.set_sensitive(True)
        if error:
            self._set_status(error)
            return False
        cg_to_unit = {
            cg: unit
            for (scope, unit), cg in self._svc_control_groups.items()
            if scope == "system"
        }
        updated = 0
        for cg, info in (data or {}).items():
            unit = cg_to_unit.get(cg)
            if not unit:
                continue
            read_bytes = info.get("read")
            write_bytes = info.get("write")
            if read_bytes is None or write_bytes is None:
                continue
            text = (
                f"R {read_bytes / (1024 * 1024):.1f}/"
                f"W {write_bytes / (1024 * 1024):.1f} MB"
            )
            for row in self.svc_store:
                if row[0] == unit and row[1] == "system":
                    row[9] = text
                    break
            self._svc_io_sources[("system", unit)] = (
                f"PolicyKit root /proc io "
                f"({info.get('readable', 0)}/{info.get('pids', 0)} pids)"
            )
            updated += 1
        self._set_status(
            f"PolicyKit updated system-service I/O for {updated} service(s)."
        )
        return False

    def _on_focus_hypr_win(self, _btn: Gtk.Button) -> None:
        model, it = self.hypr_view.get_selection().get_selected()
        if it is not None:
            addr = model[it][10]
            subprocess.Popen(
                [
                    "hyprctl",
                    "dispatch",
                    f'hl.dsp.focus({{ window = "address:{addr}" }})',
                ]
            )

    def _on_close_hypr_win(self, _btn: Gtk.Button) -> None:
        model, it = self.hypr_view.get_selection().get_selected()
        if it is not None:
            addr = model[it][10]
            subprocess.Popen(
                [
                    "hyprctl",
                    "dispatch",
                    f'hl.dsp.window.close({{ window = "address:{addr}" }})',
                ]
            )
            GLib.timeout_add(400, lambda: (self._refresh_services_tab(), False)[1])

    # =========================================================================
    # PAGE 6: POWER, WAKEUPS & POWERTOP KERNEL TUNABLES
    # =========================================================================
    def _build_page_power(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_bottom(8)

        profile_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        profile_box.append(Gtk.Label(label="Power Profile:"))
        self.profile_status_lbl = Gtk.Label(label="Checking...")
        self.profile_status_lbl.add_css_class("tm-pill")
        self.profile_status_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self._attach_widget_context(
            self.profile_status_lbl,
            "The current power profile reported by power-profiles-daemon. The "
            "buttons call powerprofilesctl set and verify with get.",
            "powerprofilesctl get",
        )
        available_profiles = PowerProfileController.list_profiles()
        known_profiles = available_profiles or [
            "power-saver",
            "balanced",
            "performance",
        ]
        for prof in known_profiles:
            b = Gtk.Button(label=prof.replace("-", " ").title())
            b.add_css_class("tm-secondary-btn")
            b.set_tooltip_text(
                "Calls powerprofilesctl set and verifies the result with powerprofilesctl get"
            )
            b.connect(
                "clicked",
                lambda _, p=prof: self._on_power_profile_clicked(p),
            )
            profile_box.append(b)
            self.profile_buttons[prof] = b
        profile_box.append(self.profile_status_lbl)
        self.auto_power_btn = Gtk.ToggleButton(label="Auto AC/Batt")
        self.auto_power_btn.add_css_class("tm-secondary-btn")
        self.auto_power_btn.set_tooltip_text(
            "Balanced on AC, Power Saver on battery. Applies only while enabled."
        )
        self.auto_power_btn.connect("toggled", self._on_auto_power_toggled)
        profile_box.append(self.auto_power_btn)
        self._refresh_power_profile_ui()
        box.append(profile_box)

        bar = Gtk.FlowBox()
        bar.set_selection_mode(Gtk.SelectionMode.NONE)
        bar.set_max_children_per_line(4)
        bar.set_row_spacing(4)
        bar.set_column_spacing(6)
        bar.set_homogeneous(False)

        btn_vfr = Gtk.Button(label="Enable Hyprland VFR")
        btn_vfr.add_css_class("tm-action-btn")
        btn_vfr.connect("clicked", lambda _: self._run_doctor_fix_id("enable_hypr_vfr"))
        bar.append(btn_vfr)

        btn_eco_vis = Gtk.Button(label="Disable Blur & Shadows (Battery)")
        btn_eco_vis.add_css_class("tm-secondary-btn")
        btn_eco_vis.connect(
            "clicked",
            lambda _: (
                subprocess.Popen(
                    [
                        "hyprctl",
                        "eval",
                        "hl.config({ debug = { vfr = true }, decoration = { blur = { enabled = false }, shadow = { enabled = false } } })",
                    ]
                ),
                self._set_status(
                    "Enabled VFR and disabled compositor blur/shadows for battery saving."
                ),
            ),
        )
        bar.append(btn_eco_vis)

        btn_tune_all = Gtk.Button(label="Optimize All BAD Kernel Tunables (Polkit)")
        btn_tune_all.add_css_class("tm-action-btn")
        btn_tune_all.connect("clicked", self._on_tune_all_power)
        bar.append(btn_tune_all)

        self.rapl_privileged_btn = Gtk.Button(label="Live RAPL (Authorize)")
        self.rapl_privileged_btn.add_css_class("tm-secondary-btn")
        self.rapl_privileged_btn.set_tooltip_text(
            "Uses the root-owned PolicyKit helper to read energy_uj twice and "
            "compute live package/core watts."
        )
        self.rapl_privileged_btn.connect("clicked", self._on_authorize_rapl)
        if not self.privileged_client.available:
            self.rapl_privileged_btn.set_sensitive(False)
            self.rapl_privileged_btn.set_tooltip_text(
                self.privileged_client.status_text()
            )
        self._attach_widget_context(
            self.rapl_privileged_btn,
            "Requests PolicyKit authorization to read RAPL energy_uj counters "
            "twice and compute live package/core watts.",
            "pkexec /usr/local/libexec/taskmgr-privileged rapl-watts",
        )
        bar.append(self.rapl_privileged_btn)
        box.append(bar)

        self.cstate_lbl = Gtk.Label(xalign=0.0)
        self.cstate_lbl.add_css_class("tm-card")
        self._attach_widget_context(
            self.cstate_lbl,
            "CPU C-state residency share and the number of PowerTOP tunables "
            "currently in a BAD state.",
            "cpupower idle-info",
        )
        self.cstate_lbl.set_wrap(True)
        box.append(self.cstate_lbl)

        self.rapl_lbl = Gtk.Label(xalign=0.0)
        self.rapl_lbl.add_css_class("tm-card")
        self.rapl_lbl.set_wrap(True)
        self._attach_widget_context(
            self.rapl_lbl,
            "Live RAPL package/core energy-derived power. N/A means energy_uj "
            "is not readable without root; the static package limit is still shown.",
            "cat /sys/class/powercap/intel-rapl:0/energy_uj",
        )
        box.append(self.rapl_lbl)

        self.battery_limit_lbl = Gtk.Label(xalign=0.0)
        self.battery_limit_lbl.add_css_class("tm-card")
        self.battery_limit_lbl.set_wrap(True)
        self._attach_widget_context(
            self.battery_limit_lbl,
            "Battery charge-stop thresholds exposed by the firmware. N/A means "
            "the battery or firmware does not expose charge_control sysfs files.",
            "find /sys/class/power_supply -name 'charge_control*'",
        )
        box.append(self.battery_limit_lbl)

        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.set_vexpand(True)
        paned.set_position(280)

        # Top table: Live Hardware Interrupts/sec (/proc/interrupts)
        self.irq_store = Gtk.ListStore(str, float, str, str, str)
        _, _, irq_sort, irq_scroll = build_tree_view(
            self.irq_store,
            [
                ("IRQ #", 0, 0, 75),
                ("Interrupts / sec", 2, 1, 120),
                ("Hardware / Driver Subsystem", 3, 3, 230),
                ("Raw Kernel Interrupt Source (/proc/interrupts)", 4, 4, 480),
            ],
        )
        irq_sort.set_sort_column_id(1, Gtk.SortType.DESCENDING)
        paned.set_start_child(irq_scroll)

        # Bottom table: PowerTOP Kernel & PCI Tunables
        self.tun_store = Gtk.ListStore(str, str, str, str, str, str)
        _, _, _, tun_scroll = build_tree_view(
            self.tun_store,
            [
                ("State", 0, 0, 85),
                ("Bus / Category", 1, 1, 130),
                ("Power Tunable", 2, 2, 310),
                ("Current", 3, 3, 95),
                ("Target", 4, 4, 95),
                ("Why It Matters", 5, 5, 360),
            ],
        )
        paned.set_end_child(tun_scroll)
        box.append(paned)

        self.stack.add_named(box, "power")

    # =========================================================================
    # PAGE 7: AUDIO (PIPEWIRE), CAMERA (V4L2) & BLUETOOTH (RFKILL)
    # =========================================================================
    def _build_page_audio(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_bottom(8)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_norm_mic = Gtk.Button(label="Normalize Default Mic Volume to 100%")
        btn_norm_mic.add_css_class("tm-action-btn")
        btn_norm_mic.connect(
            "clicked",
            lambda _: (
                subprocess.Popen(
                    ["wpctl", "set-volume", "@DEFAULT_AUDIO_SOURCE@", "1.0"]
                ),
                self._set_status("Normalized microphone gain to 100%."),
                GLib.timeout_add(300, lambda: (self._refresh_audio_tab(), False)[1]),
            ),
        )
        bar.append(btn_norm_mic)

        btn_mute_sink = Gtk.Button(label="Toggle Output Mute")
        btn_mute_sink.add_css_class("tm-secondary-btn")
        btn_mute_sink.connect(
            "clicked",
            lambda _: (
                subprocess.Popen(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
                ),
                GLib.timeout_add(300, lambda: (self._refresh_audio_tab(), False)[1]),
            ),
        )
        bar.append(btn_mute_sink)

        btn_bt_unblock = Gtk.Button(label="Unblock Bluetooth (rfkill)")
        btn_bt_unblock.add_css_class("tm-action-btn")
        btn_bt_unblock.connect(
            "clicked",
            lambda _: (
                subprocess.Popen(["rfkill", "unblock", "bluetooth"]),
                GLib.timeout_add(400, lambda: (self._refresh_audio_tab(), False)[1]),
            ),
        )
        bar.append(btn_bt_unblock)

        btn_bt_block = Gtk.Button(label="Soft-Block Bluetooth")
        btn_bt_block.add_css_class("tm-secondary-btn")
        btn_bt_block.connect(
            "clicked",
            lambda _: (
                subprocess.Popen(["rfkill", "block", "bluetooth"]),
                GLib.timeout_add(400, lambda: (self._refresh_audio_tab(), False)[1]),
            ),
        )
        bar.append(btn_bt_block)
        box.append(bar)

        self.audio_store = Gtk.ListStore(str, int, str, str, str, str)
        _, _, _, audio_scroll = build_tree_view(
            self.audio_store,
            [
                ("Type", 0, 0, 140),
                ("ID", 1, 1, 65),
                ("Device / Stream / Radio Name", 2, 2, 360),
                ("Volume / State", 3, 3, 140),
                ("Active / Default", 4, 4, 130),
                ("Health / Privacy Diagnostic", 5, 5, 280),
            ],
        )
        box.append(audio_scroll)
        self.stack.add_named(box, "audio")

    # =========================================================================
    # PAGE 8: HARDWARE BUS (PCI/USB), SENSORS, PARTITIONS & KERNEL MODULES
    # =========================================================================
    def _build_page_hardware(self) -> None:
        nb = Gtk.Notebook()
        nb.set_scrollable(True)
        nb.set_margin_top(8)
        nb.set_margin_start(10)
        nb.set_margin_end(10)
        nb.set_margin_bottom(8)

        # Sub-tab 1: PCI Bus & Kernel Drivers
        self.pci_store = Gtk.ListStore(str, str, str, str, str)
        _, _, _, pci_scroll = build_tree_view(
            self.pci_store,
            [
                ("PCI Slot", 0, 0, 90),
                ("Hardware Device Name (pci.ids)", 1, 1, 430),
                ("Bound Kernel Driver", 2, 2, 160),
                ("Runtime PM Status", 3, 3, 140),
                ("Power Control", 4, 4, 110),
            ],
        )
        nb.append_page(pci_scroll, Gtk.Label(label="PCI Bus & Drivers"))

        # Sub-tab 2: USB Bus
        self.usb_store = Gtk.ListStore(str, str, str)
        _, _, _, usb_scroll = build_tree_view(
            self.usb_store,
            [
                ("USB Bus / Device", 0, 0, 140),
                ("Vendor:Product ID", 1, 1, 140),
                ("Connected USB Peripheral", 2, 2, 520),
            ],
        )
        nb.append_page(usb_scroll, Gtk.Label(label="USB Peripherals"))

        # Sub-tab 3: All Hardware Sensors (hwmon)
        self.sensor_store = Gtk.ListStore(str, str, str, str)
        _, _, _, sen_scroll = build_tree_view(
            self.sensor_store,
            [
                ("Sensor Chip (hwmon)", 0, 0, 180),
                ("Channel / Zone", 1, 1, 220),
                ("Metric Type", 2, 2, 150),
                ("Live Reading", 3, 3, 160),
            ],
        )
        nb.append_page(sen_scroll, Gtk.Label(label="Sensors"))

        # Sub-tab 4: Block Devices, Partitions & Vault
        self.blk_store = Gtk.ListStore(str, str, str, str, str, str, str)
        _, _, _, blk_scroll = build_tree_view(
            self.blk_store,
            [
                ("Device / Partition", 0, 0, 160),
                ("Size", 1, 1, 95),
                ("Type", 2, 2, 85),
                ("Filesystem", 3, 3, 110),
                ("Used", 4, 4, 100),
                ("Use %", 5, 5, 85),
                ("Mountpoint / Model", 6, 6, 360),
            ],
        )
        nb.append_page(blk_scroll, Gtk.Label(label="Storage"))

        # Sub-tab 4b: SMART / NVMe health, with explicit missing-tool states.
        self.smart_store = Gtk.ListStore(
            str, str, str, str, str, str, str, str
        )
        _, _, _, smart_scroll = build_tree_view(
            self.smart_store,
            [
                ("Device", 0, 0, 145),
                ("Model", 1, 1, 175),
                ("Size", 2, 2, 85),
                ("SMART Health", 3, 3, 105),
                ("Temperature", 4, 4, 95),
                ("Power-On Hours", 5, 5, 105),
                ("Used", 6, 6, 80),
                ("Note", 7, 7, 260),
            ],
            max_total_width=980,
        )
        nb.append_page(smart_scroll, Gtk.Label(label="Storage Health"))

        # Sub-tab 4c: eBPF Live Events (gated by bpftrace + BTF + root)
        ebpf_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        ebpf_box.set_margin_top(6)
        ebpf_box.set_margin_start(6)
        ebpf_box.set_margin_end(6)
        ebpf_box.set_margin_bottom(6)

        self.ebpf_status_lbl = Gtk.Label(xalign=0.0)
        self.ebpf_status_lbl.set_wrap(True)
        self.ebpf_status_lbl.add_css_class("tm-card")
        ebpf_box.append(self.ebpf_status_lbl)
        self._attach_widget_context(
            self.ebpf_status_lbl,
            "Live eBPF prerequisite status: bpftrace presence, kernel BTF, and "
            "root/CAP_BPF access. The runner is disabled until all are ready.",
            "bpftrace --version; test -r /sys/kernel/btf/vmlinux; id -u",
        )

        ebpf_controls = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        ebpf_controls.append(Gtk.Label(label="Probe:"))
        self.ebpf_probe_dropdown = Gtk.DropDown.new_from_strings(
            [probe.label for probe in PROBES]
        )
        self.ebpf_probe_dropdown.connect(
            "notify::selected", lambda *_: self._update_ebpf_command()
        )
        ebpf_controls.append(self.ebpf_probe_dropdown)
        self.ebpf_start_btn = Gtk.Button(label="Start")
        self.ebpf_start_btn.add_css_class("tm-action-btn")
        self.ebpf_start_btn.connect("clicked", self._on_ebpf_start)
        ebpf_controls.append(self.ebpf_start_btn)
        self.ebpf_stop_btn = Gtk.Button(label="Stop")
        self.ebpf_stop_btn.add_css_class("tm-secondary-btn")
        self.ebpf_stop_btn.connect("clicked", self._on_ebpf_stop)
        self.ebpf_stop_btn.set_sensitive(False)
        ebpf_controls.append(self.ebpf_stop_btn)
        self.ebpf_clear_btn = Gtk.Button(label="Clear")
        self.ebpf_clear_btn.add_css_class("tm-secondary-btn")
        self.ebpf_clear_btn.connect("clicked", lambda _: self.ebpf_store.clear())
        ebpf_controls.append(self.ebpf_clear_btn)
        ebpf_box.append(ebpf_controls)

        self.ebpf_command_lbl = Gtk.Label(xalign=0.0)
        self.ebpf_command_lbl.set_wrap(True)
        self.ebpf_command_lbl.set_selectable(True)
        self.ebpf_command_lbl.add_css_class("tm-source-text")
        ebpf_box.append(self.ebpf_command_lbl)
        self._attach_widget_context(
            self.ebpf_command_lbl,
            "The exact install or root command for the selected eBPF probe. "
            "The app never starts a probe that is missing a prerequisite.",
            "sudo pacman -S bpftrace",
        )

        self.ebpf_store = Gtk.ListStore(str, str, str)
        _, _, _, ebpf_scroll = build_tree_view(
            self.ebpf_store,
            [
                ("Time", 0, 0, 90),
                ("Probe", 1, 1, 120),
                ("Event", 2, 2, 700),
            ],
            max_total_width=980,
        )
        ebpf_scroll.set_vexpand(True)
        ebpf_box.append(ebpf_scroll)
        nb.append_page(ebpf_box, Gtk.Label(label="eBPF Live Events"))

        self._ebpf_probe_commands = {
            probe.label: probe.command() for probe in PROBES
        }
        self._ebpf_active_probe = ""
        self._ebpf_stopping = False
        self._refresh_ebpf_status()

        # Sub-tab 4d: gated fan-curve and battery charge-threshold editors
        ctrl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ctrl_box.set_margin_top(8)
        ctrl_box.set_margin_start(8)
        ctrl_box.set_margin_end(8)
        ctrl_box.set_margin_bottom(8)

        self.fan_status_lbl = Gtk.Label(xalign=0.0)
        self.fan_status_lbl.set_wrap(True)
        self.fan_status_lbl.add_css_class("tm-card")
        ctrl_box.append(self.fan_status_lbl)
        self._attach_widget_context(
            self.fan_status_lbl,
            "Fan control prerequisite status. Writes require a writable hwmon "
            "pwm* output (root or a udev rule); unavailable means nothing is "
            "written and fan RPM remains read-only in the Sensors tab.",
            "find /sys/class/hwmon -name 'pwm[0-9]' -o -name 'pwm[0-9]_enable'",
        )

        fan_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fan_bar.append(Gtk.Label(label="Fan:"))
        self.fan_dropdown = Gtk.DropDown.new_from_strings(["Unavailable"])
        fan_bar.append(self.fan_dropdown)
        self.fan_apply_btn = Gtk.Button(label="Apply Curve Now")
        self.fan_apply_btn.add_css_class("tm-action-btn")
        self.fan_apply_btn.connect("clicked", self._on_fan_apply)
        fan_bar.append(self.fan_apply_btn)
        self.fan_manual_btn = Gtk.Button(label="Manual Mode")
        self.fan_manual_btn.add_css_class("tm-secondary-btn")
        self.fan_manual_btn.connect("clicked", self._on_fan_manual)
        fan_bar.append(self.fan_manual_btn)
        self.fan_auto_btn = Gtk.Button(label="Restore Auto")
        self.fan_auto_btn.add_css_class("tm-secondary-btn")
        self.fan_auto_btn.connect("clicked", self._on_fan_auto)
        fan_bar.append(self.fan_auto_btn)
        ctrl_box.append(fan_bar)

        curve_grid = Gtk.Grid(column_spacing=10, row_spacing=4)
        curve_grid.attach(Gtk.Label(label="Temp °C", xalign=0.0), 0, 0, 1, 1)
        curve_grid.attach(Gtk.Label(label="PWM 0–255", xalign=0.0), 1, 0, 1, 1)
        self.fan_curve_spins: list[tuple[Gtk.SpinButton, Gtk.SpinButton]] = []
        for row, (temp, pwm) in enumerate(
            [(40, 80), (50, 120), (60, 170), (70, 220), (80, 255)], start=1
        ):
            temp_spin = Gtk.SpinButton.new_with_range(20, 100, 1)
            temp_spin.set_value(temp)
            pwm_spin = Gtk.SpinButton.new_with_range(0, 255, 1)
            pwm_spin.set_value(pwm)
            pwm_spin.set_tooltip_text(
                "PWM duty 0–255. 0 may stop the fan on some hardware. "
                "Nothing is written until Apply Curve is clicked."
            )
            curve_grid.attach(temp_spin, 0, row, 1, 1)
            curve_grid.attach(pwm_spin, 1, row, 1, 1)
            self.fan_curve_spins.append((temp_spin, pwm_spin))
        ctrl_box.append(curve_grid)
        self.fan_action_lbl = Gtk.Label(xalign=0.0)
        self.fan_action_lbl.set_wrap(True)
        self.fan_action_lbl.set_selectable(True)
        ctrl_box.append(self.fan_action_lbl)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        ctrl_box.append(separator)

        self.battery_status_lbl = Gtk.Label(xalign=0.0)
        self.battery_status_lbl.set_wrap(True)
        self.battery_status_lbl.add_css_class("tm-card")
        ctrl_box.append(self.battery_status_lbl)
        self._attach_widget_context(
            self.battery_status_lbl,
            "Battery charge-threshold prerequisite status. Writes require "
            "charge_control_start/end_threshold with write permission; "
            "unavailable means the firmware exposes no writable threshold.",
            "find /sys/class/power_supply -name 'charge_control*'",
        )

        battery_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        battery_bar.append(Gtk.Label(label="Start %:"))
        self.battery_start_spin = Gtk.SpinButton.new_with_range(0, 100, 1)
        self.battery_start_spin.set_value(0)
        battery_bar.append(self.battery_start_spin)
        battery_bar.append(Gtk.Label(label="Stop %:"))
        self.battery_end_spin = Gtk.SpinButton.new_with_range(0, 100, 1)
        self.battery_end_spin.set_value(80)
        battery_bar.append(self.battery_end_spin)
        self.battery_apply_btn = Gtk.Button(label="Apply Threshold")
        self.battery_apply_btn.add_css_class("tm-action-btn")
        self.battery_apply_btn.connect("clicked", self._on_battery_apply)
        battery_bar.append(self.battery_apply_btn)
        ctrl_box.append(battery_bar)
        self.battery_action_lbl = Gtk.Label(xalign=0.0)
        self.battery_action_lbl.set_wrap(True)
        self.battery_action_lbl.set_selectable(True)
        ctrl_box.append(self.battery_action_lbl)

        ctrl_scroll = Gtk.ScrolledWindow()
        ctrl_scroll.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC
        )
        ctrl_scroll.set_propagate_natural_height(False)
        ctrl_scroll.set_vexpand(True)
        ctrl_scroll.set_hexpand(True)
        ctrl_scroll.set_child(ctrl_box)
        nb.append_page(ctrl_scroll, Gtk.Label(label="Fan & Charge"))
        self._refresh_hardware_controls()

        # Sub-tab 5: Loaded Kernel Modules
        mod_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        mod_box.set_margin_top(6)
        m_search = Gtk.SearchEntry(
            placeholder_text="Search loaded kernel modules (e.g. i915, mt7921e, nvme, snd_sof)..."
        )
        m_search.connect("search-changed", lambda e: self._on_mod_search(e.get_text()))
        mod_box.append(m_search)

        self.kmod_store = Gtk.ListStore(str, float, str, int, str)
        _, self.kmod_filter, _, kmod_scroll = build_tree_view(
            self.kmod_store,
            [
                ("Kernel Module", 0, 0, 220),
                ("Memory Size", 2, 1, 120),
                ("Ref Count", 3, 3, 95),
                ("Used By Modules", 4, 4, 480),
            ],
        )
        self.kmod_filter.set_visible_func(self._kmod_visible_func)
        mod_box.append(kmod_scroll)
        nb.append_page(mod_box, Gtk.Label(label="Kernel Modules"))

        # Sub-tab 6: explicit optional-feature prerequisites
        self.cap_store = Gtk.ListStore(str, str, str, str)
        _, _, _, cap_scroll = build_tree_view(
            self.cap_store,
            [
                ("Feature", 0, 0, 220),
                ("Status", 1, 1, 110),
                ("Details / Prerequisite", 2, 2, 520),
                ("Command", 3, 3, 300),
            ],
            max_total_width=980,
        )
        nb.append_page(cap_scroll, Gtk.Label(label="Optional Features"))

        self.stack.add_named(nb, "hardware")

    def _on_mod_search(self, text: str) -> None:
        self._hw_mod_query = text.strip().lower()
        self.kmod_filter.refilter()

    def _kmod_visible_func(
        self, model: Gtk.TreeModel, it: Gtk.TreeIter, _data: object
    ) -> bool:
        if not self._hw_mod_query:
            return True
        q = self._hw_mod_query
        return q in str(model[it][0]).lower() or q in str(model[it][4]).lower()

    # =========================================================================
    # PAGE 9: LIVE LOGS, KERNEL/ACPI WARNINGS & CRASH DUMPS
    # =========================================================================
    def _build_page_logs(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_bottom(8)

        bar = Gtk.FlowBox()
        bar.set_selection_mode(Gtk.SelectionMode.NONE)
        bar.set_max_children_per_line(4)
        bar.set_row_spacing(4)
        bar.set_column_spacing(6)
        bar.set_homogeneous(False)
        for mode_id, lbl in (
            ("errors", "🚨 Boot Errors (journalctl -p 0..3)"),
            ("kernel", "⚠️ Kernel & ACPI Warnings (dmesg)"),
            ("crashes", "💥 Crash Dumps (coredumpctl)"),
            ("hyprland", "🪟 Hyprland Session Log"),
        ):
            b = Gtk.Button(label=lbl)
            b.add_css_class("tm-secondary-btn")
            b.connect("clicked", lambda _, m=mode_id: self._switch_log_mode(m))
            bar.append(b)

        l_search = Gtk.SearchEntry(placeholder_text="Filter log messages...")
        l_search.set_hexpand(True)
        l_search.connect("search-changed", lambda e: self._on_log_search(e.get_text()))
        bar.append(l_search)

        btn_refresh_logs = Gtk.Button(label="Refresh Logs")
        btn_refresh_logs.add_css_class("tm-secondary-btn")
        btn_refresh_logs.connect(
            "clicked",
            lambda _: (self._refresh_logs(), self._set_status("Reloaded logs.")),
        )
        bar.append(btn_refresh_logs)
        box.append(bar)

        self.log_store = Gtk.ListStore(str, str, str, str)
        _, self.log_filter, _, log_scroll = build_tree_view(
            self.log_store,
            [
                ("Timestamp", 0, 0, 175),
                ("Component / Source", 1, 1, 175),
                ("Severity", 2, 2, 95),
                ("Message", 3, 3, 640),
            ],
        )
        self.log_filter.set_visible_func(self._log_visible_func)
        box.append(log_scroll)
        self.stack.add_named(box, "logs")

    def _switch_log_mode(self, mode: str) -> None:
        self._log_mode = mode
        self._refresh_logs()

    def _on_log_search(self, text: str) -> None:
        self._log_query = text.strip().lower()
        self.log_filter.refilter()

    def _log_visible_func(
        self, model: Gtk.TreeModel, it: Gtk.TreeIter, _data: object
    ) -> bool:
        if not self._log_query:
            return True
        q = self._log_query
        return any(q in str(model[it][i]).lower() for i in range(4))

    # =========================================================================
    # REAL-TIME TICK & PAGE REFRESHERS
    # =========================================================================
    def _on_tick(self) -> bool:
        self._load_autotheme()
        self._refresh_all()
        return True

    def _refresh_all(self) -> None:
        page = self.stack.get_visible_child_name()
        perf = self.perf_collector.sample()
        self.alerts.check_perf(perf)
        self._apply_auto_power(perf)
        mem = perf["mem"]
        swap = perf["swap"]
        gpu = perf["gpu"]
        bat = perf["battery"]

        def mhz(value):
            return f"{value} MHz" if value else "N/A"

        def temp(value):
            return f"{value:.0f}°C" if value and value > 0 else "N/A"

        # 1. Update Top Bar Pills with explicit N/A when a source is absent.
        self.pill_cpu.set_text(
            f"CPU: {perf['cpu_total']:.1f}% ({mhz(perf['avg_mhz'])} • {temp(perf['cpu_temp'])})"
        )
        if gpu.name == "No GPU detected":
            self.pill_gpu.set_text("GPU: N/A")
        elif not gpu.busy_available:
            self.pill_gpu.set_text("GPU: N/A (no counters)")
        else:
            freq_txt = f"{gpu.freq_mhz} MHz" if gpu.freq_available else "N/A"
            self.pill_gpu.set_text(
                f"GPU: {gpu.busy_pct:.1f}% ({freq_txt} • {gpu.clients} clients)"
            )
        self.pill_ram.set_text(
            f"RAM: {mem.used // (1024**2)} / {mem.total // (1024**2)} MiB ({mem.percent:.1f}%)"
        )
        self.pill_io.set_text(
            f"Net: ↓{perf['down_kbs']:.0f} ↑{perf['up_kbs']:.0f} KB/s  |  Disk: {perf['read_mbs'] + perf['write_mbs']:.1f} MB/s"
        )
        if bat["present"]:
            watts_txt = f"{bat['watts']:.1f} W" if bat["watts"] > 0 else "0.0 W"
            self.pill_bat.set_text(
                f"BAT: {bat['percent']}% • {watts_txt} • {bat['remaining_str']}"
            )
        else:
            self.pill_bat.set_text("BAT: No battery detected")

        # 2. Update Performance Charts.
        self.chart_cpu.update_chart(
            list(self.perf_collector.cpu_hist),
            f"{perf['cpu_total']:.1f}%  ({mhz(perf['avg_mhz'])}, {temp(perf['cpu_temp'])})",
            f"User: {perf['cpu_user_pct']:.1f}%  |  Kernel (Red): {perf['cpu_kernel_pct']:.1f}%  |  Load: {perf['load_avg'][0]}  |  IRQ: {perf['intr_s']:.0f}/s",
            secondary=list(self.perf_collector.cpu_kernel_hist),
            accent_rgb=self._accent_rgb,
            bg_rgb=self._bg_rgb,
        )
        self.chart_mem.update_chart(
            list(self.perf_collector.mem_hist),
            f"{mem.used // (1024**2)} / {mem.total // (1024**2)} MiB ({mem.percent:.1f}%)",
            f"Avail: {mem.available // (1024**2)} MiB  |  Cached: {getattr(mem, 'cached', 0) // (1024**2)} MiB  |  Swap: {swap.used // (1024**2)} MiB",
            accent_rgb=self._accent_rgb,
            bg_rgb=self._bg_rgb,
        )
        if gpu.name == "No GPU detected":
            gpu_title = "GPU (No GPU detected)"
            gpu_right = "N/A"
            gpu_sub = "No card* device under /sys/class/drm"
        elif not gpu.busy_available:
            gpu_title = "GPU Utilization"
            gpu_right = "N/A"
            gpu_sub = f"{gpu.name}  |  {gpu.driver}  |  {gpu.source}  |  Clients: {gpu.clients}"
        else:
            gpu_title = "GPU Utilization (%)"
            if gpu.freq_available:
                freq_txt = f"{gpu.freq_mhz} MHz"
                if gpu.max_freq_mhz:
                    freq_txt = f"{gpu.freq_mhz}/{gpu.max_freq_mhz} MHz"
                gpu_right = f"{gpu.busy_pct:.1f}%  ({freq_txt})"
            else:
                gpu_right = f"{gpu.busy_pct:.1f}%  (frequency N/A)"
            if gpu.source.startswith("nvidia-smi"):
                mem_txt = (
                    f"{gpu.mem_used_mb:.0f}/{gpu.mem_total_mb:.0f} MiB"
                    if gpu.mem_total_mb
                    else f"{gpu.mem_used_mb:.0f} MiB"
                )
                temp_txt = (
                    f"{gpu.temp_c:.0f} °C"
                    if gpu.temp_available
                    else "N/A"
                )
                gpu_sub = (
                    f"{gpu.name}  |  nvidia-smi  |  GPU Mem: {mem_txt}  |  "
                    f"Temp: {temp_txt}  |  Compute apps: {gpu.clients} (global)"
                )
            elif gpu.engines:
                eng_txt = "  |  ".join(f"{k}: {v:.1f}%" for k, v in gpu.engines.items())
                gpu_sub = (
                    f"{gpu.name}  |  {gpu.driver} DRM fdinfo  |  {eng_txt}  |  "
                    f"Clients: {gpu.clients}  |  GPU Mem: {gpu.mem_used_mb:.0f} MB  |  "
                    f"RC6: {gpu.rc6_pct:.0f}%"
                    if gpu.rc6_available
                    else f"{gpu.name}  |  {gpu.driver} DRM fdinfo  |  {eng_txt}  |  "
                    f"Clients: {gpu.clients}  |  GPU Mem: {gpu.mem_used_mb:.0f} MB  |  RC6: N/A"
                )
            else:
                gpu_sub = (
                    f"{gpu.name}  |  {gpu.driver}  |  {gpu.source}  |  Clients: {gpu.clients}  |  "
                    f"GPU Mem: {gpu.mem_used_mb:.0f} MB"
                )
        self.chart_gpu.update_chart(
            list(self.perf_collector.gpu_hist) if gpu.busy_available else [],
            gpu_right,
            gpu_sub,
            accent_rgb=self._accent_rgb,
            bg_rgb=self._bg_rgb,
            title=gpu_title,
        )
        if bat["present"]:
            self.chart_pwr.update_chart(
                list(self.perf_collector.power_watts_hist),
                f"{bat['watts']:.2f} W  ({bat['status']})",
                f"Cap: {bat['energy_now_wh']:.1f}/{bat['energy_full_wh']:.1f} Wh "
                f"(Health {bat['health_pct']}%, {bat['cycles']} cycles)  |  Platform Profile: {bat['platform_profile']}",
                accent_rgb=self._accent_rgb,
                bg_rgb=self._bg_rgb,
            )
        else:
            self.chart_pwr.update_chart(
                [],
                "N/A",
                "No /sys/class/power_supply/BAT* device on this machine",
                accent_rgb=self._accent_rgb,
                bg_rgb=self._bg_rgb,
                title="Battery (No battery detected)",
            )
        self.chart_disk.update_chart(
            list(self.perf_collector.disk_read_hist),
            f"R: {perf['read_mbs']:.2f} MB/s   W: {perf['write_mbs']:.2f} MB/s",
            f"IOPS: R {perf['read_iops']:.0f}/s  W {perf['write_iops']:.0f}/s  |  Drive Temp: {temp(perf['nvme_temp'])}",
            secondary=list(self.perf_collector.disk_write_hist),
            accent_rgb=self._accent_rgb,
            bg_rgb=self._bg_rgb,
        )
        wifi = perf["net_info"]["wifi"]
        wifi_txt = (
            f"SSID: {wifi['ssid']} ({wifi['signal']}%, {wifi['rate']})"
            if wifi["ssid"] != "N/A"
            else "Wi-Fi: no NetworkManager data"
        )
        self.chart_net.update_chart(
            list(self.perf_collector.net_down_hist),
            f"↓ {perf['down_kbs']:.1f} KB/s   ↑ {perf['up_kbs']:.1f} KB/s",
            f"Iface: {perf['net_info']['iface']} ({perf['net_info']['local_ip']})  |  {wifi_txt}",
            secondary=list(self.perf_collector.net_up_hist),
            accent_rgb=self._accent_rgb,
            bg_rgb=self._bg_rgb,
        )

        # 3. Per-core frequency & load summary (truthful N/A when unavailable).
        core_strs = []
        for idx, pct in enumerate(perf["per_core"]):
            mhz_val = perf["core_mhz"][idx] if idx < len(perf["core_mhz"]) else None
            if mhz_val:
                flag = "🔥" if mhz_val >= 1500 else ""
                core_strs.append(f"C{idx}: {pct:4.1f}% ({mhz_val} MHz{flag})")
            else:
                core_strs.append(f"C{idx}: {pct:4.1f}% (MHz N/A)")
        self.perf_cores_lbl.set_text(
            "Logical CPUs (Load & Live Clock):   " + "   |   ".join(core_strs)
        )

        if gpu.name == "No GPU detected":
            self.perf_gpu_lbl.set_text(
                "No GPU detected under /sys/class/drm/card*; GPU telemetry is unavailable."
            )
        elif gpu.source.startswith("nvidia-smi"):
            mem_txt = (
                f"{gpu.mem_used_mb:.0f}/{gpu.mem_total_mb:.0f} MiB"
                if gpu.mem_total_mb
                else f"{gpu.mem_used_mb:.0f} MiB"
            )
            temp_txt = f"{gpu.temp_c:.1f}°C" if gpu.temp_available else "N/A"
            freq_txt = f"{gpu.freq_mhz} MHz" if gpu.freq_available else "N/A"
            self.perf_gpu_lbl.set_text(
                f"GPU (nvidia-smi aggregate):   {gpu.busy_pct:.1f}%"
                f"   |   Memory: {mem_txt}"
                f"   |   Temp: {temp_txt}"
                f"   |   Clock: {freq_txt}"
                f"   |   Compute apps: {gpu.clients} (global; per-process "
                "memory appears in the process inspector)"
            )
        elif gpu.engines:
            eng_strs = [f"{k}: {v:.1f}%" for k, v in gpu.engines.items()]
            rc6_txt = f"{gpu.rc6_pct:.1f}%" if gpu.rc6_available else "N/A"
            temp_txt = f"{gpu.temp_c:.1f}°C" if gpu.temp_available else "N/A"
            freq_txt = f"{gpu.freq_mhz} MHz" if gpu.freq_available else "N/A"
            self.perf_gpu_lbl.set_text(
                f"GPU Engines ({gpu.driver} DRM fdinfo):   "
                + "   |   ".join(eng_strs)
                + f"   |   GPU Mem (clients): {gpu.mem_used_mb:.1f} MiB"
                + f"   |   Clients: {gpu.clients}"
                + f"   |   Clock: {freq_txt}"
                + f"   |   Temp: {temp_txt}"
                + f"   |   RC6 Deep Idle: {rc6_txt}"
            )
        else:
            self.perf_gpu_lbl.set_text(
                f"{gpu.name} ({gpu.driver}): no DRM fdinfo engine counters for visible clients. "
                f"Source: {gpu.source}. GPU Mem (clients): {gpu.mem_used_mb:.1f} MiB."
            )

        me = perf["mem_extra"]
        zswap_txt = f"{me['Zswap']} kB" if me["Zswap"] >= 0 else "N/A (not exposed)"
        psi = perf.get("psi", {})

        def psi_value(resource: str, kind: str = "some") -> str:
            value = psi.get(resource, {}).get(f"{kind}_avg10")
            return "N/A" if value is None else f"{value:.2f}%"

        psi_txt = (
            f"PSI now: CPU {psi_value('cpu')}  |  "
            f"Memory {psi_value('memory')} (full {psi_value('memory', 'full')})  |  "
            f"IO {psi_value('io')} (full {psi_value('io', 'full')})"
        )
        self.perf_sys_lbl.set_text(
            f"Context Switches: {perf['ctxt_s']:.0f}/s   |   Interrupts: {perf['intr_s']:.0f}/s   |   "
            f"Procs: {perf['procs_running']} running / {perf['procs_blocked']} blocked   |   "
            f"Dirty Pages: {me['Dirty']} kB   |   Slab: {me['Slab'] // 1024} MiB   |   "
            f"Zswap: {zswap_txt}   |   Vault (~/.important): {perf['vault']['status']}\n"
            f"{psi_txt}"
        )

        # 4. Page-specific heavy sampling. Process/port scans run only while
        #    their page is visible. They run on a worker thread so a 0.5 s
        #    refresh does not block typing, scrolling or button clicks.
        if page in ("processes", "ports"):
            if page == "ports":
                self._update_net_summary(perf)
            if self._sync_sampling:
                ports_list, pid_ports = self.ports_collector.sample()
                self.alerts.check_ports(ports_list)
                if page == "processes":
                    flat, grouped = self.proc_collector.sample(
                        pid_ports=pid_ports,
                        hide_kernel_threads=self._hide_kthreads,
                    )
                    self._update_process_table(flat, grouped)
                else:
                    self._update_port_table(ports_list)
            else:
                self._start_io_snapshot(page)
        elif page == "services":
            self._refresh_services_tab()
        elif page == "power":
            self._refresh_power_tab()
        elif page == "audio":
            self._refresh_audio_tab()
        elif page == "hardware":
            self._refresh_hardware_live(perf)

    def _start_io_snapshot(self, page: str) -> None:
        if self._io_worker_busy:
            return
        self._io_worker_busy = True
        hide_threads = self._hide_kthreads

        def worker() -> None:
            try:
                ports, pid_ports = self.ports_collector.sample()
                flat: list[dict] = []
                grouped: list[dict] = []
                if page == "processes":
                    flat, grouped = self.proc_collector.sample(
                        pid_ports=pid_ports,
                        hide_kernel_threads=hide_threads,
                    )
                payload = (page, ports, flat, grouped, None)
            except Exception as exc:
                payload = (page, [], [], [], str(exc))
            GLib.idle_add(self._finish_io_snapshot, *payload)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_io_snapshot(
        self,
        page: str,
        ports: list[dict],
        flat: list[dict],
        grouped: list[dict],
        error: str | None,
    ) -> bool:
        self._io_worker_busy = False
        if error:
            self._set_status(f"Sampling failed: {error}")
            return False
        if page != self.stack.get_visible_child_name():
            return False
        self.alerts.check_ports(ports)
        if page == "processes":
            self._update_process_table(flat, grouped)
        elif page == "ports":
            self._update_port_table(ports)
        return False

    def _update_process_table(
        self, flat_procs: list[dict], grouped_procs: list[dict]
    ) -> None:
        if self._proc_mode == "grouped":
            target_procs = grouped_procs
            self._group_pids_map = {g["pid"]: g["pids"] for g in grouped_procs}
        elif self._proc_mode == "tree":
            self._group_pids_map = {p["pid"]: [p["pid"]] for p in flat_procs}
            self._update_process_tree(flat_procs)
            if self._selected_pid is not None:
                self._refresh_process_inspector(self._selected_pid)
            return
        else:
            target_procs = flat_procs
            self._group_pids_map = {p["pid"]: [p["pid"]] for p in target_procs}

        seen_pids: set[int] = set()
        for p in target_procs:
            pid = p["pid"]
            seen_pids.add(pid)
            row_vals = self._proc_row_tuple(p)
            if pid in self._proc_iters:
                it = self._proc_iters[pid]
                for col_i, v in enumerate(row_vals):
                    self.proc_store.set_value(it, col_i, v)
            else:
                self._proc_iters[pid] = self.proc_store.append(row_vals)
        for dead in list(self._proc_iters.keys()):
            if dead not in seen_pids:
                self.proc_store.remove(self._proc_iters.pop(dead))

        if self._selected_pid is not None:
            self._refresh_process_inspector(self._selected_pid)

    def _update_process_tree(self, flat_procs: list[dict]) -> None:
        by_pid = {p["pid"]: p for p in flat_procs}
        keep: set[int] | None = None
        if self._proc_query:
            keep = {
                p["pid"]
                for p in flat_procs
                if self._proc_matches(p, self._proc_query)
            }
            # Keep every ancestor of a match so the branch remains navigable.
            for pid in list(keep):
                current = by_pid.get(pid)
                while current is not None:
                    ppid = current["ppid"]
                    if ppid in keep or ppid not in by_pid:
                        break
                    keep.add(ppid)
                    current = by_pid.get(ppid)
        children: dict[int, list[int]] = {}
        roots: list[int] = []
        for p in flat_procs:
            pid = p["pid"]
            if keep is not None and pid not in keep:
                continue
            ppid = p["ppid"]
            if ppid in by_pid and ppid != pid and (keep is None or ppid in keep):
                children.setdefault(ppid, []).append(pid)
            else:
                roots.append(pid)

        by_cpu = lambda pid: by_pid[pid]["cpu"]
        roots.sort(key=by_cpu, reverse=True)
        for child_list in children.values():
            child_list.sort(key=by_cpu, reverse=True)

        self._restoring_tree = True
        self.proc_tree_store.clear()
        self._tree_iters.clear()

        def add_branch(parent: Gtk.TreeIter | None, pid: int) -> None:
            tree_iter = self.proc_tree_store.append(
                parent, self._proc_row_tuple(by_pid[pid])
            )
            self._tree_iters[pid] = tree_iter
            for child in children.get(pid, []):
                add_branch(tree_iter, child)

        for root in roots:
            add_branch(None, root)
        self.proc_tree_view.expand_all()
        for pid in list(self._tree_collapsed):
            tree_iter = self._tree_iters.get(pid)
            if tree_iter is not None:
                self.proc_tree_view.collapse_row(
                    self.proc_tree_store.get_path(tree_iter)
                )
        self._restoring_tree = False
        if self._selected_pid is not None:
            self._select_pid_in_tree(self._selected_pid)

    def _select_pid_in_tree(self, pid: int) -> None:
        tree_iter = self._tree_iters.get(pid)
        if tree_iter is not None:
            try:
                self.proc_tree_view.get_selection().select_iter(tree_iter)
            except (TypeError, ValueError):
                pass

    def _on_process_tree_expanded(
        self, _view: Gtk.TreeView, tree_iter: Gtk.TreeIter, _path
    ) -> None:
        if self._restoring_tree:
            return
        pid = int(self.proc_tree_store[tree_iter][0])
        self._tree_collapsed.discard(pid)
        self._save_layout()

    def _on_process_tree_collapsed(
        self, _view: Gtk.TreeView, tree_iter: Gtk.TreeIter, _path
    ) -> None:
        if self._restoring_tree:
            return
        pid = int(self.proc_tree_store[tree_iter][0])
        self._tree_collapsed.add(pid)
        self._save_layout()

    def _update_port_table(self, ports_list: list[dict]) -> None:
        self.port_store.clear()
        for pt in ports_list:
            self.port_store.append(
                [
                    pt["proto"],
                    pt["port"],
                    pt["local"],
                    pt["remote"],
                    pt["state"],
                    pt["pid"],
                    pt["process"],
                    pt["unit"],
                    pt["purpose"],
                    pt["is_listening"],
                ]
            )

    def _update_net_summary(self, perf: dict) -> None:
        ni = perf["net_info"]
        rx_mb, tx_mb, errs, drops = perf["net_totals_mb"]
        wifi = ni["wifi"]
        wifi_txt = (
            f"{wifi['ssid']} ({wifi['signal']}%, {wifi['rate']})"
            if wifi["ssid"] != "N/A"
            else "N/A (no NetworkManager data)"
        )
        self.net_summary_lbl.set_text(
            f"Active Interface: {ni['iface']} ({ni['local_ip']})   |   Gateway: {ni['gateway']}   |   "
            f"DNS: {ni['dns']}   |   Wi-Fi: {wifi_txt}   |   "
            f"Interface Totals: RX {rx_mb} MiB / TX {tx_mb} MiB (Errors: {errs}, Drops: {drops})"
        )

    def _select_pid_in_view(self, pid: int) -> None:
        """Re-select a PID after a tree-mode rebuild without changing sort order."""
        try:
            for row in self.proc_sort:
                if int(row[0]) == pid:
                    self.proc_view.get_selection().select_iter(row.iter)
                    return
        except (TypeError, ValueError):
            return

    def _refresh_current_page(self) -> None:
        page = self.stack.get_visible_child_name()
        if page == "doctor":
            self._refresh_doctor()
        elif page == "logs":
            self._refresh_logs()
        elif page == "hardware":
            self._refresh_hardware_static()
        self._refresh_all()

    @staticmethod
    def _short_state(state: str) -> str:
        return {
            "running": "Run",
            "sleeping": "Sleep",
            "disk-sleep": "Disk",
            "wake-kill": "Wake",
            "waking": "Wake",
            "stopped": "Stop",
            "tracing-stop": "TStop",
            "zombie": "Zombie",
            "dead": "Dead",
            "idle": "Idle",
            "parked": "Park",
            "locked": "Lock",
        }.get(state, state[:6])

    @staticmethod
    def _proc_row_tuple(p: dict) -> list:
        return [
            p["pid"],
            p["ppid"],
            p["name"],
            p["user"],
            p["cpu"],
            f"{p['cpu']:.1f}%" if p.get("cpu_available") else "-",
            p["gpu"],
            f"{p['gpu']:.1f}%" if p["gpu"] > 0 else "-",
            p["mem_mb"],
            f"{p['mem_mb']:.1f} MB",
            p["disk_kbs"],
            (
                f"{p['disk_kbs']:.1f} KB/s"
                if p.get("disk_available") and p["disk_kbs"] > 0
                else ("0.0" if p.get("disk_available") else "-")
            ),
            p["wakeups_s"],
            (f"{p['wakeups_s']:.1f}/s" if p.get("ctx_available") else "-"),
            p["impact_score"],
            p["impact"],
            p["threads"],
            TaskManagerWindow._short_state(p["state"]),
            p["ports"],
            p["unit"],
            p["cmd"],
        ]

    def _refresh_process_inspector(self, pid: int) -> None:
        d = self.proc_collector.get_process_details(pid)
        fd_count = int(d.get("open_fd_count", len(d["open_fds"])))
        fd_note = " (first 120 shown)" if fd_count > len(d["open_fds"]) else ""
        fd_text = "unavailable" if d.get("fds_denied") else f"{fd_count}{fd_note}"
        sock_text = (
            f"{len(d['connections'])} (permission denied)"
            if d.get("connections_denied")
            else str(len(d["connections"]))
        )
        thread_text = (
            "unavailable" if d.get("threads_denied") else str(len(d["threads"]))
        )
        gpu_mem = self.gpu_collector.proc_gpu_mem_mb.get(d["pid"])
        gpu_mem_text = f"{gpu_mem:.1f} MiB" if gpu_mem is not None else "N/A"
        self.insp_header.set_text(
            f"Inspecting PID {d['pid']} ({d['name']})   |   Unit: {d['unit']}   |   "
            f"Threads: {thread_text}   |   Sockets: {sock_text}   |   "
            f"Open FDs: {fd_text}   |   GPU Mem: {gpu_mem_text}   |   "
            f"OOM Score: {d['oom_score']}   |   CWD: {d['cwd']}"
        )
        self.thread_store.clear()
        for t in d["threads"]:
            cpu_known = bool(t.get("cpu_known"))
            self.thread_store.append(
                [
                    t["tid"],
                    t["name"],
                    t["state"],
                    t["cpu_pct"] if cpu_known else 0.0,
                    f"{t['cpu_pct']:.1f}%" if cpu_known else "N/A",
                    t["core"],
                    f"{t['user_s']:.2f}s",
                    f"{t['sys_s']:.2f}s",
                    t["total_s"],
                ]
            )
        self.pconn_store.clear()
        if d.get("connections_denied"):
            self.pconn_store.append(
                [0, "-", "Permission denied", "owned by another user", "-"]
            )
        else:
            for c in d["connections"]:
                self.pconn_store.append(
                    [c["fd"], c["proto"], c["local"], c["remote"], c["state"]]
                )
        self.pfd_store.clear()
        if d.get("fds_denied"):
            self.pfd_store.append(
                [0, "FD list unavailable (permission denied or process exited)"]
            )
        else:
            for fd_num, target in d["open_fds"]:
                self.pfd_store.append([fd_num, target])
        self.penv_store.clear()
        self.penv_store.append(["Command Line", d["cmdline"]])
        self.penv_store.append(["Executable", d["exe"]])
        self.penv_store.append(["Working Directory", d["cwd"]])
        self.penv_store.append(["Systemd Unit / Cgroup", d["unit"]])
        if d.get("environ_denied"):
            self.penv_store.append(
                ["Permission", "Environment not readable by this user"]
            )
        else:
            for k, v in d["environ"]:
                self.penv_store.append([k, v])

    def _refresh_services_tab(self) -> None:
        self.svc_store.clear()
        for scope in ("system", "user"):
            for s in ServicesCollector.get_services(scope):
                mem = s.get("memory_mb")
                cpu = s.get("cpu_s")
                io_r = s.get("io_read_mb")
                io_w = s.get("io_write_mb")
                mem_txt = f"{mem:.1f} MB" if mem is not None else "-"
                cpu_txt = f"{cpu:.2f}s" if cpu is not None else "-"
                if io_r is not None or io_w is not None:
                    io_txt = f"R {io_r or 0:.1f}/W {io_w or 0:.1f} MB"
                else:
                    io_txt = "-"
                self._svc_io_sources[(s["scope"], s["unit"])] = s.get("io_source", "")
                self._svc_control_groups[(s["scope"], s["unit"])] = s.get(
                    "control_group", ""
                )
                self.svc_store.append(
                    [
                        s["unit"],
                        s["scope"],
                        s["load"],
                        s["active"],
                        s["sub"],
                        float(mem) if mem is not None else -1.0,
                        mem_txt,
                        float(cpu) if cpu is not None else -1.0,
                        cpu_txt,
                        io_txt,
                        s["description"],
                    ]
                )

        self.timer_store.clear()
        for t in ServicesCollector.get_timers():
            self.timer_store.append(
                [
                    t["unit"],
                    t["activates"],
                    t["scope"],
                    t["next"],
                    t["last"],
                    t["State"],
                ]
            )

        self.auto_store.clear()
        for a in ServicesCollector.get_hyprland_autostart_status():
            self.auto_store.append(
                [
                    a["command"],
                    a["target"],
                    a["status"],
                    a["pids"],
                    a["mem_mb"],
                    f"{a['mem_mb']:.1f} MB",
                ]
            )

        self.hypr_store.clear()
        for c in ServicesCollector.get_hyprland_clients():
            self.hypr_store.append(
                [
                    c["workspace"],
                    c["class"],
                    c["title"],
                    c["pid"],
                    c["cpu"],
                    f"{c['cpu']:.1f}%",
                    c["mem_mb"],
                    f"{c['mem_mb']:.1f} MB",
                    c["protocol"],
                    c["layout"],
                    c["address"],
                ]
            )

    @staticmethod
    def _battery_limit_text() -> str:
        batteries = sorted(Path("/sys/class/power_supply").glob("BAT*"))
        if not batteries:
            return "Battery charge limit: N/A (no battery exposed by the kernel)"
        parts: list[str] = []
        for bat in batteries:
            end_file = bat / "charge_control_end_threshold"
            start_file = bat / "charge_control_start_threshold"
            try:
                end = end_file.read_text(encoding="utf-8").strip()
            except OSError:
                end = ""
            try:
                start = start_file.read_text(encoding="utf-8").strip()
            except OSError:
                start = ""
            if end:
                text = f"{bat.name}: stop at {end}%"
                if start:
                    text += f" (start at {start}%)"
                parts.append(text)
            else:
                parts.append(
                    f"{bat.name}: N/A (firmware exposes no "
                    "charge_control_end_threshold)"
                )
        return "Battery charge limit: " + "  |  ".join(parts)

    def _rapl_text(self) -> str:
        if (
            self._privileged_rapl_text
            and time.monotonic() - self._privileged_rapl_ts < 30.0
        ):
            return self._privileged_rapl_text
        sample = self.rapl_collector.sample()
        parts = [
            f"{d['name']}: {d['watts']:.1f} W"
            for d in sample["domains"]
            if d.get("watts") is not None
        ]
        if parts:
            text = "RAPL live power: " + "  |  ".join(parts)
        else:
            reason = sample.get("reason", "")
            if not reason and sample["domains"]:
                reason = sample["domains"][0].get("reason", "unavailable")
            text = f"RAPL live power: N/A ({reason or 'unavailable'})"
        try:
            limit = int(
                Path(
                    "/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw"
                )
                .read_text(encoding="utf-8")
                .strip()
            )
            text += f"  |  Package limit: {limit / 1e6:.0f} W"
        except (OSError, ValueError):
            pass
        return text

    def _on_authorize_rapl(self, _btn: Gtk.Button) -> None:
        if not self.privileged_client.available:
            self._set_status(self.privileged_client.status_text())
            return
        self.rapl_privileged_btn.set_sensitive(False)
        self._set_status(
            "Waiting for PolicyKit authorization to read RAPL energy counters..."
        )

        def worker() -> None:
            rows, error = self.privileged_client.rapl_watts()
            GLib.idle_add(self._finish_privileged_rapl, rows, error)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_privileged_rapl(
        self, rows: list | None, error: str
    ) -> bool:
        if self.privileged_client.available:
            self.rapl_privileged_btn.set_sensitive(True)
        if error:
            self._set_status(error)
            return False
        parts = [
            f"{row['name']}: {row['watts']:.1f} W"
            for row in (rows or [])
            if row.get("watts") is not None
        ]
        if not parts:
            reason = next(
                (
                    row.get("reason", "")
                    for row in (rows or [])
                    if row.get("reason")
                ),
                "energy_uj is not readable",
            )
            self._set_status(f"RAPL authorized, but no watts are available: {reason}.")
            return False
        text = "RAPL live power (PolicyKit): " + "  |  ".join(parts)
        try:
            limit = int(
                Path(
                    "/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw"
                )
                .read_text(encoding="utf-8")
                .strip()
            )
            text += f"  |  Package limit: {limit / 1e6:.0f} W"
        except (OSError, ValueError):
            pass
        self._privileged_rapl_text = text
        self._privileged_rapl_ts = time.monotonic()
        self.rapl_lbl.set_text(text)
        self._set_status("RAPL live power updated via PolicyKit.")
        return False

    def _refresh_power_tab(self) -> None:
        ps = self.power_collector.sample()
        self._last_tunables = ps["tunables"]
        cs_parts = [f"{k}: {v:.1f}%" for k, v in sorted(ps["cstates_pct"].items())]
        self.cstate_lbl.set_text(
            "CPU C-State Share of Idle Time (aggregate across CPUs; deep C7/C8/C10 = maximum savings):    "
            + (
                "   |   ".join(cs_parts)
                if cs_parts
                else "N/A (no cpuidle data exposed)"
            )
            + f"    |    Bad Tunables: {ps['bad_tunables_count']}"
        )
        self.rapl_lbl.set_text(self._rapl_text())
        self.battery_limit_lbl.set_text(self._battery_limit_text())
        self.irq_store.clear()
        for irq in ps["irqs"]:
            self.irq_store.append(
                [
                    irq["irq"],
                    irq["rate"],
                    f"{irq['rate']:.1f} /s",
                    irq["subsystem"],
                    irq["description"],
                ]
            )
        self.tun_store.clear()
        for t in ps["tunables"]:
            badge = "🟢 GOOD" if t["status"] == "GOOD" else "🔴 BAD"
            self.tun_store.append(
                [badge, t["category"], t["name"], t["current"], t["target"], t["why"]]
            )
        self._maybe_refresh_power_profile_ui()

    def _on_tune_all_power(self, _btn: Gtk.Button) -> None:
        if not self._last_tunables:
            self._last_tunables = PowerAndWakeupCollector.scan_powertop_tunables()
        _, msg = PowerAndWakeupCollector.apply_all_bad_tunables(self._last_tunables)
        self.power_collector.invalidate_tunables_cache()
        self._set_status(msg)
        GLib.timeout_add(
            1200, lambda: (self._refresh_power_tab(), self._refresh_doctor(), False)[2]
        )

    def _on_power_profile_clicked(self, profile: str) -> None:
        ok, msg = PowerProfileController.set_profile(profile)
        self._set_status(msg)
        self._refresh_power_profile_ui()
        self._refresh_power_tab()

    def _on_auto_power_toggled(self, button: Gtk.ToggleButton) -> None:
        self.auto_power_enabled = button.get_active()
        self._auto_power_target = None
        self._set_status(
            "Auto power enabled: Balanced on AC, Power Saver on battery."
            if self.auto_power_enabled
            else "Auto power disabled."
        )
        if self.auto_power_enabled:
            self._refresh_all()

    def _apply_auto_power(self, perf: dict) -> None:
        if not self.auto_power_enabled:
            return
        battery = perf.get("battery", {})
        if not battery.get("present"):
            return
        target = "balanced" if battery.get("ac_online") else "power-saver"
        if target == self._auto_power_target:
            return
        if target not in PowerProfileController.list_profiles():
            return
        ok, msg = PowerProfileController.set_profile(target)
        if ok:
            self._auto_power_target = target
            self._set_status(f"Auto power: {msg}")
            self._refresh_power_profile_ui()

    def _refresh_power_profile_ui(self) -> None:
        current = PowerProfileController.get_current()
        self._last_profile_ts = time.monotonic()
        if current is None:
            self.profile_status_lbl.set_text(
                "Unavailable (power-profiles-daemon is not running)"
            )
            for b in self.profile_buttons.values():
                b.set_visible(False)
                b.set_sensitive(False)
            return
        self.profile_status_lbl.set_text(f"Current: {current}")
        for name, button in self.profile_buttons.items():
            button.set_visible(True)
            button.set_sensitive(True)
            if name == current:
                button.add_css_class("tm-profile-active")
            else:
                button.remove_css_class("tm-profile-active")

    def _maybe_refresh_power_profile_ui(self) -> None:
        if time.monotonic() - self._last_profile_ts >= 5.0:
            self._refresh_power_profile_ui()

    def _refresh_audio_tab(self) -> None:
        acb = HardwareAndMediaCollector.get_audio_camera_bluetooth()
        self.audio_store.clear()
        for s in acb["sinks"]:
            self.audio_store.append(
                [
                    "🔊 Audio Output (Sink)",
                    s["id"],
                    s["name"],
                    f"{s['vol_pct']}% {'(MUTED)' if s['muted'] else ''}",
                    "★ Default Output" if s["default"] else "Available",
                    s["warning"],
                ]
            )
        for s in acb["sources"]:
            self.audio_store.append(
                [
                    "🎙️ Audio Input (Mic)",
                    s["id"],
                    s["name"],
                    f"{s['vol_pct']}% {'(MUTED)' if s['muted'] else ''}",
                    "★ Default Mic" if s["default"] else "Available",
                    s["warning"],
                ]
            )
        for idx, st in enumerate(acb["streams"], start=1):
            self.audio_store.append(
                [
                    "🎵 Active Audio Stream",
                    idx,
                    st["stream"],
                    "Streaming",
                    "Active Client",
                    "Using PipeWire Audio",
                ]
            )
        for idx, cam in enumerate(acb["cameras"], start=1):
            self.audio_store.append(
                [
                    "📷 Webcam (V4L2)",
                    idx,
                    f"{cam['name']} ({cam['node']})",
                    "🔴 IN USE" if cam["in_use"] else "🟢 Idle",
                    cam["used_by"],
                    "Camera capture active!"
                    if cam["in_use"]
                    else "No visible process capturing video",
                ]
            )
        for rf in acb["rfkill"]:
            self.audio_store.append(
                [
                    f"📡 Radio ({rf['type']})",
                    int(rf["id"] or 0),
                    rf["device"],
                    f"Soft: {rf['soft']} | Hard: {rf['hard']}",
                    "Blocked" if rf["soft"] == "blocked" else "Unblocked",
                    "Radio disabled by software"
                    if rf["soft"] == "blocked"
                    else "Radio active",
                ]
            )

    def _refresh_hardware_static(self) -> None:
        pci_list, usb_list = HardwareAndMediaCollector.get_pci_and_usb_devices()
        self.pci_store.clear()
        for p in pci_list:
            self.pci_store.append(
                [p["slot"], p["name"], p["driver"], p["power_state"], p["power_ctrl"]]
            )
        self.usb_store.clear()
        for u in usb_list:
            self.usb_store.append([u["bus_dev"], u["usb_id"], u["name"]])

        self.kmod_store.clear()
        for m in HardwareAndMediaCollector.get_kernel_modules():
            self.kmod_store.append(
                [
                    m["name"],
                    m["size_kb"],
                    f"{m['size_kb']:.1f} KB",
                    m["instances"],
                    m["used_by"],
                ]
            )
        self.cap_store.clear()
        for cap in CapabilityCollector.get_capabilities():
            self.cap_store.append(
                [
                    cap["feature"],
                    cap["status"],
                    cap["details"],
                    cap["command"],
                ]
            )

    def _refresh_privileged_controls(self) -> None:
        if not self.privileged_client.available:
            self.privileged_client = PrivilegedClient()
        available = self.privileged_client.available
        status = self.privileged_client.status_text()
        for button in (
            self.svc_privileged_btn,
            self.rapl_privileged_btn,
        ):
            button.set_sensitive(available)
            button.set_tooltip_text(
                status
                if not available
                else "Run with PolicyKit; authorization is requested once."
            )

    def _refresh_ebpf_status(self) -> None:
        info = self.ebpf_runner.detect()
        if self.ebpf_runner.is_running:
            probe = self.ebpf_runner.current_probe
            label = probe.label if probe else "probe"
            self.ebpf_status_lbl.set_text(
                f"Running {label}... Press Stop to end capture. "
                "Output is read from the live bpftrace process."
            )
            self.ebpf_start_btn.set_sensitive(False)
            self.ebpf_stop_btn.set_sensitive(True)
            self._update_ebpf_command(info)
            return
        can_start = bool(
            info["bpftrace"]
            and info["btf"]
            and (info["root"] or self.privileged_client.available)
        )
        if info["can_run"]:
            self.ebpf_status_lbl.set_text(
                f"bpftrace ready at {info['bpftrace']}; kernel BTF present; "
                "root confirmed. Select a probe and press Start."
            )
        elif info["bpftrace"] and info["btf"] and self.privileged_client.available:
            self.ebpf_status_lbl.set_text(
                f"bpftrace ready at {info['bpftrace']}; kernel BTF present. "
                "PolicyKit authorization will be requested when Start is pressed."
            )
        else:
            self.ebpf_status_lbl.set_text(
                "eBPF unavailable: " + info["reason"] + ". "
                "Install the missing tools or the PolicyKit helper."
            )
        self.ebpf_start_btn.set_sensitive(can_start)
        self.ebpf_stop_btn.set_sensitive(False)
        self._update_ebpf_command(info)

    def _update_ebpf_command(self, info: dict | None = None) -> None:
        if info is None:
            info = self.ebpf_runner.detect()
        index = self.ebpf_probe_dropdown.get_selected()
        if not (0 <= index < len(PROBES)):
            index = 0
        probe = PROBES[index]
        if not info["bpftrace"]:
            text = "Install prerequisite: sudo pacman -S bpftrace"
        elif not info["btf"]:
            text = (
                "Kernel prerequisite: CONFIG_DEBUG_INFO_BTF is missing "
                "(/sys/kernel/btf/vmlinux)."
            )
        elif not info["root"]:
            if self.privileged_client.available:
                text = (
                    "Root authorization required. Press Start to use the "
                    f"PolicyKit helper ({self.privileged_client.helper}); "
                    f"direct command: {probe.command()}"
                )
            else:
                text = (
                    f"Root required. Run in a terminal: {probe.command()} "
                    "or install the PolicyKit helper."
                )
        else:
            text = f"Ready. Equivalent terminal command: {probe.command()}"
        self.ebpf_command_lbl.set_text(text)

    def _on_ebpf_start(self, _btn: Gtk.Button) -> None:
        index = self.ebpf_probe_dropdown.get_selected()
        if not (0 <= index < len(PROBES)):
            return
        probe = PROBES[index]
        self._ebpf_active_probe = probe.label
        self._ebpf_stopping = False
        info = self.ebpf_runner.detect()
        command = None
        allow_nonroot = False
        if not info["root"]:
            if self.privileged_client.available:
                command = self.privileged_client.bpftrace_command(probe.key)
                allow_nonroot = True
            if command is None:
                self._ebpf_active_probe = ""
                self.ebpf_status_lbl.set_text(
                    "Root is required and the PolicyKit helper is not available. "
                    + self.privileged_client.status_text()
                )
                return
        ok, msg = self.ebpf_runner.start(
            probe.key,
            self._ebpf_line_from_thread,
            self._ebpf_exit_from_thread,
            allow_nonroot=allow_nonroot,
            command=command,
        )
        self.ebpf_status_lbl.set_text(msg)
        if ok:
            self.ebpf_start_btn.set_sensitive(False)
            self.ebpf_stop_btn.set_sensitive(True)
        else:
            self._ebpf_active_probe = ""
            self.ebpf_start_btn.set_sensitive(
                bool(self.ebpf_runner.detect()["can_run"])
            )
            self.ebpf_stop_btn.set_sensitive(False)

    def _sync_ebpf_buttons(self) -> None:
        info = self.ebpf_runner.detect()
        running = self.ebpf_runner.is_running
        self.ebpf_start_btn.set_sensitive(bool(info["can_run"]) and not running)
        self.ebpf_stop_btn.set_sensitive(running)
        self._update_ebpf_command(info)

    def _on_ebpf_stop(self, _btn: Gtk.Button) -> None:
        self._ebpf_stopping = True
        msg = self.ebpf_runner.stop()
        self._ebpf_active_probe = ""
        self.ebpf_status_lbl.set_text(msg)
        self._sync_ebpf_buttons()

    def _ebpf_line_from_thread(self, line: str) -> None:
        GLib.idle_add(self._append_ebpf_line, line)

    def _append_ebpf_line(self, line: str) -> bool:
        stamp = time.strftime("%H:%M:%S")
        self.ebpf_store.append(
            [stamp, self._ebpf_active_probe or "bpftrace", line]
        )
        while len(self.ebpf_store) > 2000:
            first = self.ebpf_store.get_iter_first()
            if first is None:
                break
            self.ebpf_store.remove(first)
        return False

    def _ebpf_exit_from_thread(self, code: int) -> None:
        GLib.idle_add(self._on_ebpf_exit, code)

    def _on_ebpf_exit(self, code: int) -> bool:
        self._ebpf_active_probe = ""
        if self._ebpf_stopping:
            self._ebpf_stopping = False
            self.ebpf_status_lbl.set_text("Stopped the eBPF probe.")
        elif code == 0:
            self.ebpf_status_lbl.set_text("Probe ended.")
        else:
            self.ebpf_status_lbl.set_text(
                f"Probe ended with exit status {code}. Check that bpftrace "
                "supports this kernel/BTF and that you have root/CAP_BPF."
            )
        self._sync_ebpf_buttons()
        return False

    @staticmethod
    def _fan_device_label(device: dict) -> str:
        mode = device.get("enable", -1)
        mode_txt = {
            0: "no control",
            1: "manual",
            2: "automatic",
        }.get(mode, f"mode {mode}" if mode >= 0 else "mode N/A")
        return (
            f"{device.get('chip', 'fan')} ({device.get('id', '?')}) "
            f"pwm={device.get('pwm', -1)}/255, {mode_txt}"
        )

    def _refresh_hardware_controls(self) -> None:
        self.fan_devices = self.fan_control.discover()
        labels = [self._fan_device_label(device) for device in self.fan_devices]
        self.fan_dropdown.set_model(
            Gtk.StringList.new(labels if labels else ["Unavailable"])
        )
        if not self.fan_devices:
            self.fan_status_lbl.set_text(
                "Fan control unavailable: no pwm* outputs are exposed by hwmon. "
                "Nothing is written; fan RPM remains visible read-only in the "
                "Sensors tab."
            )
            self.fan_apply_btn.set_sensitive(False)
            self.fan_manual_btn.set_sensitive(False)
            self.fan_auto_btn.set_sensitive(False)
        else:
            writable = any(device["writable"] for device in self.fan_devices)
            enable_writable = any(
                device.get("enable_writable") for device in self.fan_devices
            )
            if writable:
                self.fan_status_lbl.set_text(
                    f"Fan control ready: {len(self.fan_devices)} pwm output(s). "
                    "Apply Curve writes the selected fan; root or a udev rule is "
                    "still required for the write itself."
                )
            else:
                self.fan_status_lbl.set_text(
                    f"Fan outputs found ({len(self.fan_devices)}), but pwm* is "
                    "read-only for this user. No writes will occur; run as root "
                    "or add a udev rule."
                )
            self.fan_apply_btn.set_sensitive(writable)
            self.fan_manual_btn.set_sensitive(enable_writable)
            self.fan_auto_btn.set_sensitive(enable_writable)

        self.battery_devices = self.battery_control.discover()
        if not self.battery_devices:
            self.battery_status_lbl.set_text(
                "Battery charge-threshold control unavailable: the firmware "
                "exposes no charge_control_* files. The Power page still shows "
                "the threshold as N/A."
            )
            self.battery_apply_btn.set_sensitive(False)
        else:
            device = self.battery_devices[0]
            if device.get("start", -1) >= 0:
                self.battery_start_spin.set_value(device["start"])
            if device.get("end", -1) >= 0:
                self.battery_end_spin.set_value(device["end"])
            if device.get("writable"):
                self.battery_status_lbl.set_text(
                    f"Battery threshold ready for {device.get('id', 'battery')}: "
                    f"start {device.get('start', -1)}%, stop "
                    f"{device.get('end', -1)}%. Apply writes the sysfs files."
                )
                self.battery_apply_btn.set_sensitive(True)
            else:
                reason = device.get("reason") or (
                    "read-only for this user; root or a udev rule is required"
                )
                self.battery_status_lbl.set_text(
                    f"Battery threshold files found for "
                    f"{device.get('id', 'battery')}, but writes are unavailable: "
                    f"{reason}. No writes will occur."
                )
                self.battery_apply_btn.set_sensitive(False)

    def _selected_fan_device(self) -> dict | None:
        index = self.fan_dropdown.get_selected()
        if 0 <= index < len(self.fan_devices):
            return self.fan_devices[index]
        return None

    def _on_fan_apply(self, _btn: Gtk.Button) -> None:
        device = self._selected_fan_device()
        if device is None:
            self.fan_action_lbl.set_text("No writable fan output is available.")
            return
        points = [
            (float(temp.get_value()), int(pwm.get_value()))
            for temp, pwm in self.fan_curve_spins
        ]
        ok, msg = self.fan_control.apply_curve(device, points)
        self.fan_action_lbl.set_text(msg)
        self._refresh_hardware_controls()
        self.fan_action_lbl.set_text(msg)

    def _on_fan_manual(self, _btn: Gtk.Button) -> None:
        device = self._selected_fan_device()
        if device is None:
            self.fan_action_lbl.set_text("No writable fan output is available.")
            return
        ok, msg = self.fan_control.set_manual(device)
        self.fan_action_lbl.set_text(msg)
        self._refresh_hardware_controls()
        self.fan_action_lbl.set_text(msg)

    def _on_fan_auto(self, _btn: Gtk.Button) -> None:
        device = self._selected_fan_device()
        if device is None:
            self.fan_action_lbl.set_text("No writable fan output is available.")
            return
        ok, msg = self.fan_control.restore_auto(device)
        self.fan_action_lbl.set_text(msg)
        self._refresh_hardware_controls()
        self.fan_action_lbl.set_text(msg)

    def _on_battery_apply(self, _btn: Gtk.Button) -> None:
        if not self.battery_devices:
            self.battery_action_lbl.set_text(
                "No writable battery charge-threshold control is available."
            )
            return
        start = int(self.battery_start_spin.get_value())
        end = int(self.battery_end_spin.get_value())
        ok, msg = self.battery_control.apply(
            self.battery_devices[0], start, end
        )
        self.battery_action_lbl.set_text(msg)
        self._refresh_hardware_controls()
        self.battery_action_lbl.set_text(msg)

    def _refresh_hardware_live(self, perf: dict) -> None:
        if len(self.pci_store) == 0:
            self._refresh_hardware_static()
        self.sensor_store.clear()
        for s in HardwareAndMediaCollector.get_all_sensors():
            self.sensor_store.append([s["chip"], s["sensor"], s["type"], s["reading"]])
        self.blk_store.clear()
        v = perf["vault"]
        if v["exists"]:
            self.blk_store.append(
                [
                    "~/.important (Vault)",
                    "-",
                    "gocryptfs",
                    "fuse.gocryptfs",
                    "-",
                    "MOUNTED" if v["mounted"] else "LOCKED",
                    v["status"],
                ]
            )
        else:
            self.blk_store.append(
                [
                    "~/.important (Vault)",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    "Not configured (no ~/.important.encrypted directory)",
                ]
            )
        for b in perf["block_devices"]:
            mnt_model = b["mount"] if b["mount"] != "-" else b["model"]
            self.blk_store.append(
                [
                    b["name"],
                    b["size"],
                    b["type"],
                    b["fstype"],
                    b["used"],
                    b["use_pct"],
                    mnt_model,
                ]
            )
        self.smart_store.clear()
        for health in StorageHealthCollector.sample(perf["block_devices"]):
            self.smart_store.append(
                [
                    health["device"],
                    health["model"],
                    health["size"],
                    health["health"],
                    health["temperature"],
                    health["power_on_hours"],
                    health["percentage_used"],
                    health["note"],
                ]
            )

    # =========================================================================
    # RIGHT-CLICK DETAILS / COMMAND FOR EVERY TABLE, CHART AND PILL
    # =========================================================================
    def _install_context_menus(self) -> None:
        self._context_view_count = 0
        self._walk_for_context(self)

    def _walk_for_context(self, widget: Gtk.Widget) -> None:
        if isinstance(widget, Gtk.TreeView):
            self._attach_tree_context(widget)
            tm_columns = getattr(widget, "tm_columns", None)
            if tm_columns:
                titles = [column[0] for column in tm_columns]
            else:
                titles = [
                    (column.get_title() or f"Column {i + 1}")
                    for i, column in enumerate(widget.get_columns())
                ]
            self._context_views.append((widget, self._context_kind(titles)))
            self._context_view_count += 1
            return
        child = widget.get_first_child()
        while child is not None:
            self._walk_for_context(child)
            child = child.get_next_sibling()

    def _attach_tree_context(self, view: Gtk.TreeView) -> None:
        gesture = Gtk.GestureClick()
        gesture.set_button(3)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect("pressed", self._on_tree_button_pressed, view)
        view.add_controller(gesture)

    def _on_tree_button_pressed(
        self,
        _gesture: Gtk.GestureClick,
        n_press: int,
        x: float,
        y: float,
        view: Gtk.TreeView,
    ) -> None:
        if n_press != 1:
            return
        pos = view.get_path_at_pos(int(x), int(y))
        if not pos:
            return
        path = pos[0]
        view.get_selection().select_path(path)
        model = view.get_model()
        if model is None:
            return
        tree_iter = model.get_iter(path)
        if tree_iter is None:
            return
        raw_values = [
            model.get_value(tree_iter, i) for i in range(model.get_n_columns())
        ]
        tm_columns = getattr(view, "tm_columns", None)
        if tm_columns:
            titles = [column[0] for column in tm_columns]
            values = [
                model.get_value(tree_iter, int(column[1])) for column in tm_columns
            ]
        else:
            values = raw_values
            titles = [
                (column.get_title() or f"Column {i + 1}")
                for i, column in enumerate(view.get_columns())
            ]
        kind = self._context_kind(titles)
        details, command = self._describe_row(
            kind, values, titles, raw_values=raw_values
        )
        self._show_context_menu(view, int(x), int(y), details, command)

    def _attach_widget_context(
        self, widget: Gtk.Widget, details: str, command: str
    ) -> None:
        self._context_target_count += 1
        gesture = Gtk.GestureClick()
        gesture.set_button(3)
        gesture.connect(
            "pressed",
            lambda _g, n, x, y: (
                self._show_context_menu(widget, int(x), int(y), details, command)
                if n == 1
                else None
            ),
        )
        widget.add_controller(gesture)

    @staticmethod
    def _context_kind(titles: list[str]) -> str:
        t = set(titles)
        if "Thread ID (TID)" in t:
            return "thread"
        if "Port" in t and "Proto" in t:
            return "port"
        if "Service Unit" in t or "Systemd Unit" in t:
            return "service"
        if "Timer Unit" in t:
            return "timer"
        if "hyprland.lua Autostart Command" in t:
            return "autostart"
        if "Window Class" in t:
            return "window"
        if "IRQ #" in t:
            return "irq"
        if "Power Tunable" in t:
            return "tunable"
        if "Volume / State" in t:
            return "audio"
        if "PCI Slot" in t:
            return "pci"
        if "USB Bus / Device" in t:
            return "usb"
        if "Sensor Chip (hwmon)" in t:
            return "sensor"
        if "SMART Health" in t:
            return "smart"
        if "Device / Partition" in t:
            return "block"
        if "Kernel Module" in t:
            return "module"
        if "Timestamp" in t:
            return "log"
        if "Event" in t and "Probe" in t and "Time" in t:
            return "ebpf"
        if "Live Finding" in t and "Diagnostic Details" in t:
            return "doctor"
        if "Feature" in t and "Details / Prerequisite" in t:
            return "capability"
        if "PID" in t and ("Process" in t or "Command" in t):
            return "process"
        return "generic"

    @staticmethod
    def _clean_value(value: object) -> str:
        return "-" if value is None or str(value) == "" else str(value)

    def _describe_row(
        self,
        kind: str,
        values: list,
        titles: list[str],
        raw_values: list | None = None,
    ) -> tuple[str, str]:
        data = {titles[i]: values[i] for i in range(min(len(titles), len(values)))}
        raw_values = raw_values if raw_values is not None else values
        get = lambda key: self._clean_value(data.get(key, "-"))

        if kind == "process":
            pid = get("PID")
            name = get("Process")
            user = get("User")
            cpu = get("CPU %")
            mem = get("Memory")
            threads = get("Threads")
            state = get("State")
            unit = get("Unit")
            cmdline = get("Command")
            gpu_mem = None
            try:
                gpu_mem = self.gpu_collector.proc_gpu_mem_mb.get(int(pid))
            except (TypeError, ValueError):
                pass
            gpu_mem_txt = (
                f"{gpu_mem:.1f} MiB" if gpu_mem is not None else "N/A"
            )
            details = (
                f"{name} is a process with PID {pid}, owned by {user}. "
                f"It is currently {state}, using {cpu} CPU, {mem} memory and "
                f"{threads} threads. GPU memory: {gpu_mem_txt}. "
                f"Systemd unit: {unit}. Command line: {cmdline}"
            )
            command = (
                f"ps -p {shlex.quote(pid)} "
                "-o pid,ppid,user,stat,pcpu,pmem,rss,etime,comm,args"
            )
            return details, command

        if kind == "thread":
            tid = get("Thread ID (TID)")
            name = get("Thread Name (/proc/task/comm)")
            state = get("State")
            cpu = get("Thread CPU %")
            core = get("CPU Core #")
            pid = self._selected_pid or "PID"
            details = (
                f"Thread {tid} ({name}) belongs to PID {pid}. It is {state}, "
                f"last seen on CPU {core}, with {cpu} measured thread CPU."
            )
            command = (
                f"ps -L -p {shlex.quote(str(pid))} -o pid,tid,psr,stat,pcpu,time,comm"
            )
            return details, command

        if kind == "port":
            port = get("Port")
            proto = get("Proto")
            state = get("State")
            local = get("Local Address")
            remote = get("Remote Address")
            process = get("Process")
            pid = get("PID")
            unit = get("Systemd Unit")
            purpose = get("Service / Command Line Purpose")
            details = (
                f"{proto} port {port} is {state}. {local} -> {remote}. "
                f"Process: {process} (PID {pid}); unit: {unit}. {purpose}"
            )
            port_text = str(port) if str(port).isdigit() else shlex.quote(str(port))
            command = f"sudo ss -tulpn | grep -E ':{port_text}\\b'"
            return details, command

        if kind == "service":
            unit = get("Systemd Unit")
            scope = get("Scope")
            active = get("Active")
            sub = get("SubState")
            memory = get("Memory")
            cpu_time = get("CPU Time")
            io = get("IO R/W")
            description = get("Description")
            details = (
                f"Systemd unit {unit} ({scope}) is {active}/{sub}. "
                f"Memory: {memory}; CPU time: {cpu_time}; I/O: {io}. "
                f"{description}"
            )
            source = self._svc_io_sources.get((scope, unit), "")
            if io == "-":
                details += (
                    " I/O is unavailable because the cgroup io controller is "
                    "not delegated and /proc does not expose every PID in the "
                    "service (hidepid)."
                )
            elif source:
                details += f" I/O source: {source}."
            prefix = "--user " if scope == "user" else ""
            return details, f"systemctl {prefix}status {shlex.quote(unit)}"

        if kind == "timer":
            unit = get("Timer Unit")
            activates = get("Activates Service")
            scope = get("Scope")
            state = get("State")
            nxt = get("Next Elapse")
            last = get("Last Triggered")
            details = (
                f"Timer {unit} ({scope}) is {state}, activates {activates}. "
                f"Next: {nxt}; last: {last}."
            )
            prefix = "--user " if scope == "user" else ""
            return details, f"systemctl {prefix}list-timers {shlex.quote(unit)}"

        if kind == "autostart":
            command_text = get("hyprland.lua Autostart Command")
            target = get("Target Daemon")
            status = get("Live Status")
            pids = get("Running PID(s)")
            details = (
                f"This is the hyprland.lua autostart entry `{command_text}`. "
                f"Target: {target}; live status: {status}; PID(s): {pids}."
            )
            command = (
                f"grep -nF -- {shlex.quote(command_text)} ~/.config/hypr/hyprland.lua"
            )
            return details, command

        if kind == "window":
            cls = get("Window Class")
            title = get("Window Title")
            ws = get("Workspace")
            pid = get("PID")
            protocol = get("Protocol")
            layout = get("Layout")
            address = self._clean_value(raw_values[-1] if raw_values else "-")
            details = (
                f"Hyprland window `{title}` (class {cls}) is on workspace {ws}, "
                f"owned by PID {pid}, using {protocol} and {layout}. "
                f"Hyprland address: {address}."
            )
            command = (
                "hyprctl clients -j | jq "
                f"'.[] | select(.address == {json.dumps(address)})'"
            )
            return details, command

        if kind == "irq":
            irq = get("IRQ #")
            rate = get("Interrupts / sec")
            subsystem = get("Hardware / Driver Subsystem")
            raw = get("Raw Kernel Interrupt Source (/proc/interrupts)")
            details = (
                f"IRQ {irq} is firing at {rate}. Classified as {subsystem}. "
                f"Kernel description: {raw}"
            )
            return details, f"grep -E '^ *{shlex.quote(irq)}:' /proc/interrupts"

        if kind == "tunable":
            name = get("Power Tunable")
            state = get("State")
            current = get("Current")
            target = get("Target")
            why = get("Why It Matters")
            path = next(
                (
                    t.get("path", "")
                    for t in self._last_tunables
                    if t.get("name") == name
                ),
                "",
            )
            details = (
                f"Power tunable `{name}` is {state}: current {current}, "
                f"target {target}. {why} Path: {path or 'not recorded'}."
            )
            if path and "*" not in path:
                command = f"cat {shlex.quote(path)}"
            elif path:
                command = f"ls -l {path}"
            else:
                command = "taskmgr --page power"
            return details, command

        if kind == "audio":
            atype = get("Type")
            ident = get("ID")
            name = get("Device / Stream / Radio Name")
            volume = get("Volume / State")
            active = get("Active / Default")
            health = get("Health / Privacy Diagnostic")
            details = f"{atype}: {name} (ID {ident}); {volume}; {active}. {health}"
            if "Radio" in atype:
                command = "rfkill list"
            elif "Camera" in atype or "Webcam" in atype:
                command = "v4l2-ctl --list-devices"
            else:
                command = f"wpctl inspect {shlex.quote(ident)}"
            return details, command

        if kind == "pci":
            slot = get("PCI Slot")
            name = get("Hardware Device Name (pci.ids)")
            driver = get("Bound Kernel Driver")
            rpm = get("Runtime PM Status")
            control = get("Power Control")
            details = (
                f"PCI device {slot}: {name}. Driver: {driver}; runtime PM: "
                f"{rpm}; power control: {control}."
            )
            return details, f"lspci -s {shlex.quote(slot)} -nnk"

        if kind == "usb":
            bus = get("USB Bus / Device")
            usb_id = get("Vendor:Product ID")
            name = get("Connected USB Peripheral")
            details = f"USB device {usb_id} at {bus}: {name}."
            return details, f"lsusb -d {shlex.quote(usb_id)}"

        if kind == "sensor":
            chip = get("Sensor Chip (hwmon)")
            channel = get("Channel / Zone")
            metric = get("Metric Type")
            reading = get("Live Reading")
            details = f"{chip} / {channel} reports {metric}: {reading}."
            return details, "sensors -A"

        if kind == "smart":
            device = get("Device")
            model = get("Model")
            size = get("Size")
            health = get("SMART Health")
            temp = get("Temperature")
            hours = get("Power-On Hours")
            used = get("Used")
            note = get("Note")
            details = (
                f"Storage device {device} ({model}, {size}). SMART health: "
                f"{health}; temperature: {temp}; power-on hours: {hours}; "
                f"life used: {used}. {note}"
            )
            return details, f"sudo smartctl -a {shlex.quote(device)}"

        if kind == "block":
            name = get("Device / Partition")
            size = get("Size")
            fstype = get("Filesystem")
            used = get("Used")
            mount = get("Mountpoint / Model")
            clean = name.replace("├─", "").replace("└─", "").strip()
            details = (
                f"Storage device/partition {clean} ({size}, {fstype}) uses "
                f"{used}; mount/model: {mount}."
            )
            if clean.startswith("~/.important"):
                command = "findmnt ~/.important || echo 'vault is not mounted'"
            else:
                command = f"lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS /dev/{shlex.quote(clean)}"
            return details, command

        if kind == "module":
            name = get("Kernel Module")
            size = get("Memory Size")
            refs = get("Ref Count")
            used = get("Used By Modules")
            details = (
                f"Kernel module {name} uses {size}, has {refs} references, "
                f"and is used by: {used}."
            )
            return details, f"modinfo {shlex.quote(name)}"

        if kind == "ebpf":
            when = get("Time")
            probe = get("Probe")
            event = get("Event")
            details = f"eBPF event at {when} from {probe}: {event}"
            command = self._ebpf_probe_commands.get(probe)
            if not command:
                command = "sudo bpftrace -l 'tracepoint:*'"
            return details, command

        if kind == "log":
            when = get("Timestamp")
            source = get("Component / Source")
            level = get("Severity")
            message = get("Message")
            details = f"{when} {source} [{level}]: {message}"
            return details, "journalctl -b -p 0..3 --no-pager"

        if kind == "doctor":
            component = get("Component")
            finding = get("Live Finding")
            details_text = get("Diagnostic Details")
            fix = get("Available One-Click Fix")
            details = (
                f"Doctor check `{component}`: {finding}. Details: {details_text}. "
                f"Available fix: {fix}."
            )
            command = "journalctl -b -p 0..3 --no-pager"
            if "PolicyKit" in component:
                command = "systemctl --user status hyprpolkitagent.service"
            elif "Trash" in component:
                command = "systemctl --user list-timers 'trash-*' --all"
            elif "Waybar" in component:
                command = "ls -l ~/.config/waybar"
            elif "Hypridle" in component:
                command = "systemctl --user status hypridle"
            elif "Boot" in component:
                command = "journalctl -b -p 0..3 --no-pager"
            elif "Duplicate" in component:
                command = "grep -n 'hl.exec_cmd' ~/.config/hypr/hyprland.lua"
            elif "Wallpaper" in component:
                command = "ps -ef | grep -E 'awww|hyprpaper'"
            return details, command

        if kind == "capability":
            feature = get("Feature")
            status = get("Status")
            details_text = get("Details / Prerequisite")
            command = get("Command")
            return (
                f"Optional feature `{feature}` is {status}. {details_text}",
                command or "echo 'No command recorded'",
            )

        details = (
            "This row belongs to the table with columns: "
            + ", ".join(titles)
            + ". Values: "
            + ", ".join(
                f"{titles[i]}={self._clean_value(values[i])}"
                for i in range(min(len(titles), len(values)))
            )
        )
        return details, "taskmgr --doctor-json"

    def _show_context_menu(
        self, widget: Gtk.Widget, x: int, y: int, details: str, command: str
    ) -> None:
        self._context_details = details
        self._context_command = command
        try:
            coords = widget.translate_coordinates(self, x, y)
            if len(coords) == 3:
                ok, wx, wy = coords
                if not ok:
                    wx, wy = x, y
            else:
                wx, wy = coords
        except (TypeError, ValueError):
            wx, wy = x, y

        menu_w = self.context_menu.measure(
            Gtk.Orientation.HORIZONTAL, -1
        ).natural
        menu_h = self.context_menu.measure(
            Gtk.Orientation.VERTICAL, -1
        ).natural
        max_x = max(8, self.get_width() - menu_w - 8)
        max_y = max(8, self.get_height() - menu_h - 8)
        px = max(8, min(int(wx), max_x))
        py = max(8, min(int(wy), max_y))

        self.context_fixed.move(self.context_menu, px, py)
        self.context_menu.set_visible(True)
        self.context_fixed.set_can_target(True)
        self.context_details_btn.grab_focus()

    def _hide_context_menu(self) -> None:
        self.context_menu.set_visible(False)
        self.context_fixed.set_can_target(False)

    def _on_context_backdrop_pressed(
        self,
        _gesture: Gtk.GestureClick,
        _n_press: int,
        x: float,
        y: float,
    ) -> bool:
        if not self.context_menu.get_visible():
            return False
        alloc = self.context_menu.get_allocation()
        if (
            alloc.x <= x < alloc.x + alloc.width
            and alloc.y <= y < alloc.y + alloc.height
        ):
            return False
        self._hide_context_menu()
        return True

    def _on_context_details_clicked(self, _btn: Gtk.Button) -> None:
        self._hide_context_menu()
        self._open_context_dialog("Details", self._context_details, None)

    def _on_context_command_clicked(self, _btn: Gtk.Button) -> None:
        self._hide_context_menu()
        self._open_context_dialog(
            "Command", self._context_details, self._context_command
        )

    def _open_context_dialog(
        self, title: str, details: str, command: str | None
    ) -> None:
        win = Gtk.Window(transient_for=self, modal=True, title=title)
        win.set_default_size(760, 320 if command else 460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)

        esc = Gtk.EventControllerKey()
        esc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        esc.connect(
            "key-pressed",
            lambda _c, k, _kc, _s: (
                (win.close(), True)[1] if k == Gdk.KEY_Escape else False
            ),
        )
        win.add_controller(esc)

        details_label = Gtk.Label(label=details, xalign=0.0, yalign=0.0)
        details_label.set_selectable(True)
        details_label.set_wrap(True)
        details_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        details_scroll = Gtk.ScrolledWindow()
        details_scroll.set_vexpand(True)
        details_scroll.set_child(details_label)
        box.append(details_scroll)

        if command:
            cmd_label = Gtk.Label(label=command, xalign=0.0)
            cmd_label.set_selectable(True)
            cmd_label.set_wrap(True)
            cmd_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            cmd_label.add_css_class("tm-source-text")
            cmd_scroll = Gtk.ScrolledWindow()
            cmd_scroll.set_child(cmd_label)
            box.append(cmd_scroll)
            copy_btn = Gtk.Button(label="Copy Command")
            copy_btn.add_css_class("tm-action-btn")
            copy_btn.connect(
                "clicked",
                lambda _: self._copy_command(command, copy_btn),
            )
            box.append(copy_btn)

        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("tm-secondary-btn")
        close_btn.connect("clicked", lambda _: win.close())
        box.append(close_btn)
        win.set_child(box)
        win.present()

    def _copy_command(self, command: str, button: Gtk.Button) -> None:
        display = Gdk.Display.get_default()
        if display is not None:
            display.get_clipboard().set(command)
            button.set_label("Copied")
            self._set_status("Command copied to the clipboard.")

    def _refresh_logs(self) -> None:
        self.log_store.clear()
        for r in HardwareAndMediaCollector.get_logs(self._log_mode):
            self.log_store.append([r["time"], r["source"], r["level"], r["message"]])
