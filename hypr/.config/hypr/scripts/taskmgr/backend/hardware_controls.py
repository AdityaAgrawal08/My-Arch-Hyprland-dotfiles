#!/usr/bin/env python3
"""Gated fan-curve and battery charge-threshold controls.

Both features only write when the kernel exposes the relevant sysfs files and
the current user can write them. Otherwise the UI reports the exact missing or
permission prerequisite instead of pretending to control hardware.
"""

from __future__ import annotations

import os
from pathlib import Path


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_int(path: Path, default: int = -1) -> int:
    try:
        return int(_read_text(path).split()[0])
    except (ValueError, IndexError):
        return default


def _write_int(path: Path, value: int) -> None:
    path.write_text(str(int(value)), encoding="utf-8")


class FanControl:
    def __init__(self, root: str | Path = "/sys/class/hwmon") -> None:
        self.root = Path(root)

    def discover(self) -> list[dict]:
        devices: list[dict] = []
        try:
            hwmons = sorted(self.root.glob("hwmon*"))
        except OSError:
            return devices
        for hwmon in hwmons:
            chip = _read_text(hwmon / "name") or hwmon.name
            temps = sorted(hwmon.glob("temp*_input"))
            for pwm in sorted(hwmon.glob("pwm[0-9]")):
                enable = hwmon / f"{pwm.name}_enable"
                devices.append(
                    {
                        "id": f"{hwmon.name}/{pwm.name}",
                        "chip": chip,
                        "pwm_path": str(pwm),
                        "enable_path": str(enable) if enable.exists() else "",
                        "temp_path": str(temps[0]) if temps else "",
                        "pwm": _read_int(pwm, -1),
                        "enable": _read_int(enable, -1) if enable.exists() else -1,
                        "writable": os.access(pwm, os.W_OK),
                        "enable_writable": (
                            os.access(enable, os.W_OK) if enable.exists() else False
                        ),
                    }
                )
        return devices

    @staticmethod
    def interpolate(points: list[tuple[float, int]], temp_c: float) -> int:
        if not points:
            return 0
        ordered = sorted(points, key=lambda item: item[0])
        if temp_c <= ordered[0][0]:
            value = ordered[0][1]
        elif temp_c >= ordered[-1][0]:
            value = ordered[-1][1]
        else:
            value = ordered[-1][1]
            for (t0, p0), (t1, p1) in zip(ordered, ordered[1:]):
                if t0 <= temp_c <= t1:
                    if t1 == t0:
                        value = p1
                    else:
                        frac = (temp_c - t0) / (t1 - t0)
                        value = round(p0 + (p1 - p0) * frac)
                    break
        return max(0, min(255, int(value)))

    def apply_curve(
        self,
        device: dict,
        points: list[tuple[float, int]],
        temp_c: float | None = None,
    ) -> tuple[bool, str]:
        pwm_path = Path(device.get("pwm_path", ""))
        if not pwm_path.exists():
            return False, "The pwm output disappeared."
        if not os.access(pwm_path, os.W_OK):
            return False, (
                "The pwm output is read-only for this user. Run as root or add a "
                "udev rule that grants write access."
            )
        if temp_c is None:
            temp_path = Path(device.get("temp_path", ""))
            raw_temp = _read_int(temp_path, -1) if temp_path.exists() else -1
            if raw_temp < 0:
                return False, "No readable temperature sensor on this hwmon chip."
            temp_c = raw_temp / 1000.0
        pwm = self.interpolate(points, temp_c)
        enable_path = Path(device.get("enable_path", ""))
        try:
            if enable_path.exists() and os.access(enable_path, os.W_OK):
                _write_int(enable_path, 1)
            _write_int(pwm_path, pwm)
        except OSError as exc:
            # Do not leave the fan stuck in manual mode after a failed write.
            try:
                if enable_path.exists() and os.access(enable_path, os.W_OK):
                    _write_int(enable_path, 2)
            except OSError:
                pass
            return False, f"Fan write failed: {exc}"
        return (
            True,
            f"Applied {pwm}/255 to {device.get('chip', 'fan')} at {temp_c:.1f} °C.",
        )

    def set_manual(self, device: dict) -> tuple[bool, str]:
        enable_path = Path(device.get("enable_path", ""))
        if not enable_path.exists():
            return False, "This fan has no pwm*_enable file; mode cannot be changed."
        if not os.access(enable_path, os.W_OK):
            return (
                False,
                "The fan mode file is read-only; root or a udev rule is required.",
            )
        try:
            _write_int(enable_path, 1)
        except OSError as exc:
            return False, f"Fan mode write failed: {exc}"
        return True, f"{device.get('chip', 'fan')} switched to manual mode."

    def restore_auto(self, device: dict) -> tuple[bool, str]:
        enable_path = Path(device.get("enable_path", ""))
        if not enable_path.exists():
            return False, "This fan has no pwm*_enable file; mode cannot be changed."
        if not os.access(enable_path, os.W_OK):
            return (
                False,
                "The fan mode file is read-only; root or a udev rule is required.",
            )
        try:
            _write_int(enable_path, 2)
        except OSError as exc:
            return False, f"Fan mode restore failed: {exc}"
        return True, f"{device.get('chip', 'fan')} restored to automatic mode."


