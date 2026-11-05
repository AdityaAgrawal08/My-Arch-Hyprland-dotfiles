# Task Manager & System Explorer

**Status:** Verified against the reference deployment on 2026-11-03.

## Purpose

`taskmgr` is a single-command GTK4 system explorer and task manager for the
Hyprland desktop. It shows what the machine is actually doing, where each value
came from, and what is failing — live rather than as a static page.

The tool is deliberately a **monitor**, not a resident daemon. It samples only
while its window is open and exits on close, so it does not add idle wakeups.

## Files and paths

| Repository path | Deployed path | Role |
| --- | --- | --- |
| `hypr/.config/hypr/scripts/taskmgr/main.py` | `~/.config/hypr/scripts/taskmgr/main.py` | GTK4 application entry point and CLI |
| `hypr/.config/hypr/scripts/taskmgr/backend/*.py` | same | Collectors, diagnostics, controls |
| `hypr/.config/hypr/scripts/taskmgr/ui/*.py` | same | GTK4 pages, Cairo charts, widgets |
| `local/.local/bin/taskmgr` | `~/.local/bin/taskmgr` | Launcher |
| `local/.local/bin/sysmon` | `~/.local/bin/sysmon` | Alias launcher |
| `local/.local/share/applications/taskmgr.desktop` | `~/.local/share/applications/taskmgr.desktop` | Desktop entry |
| `tests/test_taskmgr.py` | not deployed | Backend and truth-audit tests |

## Launch

```bash
taskmgr                       # Processes & Threads
taskmgr --page performance    # Performance
taskmgr --page power          # Power & Tunables
taskmgr --doctor-json         # Working/Not Working audit as JSON
taskmgr --verify-truth        # Cross-check values against kernel sources
taskmgr --smoke-test          # Build every page, then exit (CI)
taskmgr --lifecycle-test      # Prove a process appears, then is removed, in the live GUI store
taskmgr --power-test          # Click every power-profile button and verify the daemon state
taskmgr --async-test          # Verify the background sampler populates the process table
taskmgr --responsive-test     # Force compact mode and verify a 900x600 resize
taskmgr --report             # Write JSON/Markdown/CSV + append a SQLite snapshot
taskmgr --report --report-dir /tmp/taskmgr-report
taskmgr --waybar-json        # Print one Waybar custom-module JSON object
```

Hyprland bindings:

- `SUPER + I` — open the task manager.
- `CTRL + SHIFT + ESCAPE` — open the task manager (Windows Task Manager key).
- `SUPER + Q` — close it without the terminal close confirmation.

## The nine pages

