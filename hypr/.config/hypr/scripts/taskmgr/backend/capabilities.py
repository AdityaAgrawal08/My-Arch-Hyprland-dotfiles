#!/usr/bin/env python3
"""Detect optional capabilities and explain unavailable prerequisites honestly."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class CapabilityCollector:
    @staticmethod
    def get_capabilities() -> list[dict]:
        rows: list[dict] = []

        bpftrace = shutil.which("bpftrace")
        btf = Path("/sys/kernel/btf/vmlinux")
        if bpftrace and btf.is_file():
            root = os.geteuid() == 0
            rows.append(
                {
                    "feature": "eBPF live events",
                    "status": "Available" if root else "Partial",
                    "details": f"bpftrace found at {bpftrace}; BTF present. "
                    + (
                        "Open Hardware → eBPF Live Events to run a probe."
                        if root
                        else "The tab is visible but Start is disabled until "
                        "the app runs as root or with CAP_BPF."
                    ),
                    "command": "sudo bpftrace -l 'tracepoint:syscalls:*'",
                }
            )
        else:
            missing = []
            if not bpftrace:
                missing.append("bpftrace")
            if not btf.is_file():
                missing.append("/sys/kernel/btf/vmlinux")
            rows.append(
                {
                    "feature": "eBPF live events",
                    "status": "Unavailable",
                    "details": "Missing prerequisite(s): "
                    + ", ".join(missing)
                    + ". Install them to enable Hardware → eBPF Live Events.",
                    "command": "sudo pacman -S bpftrace",
                }
            )

        smartctl = shutil.which("smartctl")
        nvme = shutil.which("nvme")
        if smartctl or nvme:
            rows.append(
                {
                    "feature": "SMART / NVMe health",
                    "status": "Available",
                    "details": "Tooling: "
                    + ", ".join(x for x in (smartctl, nvme) if x),
                    "command": "sudo smartctl -a /dev/nvme0n1",
                }
            )
        else:
            rows.append(
                {
                    "feature": "SMART / NVMe health",
                    "status": "Unavailable",
                    "details": "Neither smartctl nor nvme-cli is installed; "
                    "the app does not invent health values.",
                    "command": "sudo pacman -S smartmontools nvme-cli",
                }
            )

        rapl = Path("/sys/class/powercap/intel-rapl:0/energy_uj")
        if rapl.is_file() and os.access(rapl, os.R_OK):
            rows.append(
                {
                    "feature": "RAPL live package power",
                    "status": "Available",
                    "details": "energy_uj is readable.",
                    "command": "cat /sys/class/powercap/intel-rapl:0/energy_uj",
                }
            )
        else:
            rows.append(
                {
                    "feature": "RAPL live package power",
                    "status": "Unavailable",
                    "details": "energy_uj is root-only on this machine; "
                    "the static package limit is shown instead.",
                    "command": "sudo cat /sys/class/powercap/intel-rapl:0/energy_uj",
                }
            )

        io_stat = next(Path("/sys/fs/cgroup/system.slice").glob("*/io.stat"), None)
        if io_stat is not None:
            rows.append(
                {
                    "feature": "Per-service disk I/O",
                    "status": "Available",
                    "details": f"cgroup io.stat is present, e.g. {io_stat}",
                    "command": "cat /sys/fs/cgroup/system.slice/*/io.stat",
                }
            )
        else:
            rows.append(
                {
                    "feature": "Per-service disk I/O",
                    "status": "Unavailable",
                    "details": "The cgroup v2 io controller is not delegated "
                    "to service cgroups on this machine; CPU time and memory "
                    "are still shown per service.",
                    "command": "cat /sys/fs/cgroup/cgroup.controllers",
                }
            )

        nvidia = False
        amd = False
        try:
            for dev in Path("/sys/bus/pci/devices").iterdir():
                try:
                    vendor = (dev / "vendor").read_text().strip()
                except OSError:
                    continue
                if vendor == "0x10de":
                    nvidia = True
                elif vendor in ("0x1002", "0x1022"):
                    amd = True
        except OSError:
            pass
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia:
            nvidia_status = "Unavailable"
            nvidia_details = "No NVIDIA GPU detected."
        elif nvidia_smi:
            nvidia_status = "Partial"
            nvidia_details = (
                f"NVIDIA GPU + nvidia-smi found at {nvidia_smi}. Aggregate "
                "utilization, temperature, memory and per-process compute "
                "memory are shown; per-process utilization is not exposed by "
                "nvidia-smi."
            )
        else:
            nvidia_status = "Partial"
            nvidia_details = (
                "NVIDIA GPU detected but nvidia-smi is not installed; aggregate "
                "telemetry is unavailable."
            )
        rows.append(
            {
                "feature": "NVIDIA GPU telemetry",
                "status": nvidia_status,
                "details": nvidia_details,
                "command": "nvidia-smi --query-gpu=name,utilization.gpu,"
                "memory.used,memory.total,temperature.gpu --format=csv",
            }
        )
        rows.append(
            {
                "feature": "AMD per-process GPU",
                "status": "Unavailable" if not amd else "Available",
                "details": "No AMD GPU detected."
                if not amd
                else "AMD amdgpu DRM fdinfo and gpu_busy_percent are supported.",
                "command": "lspci -nn | grep -i -E 'amd|ati'",
            }
        )

        threshold_files = sorted(
            str(path)
            for path in Path("/sys/class/power_supply").glob(
                "BAT*/charge_control_end_threshold"
            )
        )
        if threshold_files:
            rows.append(
                {
                    "feature": "Battery charge threshold",
                    "status": "Available",
                    "details": "Threshold control: " + ", ".join(threshold_files),
                    "command": "cat " + threshold_files[0],
                }
            )
        else:
            rows.append(
                {
                    "feature": "Battery charge threshold",
                    "status": "Unavailable",
                    "details": "This battery/firmware exposes no "
                    "charge_control_end_threshold; the Fan & Charge editor is "
                    "disabled and the app does not guess one.",
                    "command": "find /sys/class/power_supply -name 'charge_control*'",
                }
            )

        pwm_outputs = sorted(
            str(path) for path in Path("/sys/class/hwmon").glob("hwmon*/pwm[0-9]")
        )
        fan_inputs = sorted(
            str(path)
            for path in Path("/sys/class/hwmon").glob("hwmon*/fan[0-9]*_input")
        )
        if pwm_outputs:
            rows.append(
                {
                    "feature": "Fan curves / manual fan control",
                    "status": "Available",
                    "details": "Writable PWM outputs: " + ", ".join(pwm_outputs[:4]),
                    "command": "find /sys/class/hwmon -name 'pwm[0-9]'",
                }
            )
        else:
            rows.append(
                {
                    "feature": "Fan curves / manual fan control",
                    "status": "Unavailable",
                    "details": "No writable pwm* fan-control outputs are exposed by "
                    "hwmon. The Fan & Charge curve editor is disabled; fan RPM "
                    "and temperatures remain visible read-only."
                    if fan_inputs
                    else "No hwmon fan inputs or writable pwm* outputs are exposed. "
                    "Fan RPM/curves are therefore not shown.",
                    "command": "find /sys/class/hwmon -name 'pwm[0-9]' -o -name 'fan*_input'",
                }
            )

        return rows
