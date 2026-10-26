"""Shared helpers for the repo-local document toolkit.

Everything this package creates at runtime lives under ``doc-tools/tmp``.
No helper here writes to the user's home directory.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Iterator, Sequence


ROOT = Path(
    os.environ.get("DOC_TOOLS_ROOT", Path(__file__).resolve().parents[2])
).resolve()
TMP_ROOT = ROOT / "tmp" / "runtime"
CACHE_ROOT = ROOT / "tmp" / "cache"
CONFIG_ROOT = ROOT / "tmp" / "config"
HOME_ROOT = ROOT / "tmp" / "home"
ASSETS = ROOT / "assets"


class ToolError(RuntimeError):
    """A user-facing failure that should be printed without a traceback."""


def ensure_runtime_dirs() -> None:
    for path in (TMP_ROOT, CACHE_ROOT, CONFIG_ROOT, HOME_ROOT):
        path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TMPDIR", str(TMP_ROOT))
    os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_ROOT))
    os.environ.setdefault("XDG_CONFIG_HOME", str(CONFIG_ROOT))


def info(message: str) -> None:
    print(message)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def fail(message: str) -> "NoReturn":
    raise ToolError(message)


def have(command: str) -> bool:
    return shutil.which(command) is not None


def require(command: str, package_hint: str = "") -> str:
    path = shutil.which(command)
    if path:
        return path
    hint = f" Install it with: {package_hint}" if package_hint else ""
    fail(f"required command not found: {command}.{hint}")
    raise AssertionError("unreachable")


def run(
    command: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
    capture: bool = True,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command with a predictable environment."""
    ensure_runtime_dirs()
    child_env = os.environ.copy()
    child_env.update(
        {
            "HOME": str(HOME_ROOT),
            "TMPDIR": str(TMP_ROOT),
            "XDG_CACHE_HOME": str(CACHE_ROOT),
            "XDG_CONFIG_HOME": str(CONFIG_ROOT),
        }
    )
    if env:
        child_env.update(env)

    rendered = [str(part) for part in command]
    try:
        result = subprocess.run(
            rendered,
            cwd=str(cwd) if cwd else None,
            env=child_env,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"command not found: {rendered[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            f"command timed out after {timeout}s: {' '.join(rendered)}"
        ) from exc

    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            detail = f"\n{detail}"
        raise ToolError(
            f"command failed ({result.returncode}): {' '.join(rendered)}{detail}"
        )
    return result


def natural_key(value: str | Path) -> list[object]:
    parts = re.split(r"(\d+)", str(value))
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def temp_target(target: Path) -> Path:
    """Return a sibling temporary path so ``os.replace`` is atomic."""
    ensure_parent(target)
    fd, name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(fd)
    os.chmod(name, 0o644)
    return Path(name)


@contextlib.contextmanager
def staged_file(target: Path) -> Iterator[Path]:
    """Yield a temporary sibling path and atomically move it to ``target``."""
    temp = temp_target(target)
    try:
        yield temp
        if not temp.exists():
            raise ToolError(f"expected output was not created: {target}")
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


@contextlib.contextmanager
def workdir() -> Iterator[Path]:
    ensure_runtime_dirs()
    with tempfile.TemporaryDirectory(prefix="job-", dir=str(TMP_ROOT)) as directory:
        yield Path(directory)


def _range_error(spec: str, total: int) -> ToolError:
    return ToolError(f"invalid page selection {spec!r} for a {total}-page PDF")


def parse_page_ranges(spec: str, total: int) -> list[tuple[int, int]]:
    """Parse ``1-3,5,7-9`` into 1-based inclusive ranges.

    Supported tokens: ``all``, ``odd``, ``even``, ``N``, ``N-M``, ``N-`` and
    ``-M``. Ranges are returned in the order written.
    """
    if not spec or not spec.strip():
        return [(1, total)]

    tokens = [token.strip() for token in spec.split(",") if token.strip()]
    if not tokens:
        return [(1, total)]

    ranges: list[tuple[int, int]] = []
    for token in tokens:
        lowered = token.lower()
        if lowered in {"all", "*"}:
            ranges.append((1, total))
            continue
        if lowered == "odd":
            ranges.extend((page, page) for page in range(1, total + 1, 2))
            continue
        if lowered == "even":
            ranges.extend((page, page) for page in range(2, total + 1, 2))
            continue
        if lowered == "last":
            ranges.append((total, total))
            continue

        match = re.fullmatch(r"(\d*)\s*-\s*(\d*)", token)
        if match:
            first_text, last_text = match.groups()
            if not first_text and not last_text:
                raise _range_error(spec, total)
            first = int(first_text) if first_text else 1
            last = int(last_text) if last_text else total
            if first < 1 or last < 1 or first > total or last > total or first > last:
                raise _range_error(spec, total)
            ranges.append((first, last))
            continue

        if token.isdigit():
            page = int(token)
            if page < 1 or page > total:
                raise _range_error(spec, total)
            ranges.append((page, page))
            continue

        raise _range_error(spec, total)

    return ranges