| Page | What it shows | Actions |
| --- | --- | --- |
| **1. System Doctor** | ✅ / ⚠️ / ❌ audit of systemd, Hyprland autostart, `hypridle`, autotheme, trash timers, doctools, Bluetooth RFKill, `debug:vfr`, PowerTOP tunables, vault, boot errors, duplicate autostart, missing Waybar scripts, conflicting wallpaper daemons | 1-click fixes where safe |
| **2. Performance** | CPU total + kernel split + per-core MHz/temperature; RAM/swap; GPU busy + per-engine + RC6 (Intel/AMD DRM fdinfo) or aggregate utilization/temp/memory via `nvidia-smi`; disk R/W + IOPS + NVMe temp; network down/up; battery watts/health; PSI CPU/memory/IO stall pressure | Power profile buttons |
| **3. Processes & Threads** | Flat list, Group by App, and a real expandable `Gtk.TreeStore` process tree with persisted collapse state; PID, CPU %, GPU %, RSS, disk I/O, context switches/s, estimated battery impact, threads, state, ports, unit, command; bottom inspector with threads (`TID`), sockets, open FDs, environment, and GPU memory (DRM clients or NVIDIA compute apps) | SIGTERM, SIGKILL, SIGSTOP (Freeze), SIGCONT (Resume) |
| **4. Ports & Network** | Listening and established TCP/UDP sockets, local/remote address, state, PID, process, unit, command; interface, IP, gateway, DNS, Wi-Fi, RX/TX totals. The table has permanent horizontal and vertical scrollbars. | Kill process on port |
| **5. Services & Startup** | System + user services, cgroup-backed memory/CPU time, cumulative per-service I/O from cgroup `io.stat`, systemd IO accounting, or per-PID `/proc/*/io` when every PID is visible, timers, `hyprland.lua` autostart commands with live PID/RAM, Hyprland open windows | Start, stop, restart, focus/close window |
| **6. Power & Tunables** | CPU C-state residency, live RAPL package/core watts when `energy_uj` is readable (or N/A plus the static package limit), battery charge-stop thresholds (or N/A when firmware exposes none), live `/proc/interrupts` rates, PowerTOP GOOD/BAD tunables, real power-profile buttons (`powerprofilesctl set` verified with `powerprofilesctl get`) | Optimize all BAD tunables via PolicyKit; enable VFR; disable blur/shadows; switch power profile |
| **7. Audio, Camera & Bluetooth** | PipeWire sinks/sources/active links/volumes, V4L2 cameras and capturing PIDs, RFKill state | Normalize mic to 100%, mute output, block/unblock Bluetooth |
| **8. Hardware & Sensors** | PCI devices/drivers/runtime PM, USB peripherals, hwmon temperatures/fans/voltages, block devices/mounts/vault, SMART/NVMe health (or explicit N/A when `smartctl`/`nvme-cli` are absent), **eBPF Live Events**, a gated **Fan & Charge** editor for hwmon `pwm*` curves and battery `charge_control_*` thresholds, kernel modules, and an **Optional Features** prerequisite tab for eBPF/SMART/RAPL/cgroup-IO/NVIDIA/AMD/fan control | Start/stop gated `execsnoop`, `opensnoop`, `biosnoop`, `tcpretrans` probes; apply fan curve/manual/auto; apply battery charge thresholds |
| **9. Logs & Crashes** | journal errors, kernel/ACPI warnings, coredumpctl crashes, Hyprland session log | Switch source, filter, refresh |

## Keyboard

| Key | Action |
| --- | --- |
| `F5` | Refresh the current page |
| `Ctrl+R` | Refresh the current page (works even when the search entry has focus) |
| `Ctrl+F` | Jump to the Processes page and focus the search box |
| `Esc` | Close the Task Manager |
| `Ctrl+Q` | Close the Task Manager |
| `Delete` | End the selected process while the Processes page is active |

## Right-click Details and Command

Every table, every chart, every top-bar status pill, and every sidebar page
entry supports right-click (over 50 targets in total):

- **Details** opens a short plain-English explanation of the row or metric.
- **Command** opens a dialog with the exact shell command that reproduces or
  inspects the same data, plus a **Copy Command** button.

Examples:

| Right-click target | Command |
| --- | --- |
| Process row | `ps -p <pid> -o pid,ppid,user,stat,pcpu,pmem,rss,etime,comm,args` |
| Thread row | `ps -L -p <pid> -o pid,tid,psr,stat,pcpu,time,comm` |
| Port row | `sudo ss -tulpn \| grep -E ':<port>\b'` |
| Service row | `systemctl [--user] status <unit>` |
| Timer row | `systemctl [--user] list-timers <timer>` |
| IRQ row | `grep -E '^ *<irq>:' /proc/interrupts` |
| Kernel module row | `modinfo <module>` |
| Hyprland window | `hyprctl clients -j \| jq '.[] \| select(.address == "<address>")'` |
| PCI row | `lspci -s <slot> -nnk` |
| USB row | `lsusb -d <vendor:product>` |
| Sidebar page | `taskmgr --page <page-id>` |

## PolicyKit helper (system-service I/O, RAPL, eBPF)

Some values are root-only: `/proc/<pid>/io` for root-owned services under
`hidepid`, RAPL `energy_uj`, and `bpftrace`. Install the allowlisted helper once:

```bash
~/.config/hypr/scripts/taskmgr/install-privileged.sh
```

This installs:

- `/usr/local/libexec/taskmgr-privileged` (root-owned, executable)
- `/usr/share/polkit-1/actions/org.aditya.taskmgr.policy`

After that:

- **Services → Authorize System I/O** asks PolicyKit to read the cgroup PIDs and
  return per-service read/write byte sums. The normal table keeps working
  without it; user-service I/O is already read directly.
- **Power → Live RAPL (Authorize)** samples `energy_uj` twice as root and shows
  live package/core watts.
