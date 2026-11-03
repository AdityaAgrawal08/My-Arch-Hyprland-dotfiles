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
```

Hyprland bindings:

- `SUPER + I` — open the task manager.
- `CTRL + SHIFT + ESCAPE` — open the task manager (Windows Task Manager key).
- `SUPER + Q` — close it without the terminal close confirmation.

## The nine pages

| Page | What it shows | Actions |
| --- | --- | --- |
| **1. System Doctor** | ✅ / ⚠️ / ❌ audit of systemd, Hyprland autostart, `hypridle`, autotheme, trash timers, doctools, Bluetooth RFKill, `debug:vfr`, PowerTOP tunables, vault, boot errors, duplicate autostart, missing Waybar scripts, conflicting wallpaper daemons | 1-click fixes where safe |
| **2. Performance** | CPU total + kernel split + per-core MHz/temperature; RAM/swap; GPU busy + per-engine + RC6; disk R/W + IOPS + NVMe temp; network down/up; battery watts/health | Power profile buttons |
| **3. Processes & Threads** | Flat list, Group by App, Process Tree; PID, CPU %, GPU %, RSS, disk I/O, wakeups/s, estimated battery impact, threads, state, ports, unit, command; bottom inspector with threads (`TID`), sockets, open FDs, environment | SIGTERM, SIGKILL, SIGSTOP (Freeze), SIGCONT (Resume) |
| **4. Ports & Network** | Listening and established TCP/UDP sockets, local/remote address, state, PID, process, unit, command; interface, IP, gateway, DNS, Wi-Fi, RX/TX totals. The table has permanent horizontal and vertical scrollbars. | Kill process on port |
| **5. Services & Startup** | System + user services, timers, `hyprland.lua` autostart commands with live PID/RAM, Hyprland open windows | Start, stop, restart, focus/close window |
| **6. Power & Tunables** | CPU C-state residency, live `/proc/interrupts` rates, PowerTOP GOOD/BAD tunables, real power-profile buttons (`powerprofilesctl set` verified with `powerprofilesctl get`) | Optimize all BAD tunables via PolicyKit; enable VFR; disable blur/shadows; switch power profile |
| **7. Audio, Camera & Bluetooth** | PipeWire sinks/sources/active links/volumes, V4L2 cameras and capturing PIDs, RFKill state | Normalize mic to 100%, mute output, block/unblock Bluetooth |
| **8. Hardware & Sensors** | PCI devices/drivers/runtime PM, USB peripherals, hwmon temperatures/fans/voltages, block devices/mounts/vault, kernel modules | — |
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

`taskmgr --verify-truth` performs 15 independent cross-checks:

- CPU core count vs `os.cpu_count()`.
- Memory total vs `/proc/meminfo MemTotal`.
- Battery presence vs `/sys/class/power_supply/BAT*`.
- Battery watts vs `upower -i energy-rate` (0.5 W tolerance).
- Battery health vs `energy_full / energy_full_design`.
- Active interface RX/TX totals vs `psutil.net_io_counters(pernic=True)`.
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
# 15/15 independent cross-checks passed.
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
  (`i915`, `xe`, `amdgpu`). Other drivers show `N/A`.
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
- The layout is tuned for the reference 1920×1080 display at scale 1.5. At a
  much higher monitor scale the minimum table width can exceed the logical
  monitor width; reduce the scale or resize columns.
- `taskmgr` is a GUI monitor. It does not trace syscalls or eBPF events.
- Power-profile buttons are only shown when `powerprofilesctl list` and `get`
  work; if the daemon is unavailable, the page says so and shows no buttons.
- The Ports table is wider than the window by design; both scrollbars stay
  visible so every column and row remains reachable.

## Related documentation

- [system-overview.md](system-overview.md)
- [hyprland-configuration.md](hyprland-configuration.md)
- [installation-and-package-management.md](installation-and-package-management.md)
