"""Dependency and health checks for the repo-local document toolkit."""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
from pathlib import Path

from .utils import (
    CACHE_ROOT,
    CONFIG_ROOT,
    ROOT,
    TMP_ROOT,
    ensure_runtime_dirs,
    human_size,
    info,
)


PYTHON_MODULES = {
    "pypdf": ("pypdf", True, "PDF page operations"),
    "reportlab": ("reportlab", True, "fallback TOC renderer"),
    "pdf2docx": ("pdf2docx", True, "PDF -> DOCX"),
    "Pillow": ("PIL", True, "images and WebP conversion"),
    "markdown": ("markdown", False, "Markdown -> PDF/DOCX"),
    "weasyprint": ("weasyprint", False, "HTML/Markdown -> PDF and Unicode TOC"),
    "img2pdf": ("img2pdf", False, "images -> PDF"),
    "python-docx": ("docx", False, "DOCX generation helpers"),
    "cryptography": ("cryptography", True, "AES encryption support in pypdf"),
}

SYSTEM_COMMANDS = {
    "libreoffice": ("libreoffice", True, "Office -> PDF/DOCX"),
    "soffice": ("soffice", False, "LibreOffice fallback name"),
    "pdftotext": ("pdftotext", True, "PDF -> text"),
    "pdftoppm": ("pdftoppm", True, "PDF -> images / OCR rendering"),
    "pdftohtml": ("pdftohtml", False, "PDF -> HTML"),
    "pdfimages": ("pdfimages", False, "extract embedded images"),
    "pdfinfo": ("pdfinfo", False, "metadata cross-check"),
    "gs": ("gs", True, "PDF compression"),
    "qpdf": ("qpdf", False, "linearize / repair"),
    "tesseract": ("tesseract", False, "OCR"),
    "pandoc": ("pandoc", False, "optional external converter"),
    "ocrmypdf": ("ocrmypdf", False, "preferred OCR backend"),
}


def _module_status(module_name: str) -> tuple[bool, str]:
    try:
        module = importlib.import_module(module_name)
        version = (
            getattr(module, "__version__", "")
            or getattr(module, "Version", "")
            or getattr(module, "version", "")
        )
        return True, str(version)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def collect() -> dict:
    ensure_runtime_dirs()
    python_rows = []
    for label, (module_name, required, purpose) in PYTHON_MODULES.items():
        ok, version = _module_status(module_name)
        python_rows.append(
            {
                "name": label,
                "ok": ok,
                "required": required,
                "version": version,
                "purpose": purpose,
            }
        )

    command_rows = []
    for label, (command, required, purpose) in SYSTEM_COMMANDS.items():
        path = shutil.which(command)
        command_rows.append(
            {
                "name": label,
                "ok": bool(path),
                "required": required,
                "path": path or "",
                "purpose": purpose,
            }
        )

    writable = {}
    for name, path in {
        "tmp": TMP_ROOT,
        "cache": CACHE_ROOT,
        "config": CONFIG_ROOT,
    }.items():
        probe = path / ".doctor-write-test"
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            writable[name] = True
        except Exception:
            writable[name] = False

    return {
        "root": str(ROOT),
        "source": str(Path(__file__).resolve().parent.parent),
        "python": sys.version.split()[0],
        "venv": sys.executable,
        "python_modules": python_rows,
        "commands": command_rows,
        "writable": writable,
        "disk_free": shutil.disk_usage(ROOT).free,
    }


def _print_rows(rows: list[dict], kind: str) -> None:
    info(f"{kind}:")
    for row in rows:
        if row["ok"]:
            mark = "OK "
            detail = row.get("version") or row.get("path") or ""
        else:
            mark = "MISS"
            detail = "not found"
        required = "required" if row.get("required") else "optional"
        info(
            f"  [{mark}] {row['name']:<14} {required:<8} {detail:<28} {row['purpose']}"
        )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero if any optional dependency is missing.",
    )


def main(args: argparse.Namespace) -> int:
    payload = collect()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        info(f"source root   : {payload['source']}")
        info(f"state root    : {payload['root']}")
        info(f"Python        : {payload['python']}")
        info(f"Interpreter   : {payload['venv']}")
        info(f"Free disk     : {human_size(payload['disk_free'])}")
        info("")
        _print_rows(payload["python_modules"], "Python modules")
        info("")
        _print_rows(payload["commands"], "System commands")
        info("")
        info("Toolkit writable directories:")
        for name, ok in payload["writable"].items():
            info(f"  [{'OK ' if ok else 'MISS'}] {name}")

    required_missing = [
        row["name"]
        for row in payload["python_modules"] + payload["commands"]
        if row.get("required") and not row["ok"]
    ]
    optional_missing = [
        row["name"]
        for row in payload["python_modules"] + payload["commands"]
        if not row.get("required") and not row["ok"]
    ]
    bad_dirs = [name for name, ok in payload["writable"].items() if not ok]

    if bad_dirs:
        info("")
        info(f"ERROR: not writable inside the repo: {', '.join(bad_dirs)}")
    if required_missing:
        info("")
        info(f"ERROR: required dependencies missing: {', '.join(required_missing)}")
        info(f"Run: {ROOT / 'setup.sh'}")
    if optional_missing:
        info("")
        info(f"Optional backends missing: {', '.join(optional_missing)}")

    if bad_dirs or required_missing:
        return 1
    if args.strict and optional_missing:
        return 1
    return 0