- **Hardware → eBPF Live Events** can press Start without running the whole GUI
  as root; Start invokes the helper through `pkexec`, which then executes the
  allowlisted probe.

The helper accepts only three operations: `service-io` for cgroup paths under
`/system.slice`, `/user.slice`, or `/machine.slice`; `rapl-watts`; and
`bpftrace` with an allowlisted probe key. It never uses a shell and never
accepts an arbitrary command. The helper must be installed root-owned; the app
does not run the user-writable repository copy through `pkexec` unless
`TASKMGR_ALLOW_DEV_HELPER=1` is explicitly set for development.

## Background sampler, alerts, reports and history

- Process and port scans run on a background worker thread. The GTK main thread
  only renders immutable snapshots, so a 0.5 s refresh does not block typing,
  scrolling, or button clicks.
  `taskmgr --async-test` verifies that the worker populates the process table.
- **Alerts** are enabled by default and can be toggled on the Doctor page.
  They cover high battery draw, low battery, high CPU temperature, memory
  pressure, PSI memory/I/O stalls, new listening ports, and failed services.
  Set `TASKMGR_ALERTS=0` to start with alerts off.
- **Auto AC/Batt** on the Power page is opt-in: Balanced on AC, Power Saver on
  battery. It is off by default and can be toggled at runtime.
- **Compact layout** activates automatically below 1150 logical pixels, or with
  the **Compact** button. The sidebar becomes a page dropdown, secondary
  columns are hidden, notebook tabs scroll, and the compact minimum is 897 px.
  `taskmgr --responsive-test` forces a 900×600 resize and verifies it.
- **Columns** on the Processes page hides/shows columns and saves the choice and
  widths in `~/.config/taskmgr/layout.json`.
- **Fan & Charge** (Hardware page) edits a five-point temperature/PWM curve and
  battery charge start/stop thresholds. Apply is enabled only when the hwmon
  `pwm*` / `power_supply` `charge_control_*` files exist and are writable;
  otherwise the exact missing path or root/udev prerequisite is shown and no
  write occurs. The Sensors tab still shows fan RPM read-only.
- **eBPF Live Events** (Hardware page) runs `execsnoop`, `opensnoop`, `biosnoop`,
  and `tcpretrans` through `bpftrace` when `bpftrace`, kernel BTF, and
  root/CAP_BPF are available. Otherwise Start is disabled and the exact
  `sudo pacman -S bpftrace` or `sudo bpftrace -e ...` command is shown.
  Captured lines are timestamped and every row has Details/Command.
- **Process Tree** uses a real `Gtk.TreeStore`; expand/collapse state is saved as
  `tree_collapsed` in the same layout file and restored after refresh/restart.
  Search filters both the flat list and the tree; a matching child keeps its
  ancestor chain visible.
- The opt-in **Waybar JSON** mode prints one module object:
  ```json
  {"text": "CPU 2%  RAM 30%  BAT 84%", "tooltip": "...", "class": "normal"}
  ```
  Example Waybar module:
  ```json
  "custom/taskmgr": {
    "exec": "taskmgr --waybar-json",
    "return-type": "json",
    "interval": 5,
    "on-click": "taskmgr"
  }
  ```
- **Export Diagnostic Report** on the Doctor page writes:
  - `report.json` — full structured snapshot
  - `report.md` — readable summary
  - `processes.csv` and `ports.csv`
  - a **Storage health** section (real SMART/NVMe values when the tools exist,
    explicit `N/A` otherwise)
  - an append-only SQLite snapshot in `~/.local/state/taskmgr/history.db`
- CLI form:
  ```bash
  taskmgr --report
  taskmgr --report --report-dir /tmp/taskmgr-report
  ```

## Truthfulness rules

The UI follows five rules:

1. **No invented values.** If a kernel file or command does not expose a metric,
   the UI shows `N/A` (or `—` for an unavailable rate) and the data-source
   dialog explains why. It never displays a plausible zero in place of missing
   data.
2. **No guessed ownership.** Root-owned sockets show `(owner hidden)` and a
   well-known-port hint that is explicitly marked as inferred. The tool does
   not assign a PID or unit it cannot verify.
