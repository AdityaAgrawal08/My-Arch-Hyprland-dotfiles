#!/usr/bin/env python3
"""Gated bpftrace runner for the optional Live Events tab.

bpftrace needs root (or CAP_BPF) and kernel BTF. When those prerequisites are
missing the UI shows the exact install/root command instead of pretending to
capture events.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BpftraceProbe:
    key: str
    label: str
    description: str
    script: str

    def command(self) -> str:
        return f"sudo bpftrace -e {shlex.quote(self.script)}"


PROBES: tuple[BpftraceProbe, ...] = (
    BpftraceProbe(
        key="execsnoop",
        label="execsnoop",
        description="New processes as they are executed (sys_enter_execve).",
        script=(
            "tracepoint:syscalls:sys_enter_execve "
            '{ printf("%-16s %s\\n", comm, str(args->filename)); }'
        ),
    ),
    BpftraceProbe(
        key="opensnoop",
        label="opensnoop",
        description="Files opened by any process (sys_enter_openat).",
        script=(
            "tracepoint:syscalls:sys_enter_openat "
            '{ printf("%-16s %s\\n", comm, str(args->filename)); }'
        ),
    ),
    BpftraceProbe(
        key="biosnoop",
        label="biosnoop",
        description="Block I/O requests as they are issued.",
        script=(
            "tracepoint:block:block_rq_issue "
            '{ printf("%-16s %s %llu\\n", comm, str(args->rwbs), args->bytes); }'
        ),
    ),
    BpftraceProbe(
        key="tcpretrans",
        label="tcpretrans",
        description="TCP retransmissions with source/destination addresses.",
        script=(
            "tracepoint:tcp:tcp_retransmit_skb "
            '{ printf("%-16s %s:%d -> %s:%d state=%d\\n", comm, '
            "ntop(args->saddr), args->sport, ntop(args->daddr), "
            "args->dport, args->state); }"
        ),
    ),
)

PROBES_BY_KEY = {probe.key: probe for probe in PROBES}
PROBES_BY_LABEL = {probe.label: probe for probe in PROBES}


class BpftraceRunner:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._probe: BpftraceProbe | None = None
        self._stop_requested = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def current_probe(self) -> BpftraceProbe | None:
        return self._probe if self.is_running else None

    @staticmethod
    def detect() -> dict:
        bpftrace = shutil.which("bpftrace")
        btf = Path("/sys/kernel/btf/vmlinux").is_file()
        root = os.geteuid() == 0
        missing: list[str] = []
        if not bpftrace:
            missing.append("bpftrace is not installed")
        if not btf:
            missing.append("/sys/kernel/btf/vmlinux is missing")
        if not root:
            missing.append("root/CAP_BPF is required")
        if not bpftrace:
            action = "sudo pacman -S bpftrace"
        elif not btf:
            action = "install a kernel built with CONFIG_DEBUG_INFO_BTF"
        elif not root:
            action = "sudo bpftrace -e '<probe>'  # or run this app as root"
        else:
            action = ""
        return {
            "bpftrace": bpftrace,
            "btf": btf,
            "root": root,
            "can_run": bool(bpftrace and btf and root),
            "missing": missing,
            "reason": "; ".join(missing) if missing else "ready",
            "action": action,
        }

    def start(
        self,
        probe_key: str,
        on_line,
        on_exit=None,
        allow_nonroot: bool = False,
        command: list[str] | None = None,
    ) -> tuple[bool, str]:
        if self.is_running:
            return (
                False,
                f"{self._probe.label if self._probe else 'A probe'} is already running.",
            )
        probe = PROBES_BY_KEY.get(probe_key)
        if probe is None:
            return False, f"Unknown probe: {probe_key}"
        info = self.detect()
        if info["bpftrace"] is None:
            return (
                False,
                "bpftrace is not installed. Install it with: sudo pacman -S bpftrace",
            )
        if not info["btf"]:
            return False, "Kernel BTF is missing. A BTF-enabled kernel is required."
        if not info["root"] and not allow_nonroot and command is None:
            return False, f"root is required. Run: {probe.command()}"
        cmd = command or [info["bpftrace"], "-e", probe.script]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as exc:
            return False, f"Could not start bpftrace: {exc}"
        self._proc = proc
        self._probe = probe
        self._stop_requested = False
        self._thread = threading.Thread(
            target=self._read_output,
            args=(proc, on_line, on_exit),
            daemon=True,
        )
        self._thread.start()
        return True, f"Started {probe.label}. Waiting for events..."

    def _read_output(self, proc, on_line, on_exit) -> None:
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    if self._stop_requested:
                        break
                    on_line(line.rstrip())
        finally:
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except OSError:
                    pass
            code = proc.wait()
            self._proc = None
            if on_exit is not None:
                on_exit(code)

    def stop(self) -> str:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            self._proc = None
            return "No eBPF probe is running."
        self._stop_requested = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                proc.terminate()
            except OSError:
                pass
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        self._proc = None
        return "Stopped the eBPF probe."