class BatteryThresholdControl:
    def __init__(self, root: str | Path = "/sys/class/power_supply") -> None:
        self.root = Path(root)

    def discover(self) -> list[dict]:
        devices: list[dict] = []
        try:
            batteries = sorted(self.root.glob("BAT*"))
        except OSError:
            return devices
        for battery in batteries:
            start = battery / "charge_control_start_threshold"
            end = battery / "charge_control_end_threshold"
            if not start.exists() and not end.exists():
                continue
            devices.append(
                {
                    "id": battery.name,
                    "start_path": str(start) if start.exists() else "",
                    "end_path": str(end) if end.exists() else "",
                    "start": _read_int(start, -1) if start.exists() else -1,
                    "end": _read_int(end, -1) if end.exists() else -1,
                    "reason": (
                        ""
                        if end.exists()
                        else "no charge_control_end_threshold"
                    ),
                    "writable": (
                        end.exists()
                        and os.access(end, os.W_OK)
                        and (not start.exists() or os.access(start, os.W_OK))
                    ),
                }
            )
        return devices

    @staticmethod
    def validate(start: int | None, end: int | None) -> tuple[bool, str]:
        if end is None:
            return False, "A charge-stop (end) threshold is required."
        if not (0 <= end <= 100):
            return False, "The charge-stop threshold must be between 0 and 100."
        if start is not None:
            if not (0 <= start <= 100):
                return False, "The charge-start threshold must be between 0 and 100."
            if start >= end:
                return (
                    False,
                    "The charge-start threshold must be below the end threshold.",
                )
        return True, ""

    def apply(
        self,
        device: dict,
        start: int | None,
        end: int | None,
    ) -> tuple[bool, str]:
        valid, reason = self.validate(start, end)
        if not valid:
            return False, reason
        end_path = Path(device.get("end_path", ""))
        if not end_path.exists():
            return False, "This battery has no charge_control_end_threshold file."
        if not os.access(end_path, os.W_OK):
            return False, (
                "The charge threshold file is read-only for this user. Run as root "
                "or add a udev rule that grants write access."
            )
        start_path = Path(device.get("start_path", ""))
        if start is not None and start_path.exists():
            if not os.access(start_path, os.W_OK):
                return False, "The charge-start threshold file is read-only."
        try:
            if start is not None and start_path.exists():
                _write_int(start_path, start)
            _write_int(end_path, int(end))
        except OSError as exc:
            return False, f"Battery threshold write failed: {exc}"
        if start is not None:
            return True, f"{device.get('id', 'battery')}: start {start}%, stop {end}%."
        return True, f"{device.get('id', 'battery')}: stop {end}%."
