#!/usr/bin/env python3
"""Launcher toggle, debounce and PID-safety tests."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "local/.local/bin/productivity-dashboard"

FAKE_APP = """\
import os, sys, time
runtime = os.environ['XDG_RUNTIME_DIR']
open(os.path.join(runtime, 'started'), 'w').write('yes')
close = os.path.join(runtime, 'productivity-dashboard.close')
deadline = time.time() + 20
while time.time() < deadline:
    if os.path.exists(close):
        open(os.path.join(runtime, 'closed'), 'w').write('yes')
        break
    time.sleep(0.05)
"""


class LauncherTests(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(LAUNCHER)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_contains_guards(self) -> None:
        text = LAUNCHER.read_text()
        self.assertIn("flock -n 9", text)
        self.assertIn("400", text)  # debounce window
        self.assertIn("STAMPFILE", text)
        self.assertIn("CLOSEFILE", text)
        self.assertIn("9>&-", text)  # child does not inherit the lock
        self.assertIn('grep -qF -- "$APP"', text)

    def test_toggle_debounce_and_close(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dash-launch-") as tmp:
            root = Path(tmp)
            home = root / "home"
            runtime = root / "runtime"
            (home / ".config/hypr/scripts/dashboard").mkdir(parents=True)
            runtime.mkdir()
            (home / ".config/hypr/scripts/dashboard/main.py").write_text(FAKE_APP)

            env = dict(os.environ)
            env.update({"HOME": str(home), "XDG_RUNTIME_DIR": str(runtime)})

            first = subprocess.Popen(
                ["bash", str(LAUNCHER)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.time() + 5
            while time.time() < deadline and not (runtime / "started").exists():
                time.sleep(0.05)
            self.assertTrue((runtime / "started").exists(), "app never started")
            pidfile = runtime / "productivity-dashboard.pid"
            self.assertTrue(pidfile.exists())
            pid = int(pidfile.read_text().strip())
            self.assertTrue(Path(f"/proc/{pid}").exists())

            # Within 400 ms a second click is ignored (debounce).
            subprocess.run(["bash", str(LAUNCHER)], env=env, timeout=5)
            self.assertFalse((runtime / "productivity-dashboard.close").exists())

            time.sleep(0.5)
            subprocess.run(["bash", str(LAUNCHER)], env=env, timeout=5)
            self.assertTrue((runtime / "productivity-dashboard.close").exists())

            try:
                first.wait(timeout=10)
            except subprocess.TimeoutExpired:
                first.kill()
                self.fail("launcher did not exit after close request")
            self.assertTrue((runtime / "closed").exists())


if __name__ == "__main__":
    unittest.main()
