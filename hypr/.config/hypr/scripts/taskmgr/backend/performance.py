#!/usr/bin/env python3
"""Real-time Performance telemetry collector.

Covers:
- CPU total, Kernel vs User split, Per-Core load & MHz, Temperatures, Context switches/s, Interrupts/s
- Physical Memory, Swap devices (/proc/swaps), Zswap/Zram stats, Dirty/Writeback KB
- Disk I/O (Read/Write MB/s, IOPS, active %), drive temperature, lsblk partition & mount map,
  and ~/.important gocryptfs vault lock/mount status
- Network adapters (Download/Upload KB/s, total RX/TX, errors/drops, IP, Gateway, DNS, Wi-Fi SSID/Signal/Temp)
- Battery & USB-C Power Delivery telemetry (Watts, Volts, Amps, Capacity, Health, Remaining time, Power profile)
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from collections import deque
from pathlib import Path
import psutil

from .gpu import GpuCollector, GpuSnapshot
from .psi import PsiCollector


class PerformanceCollector:
    def __init__(
        self, history_len: int = 60, gpu_collector: GpuCollector | None = None
    ) -> None:
        self.history_len = history_len
        self.gpu_collector = gpu_collector or GpuCollector()

        self.cpu_hist: deque[float] = deque(maxlen=history_len)
        self.cpu_kernel_hist: deque[float] = deque(maxlen=history_len)
        self.mem_hist: deque[float] = deque(maxlen=history_len)
        self.gpu_hist: deque[float] = deque(maxlen=history_len)
        self.net_down_hist: deque[float] = deque(maxlen=history_len)
        self.net_up_hist: deque[float] = deque(maxlen=history_len)
        self.disk_read_hist: deque[float] = deque(maxlen=history_len)
        self.disk_write_hist: deque[float] = deque(maxlen=history_len)
        self.power_watts_hist: deque[float] = deque(maxlen=history_len)

        self._last_ts = time.monotonic()
        self._last_net_pernic = psutil.net_io_counters(pernic=True)
        self._last_disk = psutil.disk_io_counters()
        self._last_cpu_times = psutil.cpu_times()
        self._last_stat = self._read_proc_stat()
        self._cached_lsblk: list[dict] = []
        self._last_lsblk_ts = 0.0
        self._cached_wifi: dict = {"ssid": "N/A", "signal": 0, "rate": "N/A"}
        self._last_wifi_ts = 0.0
        self._upower_cache: dict[str, tuple[float, float | None, str | None]] = {}
        self._last_upower_ts = 0.0

        psutil.cpu_percent(interval=None, percpu=True)

    @staticmethod
    def _read_proc_stat() -> tuple[int, int, int, int]:
        ctxt = intr = procs_running = procs_blocked = 0
        try:
            with open("/proc/stat", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("ctxt "):
                        ctxt = int(line.split()[1])
                    elif line.startswith("intr "):
                        intr = int(line.split()[1])
                    elif line.startswith("procs_running "):
                        procs_running = int(line.split()[1])
                    elif line.startswith("procs_blocked "):
                        procs_blocked = int(line.split()[1])
        except OSError:
            pass
        return ctxt, intr, procs_running, procs_blocked

    @staticmethod
    def _read_meminfo_extra() -> dict[str, int]:
        out = {
            "Dirty": 0,
            "Writeback": 0,
            "Slab": 0,
            "Mapped": 0,
            "Shmem": 0,
            "Zswap": -1,
            "Zswapped": -1,
        }
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    k, _, rest = line.partition(":")
                    if k in out:
                        parts = rest.strip().split()
                        if parts and parts[0].isdigit():
                            out[k] = int(parts[0])  # kB
        except OSError:
            pass
        return out

    @staticmethod
    def _read_swaps() -> list[dict]:
        swaps = []
        try:
            with open("/proc/swaps", "r", encoding="utf-8") as f:
                lines = f.readlines()[1:]
            for line in lines:
                parts = line.split()
                if len(parts) >= 5:
                    swaps.append(
                        {
                            "device": parts[0],
                            "type": parts[1],
                            "size_mb": round(int(parts[2]) / 1024.0, 1),
                            "used_mb": round(int(parts[3]) / 1024.0, 1),
                            "priority": parts[4],
                        }
                    )
        except OSError:
            pass
        return swaps

    def _get_block_devices(self) -> list[dict]:
        now = time.monotonic()
        if now - self._last_lsblk_ts < 5.0 and self._cached_lsblk:
            return self._cached_lsblk
        self._last_lsblk_ts = now
        rows: list[dict] = []
        try:
            out = subprocess.check_output(
                [
                    "lsblk",
                    "-J",
                    "-o",
                    "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,FSUSED,FSUSE%",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            data = json.loads(out)

            def walk(devs: list[dict], prefix: str = "") -> None:
                for d in devs:
                    name = d.get("name", "")
                    mnts = [m for m in (d.get("mountpoints") or []) if m]
                    rows.append(
                        {
                            "name": f"{prefix}{name}",
                            "size": d.get("size") or "-",
                            "type": d.get("type") or "-",
                            "fstype": d.get("fstype") or "-",
                            "mount": ", ".join(mnts) if mnts else "-",
                            "model": (d.get("model") or "").strip(),
                            "used": d.get("fsused") or "-",
                            "use_pct": d.get("fsuse%") or "-",
                        }
                    )
                    children = d.get("children") or []
                    if children:
                        walk(children, prefix + "  ├─ ")

            walk(data.get("blockdevices") or [])
        except Exception:
            pass
        self._cached_lsblk = rows
        return rows

    @staticmethod
    def _check_important_vault() -> dict:
        home = Path.home()
        vault_enc = home / ".important.encrypted"
        vault_mnt = home / ".important"
        mounted = False
        try:
            with open("/proc/mounts", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == str(vault_mnt):
                        mounted = True
                        break
        except OSError:
            pass
        return {
            "exists": vault_enc.is_dir() or vault_mnt.is_dir(),
            "mounted": mounted,
            "status": "Unlocked & Mounted (gocryptfs)"
            if mounted
            else "Locked (Unmounted)",
        }

    def _get_network_details(self) -> dict:
        active_iface = "lo"
        gateway = "-"
        try:
            with open("/proc/net/route", "r", encoding="utf-8") as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == "00000000":
                        active_iface = parts[0]
                        gw_hex = parts[2]
                        gw_bytes = [int(gw_hex[i : i + 2], 16) for i in range(0, 8, 2)]
                        gw_bytes.reverse()
                        gateway = ".".join(str(b) for b in gw_bytes)
                        break
        except OSError:
            pass

        local_ip = "-"
        addrs = psutil.net_if_addrs().get(active_iface, [])
        for a in addrs:
            if a.family == socket.AF_INET:
                local_ip = a.address
                break

        dns_servers = []
        try:
            with open("/etc/resolv.conf", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        dns_servers.append(line.split()[1])
        except OSError:
            pass

        now = time.monotonic()
        if active_iface.startswith("w") and (now - self._last_wifi_ts > 4.0):
            self._last_wifi_ts = now
            try:
                res = subprocess.run(
                    ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,RATE", "dev", "wifi"],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                )
                for line in res.stdout.splitlines():
                    if line.startswith("yes:"):
                        p = line.split(":")
                        if len(p) >= 4:
                            self._cached_wifi = {
                                "ssid": p[1],
                                "signal": int(p[2]) if p[2].isdigit() else 0,
                                "rate": p[3],
                            }
                        break
            except Exception:
                pass

        return {
            "iface": active_iface,
            "local_ip": local_ip,
            "gateway": gateway,
            "dns": ", ".join(dns_servers[:3]) or "-",
            "wifi": self._cached_wifi,
        }

    @staticmethod
    def _read_file_int(path: Path, default: int = 0) -> int:
        try:
            txt = path.read_text(encoding="utf-8").strip()
            return int(txt) if txt else default
        except (OSError, ValueError):
            return default

    def _upower_rate(self, bat_name: str) -> tuple[float | None, str | None]:
        """Return (energy-rate W, time-to-empty/full string) from UPower.

        Cached for 10 s: UPower itself updates energy-rate on a slow cadence,
        so spawning it every 1.5 s would add wakeups without adding truth.
        """
        now = time.monotonic()
        if bat_name in self._upower_cache and now - self._last_upower_ts < 10.0:
            _, watts, remaining = self._upower_cache[bat_name]
            return watts, remaining

        watts: float | None = None
        remaining: str | None = None
        try:
            up_out = subprocess.check_output(
                ["upower", "-i", f"/org/freedesktop/UPower/devices/battery_{bat_name}"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.5,
            )
            for line in up_out.splitlines():
                k, _, v = line.strip().partition(":")
                v = v.strip()
                if k == "energy-rate":
                    m = re.search(r"([\d\.]+)", v)
                    if m:
                        watts = round(float(m.group(1)), 2)
                elif k == "time to empty" and v:
                    remaining = f"{v} left"
                elif k == "time to full" and v:
                    remaining = f"{v} to full"
        except Exception:
            watts, remaining = None, None

        self._upower_cache[bat_name] = (now, watts, remaining)
        self._last_upower_ts = now
        return watts, remaining

    def _read_battery_and_pd(self) -> dict:
        info = {
            "present": False,
            "percent": 0,
            "status": "AC",
            "watts": 0.0,
            "volts": 0.0,
            "cycles": 0,
            "energy_now_wh": 0.0,
            "energy_full_wh": 0.0,
            "energy_design_wh": 0.0,
            "health_pct": 100.0,
            "remaining_str": "N/A",
            "platform_profile": "unknown",
            "pd_volts": 0.0,
            "pd_amps": 0.0,
            "ac_online": False,
        }
        ps_root = Path("/sys/class/power_supply")
        if ps_root.is_dir():
            for d in sorted(ps_root.iterdir()):
                if d.name.startswith("BAT"):
                    info["present"] = True
                    info["percent"] = self._read_file_int(d / "capacity", 0)
                    try:
                        info["status"] = (
                            (d / "status").read_text(encoding="utf-8").strip()
                        )
                    except OSError:
                        info["status"] = "Unknown"
                    info["cycles"] = self._read_file_int(d / "cycle_count", 0)
                    p_uw = self._read_file_int(d / "power_now", 0)
                    v_uv = self._read_file_int(d / "voltage_now", 0)
                    e_now = self._read_file_int(d / "energy_now", 0)
                    e_full = self._read_file_int(d / "energy_full", 0)
                    e_des = self._read_file_int(d / "energy_full_design", 0)
                    info["watts"] = round(p_uw / 1e6, 2)
                    info["volts"] = round(v_uv / 1e6, 2)
                    info["energy_now_wh"] = round(e_now / 1e6, 2)
                    info["energy_full_wh"] = round(e_full / 1e6, 2)
                    info["energy_design_wh"] = round(e_des / 1e6, 2)
                    if e_des > 0:
                        info["health_pct"] = round(
                            min(100.0, (e_full / e_des) * 100.0), 1
                        )
                    if info["watts"] <= 0.0:
                        up_watts, up_remaining = self._upower_rate(d.name)
                        if up_watts is not None:
                            info["watts"] = up_watts
                        if up_remaining:
                            info["remaining_str"] = up_remaining
                    if info["remaining_str"] == "N/A":
                        if info["status"] == "Discharging" and info["watts"] > 0:
                            hrs = info["energy_now_wh"] / info["watts"]
                            info["remaining_str"] = (
                                f"{int(hrs)}h {int((hrs % 1) * 60)}m left"
                            )
                        elif info["status"] == "Charging" and info["watts"] > 0:
                            hrs = max(
                                0.0,
                                (info["energy_full_wh"] - info["energy_now_wh"])
                                / info["watts"],
                            )
                            info["remaining_str"] = (
                                f"{int(hrs)}h {int((hrs % 1) * 60)}m to full"
                            )
                        else:
                            info["remaining_str"] = info["status"]
                elif d.name.startswith("ADP") or d.name.startswith("AC"):
                    info["ac_online"] = self._read_file_int(d / "online", 0) == 1
                elif "ucsi" in d.name:
                    info["pd_volts"] = round(
                        self._read_file_int(d / "voltage_now", 0) / 1e6, 2
                    )
                    info["pd_amps"] = round(
                        self._read_file_int(d / "current_now", 0) / 1e6, 2
                    )

        pp = Path("/sys/firmware/acpi/platform_profile")
        if pp.is_file():
            try:
                info["platform_profile"] = pp.read_text().strip()
            except OSError:
                pass
        return info

    def sample(self) -> dict:
        now = time.monotonic()
        dt = max(now - self._last_ts, 1e-3)
        self._last_ts = now

        # CPU
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        cpu_total = sum(per_core) / max(len(per_core), 1)

        cur_times = psutil.cpu_times()
        d_user = max(
            0.0,
            (cur_times.user + cur_times.nice)
            - (self._last_cpu_times.user + self._last_cpu_times.nice),
        )
        d_sys = max(
            0.0,
            (cur_times.system + cur_times.irq + cur_times.softirq)
            - (
                self._last_cpu_times.system
                + self._last_cpu_times.irq
                + self._last_cpu_times.softirq
            ),
        )
        d_idle = max(
            0.0,
            (cur_times.idle + cur_times.iowait)
            - (self._last_cpu_times.idle + self._last_cpu_times.iowait),
        )
        d_tot = max(d_user + d_sys + d_idle, 1e-4)
        cpu_kernel_pct = round((d_sys / d_tot) * 100.0, 1)
        cpu_user_pct = round((d_user / d_tot) * 100.0, 1)
        self._last_cpu_times = cur_times

        freqs = psutil.cpu_freq(percpu=True) or []
        core_mhz = [round(f.current) for f in freqs]
        avg_mhz = round(sum(core_mhz) / len(core_mhz)) if core_mhz else None

        # Memory
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        mem_extra = self._read_meminfo_extra()

        # Network: report the active default-route interface, not the sum of
        # loopback, VPN, container and Wi-Fi interfaces.
        net_info = self._get_network_details()
        pernic = psutil.net_io_counters(pernic=True)
        active_iface = net_info["iface"]
        net = pernic.get(active_iface)
        if net is None:
            net = psutil.net_io_counters()
        prev_net = self._last_net_pernic.get(active_iface)
        if prev_net is not None:
            down_kbs = max(0.0, (net.bytes_recv - prev_net.bytes_recv) / dt / 1024.0)
            up_kbs = max(0.0, (net.bytes_sent - prev_net.bytes_sent) / dt / 1024.0)
        else:
            down_kbs = up_kbs = 0.0
        self._last_net_pernic = pernic

        # Disk
        disk = psutil.disk_io_counters()
        if disk and self._last_disk:
            read_mbs = max(
                0.0, (disk.read_bytes - self._last_disk.read_bytes) / dt / (1024.0**2)
            )
            write_mbs = max(
                0.0, (disk.write_bytes - self._last_disk.write_bytes) / dt / (1024.0**2)
            )
            read_iops = max(0.0, (disk.read_count - self._last_disk.read_count) / dt)
            write_iops = max(0.0, (disk.write_count - self._last_disk.write_count) / dt)
        else:
            read_mbs = write_mbs = read_iops = write_iops = 0.0
        self._last_disk = disk

        # Kernel counters
        ctxt, intr, procs_running, procs_blocked = self._read_proc_stat()
        ctxt_s = max(0.0, (ctxt - self._last_stat[0]) / dt)
        intr_s = max(0.0, (intr - self._last_stat[1]) / dt)
        self._last_stat = (ctxt, intr, procs_running, procs_blocked)

        # GPU
        gpus: list[GpuSnapshot] = self.gpu_collector.sample()
        primary_gpu = gpus[0] if gpus else GpuSnapshot()

        # Battery & Power
        battery = self._read_battery_and_pd()

        # Temperatures
        temps = psutil.sensors_temperatures()
        cpu_temp = 0.0
        nvme_temp = 0.0
        wifi_temp = 0.0
        if "coretemp" in temps and temps["coretemp"]:
            package = next(
                (
                    t.current
                    for t in temps["coretemp"]
                    if "package" in (t.label or "").lower()
                ),
                None,
            )
            cpu_temp = package if package is not None else temps["coretemp"][0].current
        elif "acpitz" in temps and temps["acpitz"]:
            cpu_temp = temps["acpitz"][0].current
        if "nvme" in temps and temps["nvme"]:
            nvme_temp = temps["nvme"][0].current
        for k, v in temps.items():
            if k.startswith("mt79") and v:
                wifi_temp = v[0].current

        # Push histories
        self.cpu_hist.append(cpu_total)
        self.cpu_kernel_hist.append(cpu_kernel_pct)
        self.mem_hist.append(mem.percent)
        if primary_gpu.busy_available:
            self.gpu_hist.append(primary_gpu.busy_pct)
        # When the driver has no visible engine counters, leave the chart empty
        # instead of seeding it with a synthetic 0 %.
        self.net_down_hist.append(down_kbs)
        self.net_up_hist.append(up_kbs)
        self.disk_read_hist.append(read_mbs)
        self.disk_write_hist.append(write_mbs)
        if battery["present"]:
            self.power_watts_hist.append(battery["watts"])

        load1, load5, load15 = os.getloadavg()
        uptime_s = int(time.time() - psutil.boot_time())

        return {
            "cpu_total": round(cpu_total, 1),
            "cpu_user_pct": cpu_user_pct,
            "cpu_kernel_pct": cpu_kernel_pct,
            "per_core": per_core,
            "core_mhz": core_mhz,
            "avg_mhz": avg_mhz,
            "cpu_temp": round(cpu_temp, 1),
            "nvme_temp": round(nvme_temp, 1),
            "wifi_temp": round(wifi_temp, 1),
            "load_avg": (round(load1, 2), round(load5, 2), round(load15, 2)),
            "psi": PsiCollector.sample(),
            "uptime_s": uptime_s,
            "ctxt_s": round(ctxt_s, 1),
            "intr_s": round(intr_s, 1),
            "procs_running": procs_running,
            "procs_blocked": procs_blocked,
            "mem": mem,
            "swap": swap,
            "mem_extra": mem_extra,
            "swaps": self._read_swaps(),
            "down_kbs": round(down_kbs, 1),
            "up_kbs": round(up_kbs, 1),
            "net_totals_mb": (
                round(net.bytes_recv / (1024 * 1024), 1),
                round(net.bytes_sent / (1024 * 1024), 1),
                net.errin + net.errout,
                net.dropin + net.dropout,
            ),
            "net_info": net_info,
            "read_mbs": round(read_mbs, 2),
            "write_mbs": round(write_mbs, 2),
            "read_iops": round(read_iops, 1),
            "write_iops": round(write_iops, 1),
            "block_devices": self._get_block_devices(),
            "vault": self._check_important_vault(),
            "gpu": primary_gpu,
            "gpus": gpus,
            "battery": battery,
        }
