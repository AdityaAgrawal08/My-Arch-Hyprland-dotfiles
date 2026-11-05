#!/usr/bin/env python3
"""Linux Pressure Stall Information (/proc/pressure) reader."""

from __future__ import annotations

from pathlib import Path


class PsiCollector:
    """Reads the kernel's PSI stall metrics without spawning any process."""

    @staticmethod
    def sample() -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for resource in ("cpu", "memory", "io"):
            path = Path(f"/proc/pressure/{resource}")
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            item: dict[str, float] = {}
            for line in lines:
                parts = line.split()
                if not parts or parts[0] not in ("some", "full"):
                    continue
                prefix = parts[0]
                for part in parts[1:]:
                    key, _, value = part.partition("=")
                    try:
                        item[f"{prefix}_{key}"] = float(value)
                    except ValueError:
                        continue
            if item:
                out[resource] = item
        return out