3. **Estimates are labeled.** The `Battery Impact (Est.)` column is a heuristic
   derived only from measured CPU %, GPU %, context switches/s, and disk I/O.
   It is not presented as a wattage measurement.
4. **Provenance is visible.** The **Data Sources** button lists the exact
   `/proc`, `/sys`, command, or service behind every category.
5. **No pre-filled history.** Every chart starts empty and fills only from real
   samples collected while the window is open; the tool never seeds a sparkline
   with synthetic zeroes.

`taskmgr --verify-truth` performs 16 independent cross-checks:

- CPU core count vs `os.cpu_count()`.
- Memory total vs `/proc/meminfo MemTotal`.
- Battery presence vs `/sys/class/power_supply/BAT*`.
- Battery watts vs `upower -i energy-rate` (0.5 W tolerance).
- Battery health vs `energy_full / energy_full_design`.
- Active interface RX/TX totals vs `psutil.net_io_counters(pernic=True)`.
- CPU PSI `avg10` vs `/proc/pressure/cpu`.
- GPU frequency vs the sysfs `gt_*_freq_mhz` files.
- CPU package temperature vs the `coretemp` package sensor (2 °C tolerance).
- Process count vs `ps -e` (5-process tolerance for races).
- Listening ports vs `ss -H -tuln` (exact set).
- System service count vs `systemctl list-units`.
- Every PCI `power/control` value vs the PCI tunable table.
- NMI watchdog vs `/proc/sys/kernel/nmi_watchdog`.
- `debug:vfr` vs the Doctor verdict.
- Root-socket rows vs the “owner hidden” rule.

## Why some values need root

The kernel hides `/proc/<pid>/fd` and the socket inode for processes owned by
other users. Without root, the tool can still show the socket tuple and the
listening port, but not the owning PID. Run `sudo taskmgr` if full ownership is
required; the GUI itself never escalates silently.

PolicyKit is used only for explicit actions: stopping a system service,
resetting failed units, or writing kernel power tunables.

## Performance behavior

- System metrics refresh every 1 s by default (0.5 s / 1 s / 2 s / Pause
  selectable).
- Process and port scans run only while page 3 or 4 is visible. Other pages do
  not pay that cost.
- UPower battery rate is cached for 10 s.
- PowerTOP policy files are cached for 8 s and invalidated after a fix.
- GPU engine counters use `/proc/<pid>/fdinfo` deltas, not polling sysfs for
  every process.
- The application exits on close; there is no tray icon or background worker.

## Dependencies

Already installed on the reference deployment:

- `python`, `python-gobject`, `python-psutil`, `gtk4`, `libadwaita`
- `systemd`, `iproute2`, `procps-ng`, `upower`, `power-profiles-daemon`
- `hyprland` (`hyprctl`), `pipewire`/`wireplumber` (`wpctl`), `bluez` (`rfkill`)
- `networkmanager` (`nmcli`, optional for Wi-Fi details)
- `pciutils` (`lsusb`), `hwdata` (`pci.ids`), `util-linux` (`lsblk`)

## Reproduction

```bash
cd ~/dotfiles
stow --target="$HOME" --no-folding local hypr
# or run ./install.sh, which links local/.local/bin/taskmgr and sysmon
taskmgr --smoke-test
taskmgr --verify-truth
```

## Verification

Verified on the reference deployment:

```text
hyprctl reload
hyprctl configerrors          # no errors
hyprctl getoption debug:vfr -j
# {"option": "debug:vfr", "bool": true, "set": true }

taskmgr --smoke-test
# SMOKE_TEST_PAGE_OK: doctor ... logs
# SMOKE_TEST_PROCESS_ROWS: <n>
# SMOKE_TEST_ESCAPE_HANDLED: True
# SMOKE_TEST_COMPLETE: ALL_9_PAGES_VERIFIED

taskmgr --lifecycle-test
# LIFECYCLE_FOUND_IN_GUI: True
# LIFECYCLE_REMOVED_FROM_GUI: True
# LIFECYCLE_TEST_PASS

taskmgr --power-test
# POWER_BUTTON power-saver: requested=power-saver actual=power-saver
# POWER_BUTTON balanced: requested=balanced actual=balanced
# POWER_BUTTON performance: requested=performance actual=performance
# POWER_RESTORED: power-saver
# POWER_TEST_PASS

# Actual Escape key event via Hyprland's dispatcher:
hyprctl dispatch 'hl.dsp.send_shortcut({ mods = "", key = "Escape" })'
# The task manager exits with status 0.

taskmgr --verify-truth
# 16/16 independent cross-checks passed.
```

