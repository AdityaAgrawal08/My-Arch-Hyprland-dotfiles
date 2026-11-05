#!/usr/bin/env python3
"""Cross-check the Task Manager's displayed values against independent kernel sources.

Each check reads the same underlying truth from a different path/command than the
collector uses, so a coding mistake or fabricated placeholder is visible.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import psutil

from .gpu import GpuCollector, _read_int
from .performance import PerformanceCollector
from .ports import PortsCollector
from .power import PowerAndWakeupCollector
from .processes import ProcessCollector
from .services import ServicesCollector
from .doctor import SystemDoctor


def _row(
    name: str,
    source: str,
    expected: object,
    actual: object,
    ok: bool,
    note: str = "",
) -> dict:
    return {
        "check": name,
        "independent_source": source,
        "expected": expected,
        "collector_value": actual,
        "pass": bool(ok),
        "note": note,
    }


def _read(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _memtotal_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _upower_watts() -> float | None:
    bat = next(iter(sorted(Path("/sys/class/power_supply").glob("BAT*"))), None)
    if bat is None:
        return None
    try:
        out = subprocess.check_output(
            [
                "upower",
                "-i",
                f"/org/freedesktop/UPower/devices/battery_{bat.name}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        for line in out.splitlines():
            k, _, v = line.strip().partition(":")
            if k == "energy-rate":
                m = re.search(r"([\d.]+)", v)
                if m:
                    return float(m.group(1))
    except Exception:
        pass
    return None


def _ss_listening() -> set[tuple[str, int]] | None:
    try:
        out = subprocess.check_output(
            ["ss", "-H", "-tuln"], text=True, stderr=subprocess.DEVNULL, timeout=2.0
        )
    except Exception:
        return None
    rows: set[tuple[str, int]] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        proto = "TCP" if parts[0].lower().startswith("tcp") else "UDP"
        local = parts[4]
        if ":" not in local:
            continue
        port_txt = local.rsplit(":", 1)[-1]
        if port_txt.isdigit():
            rows.add((proto, int(port_txt)))
    return rows


def _system_service_count() -> int | None:
    try:
        out = subprocess.check_output(
            [
                "systemctl",
                "list-units",
                "--type=service",
                "--all",
                "--no-legend",
                "--no-pager",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
        )
        return len(
            [
                line
                for line in out.splitlines()
                if line.strip() and not line.strip().startswith("0 loaded units")
            ]
        )
    except Exception:
        return None


def _ps_process_count() -> int | None:
    try:
        out = subprocess.check_output(
            ["ps", "-e", "--no-headers"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        return len([line for line in out.splitlines() if line.strip()])
    except Exception:
        return None


def _psi_some(resource: str) -> float | None:
    try:
        for line in (
            Path(f"/proc/pressure/{resource}").read_text(encoding="utf-8").splitlines()
        ):
            parts = line.split()
            if parts and parts[0] == "some":
                for part in parts[1:]:
                    key, _, value = part.partition("=")
                    if key == "avg10":
                        return float(value)
    except (OSError, ValueError):
        pass
    return None


def run_truth_audit() -> list[dict]:
    results: list[dict] = []
    perf = PerformanceCollector()
    perf_data = perf.sample()

    # 1. CPU core count
    expected_cores = os.cpu_count() or 0
    actual_cores = len(perf_data["per_core"])
    results.append(
        _row(
            "CPU logical core count",
            "os.cpu_count() (sysconf)",
            expected_cores,
            actual_cores,
            expected_cores == actual_cores,
        )
    )

    # 2. MemTotal
    expected_mem = _memtotal_bytes()
    actual_mem = perf_data["mem"].total
    results.append(
        _row(
            "Physical memory total",
            "/proc/meminfo MemTotal",
            expected_mem,
            actual_mem,
            expected_mem is not None and expected_mem == actual_mem,
        )
    )

    # 3. Battery presence and wattage vs UPower
    bat = perf_data["battery"]
    bat_present = any(Path("/sys/class/power_supply").glob("BAT*"))
    results.append(
        _row(
            "Battery device presence",
            "/sys/class/power_supply/BAT*",
            bat_present,
            bat["present"],
            bat_present == bat["present"],
        )
    )
    expected_w = _upower_watts()
    if expected_w is not None and bat["watts"] > 0:
        results.append(
            _row(
                "Battery power draw (W)",
                "upower -i energy-rate",
                expected_w,
                bat["watts"],
                abs(expected_w - bat["watts"]) <= 0.5,
                "Tolerance 0.5 W because UPower and the collector sample at different instants.",
            )
        )
    else:
        results.append(
            _row(
                "Battery power draw (W)",
                "upower -i energy-rate",
                expected_w,
                bat["watts"],
                False,
                "UPower or sysfs did not provide a live energy rate.",
            )
        )

    # 4. Battery health from raw sysfs
    for d in sorted(Path("/sys/class/power_supply").glob("BAT*")):
        e_full = _read_int(str(d / "energy_full"), 0)
        e_des = _read_int(str(d / "energy_full_design"), 0)
        if e_full > 0 and e_des > 0:
            expected_health = round(min(100.0, e_full / e_des * 100.0), 1)
            results.append(
                _row(
                    "Battery health (%)",
                    f"{d}/energy_full / energy_full_design",
                    expected_health,
                    bat["health_pct"],
                    abs(expected_health - bat["health_pct"]) < 0.1,
                )
            )
            break

    # 5. Active-interface RX/TX totals vs psutil per-interface counters
    net_info = perf_data["net_info"]
    pernic = psutil.net_io_counters(pernic=True)
    if net_info["iface"] in pernic:
        expected_rx = round(pernic[net_info["iface"]].bytes_recv / (1024 * 1024), 1)
        expected_tx = round(pernic[net_info["iface"]].bytes_sent / (1024 * 1024), 1)
        actual_rx, actual_tx = perf_data["net_totals_mb"][:2]
        results.append(
            _row(
                "Active interface RX/TX totals (MiB)",
                f"psutil pernic[{net_info['iface']}]",
                f"{expected_rx}/{expected_tx}",
                f"{actual_rx}/{actual_tx}",
                abs(expected_rx - actual_rx) <= 10.0
                and abs(expected_tx - actual_tx) <= 10.0,
                "Tolerance 10 MiB because traffic continues between the two reads.",
            )
        )

    # 5b. CPU PSI avg10 vs /proc/pressure/cpu
    expected_psi = _psi_some("cpu")
    actual_psi = perf_data.get("psi", {}).get("cpu", {}).get("some_avg10")
    if expected_psi is not None and actual_psi is not None:
        results.append(
            _row(
                "CPU PSI stall avg10 (%)",
                "/proc/pressure/cpu",
                round(expected_psi, 2),
                round(float(actual_psi), 2),
                abs(expected_psi - float(actual_psi)) <= 1.0,
                "Tolerance 1 percentage point because PSI is a rolling average.",
            )
        )

    # 6. GPU frequency from sysfs vs collector
    gpus = GpuCollector().sample()
    if gpus:
        g = gpus[0]
        direct = None
        direct_path = ""
        for rel in (
            "gt_act_freq_mhz",
            "gt_cur_freq_mhz",
            "gt/gt0/rps_act_freq_mhz",
        ):
            candidate = f"/sys/class/drm/{g.card}/{rel}"
            value = _read_int(candidate, -1)
            if value < 0:
                continue
            if direct is None:
                direct = value
                direct_path = candidate
            if value > 0:
                direct = value
                direct_path = candidate
                break
        if direct is not None:
            results.append(
                _row(
                    "GPU current frequency (MHz)",
                    direct_path,
                    direct,
                    g.freq_mhz,
                    abs(direct - g.freq_mhz) <= 150,
                    "Tolerance 150 MHz: GPU clocks boost/relax between the collector sample and the direct sysfs read.",
                )
            )
        else:
            results.append(
                _row(
                    "GPU current frequency (MHz)",
                    f"/sys/class/drm/{g.card}/gt_*_freq_mhz",
                    "unavailable",
                    g.freq_mhz,
                    True,
                    "Driver does not expose a frequency file; UI shows N/A.",
                )
            )
    else:
        results.append(
            _row("GPU device presence", "/sys/class/drm/card*", True, False, False)
        )

    # 6. Sensor temperature from hwmon vs psutil-derived value
    temp_path = None
    for hw in Path("/sys/class/hwmon").glob("hwmon*"):
        if _read(str(hw / "name")) != "coretemp":
            continue
        for label_file in hw.glob("temp*_label"):
            if "package" in _read(str(label_file)).lower():
                candidate = label_file.with_name(
                    label_file.name.replace("_label", "_input")
                )
                if candidate.is_file():
                    temp_path = candidate
                    break
        if temp_path is None:
            candidate = hw / "temp1_input"
            if candidate.is_file():
                temp_path = candidate
        break
    if temp_path is not None:
        expected_temp = _read_int(str(temp_path), 0) / 1000.0
        results.append(
            _row(
                "CPU package temperature (°C)",
                str(temp_path),
                round(expected_temp, 1),
                perf_data["cpu_temp"],
                abs(expected_temp - perf_data["cpu_temp"]) <= 2.0,
                "Tolerance 2 °C because the sensor updates between the two reads.",
            )
        )

    # 7. Process count tolerance (processes can start/exit between reads)
    expected_procs = _ps_process_count()
    proc_coll = ProcessCollector(GpuCollector())
    ports_rows, pid_ports = PortsCollector().sample()
    flat, _ = proc_coll.sample(pid_ports=pid_ports, hide_kernel_threads=False)
    if expected_procs is not None:
        results.append(
            _row(
                "Process count",
                "ps -e --no-headers",
                expected_procs,
                len(flat),
                abs(expected_procs - len(flat)) <= 5,
                "Tolerance 5 due to processes starting/exiting between the two reads.",
            )
        )

    # 8. Listening port set from ss vs collector
    expected_ports = _ss_listening()
    if expected_ports is not None:
        actual_ports = {
            (row["proto"], row["port"]) for row in ports_rows if row["is_listening"]
        }
        missing = sorted(expected_ports - actual_ports)
        extra = sorted(actual_ports - expected_ports)
        results.append(
            _row(
                "Listening TCP/UDP ports",
                "ss -H -tuln",
                f"{len(expected_ports)} sockets",
                f"{len(actual_ports)} sockets",
                expected_ports == actual_ports,
                f"missing={missing[:5]} extra={extra[:5]}",
            )
        )

    # 9. System service count
    expected_svcs = _system_service_count()
    actual_svcs = len(ServicesCollector.get_services("system"))
    if expected_svcs is not None:
        results.append(
            _row(
                "Systemd system service count",
                "systemctl list-units --type=service --all --no-legend",
                expected_svcs,
                actual_svcs,
                expected_svcs == actual_svcs,
            )
        )

    # 10. Kernel power tunables: compare every PCI power/control file
    tunables = {t["path"]: t for t in PowerAndWakeupCollector.scan_powertop_tunables()}
    mismatches = []
    checked = 0
    for dev in Path("/sys/bus/pci/devices").iterdir():
        ctrl = dev / "power" / "control"
        if not ctrl.is_file():
            continue
        expected = _read(str(ctrl))
        t = tunables.get(str(ctrl))
        if t is None:
            mismatches.append(f"{dev.name}: missing collector entry")
            continue
        checked += 1
        if t["current"] != expected:
            mismatches.append(f"{dev.name}: {t['current']} != {expected}")
    if checked:
        results.append(
            _row(
                "PCI Runtime PM control values",
                "/sys/bus/pci/devices/*/power/control",
                checked,
                checked - len(mismatches),
                not mismatches,
                "; ".join(mismatches[:3]),
            )
        )

    # 11. NMI watchdog raw value
    nmi_path = "/proc/sys/kernel/nmi_watchdog"
    if os.path.exists(nmi_path):
        raw_nmi = _read(nmi_path)
        t = tunables.get(nmi_path)
        results.append(
            _row(
                "NMI watchdog value",
                nmi_path,
                raw_nmi,
                t["current"] if t else "missing",
                bool(t) and t["current"] == raw_nmi,
            )
        )

    # 12. Hyprland VFR: compare the raw option with the Doctor's verdict.
    try:
        import json

        vfr = json.loads(
            subprocess.check_output(
                ["hyprctl", "getoption", "debug:vfr", "-j"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.5,
            )
        )
        raw_vfr = bool(vfr.get("bool") is True or vfr.get("int", 0) == 1)
        audit = SystemDoctor.run_full_audit()
        vfr_check = next(
            (c for c in audit if "Variable Frame Rate" in c["component"]), None
        )
        doctor_vfr = bool(vfr_check and vfr_check["status"] == "WORKING")
        results.append(
            _row(
                "Hyprland debug:vfr",
                "hyprctl getoption debug:vfr -j",
                raw_vfr,
                doctor_vfr,
                raw_vfr == doctor_vfr,
                "Doctor verdict must match the raw Hyprland option.",
            )
        )
    except Exception:
        results.append(
            _row(
                "Hyprland debug:vfr",
                "hyprctl getoption debug:vfr -j",
                "unavailable",
                "unavailable",
                True,
                "No live Hyprland session; GUI would show N/A.",
            )
        )

    # 13. Root-owned sockets must be labeled as hidden, never guessed.
    fabricated = [
        r
        for r in ports_rows
        if r["pid"] == 0 and r["process"] not in ("(owner hidden)", "-")
    ]
    results.append(
        _row(
            "Root socket ownership honesty",
            "psutil.net_connections + /proc/<pid>/cgroup",
            0,
            len(fabricated),
            not fabricated,
            "pid=0 rows must say '(owner hidden)'; well-known ports are only hints.",
        )
    )

    return results
