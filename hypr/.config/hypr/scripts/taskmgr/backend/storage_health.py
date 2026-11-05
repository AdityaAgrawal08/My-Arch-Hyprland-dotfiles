#!/usr/bin/env python3
"""Real SMART/NVMe health readings with explicit missing-tool states.

Never fabricates a health percentage: if no supported tool can read the
device, the value is reported as N/A and the reason is kept in the note.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time

_CACHE: tuple[float, tuple[str, ...], list[dict]] | None = None


def _as_number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _parse_smartctl_json(payload: str) -> dict:
    data = json.loads(payload)
    status = data.get("smart_status", {}).get("passed")
    health = "PASSED" if status is True else "FAILED" if status is False else "N/A"
    temp = _as_number(data.get("temperature", {}).get("current"))
    hours = _as_number(data.get("power_on_time", {}).get("hours"))
    used = _as_number(
        data.get("nvme_smart_health_information_log", {}).get("percentage_used")
    )
    messages = data.get("smartctl", {}).get("messages", [])
    note = "; ".join(
        str(m.get("string", "")).strip() for m in messages if isinstance(m, dict)
    )
    return {
        "health": health,
        "temperature": f"{temp:.0f} °C" if temp is not None else "N/A",
        "power_on_hours": f"{hours:.0f} h" if hours is not None else "N/A",
        "percentage_used": f"{used:.0f} %" if used is not None else "N/A",
        "note": note[:180],
    }


def _parse_nvme_text(payload: str) -> dict:
    fields: dict[str, str] = {}
    for line in payload.splitlines():
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key:
            fields[key] = value
    temp = fields.get("temperature", "")
    used = fields.get("percentage_used", "")
    hours = fields.get("power_on_hours", "")
    critical = fields.get("critical_warning", "").strip().lower()
    if critical in ("0", "0x0", "0x00"):
        health = "PASSED"
    elif critical:
        health = "WARNING"
    else:
        health = "N/A"
    return {
        "health": health,
        "temperature": temp or "N/A",
        "power_on_hours": hours or "N/A",
        "percentage_used": used or "N/A",
        "note": "Source: nvme smart-log; nonzero critical_warning is a warning",
    }


class StorageHealthCollector:
    @staticmethod
    def sample(block_devices: list[dict]) -> list[dict]:
        global _CACHE
        disks = tuple(
            sorted(
                str(dev.get("name", "")).strip()
                for dev in block_devices
                if dev.get("type") == "disk"
                and str(dev.get("name", "")).strip()
                and not str(dev.get("name", "")).strip().startswith(
                    ("loop", "zram", "ram", "dm-")
                )
            )
        )
        now = time.monotonic()
        if _CACHE and _CACHE[1] == disks and now - _CACHE[0] < 60.0:
            return [dict(row) for row in _CACHE[2]]

        smartctl = shutil.which("smartctl")
        nvme = shutil.which("nvme")
        rows: list[dict] = []
        for dev in block_devices:
            if dev.get("type") != "disk":
                continue
            name = str(dev.get("name", "")).strip()
            if not name or name.startswith(("loop", "zram", "ram", "dm-")):
                continue
            device = f"/dev/{name}"
            row = {
                "device": device,
                "model": dev.get("model") or "N/A",
                "size": dev.get("size") or "N/A",
                "health": "N/A",
                "temperature": "N/A",
                "power_on_hours": "N/A",
                "percentage_used": "N/A",
                "note": "smartctl/nvme-cli are not installed",
            }
            if smartctl:
                try:
                    out = subprocess.check_output(
                        [smartctl, "-a", "-j", device],
                        text=True,
                        stderr=subprocess.STDOUT,
                        timeout=6.0,
                    )
                    row.update(_parse_smartctl_json(out))
                    row["note"] = row["note"] or f"Source: {smartctl} -a -j"
                except subprocess.CalledProcessError as exc:
                    try:
                        row.update(_parse_smartctl_json(exc.output or ""))
                        row["note"] = (
                            row["note"]
                            or f"smartctl exit status {exc.returncode} (bitmask)"
                        )
                    except (ValueError, TypeError):
                        row["note"] = f"smartctl failed (exit {exc.returncode})"
                except (OSError, ValueError, TypeError) as exc:
                    row["note"] = f"smartctl failed: {exc}"
            elif nvme and name.startswith("nvme"):
                try:
                    out = subprocess.check_output(
                        [nvme, "smart-log", device],
                        text=True,
                        stderr=subprocess.STDOUT,
                        timeout=6.0,
                    )
                    row.update(_parse_nvme_text(out))
                except (OSError, subprocess.CalledProcessError) as exc:
                    row["note"] = f"nvme smart-log failed: {exc}"
            rows.append(row)
        _CACHE = (now, disks, [dict(row) for row in rows])
        return rows
