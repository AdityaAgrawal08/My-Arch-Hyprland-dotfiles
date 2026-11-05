#!/usr/bin/env python3
"""Client for the optional root-owned PolicyKit helper."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

HELPER_PATH = Path("/usr/local/libexec/taskmgr-privileged")


class PrivilegedClient:
    def __init__(
        self,
        pkexec: str | None = None,
        helper: str | Path | None = None,
    ) -> None:
        self.pkexec = pkexec if pkexec is not None else shutil.which("pkexec")
        if helper is not None:
            self.helper = Path(helper)
        else:
            self.helper = self._find_helper()

    @staticmethod
    def _find_helper() -> Path | None:
        env_path = os.environ.get("TASKMGR_PRIVILEGED_HELPER")
        if env_path:
            path = Path(env_path).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return path
        if HELPER_PATH.is_file() and os.access(HELPER_PATH, os.X_OK):
            return HELPER_PATH
        # A user-writable repository copy must never be run as root via pkexec
        # unless the developer explicitly opts in.
        if os.environ.get("TASKMGR_ALLOW_DEV_HELPER") == "1":
            dev = Path(__file__).with_name("privileged_helper.py")
            if dev.is_file() and os.access(dev, os.X_OK):
                return dev
        return None

    @property
    def available(self) -> bool:
        return bool(self.pkexec and self.helper and self.helper.is_file())

    @property
    def installed_helper(self) -> bool:
        return self.helper == HELPER_PATH

    def status_text(self) -> str:
        if not self.pkexec:
            return "PolicyKit unavailable: pkexec is not installed."
        if not self.helper or not self.helper.is_file():
            return (
                "Privileged helper not installed. Run "
                "~/.config/hypr/scripts/taskmgr/install-privileged.sh once."
            )
        if not self.installed_helper:
            return (
                f"Using a development helper at {self.helper}; install it "
                "root-owned for normal use."
            )
        return f"PolicyKit ready: {self.helper}"

    def _command(self, *args: str) -> list[str]:
        assert self.pkexec is not None and self.helper is not None
        return [self.pkexec, str(self.helper), *args]

    def _run_json(self, *args: str, timeout: float = 30.0):
        if not self.available:
            return None, self.status_text()
        try:
            result = subprocess.run(
                self._command(*args),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None, "PolicyKit authorization timed out."
        except OSError as exc:
            return None, f"Could not run the privileged helper: {exc}"
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return None, (
                f"Privileged helper failed (exit {result.returncode})"
                + (f": {detail[:240]}" if detail else ".")
            )
        try:
            return json.loads(result.stdout), ""
        except ValueError:
            return None, "Privileged helper returned invalid JSON."

    def service_io(
        self, cgroups: list[str], timeout: float = 30.0
    ) -> tuple[dict | None, str]:
        cgroups = [cg for cg in cgroups if cg]
        if not cgroups:
            return {}, ""
        return self._run_json("service-io", *cgroups, timeout=timeout)

    def rapl_watts(self, timeout: float = 30.0) -> tuple[list | None, str]:
        return self._run_json("rapl-watts", timeout=timeout)

    def bpftrace_command(self, probe_key: str) -> list[str] | None:
        if not self.available:
            return None
        return self._command("bpftrace", probe_key)
