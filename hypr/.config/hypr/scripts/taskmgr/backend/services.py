#!/usr/bin/env python3
"""Systemd Services (System & User), Timers, and Hyprland Autostart Tracker."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
import psutil


_RESOURCE_CACHE: dict[str, tuple[float, dict[str, dict]]] = {}


# Persistent Process objects are required for psutil.cpu_percent(interval=None)
# to return a real interval delta instead of a structural 0.0 %.
_HYPR_PROC_CACHE: dict[int, psutil.Process] = {}


def autostart_key(raw_cmd: str) -> str:
    """Normalize an hl.exec_cmd string for duplicate detection.

    The executable basename is kept, plus all arguments, so
    `hyprpolkitagent` and `/usr/bin/hyprpolkitagent` collide (a real
    duplicate) while `wl-paste --type text` and `wl-paste --type image`
    stay distinct (two required clipboard watchers).
    """
    parts = raw_cmd.split()
    if not parts:
        return ""
    exe = parts[0].split("/")[-1]
    if exe in ("python3", "python") and len(parts) > 1:
        return (f"{parts[1].split('/')[-1]} " + " ".join(parts[2:])).strip()
    return (f"{exe} " + " ".join(parts[1:])).strip()


class ServicesCollector:
    """Queries systemd system/user services, timers, and tracks hyprland.lua autostart commands."""

    @staticmethod
    def _read_proc_io(
        pid: int, proc_root: str | Path = "/proc"
    ) -> tuple[int, int] | None:
        path = Path(proc_root) / str(pid) / "io"
        try:
            read_bytes = None
            write_bytes = None
            for line in path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                key, _, value = line.partition(":")
                if key == "read_bytes":
                    read_bytes = int(value.strip())
                elif key == "write_bytes":
                    write_bytes = int(value.strip())
            if read_bytes is None or write_bytes is None:
                return None
            return read_bytes, write_bytes
        except (OSError, ValueError):
            return None

    @staticmethod
    def _sum_cgroup_proc_io(
        cgroup: str,
        cgroup_root: str | Path = "/sys/fs/cgroup",
        proc_root: str | Path = "/proc",
    ) -> tuple[int, int, str] | None:
        """Aggregate /proc/<pid>/io for a service when every PID is visible.

        This is a best-effort fallback for systems where the cgroup io
        controller is not delegated. If any PID is hidden (hidepid), the total
        would be an undercount, so the result is N/A instead.
        """
        procs_path = (
            Path(cgroup_root) / cgroup.lstrip("/") / "cgroup.procs"
        )
        try:
            pids = [
                int(value)
                for value in procs_path.read_text(
                    encoding="utf-8", errors="replace"
                ).split()
            ]
        except (OSError, ValueError):
            return None
        if not pids:
            return None
        total_read = 0
        total_write = 0
        readable = 0
        unreadable: list[int] = []
        for pid in pids:
            io = ServicesCollector._read_proc_io(pid, proc_root)
            if io is None:
                unreadable.append(pid)
                continue
            total_read += io[0]
            total_write += io[1]
            readable += 1
        if unreadable:
            # Distinguish a PID that exited during sampling from one hidden by
            # hidepid: only a PID still listed in cgroup.procs makes the total
            # an undercount.
            try:
                remaining = {
                    int(value)
                    for value in procs_path.read_text(
                        encoding="utf-8", errors="replace"
                    ).split()
                }
            except (OSError, ValueError):
                return None
            if any(pid in remaining for pid in unreadable):
                return None
        if readable == 0:
            return None
        return total_read, total_write, f"{readable}/{readable} processes"

    @staticmethod
    def _get_service_resources(scope: str) -> dict[str, dict]:
        """Read cgroup-backed CPU/memory/IO accounting via systemd."""
        now = time.monotonic()
        cached = _RESOURCE_CACHE.get(scope)
        if cached and now - cached[0] < 10.0:
            return cached[1]
        cmd = ["systemctl"]
        if scope == "user":
            cmd.append("--user")
        cmd += [
            "show",
            "--type=service",
            "--all",
            "-p",
            "Id,MemoryCurrent,CPUUsageNSec,ControlGroup,IOReadBytes,IOWriteBytes",
        ]
        try:
            out = subprocess.check_output(
                cmd, text=True, stderr=subprocess.DEVNULL, timeout=5.0
            )
        except Exception:
            return {}
        resources: dict[str, dict] = {}
        cur: dict[str, str] = {}

        def flush() -> None:
            unit = cur.get("Id", "")
            if not unit:
                return
            mem = cur.get("MemoryCurrent", "[not set]")
            cpu = cur.get("CPUUsageNSec", "[not set]")
            cg = cur.get("ControlGroup", "")
            mem_mb = None
            cpu_s = None
            try:
                if mem not in ("[not set]", ""):
                    mem_mb = round(int(mem) / (1024 * 1024), 1)
            except ValueError:
                pass
            try:
                if cpu not in ("[not set]", ""):
                    cpu_s = round(int(cpu) / 1e9, 2)
            except ValueError:
                pass
            io_read = io_write = None
            io_source = ""
            if cg:
                try:
                    for line in (
                        Path(f"/sys/fs/cgroup{cg}/io.stat")
                        .read_text(encoding="utf-8", errors="replace")
                        .splitlines()
                    ):
                        for part in line.split()[1:]:
                            k, _, v = part.partition("=")
                            if k == "rbytes":
                                io_read = (io_read or 0) + int(v)
                            elif k == "wbytes":
                                io_write = (io_write or 0) + int(v)
                except (OSError, ValueError):
                    pass
                if io_read is not None:
                    io_source = "cgroup io.stat"
            if io_read is None:
                try:
                    raw_read = cur.get("IOReadBytes", "[not set]")
                    if raw_read not in ("[not set]", ""):
                        io_read = int(raw_read)
                        io_source = "systemd IOReadBytes"
                except ValueError:
                    pass
            if io_write is None:
                try:
                    raw_write = cur.get("IOWriteBytes", "[not set]")
                    if raw_write not in ("[not set]", ""):
                        io_write = int(raw_write)
                        io_source = io_source or "systemd IOWriteBytes"
                except ValueError:
                    pass
            if io_read is None and cg:
                proc_io = ServicesCollector._sum_cgroup_proc_io(cg)
                if proc_io is not None:
                    io_read, io_write, source = proc_io
                    io_source = f"per-PID /proc io ({source})"
            resources[unit] = {
                "memory_mb": mem_mb,
                "cpu_s": cpu_s,
                "io_read_mb": round(io_read / (1024 * 1024), 1)
                if io_read is not None
                else None,
                "io_write_mb": round(io_write / (1024 * 1024), 1)
                if io_write is not None
                else None,
                "io_source": io_source,
                "control_group": cg,
            }

        for line in out.splitlines():
            if not line.strip():
                flush()
                cur = {}
            else:
                key, _, value = line.partition("=")
                cur[key] = value
        flush()
        _RESOURCE_CACHE[scope] = (now, resources)
        return resources

    @staticmethod
    def get_services(scope: str = "system") -> list[dict]:
        cmd = ["systemctl"]
        if scope == "user":
            cmd.append("--user")
        cmd += ["list-units", "--type=service", "--all", "--no-pager", "--output=json"]
        try:
            out = subprocess.check_output(
                cmd, text=True, stderr=subprocess.DEVNULL, timeout=3.0
            )
            units = json.loads(out)
            resources = ServicesCollector._get_service_resources(scope)
            rows = []
            for u in units:
                unit_name = u.get("unit", "")
                if not unit_name:
                    continue
                res = resources.get(unit_name, {})
                rows.append(
                    {
                        "unit": unit_name,
                        "scope": scope,
                        "load": u.get("load", ""),
                        "active": u.get("active", ""),
                        "sub": u.get("sub", ""),
                        "description": u.get("description", ""),
                        "memory_mb": res.get("memory_mb"),
                        "cpu_s": res.get("cpu_s"),
                        "io_read_mb": res.get("io_read_mb"),
                        "io_write_mb": res.get("io_write_mb"),
                        "io_source": res.get("io_source", ""),
                        "control_group": res.get("control_group", ""),
                    }
                )
            rows.sort(key=lambda x: (0 if x["active"] == "active" else 1, x["unit"]))
            return rows
        except Exception:
            return []

    @staticmethod
    def _fmt_usec(value: object) -> str:
        try:
            usec = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return str(value) if value else "n/a"
        if usec <= 0:
            return "never"
        try:
            return datetime.fromtimestamp(usec / 1e6).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return str(value)

    @staticmethod
    def _annotate_timer_states(rows: list[dict]) -> None:
        """Replace the guessed State with the real systemd ActiveState."""
        for scope in ("system", "user"):
            units = [r["unit"] for r in rows if r["scope"] == scope]
            if not units:
                continue
            cmd = ["systemctl"]
            if scope == "user":
                cmd.append("--user")
            cmd += ["show", "--property=Id,ActiveState", *units]
            try:
                out = subprocess.check_output(
                    cmd, text=True, stderr=subprocess.DEVNULL, timeout=3.0
                )
            except Exception:
                continue
            state_map: dict[str, str] = {}
            current_id = ""
            for line in out.splitlines():
                if line.startswith("Id="):
                    current_id = line[3:].strip()
                elif line.startswith("ActiveState="):
                    state = line.split("=", 1)[1].strip()
                    if current_id:
                        state_map[current_id] = state
                        current_id = ""
            for row in rows:
                if row["scope"] == scope and row["unit"] in state_map:
                    row["State"] = state_map[row["unit"]]

    @staticmethod
    def get_timers() -> list[dict]:
        rows: list[dict] = []
        for scope in ("system", "user"):
            cmd = ["systemctl"]
            if scope == "user":
                cmd.append("--user")
            cmd += ["list-timers", "--all", "--no-pager", "--output=json"]
            try:
                out = subprocess.check_output(
                    cmd, text=True, stderr=subprocess.DEVNULL, timeout=2.5
                )
                timers = json.loads(out)
                for t in timers:
                    rows.append(
                        {
                            "unit": t.get("unit", ""),
                            "activates": t.get("activates", ""),
                            "scope": scope,
                            "next": ServicesCollector._fmt_usec(t.get("next")),
                            "last": ServicesCollector._fmt_usec(t.get("last")),
                            "State": "unknown",
                        }
                    )
            except Exception:
                pass

        # Also check user timer unit files in ~/.config/systemd/user so timers
        # that are not currently loaded are visible, with their real enablement
        # state rather than a blanket "disabled" label.
        user_unit_dir = Path.home() / ".config/systemd/user"
        seen_units = {r["unit"] for r in rows}
        if user_unit_dir.is_dir():
            for tf in sorted(user_unit_dir.glob("*.timer")):
                if tf.name in seen_units:
                    continue
                enabled_state = "unknown"
                try:
                    out = subprocess.check_output(
                        ["systemctl", "--user", "is-enabled", tf.name],
                        text=True,
                        stderr=subprocess.DEVNULL,
                        timeout=1.0,
                    ).strip()
                    enabled_state = out or "unknown"
                except subprocess.CalledProcessError as exc:
                    enabled_state = (exc.stdout or "disabled").strip() or "disabled"
                except Exception:
                    pass
                is_enabled = enabled_state in (
                    "enabled",
                    "enabled-runtime",
                    "static",
                    "indirect",
                    "generated",
                )
                activates = tf.stem + ".service"
                try:
                    reported = subprocess.check_output(
                        [
                            "systemctl",
                            "--user",
                            "show",
                            tf.name,
                            "--property=Unit",
                            "--value",
                        ],
                        text=True,
                        stderr=subprocess.DEVNULL,
                        timeout=1.0,
                    ).strip()
                    if reported:
                        activates = reported
                except Exception:
                    pass
                rows.append(
                    {
                        "unit": tf.name,
                        "activates": activates,
                        "scope": "user",
                        "next": "Enabled but not active"
                        if is_enabled
                        else (
                            "Disabled"
                            if enabled_state == "disabled"
                            else f"Disabled ({enabled_state})"
                        ),
                        "last": "never",
                        "State": "unknown",
                    }
                )
        ServicesCollector._annotate_timer_states(rows)
        return rows

    @staticmethod
    def get_hyprland_autostart_status() -> list[dict]:
        """Parse hyprland.lua hl.on('hyprland.start') and match against live running processes."""
        hypr_lua = Path.home() / ".config/hypr/hyprland.lua"
        commands: list[str] = []
        if hypr_lua.is_file():
            try:
                txt = hypr_lua.read_text(encoding="utf-8", errors="replace")
                start = txt.find('hl.on("hyprland.start"')
                end = txt.find('hl.on("config.reloaded"', start + 1)
                block = txt[start:end] if start >= 0 and end > start else txt
                commands = re.findall(r'hl\.exec_cmd\(\s*"([^"]+)"\s*\)', block)
            except OSError:
                pass

        # Build live process cmdline lookup
        live_procs = []
        for p in psutil.process_iter(
            ["pid", "name", "cmdline", "cpu_percent", "memory_info"]
        ):
            try:
                info = p.info
                cmdline = " ".join(info["cmdline"] or []) or (info["name"] or "")
                rss_mb = round(
                    (info["memory_info"].rss / (1024 * 1024))
                    if info["memory_info"]
                    else 0.0,
                    1,
                )
                live_procs.append(
                    {
                        "pid": info["pid"],
                        "name": info["name"] or "",
                        "cmdline": cmdline,
                        "cpu": round(float(info["cpu_percent"] or 0.0), 1),
                        "mem_mb": rss_mb,
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Only take the autostart block entries inside hyprland.start.
        autostart_cmds = commands
        results: list[dict] = []
        seen_targets: dict[str, int] = {}

        for raw_cmd in autostart_cmds:
            parts = raw_cmd.split()
            exe = parts[0].split("/")[-1] if parts else ""
            token = exe
            target = exe
            match_kind = "token"
            type_name = ""

            if exe in ("python3", "python") and len(parts) > 1:
                token = parts[1].split("/")[-1]
                target = token
            elif exe == "wl-paste":
                m = re.search(r"--type\s+(\S+)", raw_cmd)
                type_name = m.group(1) if m else "?"
                target = f"wl-paste {type_name}"
                match_kind = "wl-paste"
            elif exe == "waybar-scale.py":
                token = "waybar"
                target = "waybar (spawned)"
                match_kind = "spawned"
            elif exe == "wallpaper_switch.sh":
                token = "awww-daemon"
                target = "awww-daemon (spawned)"
                match_kind = "spawned"
            elif exe == "battery-notify.sh":
                token = "battery-notify"
                target = "battery-notify"

            seen_targets[autostart_key(raw_cmd)] = (
                seen_targets.get(autostart_key(raw_cmd), 0) + 1
            )
            duplicate = seen_targets[autostart_key(raw_cmd)] > 1

            def matches_process(lp: dict) -> bool:
                if match_kind == "wl-paste":
                    if lp["name"] != "wl-paste":
                        return False
                    toks = lp["cmdline"].split()
                    if "--type" not in toks:
                        return False
                    idx = toks.index("--type")
                    return idx + 1 < len(toks) and toks[idx + 1] == type_name
                return token in lp["name"] or token in lp["cmdline"]

            matches = [lp for lp in live_procs if matches_process(lp)]
            if matches:
                pids = ", ".join(str(m["pid"]) for m in matches[:4])
                if len(matches) > 4:
                    pids += f" +{len(matches) - 4}"
                tot_mem = round(sum(m["mem_mb"] for m in matches), 1)
                if match_kind == "spawned":
                    status = (
                        f"Spawned daemon running "
                        f"({len(matches)} instance{'s' if len(matches) > 1 else ''})"
                    )
                else:
                    status = (
                        f"Running ({len(matches)} "
                        f"instance{'s' if len(matches) > 1 else ''})"
                    )
            else:
                pids = "-"
                tot_mem = 0.0
                status = (
                    "One-shot exited; spawned daemon not running"
                    if match_kind == "spawned"
                    else "Not Running"
                )
            if duplicate:
                status = "DUPLICATE entry in hyprland.lua; " + status

            results.append(
                {
                    "command": raw_cmd,
                    "target": target,
                    "status": status,
                    "pids": pids,
                    "mem_mb": tot_mem,
                }
            )

        return results

    @staticmethod
    def get_hyprland_clients() -> list[dict]:
        try:
            out = subprocess.check_output(
                ["hyprctl", "-j", "clients"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.5,
            )
            clients = json.loads(out)
            rows = []
            live_pids = {
                int(c.get("pid") or 0) for c in clients if int(c.get("pid") or 0) > 0
            }
            # Drop dead PIDs so the cache cannot grow without bound.
            for dead in list(_HYPR_PROC_CACHE):
                if dead not in live_pids:
                    del _HYPR_PROC_CACHE[dead]

            for c in clients:
                pid = int(c.get("pid") or 0)
                rss_mb = 0.0
                cpu_pct = 0.0
                if pid > 0:
                    try:
                        p = _HYPR_PROC_CACHE.get(pid)
                        if p is None:
                            p = psutil.Process(pid)
                            _HYPR_PROC_CACHE[pid] = p
                            p.cpu_percent(interval=None)  # baseline
                        rss_mb = round(p.memory_info().rss / (1024 * 1024), 1)
                        cpu_pct = round(p.cpu_percent(interval=None), 1)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        _HYPR_PROC_CACHE.pop(pid, None)
                rows.append(
                    {
                        "address": c.get("address", ""),
                        "workspace": str(c.get("workspace", {}).get("name", "?")),
                        "class": c.get("class", ""),
                        "title": (c.get("title") or "")[:90],
                        "pid": pid,
                        "cpu": cpu_pct,
                        "mem_mb": rss_mb,
                        "protocol": "XWayland" if c.get("xwayland") else "Wayland",
                        "layout": "Floating" if c.get("floating") else "Tiled",
                    }
                )
            return rows
        except Exception:
            return []

    @staticmethod
    def control_service(unit: str, scope: str, action: str) -> tuple[bool, str]:
        cmd = ["systemctl"]
        if scope == "user":
            cmd.append("--user")
        cmd += [action, unit]
        try:
            subprocess.Popen(cmd)
            return (
                True,
                f"Triggered 'systemctl {'--user ' if scope == 'user' else ''}{action} {unit}'",
            )
        except OSError as exc:
            return False, str(exc)
