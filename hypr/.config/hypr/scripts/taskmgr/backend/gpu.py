#!/usr/bin/env python3
"""GPU telemetry backend.

Supports:
1. DRM fdinfo per-process and per-engine GPU utilization (Intel i915/xe, AMD amdgpu)
   without requiring root privileges.
2. Sysfs frequency, RC6 sleep residency, and hwmon temperatures.
3. Zero-wakeup PCI device name lookup from /usr/share/hwdata/pci.ids.

NVIDIA per-process attribution is not implemented in this build; the Optional
Features tab reports that explicitly instead of fabricating values.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field

VENDORS = {
    "0x8086": "Intel",
    "0x1002": "AMD",
    "0x1022": "AMD",
    "0x10de": "NVIDIA",
    "0x15ad": "VMware",
    "0x1af4": "Red Hat",
}

ENGINE_LABELS = {
    "render": "3D / Render",
    "rcs": "3D / Render",
    "gfx": "3D / Render",
    "compute": "Compute",
    "ccs": "Compute",
    "copy": "Copy / Blitter",
    "bcs": "Copy / Blitter",
    "blitter": "Copy / Blitter",
    "dma": "Copy / Blitter",
    "video": "Video Decode/Encode",
    "vcs": "Video Decode/Encode",
    "video-enhance": "Video Enhance",
    "vecs": "Video Enhance",
    "vpe": "Video Enhance",
    "dec": "Video Decode",
    "enc": "Video Encode",
}

PCI_IDS_PATHS = (
    "/usr/share/hwdata/pci.ids",
    "/usr/share/misc/pci.ids",
    "/usr/share/pci.ids",
)

_UNITS = {"": 1, "B": 1, "KIB": 1 << 10, "MIB": 1 << 20, "GIB": 1 << 30}


def _read(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return default


def _read_int(path: str, default: int = 0) -> int:
    val = _read(path)
    if not val:
        return default
    try:
        return int(val.split()[0])
    except (ValueError, IndexError):
        return default


@functools.lru_cache(maxsize=256)
def pci_device_name(vendor_hex: str, device_hex: str) -> str:
    """Resolve PCI vendor/device IDs from pci.ids without waking hardware via lspci."""
    v = vendor_hex.lower().removeprefix("0x")
    d = device_hex.lower().removeprefix("0x")
    for path in PCI_IDS_PATHS:
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            vendor_name: str | None = None
            for line in fh:
                if vendor_name is None:
                    if line.startswith(v + "  "):
                        vendor_name = line[len(v) :].strip()
                    continue
                if line.startswith("#"):
                    continue
                if not line.startswith("\t"):
                    break
                if line.startswith("\t" + d + "  "):
                    clean_v = (
                        vendor_name.replace(" Corporation", "")
                        .replace(" Inc.", "")
                        .replace(" Co., Ltd", "")
                    )
                    return f"{clean_v} {line[len(d) + 1 :].strip()}"
            if vendor_name is not None:
                return vendor_name
    return ""


def _engine_label(raw: str) -> str:
    key = raw.lower()
    if key in ENGINE_LABELS:
        return ENGINE_LABELS[key]
    for prefix, label in ENGINE_LABELS.items():
        if key.startswith(prefix):
            return label
    return raw.replace("-", " ").title()


def _fdinfo_bytes(value: str) -> int:
    number, _, unit = value.partition(" ")
    try:
        return int(number) * _UNITS.get(unit.strip().upper(), 1)
    except ValueError:
        return 0


def scan_drm_fdinfo(proc_root: str = "/proc") -> tuple[dict, dict, dict]:
    """Walk /proc/*/fdinfo and aggregate DRM engine busy ns and client memory.

    Returns:
      per_dev: pdev -> {"engines": {name: ns}, "capacity": {name: n}, "mem": bytes, "clients": int}
      per_pid_ns: pid -> {engine_name: ns}
      per_pid_mem: pid -> bytes
    """
    per_dev: dict[str, dict] = {}
    per_pid_ns: dict[int, dict[str, int]] = {}
    per_pid_mem: dict[int, int] = {}
    seen_clients: set[tuple[str, str]] = set()

    try:
        pids = os.listdir(proc_root)
    except OSError:
        return per_dev, per_pid_ns, per_pid_mem

    for pid_str in pids:
        if not pid_str.isdigit():
            continue
        fdinfo_dir = f"{proc_root}/{pid_str}/fdinfo"
        try:
            fds = os.listdir(fdinfo_dir)
        except OSError:
            continue

        pid = int(pid_str)
        for fd in fds:
            try:
                with open(f"{fdinfo_dir}/{fd}", "rb") as fh:
                    blob = fh.read(4096)
            except OSError:
                continue
            if b"drm-engine" not in blob and b"drm-client-id" not in blob:
                continue

            pdev = ""
            client_id = ""
            engines: dict[str, int] = {}
            capacity: dict[str, int] = {}
            total_mem = resident_mem = 0

            for line in blob.decode("utf-8", "replace").splitlines():
                k, _, v = line.partition(":")
                v = v.strip()
                if k == "drm-pdev":
                    pdev = v
                elif k == "drm-client-id":
                    client_id = v
                elif k.startswith("drm-engine-capacity-"):
                    eng = k[len("drm-engine-capacity-") :]
                    try:
                        capacity[eng] = int(v)
                    except ValueError:
                        pass
                elif k.startswith("drm-engine-"):
                    eng = k[len("drm-engine-") :]
                    try:
                        engines[eng] = int(v.split()[0])
                    except (ValueError, IndexError):
                        pass
                elif k.startswith("drm-total-"):
                    total_mem += _fdinfo_bytes(v)
                elif k.startswith(("drm-resident-", "drm-memory-")):
                    resident_mem += _fdinfo_bytes(v)

            if not pdev and not engines:
                continue
            ident = (pdev or "default", client_id or f"{pid}/{fd}")
            if ident in seen_clients:
                continue
            seen_clients.add(ident)

            mem_bytes = resident_mem or total_mem
            bucket = per_dev.setdefault(
                pdev or "default",
                {"engines": {}, "capacity": {}, "mem": 0, "clients": 0},
            )
            bucket["clients"] += 1
            bucket["mem"] += mem_bytes
            for eng, cap in capacity.items():
                bucket["capacity"][eng] = max(bucket["capacity"].get(eng, 1), cap)
            for eng, ns in engines.items():
                bucket["engines"][eng] = bucket["engines"].get(eng, 0) + ns

            pid_eng = per_pid_ns.setdefault(pid, {})
            for eng, ns in engines.items():
                pid_eng[eng] = pid_eng.get(eng, 0) + ns
            if mem_bytes > 0:
                per_pid_mem[pid] = per_pid_mem.get(pid, 0) + mem_bytes

    return per_dev, per_pid_ns, per_pid_mem


def _number(value: object) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def query_nvidia_smi_gpus() -> list[dict]:
    """Read aggregate GPU telemetry from nvidia-smi (no root required)."""
    binary = shutil.which("nvidia-smi")
    if not binary:
        return []
    try:
        out = subprocess.check_output(
            [
                binary,
                "--query-gpu=name,pci.bus_id,utilization.gpu,memory.used,"
                "memory.total,temperature.gpu,clocks.current.graphics",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    rows: list[dict] = []
    for line in out.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 7:
            continue
        rows.append(
            {
                "name": parts[0],
                "bus_id": parts[1],
                "busy": _number(parts[2]),
                "mem_used": _number(parts[3]),
                "mem_total": _number(parts[4]),
                "temp": _number(parts[5]),
                "freq": _number(parts[6]),
            }
        )
    return rows


def query_nvidia_smi_processes() -> dict[int, float]:
    """Read per-process compute-app GPU memory from nvidia-smi."""
    binary = shutil.which("nvidia-smi")
    if not binary:
        return {}
    try:
        out = subprocess.check_output(
            [
                binary,
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    result: dict[int, float] = {}
    for line in out.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        mem = _number(parts[1])
        if mem is not None:
            result[pid] = round(mem, 1)
    return result


@dataclass(slots=True)
class GpuSnapshot:
    card: str = "-"
    name: str = "No GPU detected"
    driver: str = "-"
    pdev: str = ""
    busy_pct: float = 0.0
    busy_available: bool = False
    engines: dict[str, float] = field(default_factory=dict)
    freq_mhz: int = 0
    max_freq_mhz: int = 0
    freq_available: bool = False
    mem_used_mb: float = 0.0
    mem_total_mb: float = 0.0
    clients: int = 0
    temp_c: float = 0.0
    temp_available: bool = False
    runtime_status: str = "-"
    rc6_pct: float = 0.0
    rc6_available: bool = False
    source: str = "none"


class GpuCollector:
    """Tracks GPU engine utilization, per-process GPU %, frequencies, and RC6 residency."""

    def __init__(self) -> None:
        self._prev_dev_ns: dict[str, dict[str, int]] = {}
        self._prev_pid_ns: dict[int, dict[str, int]] = {}
        self._prev_rc6_ms: dict[str, int] = {}
        self._prev_ts = time.monotonic()
        self._nvidia_ts = 0.0
        self._nvidia_gpus: list[dict] = []
        self._nvidia_procs: dict[int, float] = {}
        self._nvidia_lock = threading.Lock()
        self._nvidia_thread: threading.Thread | None = None
        self.proc_gpu_pct: dict[int, float] = {}
        self.proc_gpu_mem_mb: dict[int, float] = {}
        # Prime initial counters
        self.sample()

    def _detect_cards(self) -> list[dict]:
        cards = []
        try:
            entries = sorted(os.listdir("/sys/class/drm"))
        except OSError:
            return cards
        for entry in entries:
            if not entry.startswith("card") or "-" in entry:
                continue
            base = f"/sys/class/drm/{entry}"
            if not os.path.exists(f"{base}/device"):
                # Connector-only or non-device card entry.
                continue
            try:
                pdev = os.path.basename(os.path.realpath(f"{base}/device"))
            except OSError:
                continue
            driver = ""
            try:
                driver = os.path.basename(os.path.realpath(f"{base}/device/driver"))
            except OSError:
                pass
            vendor = _read(f"{base}/device/vendor")
            device = _read(f"{base}/device/device")
            name = (
                pci_device_name(vendor, device)
                or f"{VENDORS.get(vendor, 'GPU')} ({driver})"
            )
            runtime_status = _read(f"{base}/device/power/runtime_status", "active")
            cards.append(
                {
                    "card": entry,
                    "base": base,
                    "pdev": pdev,
                    "driver": driver,
                    "name": name,
                    "runtime_status": runtime_status,
                }
            )
        return cards

    @staticmethod
    def _read_rc6_ms(base: str) -> int:
        for rel in (
            "gt/gt0/rc6_residency_ms",
            "power/rc6_residency_ms",
            "device/tile0/gt0/gtidle/idle_residency_ms",
        ):
            v = _read_int(f"{base}/{rel}", -1)
            if v >= 0:
                return v
        return -1

    @staticmethod
    def _read_optional_int(path: str) -> int | None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                txt = fh.read().strip()
            return int(txt.split()[0]) if txt else None
        except (OSError, ValueError, IndexError):
            return None

    @staticmethod
    def _read_temp(base: str) -> float | None:
        hwmon_root = f"{base}/device/hwmon"
        try:
            for h in os.listdir(hwmon_root):
                t = _read_int(f"{hwmon_root}/{h}/temp1_input", 0)
                if t > 0:
                    return round(t / 1000.0, 1)
        except OSError:
            pass
        return None

    def _refresh_nvidia(self) -> None:
        gpus = query_nvidia_smi_gpus()
        procs = query_nvidia_smi_processes()
        with self._nvidia_lock:
            self._nvidia_gpus = gpus
            self._nvidia_procs = procs
            self._nvidia_ts = time.monotonic()

    def _nvidia_smi_cached(self, now: float) -> tuple[list[dict], dict[int, float]]:
        with self._nvidia_lock:
            fresh = now - self._nvidia_ts < 2.0
            running = (
                self._nvidia_thread is not None
                and self._nvidia_thread.is_alive()
            )
            if not fresh and not running:
                self._nvidia_thread = threading.Thread(
                    target=self._refresh_nvidia, daemon=True
                )
                self._nvidia_thread.start()
            return self._nvidia_gpus, self._nvidia_procs

    @staticmethod
    def _apply_nvidia(snap: GpuSnapshot, nv: dict, clients: int) -> None:
        if nv.get("name"):
            snap.name = str(nv["name"])
        snap.driver = "nvidia"
        busy = nv.get("busy")
        snap.busy_available = busy is not None
        snap.busy_pct = float(busy) if busy is not None else 0.0
        mem_used = nv.get("mem_used")
        mem_total = nv.get("mem_total")
        snap.mem_used_mb = float(mem_used) if mem_used is not None else 0.0
        snap.mem_total_mb = float(mem_total) if mem_total is not None else 0.0
        temp = nv.get("temp")
        snap.temp_available = temp is not None
        snap.temp_c = float(temp) if temp is not None else 0.0
        freq = nv.get("freq")
        snap.freq_available = freq is not None
        snap.freq_mhz = int(freq) if freq is not None else 0
        snap.max_freq_mhz = 0
        snap.clients = clients
        snap.engines = {}
        snap.rc6_available = False
        snap.source = "nvidia-smi (aggregate; compute apps are global)"

    def sample(self) -> list[GpuSnapshot]:
        now = time.monotonic()
        elapsed = max(now - self._prev_ts, 1e-4)
        self._prev_ts = now

        cards = self._detect_cards()
        nvidia_gpus, nvidia_procs = self._nvidia_smi_cached(now)
        nvidia_by_pdev = {
            gpu["bus_id"][-12:].lower(): gpu
            for gpu in nvidia_gpus
            if gpu.get("bus_id")
        }
        matched_nvidia: set[str] = set()
        per_dev, per_pid_ns, per_pid_mem = scan_drm_fdinfo()

        # Per-PID GPU %
        new_proc_gpu: dict[int, float] = {}
        for pid, eng_map in per_pid_ns.items():
            prev_map = self._prev_pid_ns.get(pid, {})
            peak = 0.0
            for eng, ns in eng_map.items():
                delta = max(0, ns - prev_map.get(eng, ns))
                pct = min(100.0, (delta / (elapsed * 1e9)) * 100.0)
                if pct > peak:
                    peak = pct
            if peak >= 0.05:
                new_proc_gpu[pid] = round(peak, 1)
        self.proc_gpu_pct = new_proc_gpu
        self._prev_pid_ns = per_pid_ns
        self.proc_gpu_mem_mb = {
            pid: round(mem / (1024 * 1024), 1) for pid, mem in per_pid_mem.items()
        }

        snapshots: list[GpuSnapshot] = []
        for c in cards:
            base = c["base"]
            pdev = c["pdev"]
            snap = GpuSnapshot(
                card=c["card"],
                name=c["name"],
                driver=c["driver"],
                pdev=pdev,
                runtime_status=c["runtime_status"],
            )

            freq = None
            for rel in (
                "gt_act_freq_mhz",
                "gt_cur_freq_mhz",
                "gt/gt0/rps_act_freq_mhz",
            ):
                val = self._read_optional_int(f"{base}/{rel}")
                if val is None:
                    continue
                if freq is None:
                    freq = val
                if val > 0:
                    freq = val
                    break
            snap.freq_available = freq is not None
            snap.freq_mhz = int(freq) if freq is not None else 0

            max_freq = self._read_optional_int(f"{base}/gt_max_freq_mhz")
            if max_freq is None:
                max_freq = self._read_optional_int(f"{base}/gt_RP0_freq_mhz")
            if max_freq is None:
                max_freq = self._read_optional_int(f"{base}/gt/gt0/rps_max_freq_mhz")
            snap.max_freq_mhz = int(max_freq) if max_freq is not None else 0

            temp = self._read_temp(base)
            snap.temp_available = temp is not None
            snap.temp_c = float(temp) if temp is not None else 0.0

            rc6_ms = self._read_rc6_ms(base)
            if rc6_ms >= 0:
                snap.rc6_available = True
                prev_rc6 = self._prev_rc6_ms.get(pdev, rc6_ms)
                delta_rc6 = max(0, rc6_ms - prev_rc6)
                snap.rc6_pct = min(
                    100.0, round((delta_rc6 / (elapsed * 1000.0)) * 100.0, 1)
                )
                self._prev_rc6_ms[pdev] = rc6_ms

            # Only report engines that the driver actually exposes in DRM fdinfo.
            # Empty means no visible client counters, not a fabricated 0 % set.
            engines: dict[str, float] = {}

            bucket = per_dev.get(pdev) or per_dev.get("default")
            if bucket:
                prev_eng = self._prev_dev_ns.get(pdev, {})
                for eng_raw, ns in bucket["engines"].items():
                    delta = max(0, ns - prev_eng.get(eng_raw, ns))
                    cap = max(1, bucket["capacity"].get(eng_raw, 1))
                    pct = min(100.0, (delta / (elapsed * 1e9 * cap)) * 100.0)
                    label = _engine_label(eng_raw)
                    engines[label] = round(max(engines.get(label, 0.0), pct), 1)
                snap.mem_used_mb = round(bucket["mem"] / (1024 * 1024), 1)
                snap.clients = bucket["clients"]
                self._prev_dev_ns[pdev] = dict(bucket["engines"])

            busy_sysfs = _read_int(f"{base}/device/gpu_busy_percent", -1)
            if busy_sysfs >= 0:
                snap.busy_pct = float(busy_sysfs)
                snap.busy_available = True
                snap.source = f"sysfs {base}/device/gpu_busy_percent"
            elif engines:
                snap.busy_pct = round(max(engines.values(), default=0.0), 1)
                snap.busy_available = True
                snap.source = "DRM fdinfo (visible clients only)"
            else:
                snap.busy_pct = 0.0
                snap.busy_available = False
                snap.source = "no DRM fdinfo engine counters for visible clients"

            snap.engines = engines
            nv = nvidia_by_pdev.get(pdev.lower())
            if nv is not None:
                matched_nvidia.add(pdev.lower())
                self._apply_nvidia(snap, nv, len(nvidia_procs))
            snapshots.append(snap)

        for bus_id, nv in nvidia_by_pdev.items():
            if bus_id in matched_nvidia:
                continue
            snap = GpuSnapshot(
                card="nvidia-smi",
                name=str(nv.get("name") or "NVIDIA GPU"),
                driver="nvidia",
                pdev=bus_id,
                runtime_status="active",
            )
            self._apply_nvidia(snap, nv, len(nvidia_procs))
            snapshots.append(snap)

        for pid, mem_mb in nvidia_procs.items():
            self.proc_gpu_mem_mb[pid] = round(
                max(self.proc_gpu_mem_mb.get(pid, 0.0), mem_mb), 1
            )

        return snapshots