def expand_pages(spec: str, total: int) -> list[int]:
    pages: list[int] = []
    for first, last in parse_page_ranges(spec, total):
        pages.extend(range(first, last + 1))
    return pages


def validate_pdf(path: Path, password: str | None = None) -> tuple[int, object]:
    """Return ``(page_count, reader)`` after verifying a PDF can be opened."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            if not reader.decrypt(password or ""):
                raise ToolError(f"PDF is encrypted and requires a password: {path}")
        count = len(reader.pages)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"not a readable PDF: {path} ({exc})") from exc
    if count < 1:
        raise ToolError(f"PDF has no pages: {path}")
    return count, reader


def validate_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except Exception as exc:
        raise ToolError(f"not a readable DOCX file: {path} ({exc})") from exc
    if "word/document.xml" not in names:
        raise ToolError(f"DOCX is missing word/document.xml: {path}")


def collect_inputs(
    paths: Iterable[str | os.PathLike[str]],
    *,
    suffix: str,
    recursive: bool = False,
    excluded: Iterable[Path] = (),
) -> list[Path]:
    """Resolve explicit inputs or scan the current directory."""
    excluded_paths = {Path(item).resolve() for item in excluded}
    found: list[Path] = []
    explicit = [Path(item).expanduser() for item in paths]
    wanted = suffix.lower()

    def matches(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == wanted

    if explicit:
        for path in explicit:
            if not path.exists():
                raise ToolError(f"input not found: {path}")
            if path.is_dir():
                iterator = path.rglob("*") if recursive else path.glob("*")
                found.extend(item for item in iterator if matches(item))
            else:
                if path.suffix.lower() != wanted:
                    raise ToolError(f"expected a {suffix} file: {path}")
                if not path.is_file():
                    raise ToolError(f"not a regular file: {path}")
                found.append(path)
    else:
        base = Path.cwd()
        iterator = base.rglob("*") if recursive else base.glob("*")
        found.extend(item for item in iterator if matches(item))

    unique: dict[Path, Path] = {}
    for path in found:
        resolved = path.resolve()
        if resolved in excluded_paths:
            continue
        unique.setdefault(resolved, path)

    ordered = list(unique.values())
    if explicit:
        return ordered
    return sorted(ordered, key=lambda item: natural_key(item.name))


def output_path_for(
    source: Path,
    *,
    out_dir: Path | None,
    suffix: str,
    explicit: Path | None = None,
    prefix: str = "",
    preserve_tree: bool = False,
    base: Path | None = None,
) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    directory = out_dir.expanduser() if out_dir else source.parent
    if preserve_tree and base is not None:
        try:
            relative = source.resolve().relative_to(base.resolve()).parent
        except ValueError:
            relative = Path()
        directory = directory / relative
    return directory / f"{prefix}{source.stem}{suffix}"


def display_name(path: Path, base: Path | None = None) -> str:
    if base is not None:
        try:
            return str(path.resolve().relative_to(base.resolve()))
        except ValueError:
            pass
    return path.name


def is_image(path: Path) -> bool:
    return path.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".tif",
        ".tiff",
        ".bmp",
        ".gif",
    }


def pdf_reader_for(path: Path, password: str | None = None):
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ToolError(f"cannot open PDF: {path} ({exc})") from exc
    if reader.is_encrypted:
        if password is None:
            password = ""
        try:
            result = reader.decrypt(password)
        except Exception as exc:
            raise ToolError(f"cannot decrypt PDF: {path} ({exc})") from exc
        if not result:
            raise ToolError(f"PDF is encrypted and the password is incorrect: {path}")
    return reader
