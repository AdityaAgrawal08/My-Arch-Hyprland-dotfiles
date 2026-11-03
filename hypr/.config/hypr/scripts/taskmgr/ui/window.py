#!/usr/bin/env python3
"""Main GTK4 Window implementing the 9-Page Hyprland System Explorer & Task Manager."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from backend.doctor import SystemDoctor
from backend.gpu import GpuCollector
from backend.hardware import HardwareAndMediaCollector
from backend.performance import PerformanceCollector
from backend.ports import PortsCollector
from backend.power import PowerAndWakeupCollector
from backend.power_profiles import PowerProfileController
from backend.processes import ProcessCollector
from backend.services import ServicesCollector
from ui.widgets import SparklineAreaChart, build_tree_view, hex_to_rgb

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

        # State
        self._theme_mtime = 0.0
        self._accent_rgb = (0.82, 0.61, 0.38)
        self._bg_rgb = (0.10, 0.09, 0.09)
        self._refresh_interval_ms = 1000
        self._timer_id: int | None = None
        self._doctor_timer_id: int | None = None
        self._mapped_once = False

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

        self._load_autotheme()
        self._build_layout()
        self._setup_shortcuts()

        # Initial data population. Select the target page BEFORE the first
        # refresh so the process page is populated on the very first frame.
        self._refresh_doctor()
        self._select_page(initial_page)
        self._refresh_all()
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
        if self._doctor_timer_id is not None:
            GLib.source_remove(self._doctor_timer_id)
            self._doctor_timer_id = None
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _on_key_pressed(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
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
        self.set_child(outer)

        # 1. Top At-a-Glance Health Bar. A FlowBox wraps the pills and
        # controls instead of forcing the window wider than the monitor.
        topbar = Gtk.FlowBox()
        topbar.set_selection_mode(Gtk.SelectionMode.NONE)
        topbar.set_max_children_per_line(6)
        topbar.set_row_spacing(4)
        topbar.set_column_spacing(6)
        topbar.set_homogeneous(False)
        topbar.add_css_class("tm-topbar")

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

    def _select_page(self, page_id: str) -> None:
        row = self._page_rows.get(page_id) or self._page_rows["processes"]
        self.sidebar_list.select_row(row)
        self.stack.set_visible_child_name(row._page_id)  # type: ignore[attr-defined]

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

        # Per-core live MHz & load card
        self.perf_cores_lbl = Gtk.Label(xalign=0.0)
        self.perf_cores_lbl.add_css_class("tm-card")
        self.perf_cores_lbl.set_wrap(True)
        box.append(self.perf_cores_lbl)

        # GPU Per-Engine Breakdown + Memory/Swap/Zswap/Vault readouts
        self.perf_gpu_lbl = Gtk.Label(xalign=0.0)
        self.perf_gpu_lbl.add_css_class("tm-card")
        self.perf_gpu_lbl.set_wrap(True)
        box.append(self.perf_gpu_lbl)

        self.perf_sys_lbl = Gtk.Label(xalign=0.0)
        self.perf_sys_lbl.add_css_class("tm-card")
        self.perf_sys_lbl.set_wrap(True)
        box.append(self.perf_sys_lbl)

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

        top.append(bar)

        # Columns:
        # 0:PID(int), 1:PPID(int), 2:Name(str), 3:User(str),
        # 4:CPU(float), 5:CPU_str(str), 6:GPU(float), 7:GPU_str(str),
        # 8:MemMB(float), 9:Mem_str(str), 10:DiskKBs(float), 11:Disk_str(str),
        # 12:Wakeups(float), 13:Wakeups_str(str), 14:ImpactScore(float), 15:Impact(str),
        # 16:Threads(int), 17:State(str), 18:Ports(str), 19:Unit(str), 20:Cmd(str)
        self.proc_store = Gtk.ListStore(
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
        self.proc_view, self.proc_filter, self.proc_sort, proc_scroll = build_tree_view(
            self.proc_store,
            [
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
            ],
        )
        self.proc_filter.set_visible_func(self._proc_visible_func)
        self.proc_sort.set_sort_column_id(4, Gtk.SortType.DESCENDING)
        self.proc_view.get_selection().connect(
            "changed", self._on_proc_selection_changed
        )

        top.append(proc_scroll)
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
        if mode == "tree":
            self.proc_sort.set_sort_column_id(
                Gtk.TREE_SORTABLE_UNSORTED_SORT_COLUMN_ID, Gtk.SortType.ASCENDING
            )
        else:
            self.proc_sort.set_sort_column_id(4, Gtk.SortType.DESCENDING)
        self._refresh_all()

    def _toggle_kthreads(self, hide: bool) -> None:
        self._hide_kthreads = hide
        self._proc_iters.clear()
        self.proc_store.clear()
        self._refresh_all()

    def _on_proc_search(self, text: str) -> None:
        self._proc_query = text.strip().lower()
        self.proc_filter.refilter()

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
        svc_box.append(bar)

        self.svc_store = Gtk.ListStore(str, str, str, str, str, str)
        self.svc_view, self.svc_filter, _, svc_scroll = build_tree_view(
            self.svc_store,
            [
                ("Systemd Unit", 0, 0, 250),
                ("Scope", 1, 1, 75),
                ("Load", 2, 2, 85),
                ("Active", 3, 3, 85),
                ("SubState", 4, 4, 95),
                ("Description", 5, 5, 380),
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
        return any(q in str(model[it][i]).lower() for i in range(6))

    def _on_service_action(self, action: str) -> None:
        model, it = self.svc_view.get_selection().get_selected()
        if it is not None:
            unit, scope = model[it][0], model[it][1]
            _, msg = ServicesCollector.control_service(unit, scope, action)
            self._set_status(msg)
            GLib.timeout_add(900, lambda: (self._refresh_services_tab(), False)[1])

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
        available_profiles = PowerProfileController.list_profiles()
        if PowerProfileController.is_available() and available_profiles:
            for prof in available_profiles:
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
            self._refresh_power_profile_ui()
        else:
            self.profile_status_lbl.set_text(
                "Unavailable (power-profiles-daemon is not running)"
            )
            profile_box.append(self.profile_status_lbl)
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
        box.append(bar)

        self.cstate_lbl = Gtk.Label(xalign=0.0)
        self.cstate_lbl.add_css_class("tm-card")
        self.cstate_lbl.set_wrap(True)
        box.append(self.cstate_lbl)

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
        nb.append_page(sen_scroll, Gtk.Label(label="Thermal, Fan & Voltage Sensors"))

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
        nb.append_page(blk_scroll, Gtk.Label(label="Storage & Partitions"))

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
        nb.append_page(mod_box, Gtk.Label(label="Kernel Modules (/proc/modules)"))

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
            gpu_right = (
                f"{gpu.busy_pct:.1f}%  ({gpu.freq_mhz}/{gpu.max_freq_mhz} MHz)"
                if gpu.freq_available and gpu.max_freq_mhz
                else f"{gpu.busy_pct:.1f}%  (frequency N/A)"
            )
            if gpu.engines:
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
        self.perf_sys_lbl.set_text(
            f"Context Switches: {perf['ctxt_s']:.0f}/s   |   Interrupts: {perf['intr_s']:.0f}/s   |   "
            f"Procs: {perf['procs_running']} running / {perf['procs_blocked']} blocked   |   "
            f"Dirty Pages: {me['Dirty']} kB   |   Slab: {me['Slab'] // 1024} MiB   |   "
            f"Zswap: {zswap_txt}   |   Vault (~/.important): {perf['vault']['status']}"
        )

        # 4. Page-specific heavy sampling. Process/port scans run only while
        #    their page is visible so an idle monitor does not itself cause wakeups.
        if page in ("processes", "ports"):
            ports_list, pid_ports = self.ports_collector.sample()
        else:
            ports_list, pid_ports = [], {}

        if page == "processes":
            flat_procs, grouped_procs = self.proc_collector.sample(
                pid_ports=pid_ports, hide_kernel_threads=self._hide_kthreads
            )

            if self._proc_mode == "grouped":
                target_procs = grouped_procs
                self._group_pids_map = {g["pid"]: g["pids"] for g in grouped_procs}
            elif self._proc_mode == "tree":
                target_procs = self.proc_collector.build_tree_order(flat_procs)
                self._group_pids_map = {p["pid"]: [p["pid"]] for p in target_procs}
            else:
                target_procs = flat_procs
                self._group_pids_map = {p["pid"]: [p["pid"]] for p in target_procs}

            if self._proc_mode == "tree":
                self.proc_store.clear()
                self._proc_iters.clear()
                for p in target_procs:
                    self._proc_iters[p["pid"]] = self.proc_store.append(
                        self._proc_row_tuple(p)
                    )
                if self._selected_pid is not None:
                    self._select_pid_in_view(self._selected_pid)
            else:
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

        elif page == "ports":
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
        elif page == "services":
            self._refresh_services_tab()
        elif page == "power":
            self._refresh_power_tab()
        elif page == "audio":
            self._refresh_audio_tab()
        elif page == "hardware":
            self._refresh_hardware_live(perf)

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
        self.insp_header.set_text(
            f"Inspecting PID {d['pid']} ({d['name']})   |   Unit: {d['unit']}   |   "
            f"Threads: {thread_text}   |   Sockets: {sock_text}   |   "
            f"Open FDs: {fd_text}   |   "
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
                self.svc_store.append(
                    [
                        s["unit"],
                        s["scope"],
                        s["load"],
                        s["active"],
                        s["sub"],
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

    def _refresh_power_profile_ui(self) -> None:
        current = PowerProfileController.get_current()
        self._last_profile_ts = time.monotonic()
        if current is None:
            self.profile_status_lbl.set_text(
                "Unavailable (powerprofilesctl get failed)"
            )
            for b in self.profile_buttons.values():
                b.set_sensitive(False)
            return
        self.profile_status_lbl.set_text(f"Current: {current}")
        for name, button in self.profile_buttons.items():
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

    def _refresh_logs(self) -> None:
        self.log_store.clear()
        for r in HardwareAndMediaCollector.get_logs(self._log_mode):
            self.log_store.append([r["time"], r["source"], r["level"], r["message"]])
