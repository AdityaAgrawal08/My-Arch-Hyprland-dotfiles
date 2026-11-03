#!/usr/bin/env python3
"""Power, Battery, CPU C-States, Hardware Interrupts/sec, and PowerTOP Tunables backend."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from .gpu import pci_device_name


def _read(path: str | Path, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return default


def _classify_irq(irq: str, desc: str) -> str:
    low = desc.lower()
    tokens = set(re.findall(r"[a-z0-9_]+", low))
    if "idma64" in low or "intc1055" in low or "i2c" in low or "elan" in low:
        return "I2C / DMA Controller"
    if "i915" in low or "drm" in low or "xe" in tokens:
        return "GPU Driver"
    if "mt7921" in low or "wlan" in low or "wifi" in low:
        return "Wi-Fi Adapter"
    if "nvme" in low:
        return "NVMe SSD Queue"
    if "xhci" in low or "usb" in low:
        return "USB / Thunderbolt xHCI Host"
    if "snd" in low or "sof" in low or "hda" in low or "audio" in low:
        return "Audio Subsystem (SOF / HDA)"
    if irq == "LOC":
        return "Local APIC Timer"
    if irq == "RES":
        return "CPU Rescheduling IPI"
    if irq == "CAL":
        return "Function Call IPI"
    if irq == "TLB":
        return "TLB Shootdown"
    return "System / Platform Interrupt"


class PowerAndWakeupCollector:
    """Tracks CPU C-state residency, live /proc/interrupts rates, and PowerTOP kernel tunables."""

    def __init__(self) -> None:
        self._last_ts = time.monotonic()
        self._prev_irqs = self._read_interrupts()
        self._prev_cstates = self._read_cpuidle_times()
        self._tunables_cache: list[dict] = []
        self._last_tunables_ts = 0.0

    @staticmethod
    def _read_interrupts() -> dict[str, tuple[int, str]]:
        out: dict[str, tuple[int, str]] = {}
        try:
            with open("/proc/interrupts", "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if not lines:
                return out
            ncpus = len(lines[0].split())
            for line in lines[1:]:
                parts = line.split()
                if len(parts) < 2:
                    continue
                irq = parts[0].rstrip(":")
                nums = []
                idx = 1
                while idx < len(parts) and idx <= ncpus and parts[idx].isdigit():
                    nums.append(int(parts[idx]))
                    idx += 1
                desc = " ".join(parts[idx:]) or irq
                out[irq] = (sum(nums), desc)
        except OSError:
            pass
        return out

    @staticmethod
    def _read_cpuidle_times() -> dict[str, int]:
        """Sum microseconds spent in each C-state across all logical CPUs."""
        totals: dict[str, int] = {}
        cpu_root = Path("/sys/devices/system/cpu")
        for state_dir in cpu_root.glob("cpu[0-9]*/cpuidle/state*"):
            name = _read(state_dir / "name")
            t_str = _read(state_dir / "time")
            if name and t_str.isdigit():
                totals[name] = totals.get(name, 0) + int(t_str)
        return totals

    @staticmethod
    def scan_powertop_tunables() -> list[dict]:
        """Inspect kernel and sysfs power management tunables (GOOD vs BAD)."""
        tunables: list[dict] = []

        # 1. NMI Watchdog
        nmi_path = "/proc/sys/kernel/nmi_watchdog"
        if os.path.exists(nmi_path):
            nmi = _read(nmi_path, "0")
            tunables.append(
                {
                    "category": "Kernel",
                    "name": "NMI Watchdog Off",
                    "status": "GOOD" if nmi == "0" else "BAD",
                    "current": nmi,
                    "target": "0",
                    "path": nmi_path,
                    "why": "Disabling NMI watchdog prevents periodic CPU timer wakeups",
                }
            )

        # 2. VM Dirty Writeback Timeout
        wb_path = "/proc/sys/vm/dirty_writeback_centisecs"
        if os.path.exists(wb_path):
            wb = _read(wb_path, "500")
            wb_ok = wb.isdigit() and int(wb) >= 1500
            tunables.append(
                {
                    "category": "VM / Disk",
                    "name": "VM Writeback Timeout (>= 15s)",
                    "status": "GOOD" if wb_ok else "BAD",
                    "current": f"{wb} cs",
                    "target": "1500",
                    "path": wb_path,
                    "why": "Reduces background NVMe wakeups from frequent page cache flushes",
                }
            )

        # 3. Audio Codec Power Management
        for mod_path in (
            "/sys/module/snd_hda_intel/parameters/power_save",
            "/sys/module/snd_ac97_codec/parameters/power_save",
        ):
            if os.path.exists(mod_path):
                val = _read(mod_path, "0")
                tunables.append(
                    {
                        "category": "Audio",
                        "name": "Audio Codec Runtime Power Save",
                        "status": "GOOD" if val != "0" else "BAD",
                        "current": val,
                        "target": "1",
                        "path": mod_path,
                        "why": "Powers down audio codec after 1s of silence",
                    }
                )

        # 4. CPU Energy Performance Preference (EPP)
        epp = _read(
            "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference", ""
        )
        if epp:
            tunables.append(
                {
                    "category": "CPU P-State",
                    "name": "CPU Energy Performance Preference (EPP)",
                    "status": "GOOD" if epp in ("balance_power", "power") else "BAD",
                    "current": epp,
                    "target": "balance_power",
                    "path": "/sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference",
                    "why": "Allows CPU cores to drop voltage/clocks aggressively on battery",
                }
            )

        # 5. PCI Device Runtime PM (/sys/bus/pci/devices/*/power/control)
        pci_root = Path("/sys/bus/pci/devices")
        if pci_root.is_dir():
            for dev in sorted(pci_root.iterdir()):
                ctrl_path = dev / "power" / "control"
                if not ctrl_path.is_file():
                    continue
                ctrl = _read(ctrl_path, "auto")
                vendor = _read(dev / "vendor")
                device = _read(dev / "device")
                dev_name = pci_device_name(vendor, device) or dev.name
                tunables.append(
                    {
                        "category": f"PCI ({dev.name})",
                        "name": f"Runtime PM: {dev_name[:52]}",
                        "status": "GOOD" if ctrl == "auto" else "BAD",
                        "current": ctrl,
                        "target": "auto",
                        "path": str(ctrl_path),
                        "why": "Allows PCI device to enter D3cold/D3hot low-power state when idle",
                    }
                )

        tunables.sort(key=lambda x: (0 if x["status"] == "BAD" else 1, x["category"]))
        return tunables

    def _scan_tunables_cached(self) -> list[dict]:
        """Cache the static sysfs/procfs policy scan; values change only on user action."""
        now = time.monotonic()
        if self._tunables_cache and now - self._last_tunables_ts < 8.0:
            return list(self._tunables_cache)
        self._tunables_cache = self.scan_powertop_tunables()
        self._last_tunables_ts = now
        return list(self._tunables_cache)

    def invalidate_tunables_cache(self) -> None:
        """Force the next sample to re-read policy files after a fix."""
        self._last_tunables_ts = 0.0
        self._tunables_cache = []

    def sample(self) -> dict:
        now = time.monotonic()
        dt = max(now - self._last_ts, 1e-3)
        self._last_ts = now

        # 1. Interrupt delta rates
        cur_irqs = self._read_interrupts()
        irq_rows: list[dict] = []
        for irq, (cnt, desc) in cur_irqs.items():
            prev_cnt = self._prev_irqs.get(irq, (cnt, desc))[0]
            rate = max(0.0, (cnt - prev_cnt) / dt)
            if rate >= 0.5:
                irq_rows.append(
                    {
                        "irq": irq,
                        "rate": round(rate, 1),
                        "subsystem": _classify_irq(irq, desc),
                        "description": desc,
                    }
                )
        self._prev_irqs = cur_irqs
        irq_rows.sort(key=lambda x: x["rate"], reverse=True)

        # 2. C-state residency %
        cur_cstates = self._read_cpuidle_times()
        cstate_deltas: dict[str, int] = {}
        for name, us in cur_cstates.items():
            prev_us = self._prev_cstates.get(name, us)
            cstate_deltas[name] = max(0, us - prev_us)
        self._prev_cstates = cur_cstates

        total_idle_us = max(sum(cstate_deltas.values()), 1)
        cstates_pct = {
            name: round((delta_us / total_idle_us) * 100.0, 1)
            for name, delta_us in cstate_deltas.items()
        }

        tunables = self._scan_tunables_cached()
        bad_count = sum(1 for t in tunables if t["status"] == "BAD")

        return {
            "irqs": irq_rows[:25],
            "cstates_pct": cstates_pct,
            "tunables": tunables,
            "bad_tunables_count": bad_count,
        }

    @staticmethod
    def apply_all_bad_tunables(tunables: list[dict]) -> tuple[bool, str]:
        """Write target values to all BAD tunables in a single Polkit shell invocation."""
        cmds: list[str] = []
        for t in tunables:
            if t["status"] != "BAD":
                continue
            p = t["path"]
            target = t["target"]
            if "*" in p:
                cmds.append(
                    f"for f in {p}; do [ -w \"$f\" ] && printf '%s' '{target}' > \"$f\" 2>/dev/null || true; done"
                )
            else:
                cmds.append(
                    f"[ -w '{p}' ] && printf '%s' '{target}' > '{p}' 2>/dev/null || true"
                )
        if not tunables:
            return False, "No power tunables were readable; nothing was changed."
        if not cmds:
            return True, f"Scanned {len(tunables)} tunables; none are in BAD state."
        script = "; ".join(cmds)
        try:
            subprocess.Popen(["pkexec", "sh", "-c", script])
            return True, f"Applying {len(cmds)} power tunables via PolicyKit..."
        except OSError as exc:
            return False, str(exc)
