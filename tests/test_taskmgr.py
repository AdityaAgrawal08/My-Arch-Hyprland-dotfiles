#!/usr/bin/env python3
"""Unit and integration tests for the Hyprland Task Manager & System Explorer."""

from __future__ import annotations

import subprocess
import sys
import time
import unittest
from pathlib import Path

TASKMGR_ROOT = Path(__file__).resolve().parents[1] / "hypr/.config/hypr/scripts/taskmgr"
if str(TASKMGR_ROOT) not in sys.path:
    sys.path.insert(0, str(TASKMGR_ROOT))

from backend.doctor import SystemDoctor
from backend.gpu import GpuCollector, GpuSnapshot, pci_device_name
from backend.hardware import HardwareAndMediaCollector
from backend.performance import PerformanceCollector
from backend.ports import PortsCollector
from backend.power import PowerAndWakeupCollector
from backend.power_profiles import PowerProfileController
from backend.processes import ProcessCollector
from backend.services import ServicesCollector
from backend.verification import run_truth_audit


class TestTaskMgrBackend(unittest.TestCase):
    def test_gpu_snapshot_has_no_fabricated_defaults(self) -> None:
        snap = GpuSnapshot()
        self.assertEqual(snap.name, "No GPU detected")
        self.assertEqual(snap.driver, "-")
        self.assertEqual(snap.engines, {})
        self.assertFalse(snap.freq_available)
        self.assertFalse(snap.rc6_available)

    def test_pci_device_lookup(self) -> None:
        name = pci_device_name("0x8086", "0x46a8")
        self.assertTrue(isinstance(name, str))

    def test_gpu_collector(self) -> None:
        gpu = GpuCollector()
        snaps = gpu.sample()
        self.assertGreaterEqual(len(snaps), 1)
        self.assertIn("3D / Render", snaps[0].engines)

    def test_performance_collector(self) -> None:
        perf = PerformanceCollector()
        data = perf.sample()
        self.assertIn("cpu_total", data)
        self.assertIn("per_core", data)
        self.assertIn("mem", data)
        self.assertIn("battery", data)
        self.assertIn("vault", data)
        self.assertGreater(len(data["per_core"]), 0)

    def test_processes_and_ports_collector(self) -> None:
        ports_coll = PortsCollector()
        ports, pid_ports = ports_coll.sample()
        self.assertIsInstance(ports, list)
        self.assertIsInstance(pid_ports, dict)

        proc_coll = ProcessCollector(GpuCollector())
        flat, grouped = proc_coll.sample(pid_ports=pid_ports)
        self.assertGreater(len(flat), 5)
        self.assertGreater(len(grouped), 2)

        tree = proc_coll.build_tree_order(flat)
        self.assertEqual(len(tree), len(flat))

        details = proc_coll.get_process_details(flat[0]["pid"])
        self.assertEqual(details["pid"], flat[0]["pid"])
        self.assertIsInstance(details["threads"], list)

    def test_services_and_power_and_doctor(self) -> None:
        svcs = ServicesCollector.get_services("system")
        self.assertGreater(len(svcs), 5)

        timers = ServicesCollector.get_timers()
        self.assertGreater(len(timers), 0)

        autostart = ServicesCollector.get_hyprland_autostart_status()
        self.assertGreater(len(autostart), 0)

        pwr = PowerAndWakeupCollector().sample()
        self.assertIn("tunables", pwr)
        self.assertIn("irqs", pwr)
        self.assertIn("cstates_pct", pwr)

        pci, usb = HardwareAndMediaCollector.get_pci_and_usb_devices()
        self.assertGreater(len(pci), 0)
        self.assertGreater(len(usb), 0)

        audit = SystemDoctor.run_full_audit()
        self.assertGreaterEqual(len(audit), 10)

        # Every tunable must point at a real, existing path (or a glob rooted
        # in a real directory). No placeholder policy rows.
        for t in PowerAndWakeupCollector.scan_powertop_tunables():
            if "*" in t["path"]:
                prefix = t["path"].split("*")[0]
                self.assertTrue(Path(prefix).parent.exists(), msg=t["path"])
            else:
                self.assertTrue(Path(t["path"]).exists(), msg=t["path"])

    def test_root_sockets_are_not_guessed(self) -> None:
        rows, _ = PortsCollector().sample()
        for row in rows:
            if row["pid"] == 0:
                self.assertEqual(row["process"], "(owner hidden)")
                self.assertIn("owner hidden", row["purpose"].lower())

    def test_empty_tunable_fix_is_not_reported_as_success(self) -> None:
        ok, msg = PowerAndWakeupCollector.apply_all_bad_tunables([])
        self.assertFalse(ok)
        self.assertIn("No power tunables", msg)

    def test_truth_audit_shape(self) -> None:
        results = run_truth_audit()
        self.assertGreaterEqual(len(results), 10)
        for item in results:
            self.assertIn("check", item)
            self.assertIn("independent_source", item)
            self.assertIn("expected", item)
            self.assertIn("collector_value", item)
            self.assertIn("pass", item)
            self.assertIsInstance(item["pass"], bool)

    def test_app_grouping_does_not_hijack_unrelated_names(self) -> None:
        self.assertEqual(
            ProcessCollector._normalize_app_group("zen", "zen"), "Zen Browser"
        )
        self.assertNotEqual(
            ProcessCollector._normalize_app_group("zenity", "zenity"),
            "Zen Browser",
        )
        self.assertNotEqual(
            ProcessCollector._normalize_app_group("hypridle", "hypridle"),
            "Hyprland Desktop Suite",
        )

    def test_power_profiles_are_real_when_available(self) -> None:
        if not PowerProfileController.is_available():
            self.skipTest("power-profiles-daemon is not available")
        profiles = PowerProfileController.list_profiles()
        self.assertIn("power-saver", profiles)
        self.assertIn("balanced", profiles)
        self.assertIn("performance", profiles)
        self.assertIn(PowerProfileController.get_current(), profiles)

    def test_coredump_line_parser(self) -> None:
        row = HardwareAndMediaCollector._parse_coredump_line(
            "Sat 2026-09-26 11:50:16 IST 692 969 969 SIGABRT missing /usr/bin/sddm-greeter -"
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["time"], "Sat 2026-09-26 11:50:16 IST")
        self.assertIn("PID 692", row["source"])
        self.assertEqual(row["level"], "SIGABRT")
        self.assertIn("/usr/bin/sddm-greeter", row["message"])

    def test_new_process_appears_and_disappears_live(self) -> None:
        proc = subprocess.Popen(
            ["bash", "-c", "exec -a taskmgr_probe_sleeper sleep 30"]
        )
        collector = ProcessCollector(GpuCollector())
        try:
            time.sleep(0.2)
            flat, _ = collector.sample(hide_kernel_threads=False)
            self.assertIn(proc.pid, {p["pid"] for p in flat})
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        time.sleep(0.2)
        flat_after, _ = collector.sample(hide_kernel_threads=False)
        self.assertNotIn(proc.pid, {p["pid"] for p in flat_after})


if __name__ == "__main__":
    unittest.main()
