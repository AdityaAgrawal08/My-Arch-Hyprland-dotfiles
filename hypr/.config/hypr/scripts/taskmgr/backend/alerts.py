#!/usr/bin/env python3
"""Threshold alerts with cooldowns and desktop notifications."""

from __future__ import annotations

import os
import shutil
import subprocess
import time


class AlertManager:
    def __init__(self) -> None:
        self.enabled = os.environ.get("TASKMGR_ALERTS", "1") != "0"
        self._last: dict[str, float] = {}
        self._known_listening: set[tuple[str, int]] | None = None

    def _can_fire(self, key: str, cooldown: float = 300.0) -> bool:
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        if now - last < cooldown:
            return False
        self._last[key] = now
        return True

    @staticmethod
    def _notify(title: str, body: str) -> None:
        if shutil.which("notify-send") is None:
            return
        try:
            subprocess.Popen(
                ["notify-send", "-a", "Task Manager", "-u", "normal", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def check_perf(self, perf: dict) -> None:
        if not self.enabled:
            return
        battery = perf.get("battery", {})
        if battery.get("present"):
            if (
                battery.get("status") == "Discharging"
                and battery.get("watts", 0) >= 20.0
                and self._can_fire("battery_draw")
            ):
                self._notify(
                    "High battery draw",
                    f"{battery['watts']:.1f} W while discharging. "
                    "Open the Power page to inspect interrupts and tunables.",
                )
            if battery.get("percent", 100) <= 20 and self._can_fire("battery_low"):
                self._notify(
                    "Battery low",
                    f"{battery['percent']}% remaining "
                    f"({battery.get('remaining_str', 'time unknown')}).",
                )

        cpu_temp = perf.get("cpu_temp", 0)
        if cpu_temp >= 90 and self._can_fire("cpu_temp"):
            self._notify(
                "CPU temperature high",
                f"Package temperature is {cpu_temp:.0f} °C.",
            )

        mem = perf.get("mem")
        if mem is not None and mem.percent >= 90 and self._can_fire("memory"):
            self._notify(
                "Memory pressure high",
                f"RAM usage is {mem.percent:.0f}% "
                f"({mem.used // (1024**2)} / {mem.total // (1024**2)} MiB).",
            )

        psi_mem = perf.get("psi", {}).get("memory", {}).get("some_avg10")
        if psi_mem is not None and psi_mem >= 10 and self._can_fire("psi_memory"):
            self._notify(
                "Memory stall pressure",
                f"PSI memory some avg10 is {psi_mem:.1f}%. "
                "Processes are stalling waiting for memory.",
            )

        psi_io = perf.get("psi", {}).get("io", {}).get("some_avg10")
        if psi_io is not None and psi_io >= 20 and self._can_fire("psi_io"):
            self._notify(
                "I/O stall pressure",
                f"PSI I/O some avg10 is {psi_io:.1f}%.",
            )

    def check_ports(self, ports: list[dict]) -> None:
        if not self.enabled:
            return
        listening = {
            (str(row.get("proto", "")), int(row.get("port", 0)))
            for row in ports
            if row.get("is_listening")
        }
        if self._known_listening is None:
            self._known_listening = listening
            return
        new_ports = sorted(listening - self._known_listening)
        self._known_listening = listening
        for proto, port in new_ports:
            key = f"port:{proto}:{port}"
            if self._can_fire(key, 60.0):
                self._notify(
                    "New listening port",
                    f"{proto} port {port} is now listening. "
                    "Open Ports & Network to identify the owner.",
                )

    def check_doctor(self, checks: list[dict]) -> None:
        if not self.enabled:
            return
        for check in checks:
            if check.get("status") != "NOT WORKING":
                continue
            component = check.get("component", "unknown")
            if self._can_fire(f"doctor:{component}", 900.0):
                self._notify(
                    "System Doctor failure",
                    f"{component}: {check.get('summary', '')}",
                )
