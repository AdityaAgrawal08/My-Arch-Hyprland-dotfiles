#!/usr/bin/env python3
"""Process, Application Group, Process Tree, and Deep Thread/Socket/FD Inspector."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path
import psutil

from .gpu import GpuCollector

CLK_TCK = (
    os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    if "SC_CLK_TCK" in os.sysconf_names
    else 100
)


class ProcessCollector:
    """Samples all processes with delta CPU %, GPU %, Disk R/W KB/s, Wakeups/s, and Battery Impact."""

    def __init__(self, gpu_collector: GpuCollector) -> None:
        self.gpu_collector = gpu_collector
        self._last_ts = time.monotonic()
        self._prev_io: dict[tuple[int, float], tuple[int, int]] = {}
        self._prev_ctx: dict[tuple[int, float], int] = {}
        self._prev_tid_ticks: dict[tuple[tuple[int, float], int], int] = {}
        self._last_tid_ts = time.monotonic()
        self._seen_keys: set[tuple[int, float]] = set()
        # Prime per-process CPU, disk I/O, and context-switch counters so the
        # first displayed sample is a real interval, not a structural zero.
        try:
            for p in psutil.process_iter(
                [
                    "pid",
                    "create_time",
                    "cpu_percent",
                    "io_counters",
                    "num_ctx_switches",
                ]
            ):
                info = p.info
                _ = info["cpu_percent"]
                key = (
                    int(info["pid"]),
                    round(float(info["create_time"] or 0.0), 3),
                )
                self._seen_keys.add(key)
                io_c = info.get("io_counters")
                if io_c is not None:
                    self._prev_io[key] = (
                        int(io_c.read_bytes),
                        int(io_c.write_bytes),
                    )
                ctx_c = info.get("num_ctx_switches")
                if ctx_c is not None:
                    self._prev_ctx[key] = int(ctx_c.voluntary + ctx_c.involuntary)
        except Exception:
            pass

    @staticmethod
    def get_unit_for_pid(pid: int) -> str:
        try:
            with open(
                f"/proc/{pid}/cgroup", "r", encoding="utf-8", errors="replace"
            ) as f:
                for line in f:
                    parts = line.strip().split("/")
                    for part in reversed(parts):
                        if part.endswith((".service", ".scope", ".slice")):
                            return part
        except OSError:
            pass
        return "-"

    @staticmethod
    def _classify_power_impact(
        cpu_pct: float, gpu_pct: float, ctx_s: float, disk_kbs: float, state: str
    ) -> tuple[str, float]:
        if state in ("stopped", "T"):
            return "Frozen (Idle)", 0.0
        score = (cpu_pct * 1.5) + (gpu_pct * 1.8) + (ctx_s / 35.0) + (disk_kbs / 512.0)
        if score >= 45.0:
            return "Very High", score
        if score >= 18.0:
            return "High", score
        if score >= 5.0:
            return "Moderate", score
        if score >= 1.0:
            return "Low", score
        return "Very Low", score

    @staticmethod
    def _normalize_app_group(name: str, cmd: str) -> str:
        low = name.lower()
        cmd_low = cmd.lower()
        if "brave" in low or "brave" in cmd_low:
            return "Brave Browser"
        if low in ("zen", "zen-bin", "zen-browser") or "zen-bin" in cmd_low:
            return "Zen Browser"
        if "firefox" in low:
            return "Firefox"
        if "chromium" in low:
            return "Chromium"
        if "code" in low or "vscode" in cmd_low:
            return "VS Code"
        if "opencode" in low or "opencode" in cmd_low:
            return "OpenCode Agent"
        if "kitty" in low or "kitten" in low:
            return "Kitty Terminal"
        if "nvim" in low or "neovim" in cmd_low:
            return "Neovim"
        if "hyprland" in low:
            return "Hyprland Desktop Suite"
        if "waybar" in low:
            return "Waybar Status Bar"
        if "pipewire" in low or "wireplumber" in low:
            return "PipeWire Audio Stack"
        if "warp-svc" in low or "warp-taskbar" in low:
            return "Cloudflare WARP"
        if "valkey" in low or "redis" in low:
            return "Valkey / Redis"
        return name

    def sample(
        self,
        pid_ports: dict[int, list[str]] | None = None,
        hide_kernel_threads: bool = True,
    ) -> tuple[list[dict], list[dict]]:
        now = time.monotonic()
        dt = max(now - self._last_ts, 1e-3)
        self._last_ts = now
        pid_ports = pid_ports or {}

        gpu_pct_map = self.gpu_collector.proc_gpu_pct
        procs: list[dict] = []
        new_io: dict[int, tuple[int, int]] = {}
        new_ctx: dict[int, int] = {}

        attrs = [
            "pid",
            "ppid",
            "create_time",
            "name",
            "username",
            "cpu_percent",
            "memory_info",
            "memory_percent",
            "num_threads",
            "status",
            "cmdline",
            "num_ctx_switches",
            "io_counters",
            "nice",
        ]

        for p in psutil.process_iter(attrs=attrs):
            try:
                info = p.info
                pid = int(info["pid"])
                ppid = int(info["ppid"] or 0)
                if hide_kernel_threads and (pid == 2 or ppid == 2):
                    continue
                proc_key = (
                    pid,
                    round(float(info["create_time"] or 0.0), 3),
                )

                name = info["name"] or "?"
                cmd_list = info["cmdline"] or []
                if hide_kernel_threads and not cmd_list and ppid == 0 and pid != 1:
                    continue

                cmd = " ".join(cmd_list) or f"[{name}]"
                cpu_available = proc_key in self._seen_keys
                self._seen_keys.add(proc_key)
                cpu_pct = round(float(info["cpu_percent"] or 0.0), 1)
                gpu_pct = float(gpu_pct_map.get(pid, 0.0))
                rss_mb = round(
                    (info["memory_info"].rss / (1024 * 1024))
                    if info["memory_info"]
                    else 0.0,
                    1,
                )
                mem_pct = round(float(info["memory_percent"] or 0.0), 1)

                # Per-process Disk I/O rate
                disk_kbs = 0.0
                disk_available = False
                io_c = info.get("io_counters")
                if io_c is not None:
                    rb, wb = int(io_c.read_bytes), int(io_c.write_bytes)
                    new_io[pid] = (rb, wb)
                    if proc_key in self._prev_io:
                        prb, pwb = self._prev_io[proc_key]
                        disk_kbs = round(
                            max(0.0, ((rb - prb) + (wb - pwb)) / dt / 1024.0), 1
                        )
                        disk_available = True

                # Per-process Context Switches (context switches per second)
                ctx_s = 0.0
                ctx_available = False
                ctx_c = info.get("num_ctx_switches")
                if ctx_c is not None:
                    total_ctx = int(ctx_c.voluntary + ctx_c.involuntary)
                    new_ctx[pid] = total_ctx
                    if proc_key in self._prev_ctx:
                        ctx_s = round(
                            max(0.0, (total_ctx - self._prev_ctx[proc_key]) / dt),
                            1,
                        )
                        ctx_available = True

                state = info["status"] or "?"
                impact_label, impact_score = self._classify_power_impact(
                    cpu_pct, gpu_pct, ctx_s, disk_kbs, state
                )
                port_list = sorted(set(pid_ports.get(pid, [])))
                ports_str = ", ".join(port_list[:4])
                if len(port_list) > 4:
                    ports_str += f" +{len(port_list) - 4}"
                unit = self.get_unit_for_pid(pid)

                procs.append(
                    {
                        "pid": pid,
                        "ppid": ppid,
                        "create_time": float(info["create_time"] or 0.0),
                        "name": name,
                        "group": self._normalize_app_group(name, cmd),
                        "user": info["username"] or "?",
                        "cpu": cpu_pct,
                        "cpu_available": cpu_available,
                        "gpu": gpu_pct,
                        "mem_mb": rss_mb,
                        "mem_pct": mem_pct,
                        "disk_kbs": disk_kbs,
                        "disk_available": disk_available,
                        "wakeups_s": ctx_s,
                        "ctx_available": ctx_available,
                        "impact": impact_label,
                        "impact_score": round(impact_score, 1),
                        "threads": int(info["num_threads"] or 1),
                        "state": state,
                        "nice": int(info["nice"] or 0),
                        "ports": ports_str,
                        "unit": unit,
                        "cmd": cmd[:200],
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        self._prev_io = new_io
        self._prev_ctx = new_ctx
        # Prune baselines for processes that no longer exist. Keys include
        # create_time, so a recycled PID is never compared against the old
        # process's counters.
        live_keys = {
            (p["pid"], round(float(p.get("create_time") or 0.0), 3)) for p in procs
        }
        self._seen_keys.intersection_update(live_keys)
        for key in list(self._prev_tid_ticks):
            if key[0] not in live_keys:
                del self._prev_tid_ticks[key]

        # Build App Group aggregation
        groups_map: dict[str, dict] = {}
        for pr in procs:
            gname = pr["group"]
            g = groups_map.get(gname)
            if g is None:
                g = {
                    "pid": pr["pid"],  # lead/representative PID
                    "ppid": pr["ppid"],
                    "name": f"{gname} (1 proc)",
                    "group": gname,
                    "user": pr["user"],
                    "cpu": pr["cpu"],
                    "cpu_available": pr["cpu_available"],
                    "gpu": pr["gpu"],
                    "mem_mb": pr["mem_mb"],
                    "mem_pct": pr["mem_pct"],
                    "disk_kbs": pr["disk_kbs"],
                    "disk_available": pr["disk_available"],
                    "wakeups_s": pr["wakeups_s"],
                    "ctx_available": pr["ctx_available"],
                    "impact_score": pr["impact_score"],
                    "threads": pr["threads"],
                    "state": pr["state"],
                    "ports_set": set(pr["ports"].split(", ")) if pr["ports"] else set(),
                    "unit": pr["unit"],
                    "units": {pr["unit"]},
                    "users": {pr["user"]},
                    "count": 1,
                    "pids": [pr["pid"]],
                }
                groups_map[gname] = g
            else:
                g["count"] += 1
                g["pids"].append(pr["pid"])
                g["units"].add(pr["unit"])
                g["users"].add(pr["user"])
                if pr["pid"] < g["pid"]:
                    g["pid"] = pr["pid"]
                g["name"] = f"{gname} ({g['count']} procs)"
                g["cpu"] = round(g["cpu"] + pr["cpu"], 1)
                g["cpu_available"] = g["cpu_available"] or pr["cpu_available"]
                g["gpu"] = round(max(g["gpu"], pr["gpu"]), 1)
                g["mem_mb"] = round(g["mem_mb"] + pr["mem_mb"], 1)
                g["mem_pct"] = round(g["mem_pct"] + pr["mem_pct"], 1)
                g["disk_kbs"] = round(g["disk_kbs"] + pr["disk_kbs"], 1)
                g["disk_available"] = g["disk_available"] or pr["disk_available"]
                g["wakeups_s"] = round(g["wakeups_s"] + pr["wakeups_s"], 1)
                g["ctx_available"] = g["ctx_available"] or pr["ctx_available"]
                g["impact_score"] = round(g["impact_score"] + pr["impact_score"], 1)
                g["threads"] += pr["threads"]
                if pr["ports"]:
                    g["ports_set"].update(pr["ports"].split(", "))

        grouped_rows: list[dict] = []
        for g in groups_map.values():
            imp_lbl, _ = self._classify_power_impact(
                g["cpu"], g["gpu"], g["wakeups_s"], g["disk_kbs"], "aggregate"
            )
            grouped_rows.append(
                {
                    "pid": g["pid"],
                    "ppid": g["ppid"],
                    "name": g["name"],
                    "group": g["group"],
                    "user": g["user"] if len(g["users"]) == 1 else "multiple users",
                    "cpu": g["cpu"],
                    "cpu_available": g["cpu_available"],
                    "gpu": g["gpu"],
                    "mem_mb": g["mem_mb"],
                    "mem_pct": g["mem_pct"],
                    "disk_kbs": g["disk_kbs"],
                    "disk_available": g["disk_available"],
                    "wakeups_s": g["wakeups_s"],
                    "ctx_available": g["ctx_available"],
                    "impact": imp_lbl,
                    "impact_score": g["impact_score"],
                    "threads": g["threads"],
                    "state": "-",
                    "ports": ", ".join(sorted(g["ports_set"])[:5])
                    + (
                        f" +{len(g['ports_set']) - 5}"
                        if len(g["ports_set"]) > 5
                        else ""
                    ),
                    "unit": g["unit"] if len(g["units"]) == 1 else "multiple units",
                    "cmd": f"PIDs: {', '.join(str(x) for x in g['pids'][:12])}",
                    "pids": g["pids"],
                }
            )

        return procs, grouped_rows

    @staticmethod
    def build_tree_order(procs: list[dict]) -> list[dict]:
        """Arrange processes in parent -> child tree order with visual branch prefixes."""
        by_pid = {p["pid"]: dict(p) for p in procs}
        children: dict[int, list[int]] = {}
        roots: list[int] = []
        for p in procs:
            pid = p["pid"]
            ppid = p["ppid"]
            if ppid in by_pid and ppid != pid:
                children.setdefault(ppid, []).append(pid)
            else:
                roots.append(pid)

        for k in children:
            children[k].sort(key=lambda x: by_pid[x]["cpu"], reverse=True)
        roots.sort(key=lambda x: by_pid[x]["cpu"], reverse=True)

        ordered: list[dict] = []
        visited: set[int] = set()

        def dfs(pid: int, depth: int, is_last: bool) -> None:
            if pid in visited:
                return
            visited.add(pid)
            item = by_pid[pid]
            if depth > 0:
                branch = "└─ " if is_last else "├─ "
                item["name"] = ("   " * (depth - 1)) + branch + item["name"]
            ordered.append(item)
            kids = children.get(pid, [])
            for idx, kpid in enumerate(kids):
                dfs(kpid, depth + 1, idx == len(kids) - 1)

        for rpid in roots:
            dfs(rpid, 0, True)
        return ordered

    def get_process_details(self, pid: int) -> dict:
        """Inspect a single PID: live threads (TID, name, CPU%, core, state), sockets, open FDs, and env."""
        now = time.monotonic()
        dt = max(now - self._last_tid_ts, 0.2)
        self._last_tid_ts = now

        details = {
            "pid": pid,
            "name": "-",
            "cmdline": "-",
            "cwd": "-",
            "exe": "-",
            "unit": self.get_unit_for_pid(pid),
            "oom_score": 0,
            "threads": [],
            "threads_denied": False,
            "connections": [],
            "connections_denied": False,
            "open_fds": [],
            "open_fd_count": 0,
            "fds_denied": False,
            "environ": [],
            "environ_denied": False,
        }

        try:
            proc = psutil.Process(pid)
            proc_key = (pid, round(float(proc.create_time() or 0.0), 3))
            details["name"] = proc.name()
            details["cmdline"] = " ".join(proc.cmdline()) or proc.name()
            try:
                details["cwd"] = proc.cwd()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                details["cwd"] = "(Permission Denied)"
            try:
                details["exe"] = proc.exe()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                details["exe"] = "-"

            try:
                details["oom_score"] = int(
                    Path(f"/proc/{pid}/oom_score").read_text().strip()
                )
            except OSError:
                pass

            # 1. Threads with live per-thread CPU% delta and last CPU core
            task_dir = Path(f"/proc/{pid}/task")
            t_list = []
            if task_dir.is_dir():
                for tid_dir in task_dir.iterdir():
                    if not tid_dir.name.isdigit():
                        continue
                    tid = int(tid_dir.name)
                    try:
                        t_name = (
                            (tid_dir / "comm")
                            .read_text(encoding="utf-8", errors="replace")
                            .strip()
                        )
                        stat_raw = (tid_dir / "stat").read_text(
                            encoding="utf-8", errors="replace"
                        )
                        after_comm = stat_raw.rsplit(")", 1)[1].split()
                        t_state = after_comm[0]
                        utime_ticks = int(after_comm[11])
                        stime_ticks = int(after_comm[12])
                        total_ticks = utime_ticks + stime_ticks
                        cpu_core = int(after_comm[36]) if len(after_comm) > 36 else 0

                        prev_ticks = self._prev_tid_ticks.get((proc_key, tid))
                        cpu_known = prev_ticks is not None
                        if prev_ticks is None:
                            tid_cpu_pct = 0.0
                        else:
                            delta_ticks = max(0, total_ticks - prev_ticks)
                            tid_cpu_pct = min(
                                100.0,
                                round((delta_ticks / float(CLK_TCK) / dt) * 100.0, 1),
                            )
                        self._prev_tid_ticks[(proc_key, tid)] = total_ticks

                        t_list.append(
                            {
                                "tid": tid,
                                "name": t_name,
                                "state": t_state,
                                "cpu_pct": tid_cpu_pct,
                                "cpu_known": cpu_known,
                                "core": cpu_core,
                                "user_s": round(utime_ticks / float(CLK_TCK), 2),
                                "sys_s": round(stime_ticks / float(CLK_TCK), 2),
                                "total_s": round(total_ticks / float(CLK_TCK), 2),
                            }
                        )
                    except (OSError, ValueError, IndexError):
                        continue
            else:
                details["threads_denied"] = True
            t_list.sort(key=lambda x: (x["cpu_pct"], x["total_s"]), reverse=True)
            details["threads"] = t_list

            # 2. Connections
            try:
                for c in proc.net_connections(kind="all"):
                    proto = (
                        "TCP"
                        if c.type == socket.SOCK_STREAM
                        else ("UDP" if c.type == socket.SOCK_DGRAM else "UNIX")
                    )
                    laddr = (
                        f"{c.laddr.ip}:{c.laddr.port}"
                        if hasattr(c.laddr, "ip")
                        else str(c.laddr or "-")
                    )
                    raddr = (
                        f"{c.raddr.ip}:{c.raddr.port}"
                        if hasattr(c.raddr, "ip")
                        else str(c.raddr or "-")
                    )
                    details["connections"].append(
                        {
                            "fd": c.fd,
                            "proto": proto,
                            "local": laddr,
                            "remote": raddr,
                            "state": c.status,
                        }
                    )
            except psutil.AccessDenied:
                details["connections_denied"] = True
            except psutil.NoSuchProcess:
                pass

            # 3. Open FDs (/proc/<pid>/fd)
            fd_dir = Path(f"/proc/{pid}/fd")
            try:
                fd_entries = list(fd_dir.iterdir())
            except OSError:
                details["open_fd_count"] = 0
                details["fds_denied"] = True
            else:
                details["open_fd_count"] = len(fd_entries)
                for fd_entry in sorted(
                    fd_entries,
                    key=lambda x: int(x.name) if x.name.isdigit() else 9999,
                )[:120]:
                    try:
                        target = os.readlink(fd_entry)
                        details["open_fds"].append((int(fd_entry.name), target))
                    except OSError:
                        continue

            # 4. Environment variables
            try:
                env = proc.environ()
                for k in sorted(env.keys()):
                    if any(
                        sec in k.upper()
                        for sec in ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH")
                    ):
                        details["environ"].append((k, "******** (redacted)"))
                    else:
                        details["environ"].append((k, env[k][:160]))
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                details["environ_denied"] = True

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        return details

    @staticmethod
    def send_signal_to_pids(pids: list[int], sig: int) -> tuple[bool, str]:
        """Send signal (SIGTERM, SIGKILL, SIGSTOP, SIGCONT) to one or more PIDs."""
        need_root: list[str] = []
        count = 0
        for pid in pids:
            if pid <= 1:
                continue
            try:
                os.kill(pid, sig)
                count += 1
            except PermissionError:
                need_root.append(str(pid))
            except ProcessLookupError:
                pass
        if need_root:
            try:
                subprocess.Popen(["pkexec", "kill", f"-{int(sig)}", *need_root])
                return (
                    True,
                    f"Sent signal {sig} via Polkit to PID(s) {', '.join(need_root)}",
                )
            except OSError as exc:
                return False, str(exc)
        return True, f"Sent signal {sig} to {count} process(es)"
