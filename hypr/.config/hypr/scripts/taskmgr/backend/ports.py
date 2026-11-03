#!/usr/bin/env python3
"""Ports, Active Connections, and Socket-to-Service Mapper."""

from __future__ import annotations

import re
import socket
import subprocess
import time
import psutil

WELL_KNOWN_DAEMONS = {
    22: ("SSH", "well-known SSH port"),
    53: ("DNS", "well-known DNS port"),
    68: ("DHCP", "well-known DHCP client port"),
    443: ("HTTPS", "well-known HTTPS port"),
    631: ("CUPS", "well-known CUPS/IPP printing port"),
    3306: ("MariaDB/MySQL", "well-known database port"),
    5353: ("mDNS", "well-known multicast DNS port"),
    5432: ("PostgreSQL", "well-known database port"),
    6379: ("Valkey/Redis", "well-known key-value store port"),
    8080: ("HTTP-alt", "well-known HTTP alternative port"),
    11434: ("Ollama", "well-known local LLM port"),
}


class PortsCollector:
    def __init__(self) -> None:
        self._service_pid_map: dict[int, str] = {}
        self._last_map_ts = 0.0

    def _refresh_systemd_maps(self) -> None:
        now = time.monotonic()
        if now - self._last_map_ts < 5.0:
            return
        self._last_map_ts = now
        pid_map: dict[int, str] = {}

        try:
            out = subprocess.check_output(
                [
                    "systemctl",
                    "show",
                    "--type=service",
                    "--all",
                    "--property=Id,MainPID,ExecMainPID",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            cur_id = ""
            for line in out.splitlines():
                if line.startswith("Id="):
                    cur_id = line[3:].strip()
                elif line.startswith(("MainPID=", "ExecMainPID=")):
                    pid = int(line.split("=", 1)[1].strip() or 0)
                    if pid > 0 and cur_id:
                        pid_map[pid] = cur_id
        except Exception:
            pass

        self._service_pid_map = pid_map

    @staticmethod
    def _unit_for_pid(pid: int) -> str:
        try:
            with open(
                f"/proc/{pid}/cgroup", "r", encoding="utf-8", errors="replace"
            ) as f:
                for line in f:
                    for part in reversed(line.strip().split("/")):
                        if part.endswith((".service", ".scope", ".slice")):
                            return part
        except OSError:
            pass
        return "-"

    def sample(self) -> tuple[list[dict], dict[int, list[str]]]:
        """Return (all_connections_list, pid_to_ports_map)."""
        self._refresh_systemd_maps()
        rows: list[dict] = []
        pid_ports: dict[int, list[str]] = {}

        try:
            conns = psutil.net_connections(kind="inet")
        except psutil.AccessDenied:
            conns = []

        for c in conns:
            is_tcp = c.type == socket.SOCK_STREAM
            proto = "TCP" if is_tcp else "UDP"
            lip = c.laddr.ip if c.laddr else "-"
            lport = int(c.laddr.port) if c.laddr else 0
            laddr = f"{lip}:{lport}" if c.laddr else "-"

            rip = c.raddr.ip if c.raddr else "*"
            rport = int(c.raddr.port) if c.raddr else 0
            raddr = f"{rip}:{rport}" if c.raddr else "*:*"

            state = (
                c.status
                if c.status != psutil.CONN_NONE
                else ("UNCONN" if not c.raddr else "ACTIVE")
            )
            is_listening = state in ("LISTEN", "UNCONN")
            pid = int(c.pid or 0)

            proc_name = "-"
            unit = "-"
            purpose = "-"

            if pid > 0:
                try:
                    p = psutil.Process(pid)
                    proc_name = p.name()
                    purpose = " ".join(p.cmdline()[:5]) or proc_name
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = self._service_pid_map.get(pid, f"pid:{pid}").replace(
                        ".service", ""
                    )
                    purpose = (
                        f"System daemon ({self._service_pid_map.get(pid, proc_name)})"
                    )
                unit = self._service_pid_map.get(pid) or self._unit_for_pid(pid)
                if is_listening:
                    pid_ports.setdefault(pid, []).append(f"{proto}:{lport}")
            else:
                # The kernel hides the owning socket inode/PID from an
                # unprivileged process. Only state what is actually known.
                hint = WELL_KNOWN_DAEMONS.get(lport)
                hint_txt = (
                    f" Likely {hint[0]} ({hint[1]}) - inferred from the port number, not verified."
                    if hint
                    else ""
                )
                proc_name = "(owner hidden)"
                purpose = (
                    "Owner hidden (root-owned or hidden socket); PID and command require root (PolicyKit/sudo)."
                    + hint_txt
                )

            rows.append(
                {
                    "proto": proto,
                    "port": lport,
                    "local_ip": lip,
                    "local": laddr,
                    "remote": raddr,
                    "state": state,
                    "is_listening": is_listening,
                    "pid": pid,
                    "process": proc_name,
                    "unit": unit,
                    "purpose": purpose[:160],
                }
            )

        rows.sort(key=lambda x: (0 if x["is_listening"] else 1, x["port"], x["proto"]))
        return rows, pid_ports