`python3 -m unittest tests/test_taskmgr.py -v` covers the collectors, the
no-fabricated-default GPU snapshot, root-socket honesty, empty-tunable behavior,
and the truth-audit response shape.

## Known limitations

- Root-owned socket PID/command requires root; the UI says so instead of
  guessing.
- CPU percentages are raw Linux per-process values (psutil sums all threads),
  so a multi-threaded process can exceed 100%. Windows Task Manager normalizes
  to total machine capacity; this tool deliberately keeps the Linux meaning.
- GPU per-engine data requires a driver that exposes DRM `fdinfo` counters
  (`i915`, `xe`, `amdgpu`). NVIDIA uses `nvidia-smi` for aggregate utilization,
  temperature and memory, plus per-process compute-app memory; `nvidia-smi`
  does not expose per-process utilization.
- Per-process GPU % is the busiest visible engine, capped at 100%, not a sum
  across all engines.
- GPU memory totals are client-attributed and only include processes this user
  may inspect.
- C-state residency is a share of aggregate CPU idle time across all CPUs,
  not per-core wall-clock residency.
- Wi-Fi SSID/signal requires NetworkManager (`nmcli`).
- `hyprland.lua` autostart parsing handles literal `hl.exec_cmd("...")`
  strings; computed commands are not evaluated.
- Tree mode rebuilds rows when order changes; selection is restored, but scroll
  position is not preserved.
- The “Battery Impact” score is a heuristic, not a measured wattage.
- HP firmware may not expose `power_now`; UPower `energy-rate` is used instead.
- Kernel/ACPI boot errors are reported verbatim; repeated firmware messages are
  counted individually.
- `taskmgr` does not ship its own eBPF programs. The eBPF Live Events tab is a
  gated runner around `bpftrace`; without `bpftrace`, BTF, or root/CAP_BPF it
  shows the prerequisite and starts nothing.
- Power-profile buttons are only shown when `powerprofilesctl list` and `get`
  work; if the daemon is unavailable, the page says so and shows no buttons.
- Ports table is wider than the window by design; both scrollbars stay
  visible so every column and row remains reachable.
- Fan-curve and battery-threshold writes require writable sysfs files (root or
  a udev rule). On the reference machine no `pwm*` or `charge_control_*` files
  are exposed, so both editors are disabled and report the prerequisite.
- Per-service disk I/O prefers cgroup `io.stat`, then systemd
  `IOReadBytes`/`IOWriteBytes`, then aggregation of `/proc/<pid>/io` for the
  service's cgroup PIDs. The per-PID fallback is used only when every PID is
  visible; with `hidepid=invisible`, root-owned system services still show
  `N/A` because a partial sum would undercount. User services whose PIDs are
  visible show real cumulative I/O. CPU time and memory are always real.
- RAPL live package/core watts are computed from `energy_uj` deltas when the
  counters are readable. On this machine they are root-only, so the page shows
  `N/A` and the static package limit instead of a fabricated wattage.
- New-listening-port alerts are evaluated when the Processes or Ports page is
  active; the other alert thresholds run on every tick.
- Hardware → **Storage Health** lists every physical disk; without `smartctl` or
  `nvme-cli` each device says `N/A` and names the missing tools. The
  **Optional Features** tab explicitly reports eBPF, SMART/NVMe,
  RAPL, cgroup-I/O, NVIDIA/AMD, and fan-control prerequisites as
  Available/Unavailable with the
  exact install or inspect command. Missing tooling is never faked.
- A compact layout activates automatically below 1150 logical pixels: the
  sidebar is replaced by a page dropdown, secondary table columns are hidden,
  and notebook tabs become scrollable. The compact minimum is 897×310; the
  `--responsive-test` path verifies a 900×600 resize.

## Related documentation

- [system-overview.md](system-overview.md)
- [hyprland-configuration.md](hyprland-configuration.md)
- [installation-and-package-management.md](installation-and-package-management.md)
