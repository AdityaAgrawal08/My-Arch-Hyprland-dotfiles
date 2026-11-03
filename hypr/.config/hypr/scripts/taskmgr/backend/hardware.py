#!/usr/bin/env python3
"""Hardware Bus (PCI/USB), Audio (PipeWire), Camera (V4L2), Bluetooth (RFKill), Sensors & Logs."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .gpu import pci_device_name


def _read(path: str | Path, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return default


class HardwareAndMediaCollector:
    """Collects Audio/Camera/Bluetooth status, PCI/USB buses, hwmon sensors, kernel modules, and logs."""

    @staticmethod
    def get_audio_camera_bluetooth() -> dict:
        sinks: list[dict] = []
        sources: list[dict] = []
        streams: list[dict] = []
        cameras: list[dict] = []
        rfkill_items: list[dict] = []

        # 1. Parse wpctl status
        try:
            out = subprocess.check_output(
                ["wpctl", "status"], text=True, stderr=subprocess.DEVNULL, timeout=2.0
            )
            section = ""
            subsection = ""
            for raw_line in out.splitlines():
                line = (
                    raw_line.replace("│", "")
                    .replace("├─", "")
                    .replace("└─", "")
                    .strip()
                )
                if line in ("Audio", "Video", "Settings"):
                    section = line
                    subsection = ""
                    continue
                if line.endswith(":") and any(
                    k in line
                    for k in ("Devices:", "Sinks:", "Sources:", "Streams:", "Clients:")
                ):
                    subsection = line.rstrip(":")
                    continue

                if section == "Audio" and subsection in ("Sinks", "Sources"):
                    is_default = line.startswith("*")
                    clean = line.lstrip("*").strip()
                    m = re.match(
                        r"^(\d+)\.\s+(.+?)\s+\[vol:\s*([\d\.]+)(?:\s+(MUTED))?\]", clean
                    )
                    if m:
                        vol_pct = round(float(m.group(3)) * 100)
                        item = {
                            "id": int(m.group(1)),
                            "name": m.group(2).strip(),
                            "vol_pct": vol_pct,
                            "muted": bool(m.group(4)),
                            "default": is_default,
                            "warning": "Over-amplified (>100%)"
                            if vol_pct > 100
                            else "OK",
                        }
                        if subsection == "Sinks":
                            sinks.append(item)
                        else:
                            sources.append(item)
                elif section == "Audio" and subsection == "Streams":
                    # Only active links contain ">" (source -> destination).
                    # A bare "95. opencode" line is a client header, not a stream.
                    if ">" in line:
                        streams.append({"stream": line})
        except Exception:
            pass

        # 2. Check V4L2 cameras (/dev/video*) and which PID has them open
        video_holders: dict[str, list[str]] = {}
        for pid_dir in Path("/proc").glob("[0-9]*"):
            fd_dir = pid_dir / "fd"
            try:
                for fd in fd_dir.iterdir():
                    target = os.readlink(fd)
                    if target.startswith("/dev/video"):
                        comm = _read(pid_dir / "comm", pid_dir.name)
                        video_holders.setdefault(target, []).append(
                            f"{comm} (PID {pid_dir.name})"
                        )
            except OSError:
                continue

        v4l_root = Path("/sys/class/video4linux")
        if v4l_root.is_dir():
            for vdev in sorted(v4l_root.iterdir()):
                dev_node = f"/dev/{vdev.name}"
                name = _read(vdev / "name", vdev.name)
                users = video_holders.get(dev_node, [])
                cameras.append(
                    {
                        "node": dev_node,
                        "name": name,
                        "in_use": bool(users),
                        "used_by": ", ".join(sorted(set(users)))
                        if users
                        else "Idle (no visible process has it open)",
                    }
                )

        # 3. RFKill (Bluetooth / Wi-Fi soft & hard block)
        try:
            rf_out = subprocess.check_output(
                ["rfkill", "-J"], text=True, stderr=subprocess.DEVNULL, timeout=1.5
            )
            rf_data = json.loads(rf_out)
            for item in rf_data.get("rfkilldevices", []):
                rfkill_items.append(
                    {
                        "id": item.get("id"),
                        "type": item.get("type", ""),
                        "device": item.get("device", ""),
                        "soft": item.get("soft", ""),
                        "hard": item.get("hard", ""),
                    }
                )
        except Exception:
            pass

        return {
            "sinks": sinks,
            "sources": sources,
            "streams": streams,
            "cameras": cameras,
            "rfkill": rfkill_items,
        }

    @staticmethod
    def get_pci_and_usb_devices() -> tuple[list[dict], list[dict]]:
        pci_list: list[dict] = []
        pci_root = Path("/sys/bus/pci/devices")
        if pci_root.is_dir():
            for d in sorted(pci_root.iterdir()):
                vendor = _read(d / "vendor")
                device = _read(d / "device")
                name = pci_device_name(vendor, device) or f"{vendor}:{device}"
                driver = "-"
                try:
                    driver = os.path.basename(os.path.realpath(d / "driver"))
                except OSError:
                    pass
                rpm_status = _read(d / "power" / "runtime_status", "-")
                rpm_ctrl = _read(d / "power" / "control", "-")
                pci_list.append(
                    {
                        "slot": d.name.removeprefix("0000:"),
                        "name": name,
                        "driver": driver,
                        "power_state": rpm_status,
                        "power_ctrl": rpm_ctrl,
                    }
                )

        usb_list: list[dict] = []
        try:
            out = subprocess.check_output(
                ["lsusb"], text=True, stderr=subprocess.DEVNULL, timeout=2.0
            )
            for line in out.splitlines():
                m = re.match(
                    r"^Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-fA-F:]+)\s+(.*)$",
                    line,
                )
                if m:
                    usb_list.append(
                        {
                            "bus_dev": f"Bus {m.group(1)} Dev {m.group(2)}",
                            "usb_id": m.group(3),
                            "name": m.group(4).strip(),
                        }
                    )
        except Exception:
            pass

        return pci_list, usb_list

    @staticmethod
    def get_all_sensors() -> list[dict]:
        rows: list[dict] = []
        hwmon_root = Path("/sys/class/hwmon")
        if not hwmon_root.is_dir():
            return rows
        for hw in sorted(hwmon_root.iterdir()):
            chip = _read(hw / "name", hw.name)
            # Temperatures
            for tf in sorted(hw.glob("temp*_input")):
                prefix = tf.name.split("_")[0]
                label = _read(hw / f"{prefix}_label", prefix)
                raw = _read(tf)
                if raw.lstrip("-").isdigit():
                    val_c = int(raw) / 1000.0
                    rows.append(
                        {
                            "chip": chip,
                            "sensor": label,
                            "type": "Temperature",
                            "reading": f"{val_c:.1f} °C",
                        }
                    )
            # Fans
            for ff in sorted(hw.glob("fan*_input")):
                prefix = ff.name.split("_")[0]
                label = _read(hw / f"{prefix}_label", prefix)
                raw = _read(ff)
                if raw.isdigit():
                    rows.append(
                        {
                            "chip": chip,
                            "sensor": label,
                            "type": "Cooling Fan",
                            "reading": f"{int(raw)} RPM",
                        }
                    )
            # Voltages
            for vf in sorted(hw.glob("in*_input")):
                prefix = vf.name.split("_")[0]
                label = _read(hw / f"{prefix}_label", prefix)
                raw = _read(vf)
                if raw.lstrip("-").isdigit():
                    rows.append(
                        {
                            "chip": chip,
                            "sensor": label,
                            "type": "Voltage",
                            "reading": f"{int(raw) / 1000.0:.2f} V",
                        }
                    )
        return rows

    @staticmethod
    def get_kernel_modules() -> list[dict]:
        mods: list[dict] = []
        try:
            with open("/proc/modules", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4:
                        used_by = parts[3].strip(",") if parts[3] != "-" else "none"
                        mods.append(
                            {
                                "name": parts[0],
                                "size_kb": round(int(parts[1]) / 1024.0, 1),
                                "instances": int(parts[2]),
                                "used_by": used_by,
                            }
                        )
        except OSError:
            pass
        mods.sort(key=lambda x: x["size_kb"], reverse=True)
        return mods

    @staticmethod
    def _parse_coredump_line(line: str) -> dict | None:
        """Parse one `coredumpctl list --no-legend` row.

        Columns fixed at the end: PID UID GID SIG COREFILE EXE SIZE.
        Everything before them is the timestamp (which contains spaces).
        """
        parts = line.split()
        if len(parts) < 8:
            return None
        pid, uid, gid, sig, corefile, exe, size = parts[-7:]
        return {
            "time": " ".join(parts[:-7]),
            "source": f"PID {pid} (UID {uid}, GID {gid})",
            "level": sig,
            "message": f"Core: {corefile}; executable: {exe}; size: {size}",
        }

    @staticmethod
    def get_logs(mode: str = "errors") -> list[dict]:
        """Fetch structured logs: 'errors' (p0..3), 'kernel' (dmesg warnings/errors), 'crashes', or 'hyprland'."""
        rows: list[dict] = []
        if mode in ("errors", "kernel"):
            cmd = ["journalctl", "-b", "--no-pager", "-n", "500", "-o", "short-iso"]
            if mode == "errors":
                cmd += ["-p", "0..3"]
            else:
                cmd += ["-k", "-p", "0..4"]
            try:
                out = subprocess.check_output(
                    cmd, text=True, stderr=subprocess.DEVNULL, timeout=2.5
                )
                for line in reversed(out.splitlines()):
                    if not line.strip() or line.startswith("--"):
                        continue
                    parts = line.split(None, 3)
                    if len(parts) >= 4:
                        rows.append(
                            {
                                "time": parts[0],
                                "source": parts[2].rstrip(":"),
                                "level": "ERROR" if mode == "errors" else "KERNEL/ACPI",
                                "message": parts[3][:240],
                            }
                        )
            except Exception as exc:
                rows.append(
                    {
                        "time": "-",
                        "source": "journalctl",
                        "level": "UNAVAILABLE",
                        "message": f"Could not read the journal: {exc}",
                    }
                )
        elif mode == "crashes":
            coredump_ok = False
            try:
                out = subprocess.check_output(
                    ["coredumpctl", "list", "--no-pager", "--no-legend"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=2.5,
                )
                coredump_ok = True
                for line in reversed(out.splitlines()):
                    parsed = HardwareAndMediaCollector._parse_coredump_line(line)
                    if parsed is not None:
                        rows.append(parsed)
            except Exception as exc:
                rows.append(
                    {
                        "time": "-",
                        "source": "coredumpctl",
                        "level": "UNAVAILABLE",
                        "message": f"Could not query systemd-coredump: {exc}",
                    }
                )
            if coredump_ok and not rows:
                rows.append(
                    {
                        "time": "-",
                        "source": "coredumpctl",
                        "level": "OK",
                        "message": "No application core dumps recorded by systemd-coredump.",
                    }
                )
        elif mode == "hyprland":
            sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
            log_paths = []
            if sig:
                log_paths.append(Path(f"/tmp/hypr/{sig}/hyprland.log"))
                log_paths.append(
                    Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
                    / "hypr"
                    / sig
                    / "hyprland.log"
                )
            for p in (
                Path("/tmp/hypr").glob("*/hyprland.log")
                if Path("/tmp/hypr").is_dir()
                else []
            ):
                log_paths.append(p)
            for p in Path(
                os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            ).glob("hypr/*/hyprland.log"):
                log_paths.append(p)
            for lp in log_paths:
                if lp.is_file():
                    try:
                        lines = lp.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()[-300:]
                        for ln in reversed(lines):
                            if ln.strip():
                                lvl = (
                                    "WARN/ERR"
                                    if any(k in ln for k in ("ERR", "WARN", "error"))
                                    else "INFO"
                                )
                                rows.append(
                                    {
                                        "time": "session",
                                        "source": "Hyprland",
                                        "level": lvl,
                                        "message": ln.strip()[:240],
                                    }
                                )
                        break
                    except OSError:
                        pass
            if not rows:
                rows.append(
                    {
                        "time": "-",
                        "source": "Hyprland",
                        "level": "UNAVAILABLE",
                        "message": "No Hyprland session log file found for this instance.",
                    }
                )
        return rows
