#!/usr/bin/env python3
"""JSON/Markdown/CSV diagnostic report and SQLite history snapshots."""

from __future__ import annotations

import csv
import dataclasses
import json
import os
import platform
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from .doctor import SystemDoctor
from .gpu import GpuCollector
from .hardware import HardwareAndMediaCollector
from .performance import PerformanceCollector
from .ports import PortsCollector
from .power import PowerAndWakeupCollector
from .processes import ProcessCollector
from .services import ServicesCollector
from .storage_health import StorageHealthCollector


def _state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")))
    return base / "taskmgr"


def _json_safe_perf(perf: dict) -> dict:
    out = {k: v for k, v in perf.items() if k not in ("mem", "swap", "gpu")}
    mem = perf.get("mem")
    swap = perf.get("swap")
    gpu = perf.get("gpu")
    if mem is not None:
        out["memory"] = {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "cached": getattr(mem, "cached", 0),
            "percent": mem.percent,
        }
    if swap is not None:
        out["swap"] = {
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
            "percent": swap.percent,
        }
    if gpu is not None and dataclasses.is_dataclass(gpu):
        out["gpu"] = dataclasses.asdict(gpu)
    return out


def _collect() -> dict:
    # Let the interval-based CPU/disk/network collectors establish a real
    # baseline instead of reporting the structural 0.0 of an instant sample.
    perf_collector = PerformanceCollector()
    time.sleep(0.6)
    perf = perf_collector.sample()
    ports_collector = PortsCollector()
    ports, pid_ports = ports_collector.sample()
    procs, groups = ProcessCollector(GpuCollector()).sample(
        pid_ports=pid_ports, hide_kernel_threads=False
    )
    services = {
        "system": ServicesCollector.get_services("system"),
        "user": ServicesCollector.get_services("user"),
    }
    power = PowerAndWakeupCollector().sample()
    pci, usb = HardwareAndMediaCollector.get_pci_and_usb_devices()
    sensors = HardwareAndMediaCollector.get_all_sensors()
    storage_health = StorageHealthCollector.sample(perf.get("block_devices", []))
    doctor = SystemDoctor.run_full_audit()
    return {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "host": {
            "hostname": platform.node(),
            "kernel": platform.release(),
            "platform": platform.platform(),
            "uptime_s": perf.get("uptime_s"),
        },
        "performance": _json_safe_perf(perf),
        "psi": perf.get("psi", {}),
        "processes": procs,
        "app_groups": groups,
        "ports": ports,
        "services": services,
        "power": power,
        "hardware": {
            "pci": pci,
            "usb": usb,
            "sensors": sensors,
            "storage_health": storage_health,
        },
        "doctor": doctor,
    }


def _write_history(report: dict) -> Path:
    state = _state_dir()
    state.mkdir(parents=True, exist_ok=True)
    db = state / "history.db"
    perf = report.get("performance", {})
    mem = perf.get("memory", {})
    swap = perf.get("swap", {})
    gpu = perf.get("gpu", {})
    battery = perf.get("battery", {})
    psi = report.get("psi", {})
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                ts TEXT PRIMARY KEY,
                cpu REAL,
                mem_pct REAL,
                swap_pct REAL,
                gpu_pct REAL,
                battery_pct INTEGER,
                battery_watts REAL,
                net_down_kbs REAL,
                net_up_kbs REAL,
                disk_read_mbs REAL,
                disk_write_mbs REAL,
                psi_cpu_some REAL,
                psi_mem_some REAL,
                psi_io_some REAL
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["generated"],
                perf.get("cpu_total"),
                mem.get("percent"),
                swap.get("percent"),
                gpu.get("busy_pct"),
                battery.get("percent"),
                battery.get("watts"),
                perf.get("down_kbs"),
                perf.get("up_kbs"),
                perf.get("read_mbs"),
                perf.get("write_mbs"),
                psi.get("cpu", {}).get("some_avg10"),
                psi.get("memory", {}).get("some_avg10"),
                psi.get("io", {}).get("some_avg10"),
            ),
        )
        conn.commit()
    return db


