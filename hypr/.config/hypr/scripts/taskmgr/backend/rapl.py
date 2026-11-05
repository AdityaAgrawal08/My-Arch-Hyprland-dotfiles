#!/usr/bin/env python3
"""RAPL energy counters from /sys/class/powercap.

Reads package/core/uncore/dram energy_uj domains and derives watts between
samples. energy_uj is root-only on many distributions; when it is unreadable
the collector reports that instead of fabricating power.
"""

from __future__ import annotations

import time
from pathlib import Path


class RaplCollector:
    def __init__(self, root: str | Path = "/sys/class/powercap") -> None:
        self.root = Path(root)
        self._prev: dict[str, tuple[float, int]] = {}

    def _domains(self) -> list[Path]:
        return sorted(self.root.glob("intel-rapl:*"), key=lambda p: p.name)

    def sample(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        domains = self._domains()
        if not domains:
            return {
                "available": False,
                "reason": "no intel-rapl domains exposed",
                "domains": [],
            }
        rows: list[dict] = []
        any_readable = False
        for domain in domains:
            name = domain.name
            try:
                name = (domain / "name").read_text(
                    encoding="utf-8"
                ).strip() or domain.name
            except OSError:
                pass
            energy_path = domain / "energy_uj"
            try:
                energy = int(energy_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                rows.append(
                    {
                        "name": name,
                        "path": str(energy_path),
                        "watts": None,
                        "reason": "energy_uj is not readable (root-only)",
                    }
                )
                continue
            any_readable = True
            max_range: int | None = None
            try:
                max_range = int(
                    (domain / "max_energy_range_uj").read_text(encoding="utf-8").strip()
                )
            except (OSError, ValueError):
                pass
            prev = self._prev.get(str(domain))
            watts: float | None = None
            reason = ""
            if prev is None:
                reason = "first sample; another read is needed"
            else:
                elapsed = now - prev[0]
                if elapsed > 5.0:
                    reason = "stale sample; waiting for a fresh read"
                elif elapsed > 0:
                    delta = energy - prev[1]
                    if delta < 0 and max_range:
                        delta += max_range
                    if delta >= 0:
                        watts = round((delta / 1e6) / elapsed, 2)
                    else:
                        reason = "counter reset or wrapped without a range"
                else:
                    reason = "no elapsed time"
            self._prev[str(domain)] = (now, energy)
            rows.append(
                {
                    "name": name,
                    "path": str(energy_path),
                    "watts": watts,
                    "reason": reason,
                }
            )
        if not any_readable:
            return {
                "available": False,
                "reason": "energy_uj is not readable (root-only on this machine)",
                "domains": rows,
            }
        return {"available": True, "reason": "", "domains": rows}
