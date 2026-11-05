#!/usr/bin/env python3
"""Unit and integration tests for the Hyprland Task Manager & System Explorer."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TASKMGR_ROOT = Path(__file__).resolve().parents[1] / "hypr/.config/hypr/scripts/taskmgr"
if str(TASKMGR_ROOT) not in sys.path:
    sys.path.insert(0, str(TASKMGR_ROOT))

from backend.alerts import AlertManager
from backend.capabilities import CapabilityCollector
from backend.ebpf import BpftraceRunner, PROBES
from backend.doctor import SystemDoctor
from backend.gpu import GpuCollector, GpuSnapshot, pci_device_name
from backend.hardware_controls import BatteryThresholdControl, FanControl
from backend.hardware import HardwareAndMediaCollector
from backend.performance import PerformanceCollector
from backend.ports import PortsCollector
from backend.power import PowerAndWakeupCollector
from backend.power_profiles import PowerProfileController
from backend.processes import ProcessCollector
from backend.rapl import RaplCollector
from backend.privileged_client import PrivilegedClient
import backend.privileged_helper as privileged_helper
from backend.services import ServicesCollector
from backend.storage_health import (
    StorageHealthCollector,
    _parse_nvme_text,
    _parse_smartctl_json,
)
from backend.verification import run_truth_audit


class TestTaskMgrBackend(unittest.TestCase):
    def test_gpu_snapshot_has_no_fabricated_defaults(self) -> None:
        snap = GpuSnapshot()
        self.assertEqual(snap.name, "No GPU detected")
        self.assertEqual(snap.driver, "-")
        self.assertEqual(snap.engines, {})
        self.assertFalse(snap.freq_available)
        self.assertFalse(snap.rc6_available)
        self.assertEqual(snap.mem_total_mb, 0.0)

    def test_pci_device_lookup(self) -> None:
        name = pci_device_name("0x8086", "0x46a8")
        self.assertTrue(isinstance(name, str))

    def test_nvidia_smi_fallback_parses_aggregate_and_process_memory(self) -> None:
        def fake_check_output(cmd, **_kwargs):
            command = " ".join(str(part) for part in cmd)
            if "--query-gpu=" in command:
                return (
                    "NVIDIA Test GPU, 00000000:01:00.0, "
                    "42, 1024, 8192, 55, 1500\n"
                )
            if "--query-compute-apps=" in command:
                return "1234, 512\n5678, 256\n"
            raise subprocess.CalledProcessError(1, cmd)

        with patch(
            "backend.gpu.shutil.which", return_value="/usr/bin/nvidia-smi"
        ):
            with patch(
                "backend.gpu.subprocess.check_output",
                side_effect=fake_check_output,
            ):
                with patch.object(
                    GpuCollector, "_detect_cards", return_value=[]
                ):
                    collector = GpuCollector()
                    if collector._nvidia_thread is not None:
                        collector._nvidia_thread.join(timeout=5.0)
                    snaps = collector.sample()

        self.assertEqual(len(snaps), 1)
        gpu = snaps[0]
        self.assertEqual(gpu.name, "NVIDIA Test GPU")
        self.assertEqual(gpu.driver, "nvidia")
        self.assertTrue(gpu.busy_available)
        self.assertEqual(gpu.busy_pct, 42.0)
        self.assertEqual(gpu.mem_used_mb, 1024.0)
        self.assertEqual(gpu.mem_total_mb, 8192.0)
        self.assertTrue(gpu.temp_available)
        self.assertEqual(gpu.temp_c, 55.0)
        self.assertTrue(gpu.freq_available)
        self.assertEqual(gpu.freq_mhz, 1500)
        self.assertIn("nvidia-smi", gpu.source)
        self.assertEqual(gpu.clients, 2)
        self.assertEqual(collector.proc_gpu_mem_mb.get(1234), 512.0)
        self.assertEqual(collector.proc_gpu_mem_mb.get(5678), 256.0)

        card = {
            "card": "card1",
            "base": "/sys/class/drm/card1",
            "pdev": "0000:01:00.0",
            "driver": "nvidia",
            "name": "NVIDIA Test GPU",
            "runtime_status": "active",
        }
        with patch(
            "backend.gpu.shutil.which", return_value="/usr/bin/nvidia-smi"
        ):
            with patch(
                "backend.gpu.subprocess.check_output",
                side_effect=fake_check_output,
            ):
                with patch.object(
                    GpuCollector, "_detect_cards", return_value=[card]
                ):
                    matched = GpuCollector()
                    if matched._nvidia_thread is not None:
                        matched._nvidia_thread.join(timeout=5.0)
                    matched_snaps = matched.sample()
        self.assertEqual(len(matched_snaps), 1)
        self.assertEqual(matched_snaps[0].pdev, "0000:01:00.0")
        self.assertIn("nvidia-smi", matched_snaps[0].source)
        self.assertFalse(matched_snaps[0].engines)

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

    def test_privileged_helper_protocol_and_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cgroup_root = root / "cgroup"
            service_cg = cgroup_root / "system.slice" / "test.service"
            service_cg.mkdir(parents=True)
            (service_cg / "cgroup.procs").write_text("111\n")
            proc_root = root / "proc"
            pid_dir = proc_root / "111"
            pid_dir.mkdir(parents=True)
            (pid_dir / "io").write_text(
                "read_bytes: 1048576\nwrite_bytes: 2097152\n"
            )
            result = privileged_helper.service_io(
                ["/system.slice/test.service", "/etc/passwd"],
                cgroup_root=cgroup_root,
                proc_root=proc_root,
            )
            self.assertIn("/system.slice/test.service", result)
            self.assertNotIn("/etc/passwd", result)
            self.assertEqual(result["/system.slice/test.service"]["read"], 1048576)
            self.assertEqual(result["/system.slice/test.service"]["write"], 2097152)

            rapl_root = root / "powercap"
            domain = rapl_root / "intel-rapl:0"
            domain.mkdir(parents=True)
            (domain / "name").write_text("package-0\n")
            (domain / "energy_uj").write_text("1000000\n")
            (domain / "max_energy_range_uj").write_text("100000000\n")

            def fake_sleep(_seconds):
                (domain / "energy_uj").write_text("2000000\n")

            with patch(
                "backend.privileged_helper.time.sleep",
                side_effect=fake_sleep,
            ):
                rows = privileged_helper.rapl_watts(
                    root=rapl_root, sleep_s=2.0
                )
            self.assertEqual(rows[0]["name"], "package-0")
            self.assertEqual(rows[0]["watts"], 0.5)

        with patch(
            "backend.privileged_helper.shutil.which", return_value=None
        ):
            self.assertEqual(privileged_helper.run_bpftrace("execsnoop"), 127)
        self.assertEqual(privileged_helper.run_bpftrace("not-a-probe"), 2)

    def test_privileged_client_protocol_with_fake_pkexec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkexec = root / "pkexec"
            pkexec.write_text(
                "#!/bin/sh\n"
                'case "$2" in\n'
                "  service-io) printf '%s\\n' "
                "'{\"/system.slice/test.service\":{\"read\":1048576,"
                "\"write\":2097152,\"pids\":2,\"readable\":2}}' ;;\n"
                "  rapl-watts) printf '%s\\n' "
                "'[{\"name\":\"package-0\",\"watts\":1.2,"
                "\"reason\":\"\"}]' ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n"
            )
            pkexec.chmod(0o755)
            helper = root / "helper"
            helper.write_text("#!/bin/sh\n")
            helper.chmod(0o755)

            client = PrivilegedClient(pkexec=str(pkexec), helper=helper)
            self.assertTrue(client.available)
            data, error = client.service_io(["/system.slice/test.service"])
            self.assertEqual(error, "")
            self.assertEqual(data["/system.slice/test.service"]["read"], 1048576)

            rows, error = client.rapl_watts()
            self.assertEqual(error, "")
            self.assertEqual(rows[0]["watts"], 1.2)

            command = client.bpftrace_command("execsnoop")
            self.assertEqual(command[0], str(pkexec))
            self.assertEqual(command[1], str(helper))
            self.assertEqual(command[2:], ["bpftrace", "execsnoop"])

        missing = PrivilegedClient(
            pkexec="/tmp/no-such-pkexec", helper="/tmp/no-such-helper"
        )
        self.assertFalse(missing.available)
        data, error = missing.service_io(["/system.slice/test.service"])
        self.assertIsNone(data)
        self.assertIn("not installed", error)

    def test_service_proc_io_fallback_is_honest_about_hidden_pids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cgroup_root = Path(tmp) / "cgroup"
            service_cg = cgroup_root / "test.service"
            service_cg.mkdir(parents=True)
            (service_cg / "cgroup.procs").write_text("111\n222\n")
            proc_root = Path(tmp) / "proc"
            for pid, read_bytes, write_bytes in (
                (111, 100, 20),
                (222, 200, 30),
            ):
                pid_dir = proc_root / str(pid)
                pid_dir.mkdir(parents=True)
                (pid_dir / "io").write_text(
                    f"read_bytes: {read_bytes}\nwrite_bytes: {write_bytes}\n"
                )
            total = ServicesCollector._sum_cgroup_proc_io(
                "test.service", cgroup_root, proc_root
            )
            self.assertEqual(total, (300, 50, "2/2 processes"))

            # One hidden PID makes the sum an undercount, so it must be N/A.
            (proc_root / "222" / "io").unlink()
            self.assertIsNone(
                ServicesCollector._sum_cgroup_proc_io(
                    "test.service", cgroup_root, proc_root
                )
            )

            # A PID that exited and left cgroup.procs is not an undercount.
            (service_cg / "cgroup.procs").write_text("111\n")
            self.assertEqual(
                ServicesCollector._sum_cgroup_proc_io(
                    "test.service", cgroup_root, proc_root
                ),
                (100, 20, "1/1 processes"),
            )

            self.assertEqual(
                ServicesCollector._read_proc_io(111, proc_root), (100, 20)
            )
            self.assertIsNone(
                ServicesCollector._read_proc_io(999, proc_root)
            )

    def test_fan_curve_control_reads_writes_and_restores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hwmon = root / "hwmon0"
            hwmon.mkdir()
            (hwmon / "name").write_text("testfan\n")
            (hwmon / "pwm1").write_text("128\n")
            (hwmon / "pwm1_enable").write_text("2\n")
            (hwmon / "temp1_input").write_text("60000\n")

            control = FanControl(root)
            devices = control.discover()
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["chip"], "testfan")
            self.assertEqual(devices[0]["pwm"], 128)
            self.assertEqual(devices[0]["enable"], 2)
            self.assertTrue(devices[0]["writable"])
            self.assertEqual(
                FanControl.interpolate(
                    [(40, 80), (60, 180), (80, 255)], 50
                ),
                130,
            )
            self.assertEqual(
                FanControl.interpolate([(40, 80), (60, 180)], 30), 80
            )
            self.assertEqual(
                FanControl.interpolate([(40, 80), (60, 180)], 90), 180
            )

            ok, msg = control.apply_curve(
                devices[0], [(40, 80), (60, 180), (80, 255)], temp_c=50
            )
            self.assertTrue(ok, msg)
            self.assertEqual((hwmon / "pwm1").read_text().strip(), "130")
            self.assertEqual(
                (hwmon / "pwm1_enable").read_text().strip(), "1"
            )

            ok, msg = control.restore_auto(devices[0])
            self.assertTrue(ok, msg)
            self.assertEqual(
                (hwmon / "pwm1_enable").read_text().strip(), "2"
            )

        empty = FanControl("/tmp/no-such-hwmon-root")
        self.assertEqual(empty.discover(), [])
        ok, msg = empty.apply_curve({"pwm_path": "/tmp/no-such-pwm"}, [(40, 80)])
        self.assertFalse(ok)
        self.assertIn("disappeared", msg)

    def test_battery_charge_threshold_control_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            battery = root / "BAT0"
            battery.mkdir()
            start = battery / "charge_control_start_threshold"
            end = battery / "charge_control_end_threshold"
            start.write_text("0\n")
            end.write_text("80\n")

            control = BatteryThresholdControl(root)
            devices = control.discover()
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["start"], 0)
            self.assertEqual(devices[0]["end"], 80)
            self.assertTrue(devices[0]["writable"])

            ok, msg = control.apply(devices[0], 20, 80)
            self.assertTrue(ok, msg)
            self.assertEqual(start.read_text().strip(), "20")
            self.assertEqual(end.read_text().strip(), "80")

            for bad_start, bad_end in ((80, 80), (90, 80), (-1, 80), (0, 101)):
                valid, _ = BatteryThresholdControl.validate(bad_start, bad_end)
                self.assertFalse(valid, (bad_start, bad_end))
            valid, _ = BatteryThresholdControl.validate(20, 80)
            self.assertTrue(valid)

        empty = BatteryThresholdControl("/tmp/no-such-power-supply-root")
        self.assertEqual(empty.discover(), [])
        ok, msg = empty.apply(
            {"id": "BAT0", "end_path": "/tmp/no-such-end"}, 20, 80
        )
        self.assertFalse(ok)
        self.assertIn("no charge_control_end_threshold", msg)

    def test_rapl_energy_math_and_permission_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            domain = root / "intel-rapl:0"
            domain.mkdir()
            (domain / "name").write_text("package-0\n")
            (domain / "max_energy_range_uj").write_text("100000000\n")
            (domain / "energy_uj").write_text("1000000\n")
            collector = RaplCollector(root)
            first = collector.sample(now=100.0)
            self.assertTrue(first["available"])
            self.assertIsNone(first["domains"][0]["watts"])
            (domain / "energy_uj").write_text("2000000\n")
            second = collector.sample(now=102.0)
            self.assertEqual(second["domains"][0]["watts"], 0.5)

            (domain / "energy_uj").chmod(0)
            blocked = RaplCollector(root).sample(now=103.0)
            self.assertFalse(blocked["available"])
            self.assertIn("not readable", blocked["reason"])
            (domain / "energy_uj").chmod(0o644)

        empty = RaplCollector("/tmp/no-such-rapl-root").sample()
        self.assertFalse(empty["available"])

    def test_ebpf_runner_is_gated_and_streams_output(self) -> None:
        runner = BpftraceRunner()
        self.assertEqual(len(PROBES), 4)
        self.assertTrue(any(p.key == "execsnoop" for p in PROBES))
        self.assertIn("sudo bpftrace", PROBES[0].command())

        with patch("backend.ebpf.shutil.which", return_value=None):
            ok, msg = runner.start("execsnoop", lambda line: None)
            self.assertFalse(ok)
            self.assertIn("not installed", msg)

        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "bpftrace"
            fake.write_text(
                "#!/bin/sh\n"
                "echo 'Attaching 1 probe...'\n"
                "echo 'execsnoop  /usr/bin/test'\n"
                "sleep 0.1\n"
                "echo 'execsnoop  /usr/bin/test2'\n"
            )
            fake.chmod(0o755)
            env_path = tmp + ":" + os.environ.get("PATH", "")
            with patch.dict(os.environ, {"PATH": env_path}):
                with patch("backend.ebpf.os.geteuid", return_value=1000):
                    ok, msg = runner.start("execsnoop", lambda line: None)
                    self.assertFalse(ok)
                    self.assertIn("root is required", msg)

                    lines: list[str] = []
                    exits: list[int] = []
                    ok, msg = runner.start(
                        "execsnoop",
                        lines.append,
                        exits.append,
                        allow_nonroot=True,
                    )
                    self.assertTrue(ok, msg)
                    if runner._thread is not None:
                        runner._thread.join(timeout=5.0)
                    self.assertTrue(any("execsnoop" in line for line in lines), lines)
                    self.assertEqual(exits, [0])

    def test_storage_health_parser_and_missing_tools(self) -> None:
        parsed = _parse_smartctl_json(
            """{
              "smart_status": {"passed": true},
              "temperature": {"current": 35},
              "power_on_time": {"hours": 123},
              "nvme_smart_health_information_log": {"percentage_used": 2},
              "smartctl": {"messages": []}
            }"""
        )
        self.assertEqual(parsed["health"], "PASSED")
        self.assertEqual(parsed["temperature"], "35 °C")
        self.assertEqual(parsed["power_on_hours"], "123 h")
        self.assertEqual(parsed["percentage_used"], "2 %")

        with patch(
            "backend.storage_health.shutil.which", return_value=None
        ):
            rows = StorageHealthCollector.sample(
                [
                    {
                        "type": "disk",
                        "name": "nvme0n1",
                        "model": "TestDisk",
                        "size": "1T",
                    }
                ]
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["health"], "N/A")
        self.assertIn("not installed", rows[0]["note"])

        nvme_ok = _parse_nvme_text(
            "critical_warning : 0\ntemperature : 40 °C\n"
            "percentage_used : 3 %\npower_on_hours : 99\n"
        )
        self.assertEqual(nvme_ok["health"], "PASSED")
        nvme_warn = _parse_nvme_text("critical_warning : 0x4\n")
        self.assertEqual(nvme_warn["health"], "WARNING")

    def test_optional_capabilities_are_explicit(self) -> None:
        rows = CapabilityCollector.get_capabilities()
        self.assertGreaterEqual(len(rows), 5)
        for row in rows:
            self.assertIn(row["status"], ("Available", "Unavailable", "Partial"))
            self.assertTrue(row["feature"])
            self.assertTrue(row["details"])
            self.assertTrue(row["command"])

    def test_alert_manager_thresholds_and_cooldowns(self) -> None:
        manager = AlertManager()
        manager.enabled = True
        perf = {
            "battery": {
                "present": True,
                "status": "Discharging",
                "watts": 25.0,
                "percent": 15,
                "remaining_str": "30m left",
            },
            "cpu_temp": 95.0,
            "mem": SimpleNamespace(percent=95.0, used=1, total=1),
            "psi": {
                "memory": {"some_avg10": 12.0},
                "io": {"some_avg10": 25.0},
            },
        }
        with patch.object(AlertManager, "_notify") as notify:
            manager.check_perf(perf)
            first = notify.call_count
            self.assertGreaterEqual(first, 4)
            manager.check_perf(perf)
            self.assertEqual(notify.call_count, first)

        with patch.object(AlertManager, "_notify") as notify:
            manager.check_ports([{"is_listening": True, "proto": "TCP", "port": 12345}])
            self.assertEqual(notify.call_count, 0)
            manager.check_ports(
                [
                    {"is_listening": True, "proto": "TCP", "port": 12345},
                    {"is_listening": True, "proto": "TCP", "port": 23456},
                ]
            )
            self.assertEqual(notify.call_count, 1)

        with patch.object(AlertManager, "_notify") as notify:
            manager.check_doctor(
                [
                    {
                        "status": "NOT WORKING",
                        "component": "Test Service",
                        "summary": "failed",
                    }
                ]
            )
            self.assertEqual(notify.call_count, 1)

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