def _markdown(report: dict) -> str:
    perf = report.get("performance", {})
    mem = perf.get("memory", {})
    battery = perf.get("battery", {})
    doctor = report.get("doctor", [])
    counts: dict[str, int] = {}
    for check in doctor:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    lines = [
        "# Task Manager Diagnostic Report",
        "",
        f"- Generated: `{report['generated']}`",
        f"- Host: `{report['host']['hostname']}` / `{report['host']['kernel']}`",
        f"- CPU: **{perf.get('cpu_total', '?')}%**  |  "
        f"RAM: **{mem.get('percent', '?')}%**  |  "
        f"Battery: **{battery.get('percent', '?')}% / {battery.get('watts', '?')} W**",
        "",
        "## Doctor",
        "",
        f"Working: **{counts.get('WORKING', 0)}**, "
        f"Warnings: **{counts.get('WARNING', 0)}**, "
        f"Failing: **{counts.get('NOT WORKING', 0)}**",
        "",
    ]
    for check in doctor:
        if check["status"] == "WORKING":
            continue
        lines.append(
            f"- **{check['status']}** `{check['component']}`: "
            f"{check['summary']} — {check['details']}"
        )
    procs = sorted(
        report.get("processes", []),
        key=lambda p: (p.get("cpu", 0.0), p.get("mem_mb", 0.0)),
        reverse=True,
    )[:10]
    lines += [
        "",
        "## Top processes by CPU",
        "",
        "| PID | Process | CPU % | Memory | Unit |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for p in procs:
        lines.append(
            f"| {p['pid']} | {p['name']} | {p['cpu']} | "
            f"{p['mem_mb']} MB | {p['unit']} |"
        )
    storage = report.get("hardware", {}).get("storage_health", [])
    if storage:
        lines += [
            "",
            "## Storage health",
            "",
            "| Device | Model | SMART | Temp | Power-On | Used |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for h in storage:
            lines.append(
                f"| {h['device']} | {h['model']} | {h['health']} | "
                f"{h['temperature']} | {h['power_on_hours']} | "
                f"{h['percentage_used']} |"
            )

    listening = [p for p in report.get("ports", []) if p.get("is_listening")]
    lines += [
        "",
        f"## Listening ports ({len(listening)})",
        "",
        "| Proto | Port | Local | Process | PID |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for p in listening:
        lines.append(
            f"| {p['proto']} | {p['port']} | {p['local']} | "
            f"{p['process']} | {p['pid']} |"
        )
    return "\n".join(lines) + "\n"


def write_report(outdir: str | None = None) -> dict[str, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = Path(outdir).expanduser() if outdir else _state_dir() / "reports" / stamp
    target.mkdir(parents=True, exist_ok=True)
    report = _collect()

    json_path = target / "report.json"
    md_path = target / "report.md"
    proc_path = target / "processes.csv"
    port_path = target / "ports.csv"

    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")

    with proc_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "pid",
                "name",
                "user",
                "cpu_percent",
                "gpu_percent",
                "memory_mb",
                "threads",
                "state",
                "unit",
                "command",
            ]
        )
        for p in report["processes"]:
            writer.writerow(
                [
                    p.get("pid"),
                    p.get("name"),
                    p.get("user"),
                    p.get("cpu"),
                    p.get("gpu"),
                    p.get("mem_mb"),
                    p.get("threads"),
                    p.get("state"),
                    p.get("unit"),
                    p.get("cmd"),
                ]
            )

    with port_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "proto",
                "local",
                "remote",
                "state",
                "pid",
                "process",
                "unit",
                "purpose",
            ]
        )
        for p in report["ports"]:
            writer.writerow(
                [
                    p.get("proto"),
                    p.get("local"),
                    p.get("remote"),
                    p.get("state"),
                    p.get("pid"),
                    p.get("process"),
                    p.get("unit"),
                    p.get("purpose"),
                ]
            )

    db = _write_history(report)
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "processes_csv": str(proc_path),
        "ports_csv": str(port_path),
        "history_db": str(db),
    }
