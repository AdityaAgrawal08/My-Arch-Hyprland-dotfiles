#!/usr/bin/env python3
"""Render every autotheme template from a single theme.json document."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def home() -> Path:
    return Path(os.environ.get("HOME", str(Path.home())))


def cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", home() / ".cache")) / "autotheme"


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", home() / ".config"))


def manifest(templates: Path, cache: Path, config: Path) -> list[tuple[Path, Path]]:
    return [
        (templates / "kitty-opaque.conf", cache / "kitty-opaque.conf"),
        (templates / "kitty-transparent.conf", cache / "kitty-transparent.conf"),
        (templates / "waybar.css", cache / "waybar.css"),
        (templates / "wofi.css", cache / "wofi.css"),
        (templates / "wofi-confirm.css", cache / "wofi-confirm.css"),
        (templates / "gtk.css", cache / "gtk.css"),
        (templates / "hyprlock-colors.conf", cache / "hyprlock-colors.conf"),
        (templates / "dunst-colors.conf", config / "dunst/dunstrc.d/autotheme.conf"),
    ]


def render(template: Path, output: Path, values: dict[str, object]) -> None:
    text = template.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"{template.name}: missing theme key {key!r}")
        return str(values[key])

    rendered = PLACEHOLDER.sub(replace, text)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.chmod(temporary, 0o644)
    temporary.replace(output)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--theme", type=Path, required=True, help="canonical theme.json"
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "templates",
        help="template directory",
    )
    args = parser.parse_args(argv)

    try:
        values = json.loads(args.theme.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"render: cannot read theme: {error}", file=sys.stderr)
        return 1

    cache = cache_dir()
    config = config_dir()
    cache.mkdir(parents=True, exist_ok=True)

    try:
        for template, output in manifest(args.templates, cache, config):
            if not template.is_file():
                raise FileNotFoundError(template)
            render(template, output, values)
    except Exception as error:  # noqa: BLE001 - shell wrapper needs a clean failure
        print(f"render: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
