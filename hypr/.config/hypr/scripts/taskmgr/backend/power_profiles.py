#!/usr/bin/env python3
"""Real, verified power-profile control via power-profiles-daemon."""

from __future__ import annotations

import re
import shutil
import subprocess

PROFILE_ORDER = {"power-saver": 0, "balanced": 1, "performance": 2}


class PowerProfileController:
    """Thin wrapper around powerprofilesctl with post-change verification."""

    @staticmethod
    def is_available() -> bool:
        if shutil.which("powerprofilesctl") is None:
            return False
        return PowerProfileController.get_current() is not None

    @staticmethod
    def get_current() -> str | None:
        try:
            out = subprocess.check_output(
                ["powerprofilesctl", "get"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
            ).strip()
            return out or None
        except Exception:
            return None

    @staticmethod
    def list_profiles() -> list[str]:
        try:
            out = subprocess.check_output(
                ["powerprofilesctl", "list"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
            )
        except Exception:
            return []
        profiles: list[str] = []
        for line in out.splitlines():
            stripped = line.strip()
            match = re.match(r"^\*?\s*([a-z][a-z0-9-]*):\s*$", stripped)
            if match:
                profiles.append(match.group(1))
        return sorted(set(profiles), key=lambda p: (PROFILE_ORDER.get(p, 99), p))

    @staticmethod
    def set_profile(profile: str) -> tuple[bool, str]:
        """Apply a profile and verify the daemon actually reports it.

        Returns (success, message). A zero exit status is not enough: the
        daemon can accept the command and still remain on a different profile
        (for example when the platform driver does not support it), so the
        current profile is read back and compared.
        """
        supported = PowerProfileController.list_profiles()
        if not supported:
            return (
                False,
                "Power profile control is unavailable (powerprofilesctl list failed).",
            )
        if profile not in supported:
            return (
                False,
                f"Profile '{profile}' is not offered by power-profiles-daemon.",
            )
        try:
            proc = subprocess.run(
                ["powerprofilesctl", "set", profile],
                text=True,
                capture_output=True,
                timeout=10.0,
            )
        except Exception as exc:
            return False, f"powerprofilesctl set {profile} failed: {exc}"
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            return (
                False,
                f"powerprofilesctl set {profile} failed: {detail or 'exit ' + str(proc.returncode)}",
            )
        current = PowerProfileController.get_current()
        if current != profile:
            return (
                False,
                f"Requested {profile}, but the daemon reports {current or 'unknown'}.",
            )
        return (
            True,
            f"Power profile set to {profile} (verified with powerprofilesctl get).",
        )
