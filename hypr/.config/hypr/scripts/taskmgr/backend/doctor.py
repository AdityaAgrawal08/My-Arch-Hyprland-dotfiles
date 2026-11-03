#!/usr/bin/env python3
"""System Doctor ("Working vs. Not Working") Comprehensive Audit & Remediation Engine."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
import psutil

from .power import PowerAndWakeupCollector
from .services import autostart_key


class SystemDoctor:
    """Audits every layer of the Arch Linux + Hyprland laptop and provides one-click fixes."""

    @staticmethod
    def run_full_audit() -> list[dict]:
        checks: list[dict] = []
        home = Path.home()

        # 1. Systemd Failed System Units
        try:
            out = subprocess.check_output(
                ["systemctl", "--failed", "--no-pager", "--output=json"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            failed_sys = json.loads(out) if out.strip() else []
            if not failed_sys:
                checks.append(
                    {
                        "status": "WORKING",
                        "category": "Systemd (System)",
                        "component": "System Services",
                        "summary": "0 failed system units",
                        "details": "No unit is currently in the failed state.",
                        "fix_id": "",
                        "fix_label": "",
                    }
                )
            else:
                names = ", ".join(u.get("unit", "?") for u in failed_sys)
                checks.append(
                    {
                        "status": "NOT WORKING",
                        "category": "Systemd (System)",
                        "component": "Failed System Services",
                        "summary": f"{len(failed_sys)} failed unit(s): {names}",
                        "details": "Run systemctl reset-failed or inspect Logs tab.",
                        "fix_id": "reset_failed_system",
                        "fix_label": "Reset Failed Units",
                    }
                )
        except Exception as exc:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Systemd (System)",
                    "component": "System Services",
                    "summary": "Could not query systemd",
                    "details": f"systemctl --failed failed: {exc}",
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        # 2. Systemd Failed User Units
        try:
            out = subprocess.check_output(
                ["systemctl", "--user", "--failed", "--no-pager", "--output=json"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            failed_usr = json.loads(out) if out.strip() else []
            if not failed_usr:
                checks.append(
                    {
                        "status": "WORKING",
                        "category": "Systemd (User)",
                        "component": "User Session Services",
                        "summary": "0 failed user units",
                        "details": "No user unit is in the failed state (this is not a liveness check for every daemon).",
                        "fix_id": "",
                        "fix_label": "",
                    }
                )
            else:
                names = ", ".join(u.get("unit", "?") for u in failed_usr)
                checks.append(
                    {
                        "status": "NOT WORKING",
                        "category": "Systemd (User)",
                        "component": "Failed User Services",
                        "summary": f"{len(failed_usr)} failed unit(s): {names}",
                        "details": "User session systemd unit failed.",
                        "fix_id": "reset_failed_user",
                        "fix_label": "Reset User Units",
                    }
                )
        except Exception as exc:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Systemd (User)",
                    "component": "User Session Services",
                    "summary": "Could not query the user systemd manager",
                    "details": f"systemctl --user --failed failed: {exc}",
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        # 3. Hypridle Idle/Lock Daemon
        hypridle_running = any(
            (p.info.get("name") or "") == "hypridle"
            for p in psutil.process_iter(["name"])
        )
        if hypridle_running:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Hyprland Session",
                    "component": "Hypridle (Idle & Lid Lock)",
                    "summary": "hypridle daemon is running",
                    "details": "Automatic lid-close lock and DPMS wakeup hooks are active.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Hyprland Session",
                    "component": "Hypridle (Idle & Lid Lock)",
                    "summary": "hypridle is NOT running",
                    "details": "hypridle.conf is configured, but hypridle is not running in this session.",
                    "fix_id": "start_hypridle",
                    "fix_label": "Start hypridle Now",
                }
            )

        # 4. Autotheme Engine & Wallpaper Daemon
        theme_json = home / ".cache/autotheme/theme.json"
        awww_running = any(
            (p.info.get("name") or "") in ("awww-daemon", "hyprpaper")
            for p in psutil.process_iter(["name"])
        )
        if theme_json.is_file() and awww_running:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Dotfiles / Autotheme",
                    "component": "Wallpaper & Material You Engine",
                    "summary": "theme.json present & wallpaper daemon active",
                    "details": f"Active palette: {theme_json}",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "NOT WORKING",
                    "category": "Dotfiles / Autotheme",
                    "component": "Wallpaper & Material You Engine",
                    "summary": "Wallpaper daemon or theme.json missing",
                    "details": "Run wallpaper_switch.sh restore to start awww-daemon and render surfaces.",
                    "fix_id": "restore_autotheme",
                    "fix_label": "Restore Autotheme",
                }
            )

        # 5. CAS Trash System & User Timers
        trash_db = home / ".local/share/trash-system/db/trash.db"
        try:
            t_out = subprocess.check_output(
                ["systemctl", "--user", "list-timers", "--no-pager", "--output=json"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            active_timers = [
                t.get("unit", "") for t in (json.loads(t_out) if t_out.strip() else [])
            ]
        except Exception:
            active_timers = []
        trash_required = (
            "trash-age.timer",
            "trash-clean.timer",
            "trash-notify.timer",
        )
        missing_trash_timers = [t for t in trash_required if t not in active_timers]
        if trash_db.is_file() and not missing_trash_timers:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Dotfiles / Trash CAS",
                    "component": "CAS Trash DB & Cleanup Timers",
                    "summary": "trash.db initialized & all 3 user timers active",
                    "details": f"Active user timers: {', '.join(active_timers)}",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Dotfiles / Trash CAS",
                    "component": "CAS Trash DB & Cleanup Timers",
                    "summary": (
                        f"DB {'present' if trash_db.is_file() else 'missing'}; "
                        f"active trash timers {len(trash_required) - len(missing_trash_timers)}/3"
                        + (
                            f"; missing: {', '.join(missing_trash_timers)}"
                            if missing_trash_timers
                            else ""
                        )
                    ),
                    "details": "Enable the missing timers with systemctl --user enable --now.",
                    "fix_id": "enable_trash_timers",
                    "fix_label": "Init DB & Enable Timers",
                }
            )

        # 6. Document & PDF Toolkit (doctools venv + wrappers)
        doc_venv = home / ".local/share/doctools/venv/bin/python"
        doc_bin = home / ".local/bin/doc"
        pdfmerge_bin = home / ".local/bin/pdfmerge"
        missing_doc = [
            str(p) for p in (doc_venv, doc_bin, pdfmerge_bin) if not p.exists()
        ]
        if not missing_doc:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Dotfiles / DocTools",
                    "component": "PDF & Document Suite (doctools)",
                    "summary": "Python venv and CLI wrappers present",
                    "details": f"venv: {doc_venv}; wrappers: {doc_bin}, {pdfmerge_bin}",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "NOT WORKING",
                    "category": "Dotfiles / DocTools",
                    "component": "PDF & Document Suite (doctools)",
                    "summary": f"{len(missing_doc)} required doctools path(s) missing",
                    "details": ", ".join(missing_doc),
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        # 7. Bluetooth RFKill vs Blueman Applet
        blueman_pids = [
            p.info["pid"]
            for p in psutil.process_iter(["pid", "name"])
            if "blueman" in (p.info.get("name") or "")
        ]
        bt_soft_blocked = False
        try:
            rf = json.loads(
                subprocess.check_output(
                    ["rfkill", "-J"], text=True, stderr=subprocess.DEVNULL, timeout=1.5
                )
            )
            for dev in rf.get("rfkilldevices", []):
                if dev.get("type") == "bluetooth" and dev.get("soft") == "blocked":
                    bt_soft_blocked = True
        except Exception:
            pass
        if bt_soft_blocked and blueman_pids:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Hardware / Radio",
                    "component": "Bluetooth Adapter",
                    "summary": "Bluetooth is soft-blocked while blueman-applet is running",
                    "details": "Either unblock Bluetooth to use it, or stop blueman-applet to save battery wakeups.",
                    "fix_id": "unblock_bluetooth",
                    "fix_label": "Unblock Bluetooth",
                }
            )
        else:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Hardware / Radio",
                    "component": "Bluetooth Adapter",
                    "summary": "Soft-blocked (Off)"
                    if bt_soft_blocked
                    else "Unblocked & Ready",
                    "details": "rfkill and blueman-applet state were checked; no contradictory block/tray state detected.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        # 7b. PolicyKit authentication agent
        polkit_agent_names = (
            "hyprpolkitagent",
            "polkit-gnome-authentication-agent-1",
            "polkit-kde-authentication-agent-1",
            "lxpolkit",
            "mate-polkit",
            "xfce-polkit",
        )
        polkit_pids = [
            p.info["pid"]
            for p in psutil.process_iter(["pid", "name"])
            if (p.info.get("name") or "") in polkit_agent_names
        ]
        polkit_service_active = False
        try:
            polkit_service_active = (
                subprocess.run(
                    ["systemctl", "--user", "is-active", "hyprpolkitagent.service"],
                    text=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.5,
                ).returncode
                == 0
            )
        except Exception:
            pass
        if polkit_pids or polkit_service_active:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Hardware / PolicyKit",
                    "component": "PolicyKit Authentication Agent",
                    "summary": "A PolicyKit agent is running",
                    "details": (
                        f"Process PID(s): {', '.join(map(str, polkit_pids))}"
                        if polkit_pids
                        else "hyprpolkitagent.service is active"
                    ),
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Hardware / PolicyKit",
                    "component": "PolicyKit Authentication Agent",
                    "summary": "No PolicyKit authentication agent is running",
                    "details": "Privileged GUI actions cannot prompt for a password.",
                    "fix_id": "start_hyprpolkitagent",
                    "fix_label": "Start hyprpolkitagent",
                }
            )

        # 8. Hyprland VFR (Variable Frame Rate) Battery Setting (debug:vfr in Hyprland 0.56)
        vfr_enabled = False
        vfr_query_ok = False
        try:
            vfr_out = subprocess.check_output(
                ["hyprctl", "getoption", "debug:vfr", "-j"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.5,
            )
            vfr_data = json.loads(vfr_out)
            vfr_enabled = bool(
                vfr_data.get("bool") is True or vfr_data.get("int", 0) == 1
            )
            vfr_query_ok = True
        except Exception:
            pass
        if not vfr_query_ok:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Power / Compositor",
                    "component": "Hyprland Variable Frame Rate (debug:vfr)",
                    "summary": "Could not query the live Hyprland session",
                    "details": "hyprctl getoption debug:vfr failed; VFR state is unknown.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        elif vfr_enabled:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Power / Compositor",
                    "component": "Hyprland Variable Frame Rate (debug:vfr)",
                    "summary": "VFR is enabled (saves GPU frame-commit wakeups)",
                    "details": "Hyprland skips frame commits when screen is static.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Power / Compositor",
                    "component": "Hyprland Variable Frame Rate (debug:vfr)",
                    "summary": "debug:vfr is disabled (causes continuous GPU frame commits)",
                    "details": "Enabling VFR cuts compositor/GPU frame-commit wakeups.",
                    "fix_id": "enable_hypr_vfr",
                    "fix_label": "Enable VFR Now",
                }
            )

        # 9. PowerTOP Kernel & PCI Tunables
        tunables = PowerAndWakeupCollector.scan_powertop_tunables()
        bad_tunables = [t for t in tunables if t["status"] == "BAD"]
        if not bad_tunables:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Power / Kernel Tunables",
                    "component": "PCI, NVMe, Wi-Fi & Kernel Power Saving",
                    "summary": "All kernel power tunables are in GOOD state",
                    "details": f"{len(tunables)} tunables verified.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            sample_names = ", ".join(t["name"] for t in bad_tunables[:3])
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Power / Kernel Tunables",
                    "component": "PowerTOP Kernel & PCI Tunables",
                    "summary": f"{len(bad_tunables)} tunable(s) in BAD state ({sample_names}...)",
                    "details": "Network and NVMe devices may have Runtime PM disabled.",
                    "fix_id": "tune_all_power",
                    "fix_label": "Optimize All Tunables",
                }
            )

        # 10. Background Services Drain Check (warp-svc / valkey)
        bg_drainers = []
        for p in psutil.process_iter(["name", "pid"]):
            nm = (p.info.get("name") or "").lower()
            if nm in ("warp-svc", "valkey-server", "redis-server"):
                bg_drainers.append(f"{nm} (PID {p.info['pid']})")
        if bg_drainers:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Power / Background Daemons",
                    "component": "Always-On Background Services",
                    "summary": f"Active background daemons: {', '.join(bg_drainers)}",
                    "details": "These daemons keep sockets and wakeup sources active; inspect the Power page for their live interrupt/context-switch impact.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Power / Background Daemons",
                    "component": "Always-On Background Services",
                    "summary": "warp-svc / valkey are not running",
                    "details": "Neither background daemon was found in the live process scan.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        # 11. Encrypted Vault (~/.important)
        vault_mnt = home / ".important"
        vault_enc = home / ".important.encrypted"
        mounted = False
        try:
            with open("/proc/mounts", "r", encoding="utf-8") as f:
                mounted = any(
                    line.split()[1] == str(vault_mnt)
                    for line in f
                    if len(line.split()) >= 2
                )
        except OSError:
            pass
        if not vault_mnt.is_dir() and not vault_enc.is_dir():
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Security / Vault",
                    "component": "Encrypted Vault (~/.important)",
                    "summary": "Not configured (no ~/.important.encrypted found)",
                    "details": "The Fish cd wrapper has nothing to unlock on this machine.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "WARNING" if mounted else "WORKING",
                    "category": "Security / Vault",
                    "component": "Encrypted Vault (~/.important)",
                    "summary": "Vault is currently UNLOCKED & MOUNTED"
                    if mounted
                    else "Vault is safely LOCKED (unmounted)",
                    "details": "Auto-unlocked by Fish cd wrapper when entering ~/.important.",
                    "fix_id": "lock_vault" if mounted else "",
                    "fix_label": "Lock Vault Now" if mounted else "",
                }
            )

        # 12. Kernel / ACPI Boot Errors
        try:
            err_out = subprocess.check_output(
                ["journalctl", "-b", "-p", "0..3", "--no-pager", "-q"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            err_lines = [l for l in err_out.splitlines() if l.strip()]
            if not err_lines:
                checks.append(
                    {
                        "status": "WORKING",
                        "category": "Kernel / Journal",
                        "component": "Boot Error Log (journalctl -p 0..3)",
                        "summary": "0 critical/error messages this boot",
                        "details": "Clean boot journal.",
                        "fix_id": "",
                        "fix_label": "",
                    }
                )
            else:
                checks.append(
                    {
                        "status": "WARNING",
                        "category": "Kernel / Journal",
                        "component": "Boot Error Log (journalctl -p 0..3)",
                        "summary": f"{len(err_lines)} priority 0..3 entries logged this boot (see Logs & Crashes tab)",
                        "details": err_lines[-1][:140],
                        "fix_id": "",
                        "fix_label": "",
                    }
                )
        except Exception as exc:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Kernel / Journal",
                    "component": "Boot Error Log (journalctl -p 0..3)",
                    "summary": "Could not read the boot journal",
                    "details": str(exc),
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        # 13. Duplicate autostart entries in hyprland.lua
        hypr_lua = home / ".config/hypr/hyprland.lua"
        if hypr_lua.is_file():
            try:
                txt = hypr_lua.read_text(encoding="utf-8", errors="replace")
                start = txt.find('hl.on("hyprland.start"')
                end = txt.find('hl.on("config.reloaded"', start + 1)
                block = txt[start:end] if start >= 0 and end > start else txt
                cmds = re.findall(r'hl\.exec_cmd\(\s*"([^"]+)"\s*\)', block)
                normalized: dict[str, list[str]] = {}
                for c in cmds:
                    key = autostart_key(c)
                    if key:
                        normalized.setdefault(key, []).append(c)
                dups = {k: v for k, v in normalized.items() if len(v) > 1}
                if dups:
                    desc = "; ".join(f"{k} x{len(v)}" for k, v in dups.items())
                    checks.append(
                        {
                            "status": "WARNING",
                            "category": "Hyprland Session",
                            "component": "Duplicate hyprland.lua Autostart",
                            "summary": f"Duplicate autostart entries: {desc}",
                            "details": "The same program is launched more than once in hl.on('hyprland.start').",
                            "fix_id": "",
                            "fix_label": "",
                        }
                    )
                else:
                    checks.append(
                        {
                            "status": "WORKING",
                            "category": "Hyprland Session",
                            "component": "Duplicate hyprland.lua Autostart",
                            "summary": "No duplicate autostart targets",
                            "details": f"Parsed {len(cmds)} hl.exec_cmd entries.",
                            "fix_id": "",
                            "fix_label": "",
                        }
                    )
            except OSError:
                pass
        else:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Hyprland Session",
                    "component": "Hyprland Autostart Config",
                    "summary": "hyprland.lua not found",
                    "details": f"Expected {hypr_lua}",
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        # 14. Waybar module scripts referenced but missing
        waybar_cfg = home / ".config/waybar/config.jsonc"
        if waybar_cfg.is_file():
            try:
                cfg = waybar_cfg.read_text(encoding="utf-8", errors="replace")
                missing = []
                for match in re.finditer(r'\$HOME/([^"\s]+)', cfg):
                    path = home / match.group(1)
                    if "$" not in match.group(1) and not path.exists():
                        missing.append(str(path))
                if missing:
                    checks.append(
                        {
                            "status": "WARNING",
                            "category": "Dotfiles / Waybar",
                            "component": "Waybar Module Scripts",
                            "summary": f"{len(missing)} referenced script(s) missing",
                            "details": ", ".join(missing),
                            "fix_id": "",
                            "fix_label": "",
                        }
                    )
                else:
                    checks.append(
                        {
                            "status": "WORKING",
                            "category": "Dotfiles / Waybar",
                            "component": "Waybar Module Scripts",
                            "summary": "All referenced $HOME scripts exist",
                            "details": "Only literal $HOME references in the Waybar config were checked.",
                            "fix_id": "",
                            "fix_label": "",
                        }
                    )
            except OSError:
                pass
        else:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Dotfiles / Waybar",
                    "component": "Waybar Module Scripts",
                    "summary": "Waybar config not found",
                    "details": f"Expected {waybar_cfg}",
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        # 15. Conflicting wallpaper daemons
        wall_names = {(p.info.get("name") or "") for p in psutil.process_iter(["name"])}
        if "awww-daemon" in wall_names and "hyprpaper" in wall_names:
            checks.append(
                {
                    "status": "WARNING",
                    "category": "Dotfiles / Autotheme",
                    "component": "Wallpaper Daemons",
                    "summary": "Both awww-daemon and hyprpaper are running",
                    "details": "They draw two wallpaper layers; stop one to avoid GPU wakeups.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )
        else:
            checks.append(
                {
                    "status": "WORKING",
                    "category": "Dotfiles / Autotheme",
                    "component": "Wallpaper Daemons",
                    "summary": "No conflicting wallpaper daemons",
                    "details": "At most one of awww-daemon / hyprpaper is running.",
                    "fix_id": "",
                    "fix_label": "",
                }
            )

        return checks

    @staticmethod
    def execute_fix(fix_id: str) -> tuple[bool, str]:
        home = Path.home()
        try:
            if fix_id == "reset_failed_system":
                subprocess.Popen(["pkexec", "systemctl", "reset-failed"])
                return True, "Resetting failed system units..."
            if fix_id == "reset_failed_user":
                subprocess.Popen(["systemctl", "--user", "reset-failed"])
                return True, "Reset failed user units."
            if fix_id == "start_hypridle":
                subprocess.Popen(["hypridle"], start_new_session=True)
                return True, "Started hypridle daemon."
            if fix_id == "start_hyprpolkitagent":
                subprocess.Popen(
                    ["systemctl", "--user", "start", "hyprpolkitagent.service"]
                )
                return True, "Started hyprpolkitagent.service."
            if fix_id == "restore_autotheme":
                script = home / ".config/hypr/scripts/wallpaper_switch.sh"
                subprocess.Popen([str(script), "restore"])
                return True, "Restoring wallpaper and autotheme surfaces..."
            if fix_id == "enable_trash_timers":
                init_script = home / "dotfiles/trash/scripts/init-db.sh"
                if init_script.is_file():
                    subprocess.run(["bash", str(init_script)], check=False)
                subprocess.Popen(
                    [
                        "systemctl",
                        "--user",
                        "enable",
                        "--now",
                        "trash-age.timer",
                        "trash-clean.timer",
                        "trash-notify.timer",
                    ]
                )
                return True, "Initialized trash.db and enabled user trash timers."
            if fix_id == "unblock_bluetooth":
                subprocess.Popen(["rfkill", "unblock", "bluetooth"])
                return True, "Unblocked Bluetooth adapter."
            if fix_id == "enable_hypr_vfr":
                subprocess.Popen(
                    ["hyprctl", "eval", "hl.config({ debug = { vfr = true } })"]
                )
                return True, "Enabled Hyprland Variable Frame Rate (debug.vfr = true)."
            if fix_id == "tune_all_power":
                tunables = PowerAndWakeupCollector.scan_powertop_tunables()
                return PowerAndWakeupCollector.apply_all_bad_tunables(tunables)
            if fix_id == "lock_vault":
                subprocess.Popen(["fusermount3", "-u", "--", str(home / ".important")])
                return True, "Unmounted and locked ~/.important."
        except OSError as exc:
            return False, str(exc)
        return False, f"Unknown fix action: {fix_id}"
