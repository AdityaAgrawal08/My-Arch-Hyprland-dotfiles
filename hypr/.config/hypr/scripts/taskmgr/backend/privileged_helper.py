#!/usr/bin/python3
"""Minimal PolicyKit helper for taskmgr.

Install this file root-owned (for example /usr/local/libexec/taskmgr-privileged)
and pair it with the org.aditya.taskmgr.policy action. It only supports three
allowlisted operations:

  service-io <cgroup> [...]   read /proc/<pid>/io for all PIDs in each cgroup
  rapl-watts                  sample RAPL energy_uj twice and return watts
  bpftrace <probe-key>        exec an allowlisted bpftrace one-liner

No shell is used and no arbitrary command/path is accepted.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

PROBES = {
    "execsnoop": (
        "tracepoint:syscalls:sys_enter_execve "
        '{ printf("%-16s %s\\n", comm, str(args->filename)); }'
    ),
    "opensnoop": (
        "tracepoint:syscalls:sys_enter_openat "
        '{ printf("%-16s %s\\n", comm, str(args->filename)); }'
    ),
    "biosnoop": (
        "tracepoint:block:block_rq_issue "
        '{ printf("%-16s %s %llu\\n", comm, str(args->rwbs), args->bytes); }'
    ),
    "tcpretrans": (
        "tracepoint:tcp:tcp_retransmit_skb "
        '{ printf("%-16s %s:%d -> %s:%d state=%d\\n", comm, '
        "ntop(args->saddr), args->sport, ntop(args->daddr), "
        "args->dport, args->state); }"
    ),
}

ALLOWED_CGROUP_PREFIXES = (
    "/system.slice/",
    "/user.slice/",
    "/machine.slice/",
)


def _read_proc_io(pid: int, proc_root: Path) -> tuple[int, int] | None:
    path = proc_root / str(pid) / "io"
    try:
        read_bytes = None
        write_bytes = None
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
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


def service_io(
    cgroups: list[str],
    cgroup_root: str | Path = "/sys/fs/cgroup",
    proc_root: str | Path = "/proc",
) -> dict:
    cgroup_root = Path(cgroup_root)
    proc_root = Path(proc_root)
    result: dict[str, dict] = {}
    for raw in cgroups:
        cgroup = raw.strip()
        if not cgroup.startswith(ALLOWED_CGROUP_PREFIXES):
            continue
        if ".." in cgroup.split("/"):
            continue
        procs_path = cgroup_root / cgroup.lstrip("/") / "cgroup.procs"
        try:
            pids = [
                int(value)
                for value in procs_path.read_text(
                    encoding="utf-8", errors="replace"
                ).split()
            ]
        except (OSError, ValueError):
            continue
        total_read = 0
        total_write = 0
        readable = 0
        unreadable: list[int] = []
        for pid in pids:
            io = _read_proc_io(pid, proc_root)
            if io is None:
                unreadable.append(pid)
                continue
            total_read += io[0]
            total_write += io[1]
            readable += 1
        if unreadable:
            try:
                remaining = {
                    int(value)
                    for value in procs_path.read_text(
                        encoding="utf-8", errors="replace"
                    ).split()
                }
            except (OSError, ValueError):
                remaining = set()
            if any(pid in remaining for pid in unreadable):
                result[cgroup] = {
                    "read": None,
                    "write": None,
                    "pids": len(pids),
                    "readable": readable,
                }
                continue
        result[cgroup] = {
            "read": total_read if readable else None,
            "write": total_write if readable else None,
            "pids": len(pids),
            "readable": readable,
        }
    return result


def _rapl_sample(root: Path) -> dict[str, dict]:
    sample: dict[str, dict] = {}
    for domain in sorted(root.glob("intel-rapl:*")):
        name = domain.name
        try:
            name = (domain / "name").read_text(encoding="utf-8").strip() or domain.name
        except OSError:
            pass
        try:
            energy = int((domain / "energy_uj").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            sample[str(domain)] = {
                "name": name,
                "energy": None,
                "max": None,
                "reason": "energy_uj is not readable",
            }
            continue
        max_range = None
        try:
            max_range = int(
                (domain / "max_energy_range_uj").read_text(encoding="utf-8").strip()
            )
        except (OSError, ValueError):
            pass
        sample[str(domain)] = {
            "name": name,
            "energy": energy,
            "max": max_range,
            "reason": "",
        }
    return sample


def rapl_watts(
    root: str | Path = "/sys/class/powercap", sleep_s: float = 1.0
) -> list[dict]:
    root = Path(root)
    first = _rapl_sample(root)
    time.sleep(max(0.0, sleep_s))
    second = _rapl_sample(root)
    rows: list[dict] = []
    for key, first_row in first.items():
        second_row = second.get(key, {})
        first_energy = first_row.get("energy")
        second_energy = second_row.get("energy")
        watts = None
        reason = first_row.get("reason", "")
        if first_energy is not None and second_energy is not None:
            delta = second_energy - first_energy
            max_range = second_row.get("max") or first_row.get("max")
            if delta < 0 and max_range:
                delta += max_range
            if delta >= 0 and sleep_s > 0:
                watts = round((delta / 1e6) / sleep_s, 2)
            else:
                reason = "counter reset or no elapsed time"
        rows.append(
            {
                "name": first_row.get("name", key),
                "watts": watts,
                "reason": reason,
            }
        )
    return rows


def run_bpftrace(probe_key: str) -> int:
    script = PROBES.get(probe_key)
    if script is None:
        print(f"Unknown probe: {probe_key}", file=sys.stderr)
        return 2
    binary = shutil.which(
        "bpftrace",
        path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    )
    if not binary:
        print("bpftrace is not installed", file=sys.stderr)
        return 127
    try:
        os.execv(binary, [binary, "-e", script])
    except OSError as exc:
        print(f"Could not execute bpftrace: {exc}", file=sys.stderr)
        return 126
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: taskmgr-privileged service-io <cgroup>... | "
            "rapl-watts | bpftrace <probe>",
            file=sys.stderr,
        )
        return 2
    command = argv[1]
    if command == "service-io":
        print(json.dumps(service_io(argv[2:])))
        return 0
    if command == "rapl-watts":
        print(json.dumps(rapl_watts()))
        return 0
    if command == "bpftrace":
        if len(argv) < 3:
            print("missing probe key", file=sys.stderr)
            return 2
        return run_bpftrace(argv[2])
    print(f"Unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
