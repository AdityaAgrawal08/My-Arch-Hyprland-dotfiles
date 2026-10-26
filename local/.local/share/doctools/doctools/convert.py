"""Document conversion commands: Office, Markdown, DOCX and generic doc2pdf."""

from __future__ import annotations

import argparse
import html
import os
import shutil
import sys
from pathlib import Path

from .utils import (
    ToolError,
    ensure_parent,
    fail,
    have,
    human_size,
    info,
    run,
    temp_target,
    validate_docx,
    validate_pdf,
    warn,
    workdir,
)


OFFICE_SUFFIXES = {
    ".doc",
    ".docx",
    ".odt",
    ".rtf",
    ".txt",
    ".html",
    ".htm",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".csv",
    ".odp",
    ".ods",
}
MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".txt"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif"}


def _libreoffice() -> str:
    if have("libreoffice"):
        return "libreoffice"
    if have("soffice"):
        return "soffice"
    fail("LibreOffice is not installed. Install libreoffice-fresh.")
    raise AssertionError("unreachable")


def _expand_inputs(raw: list[str], recursive: bool) -> list[Path]:
    paths: list[Path] = []
    for item in raw:
        path = Path(item).expanduser()
        if not path.exists():
            fail(f"input not found: {path}")
        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            paths.extend(child for child in iterator if child.is_file())
        else:
            paths.append(path)
    if not paths:
        fail("no input files found")
    return paths


def _target_path(
    source: Path,
    *,
    explicit: str | None,
    out_dir: str | None,
    suffix: str,
    multi: bool,
    preserve_tree: bool = False,
    base: Path | None = None,
) -> Path:
    if explicit:
        target = Path(explicit).expanduser()
        if multi:
            if target.suffix and not target.is_dir():
                fail("--output must be a directory when converting multiple files")
            target.mkdir(parents=True, exist_ok=True)
            return target / f"{source.stem}{suffix}"
        if target.suffix == "" or target.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            return target / f"{source.stem}{suffix}"
        return target
    directory = Path(out_dir).expanduser() if out_dir else source.parent
    if preserve_tree and base is not None:
        try:
            relative = source.resolve().relative_to(base.resolve()).parent
        except ValueError:
            relative = Path()
        directory = directory / relative
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{source.stem}{suffix}"


def _check_clobber(path: Path, no_clobber: bool) -> None:
    if no_clobber and path.exists():
        fail(f"refusing to overwrite existing file: {path}")


def libreoffice_convert(
    source: Path,
    target: Path,
    target_extension: str,
    *,
    timeout: int = 300,
) -> Path:
    """Convert with an isolated LibreOffice profile; never write to the CWD."""
    lo = _libreoffice()
    source = source.resolve()
    target = target.expanduser()
    ensure_parent(target)

    with workdir() as job:
        profile = job / "lo-profile"
        outdir = job / "out"
        outdir.mkdir()
        command = [
            lo,
            "--headless",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            target_extension,
            "--outdir",
            str(outdir),
            str(source),
        ]
        try:
            run(command, timeout=timeout)
        except ToolError:
            # Older LibreOffice builds reject file:// profile URIs expressed
            # without an explicit localhost. Retry once without the profile.
            command = [
                lo,
                "--headless",
                "--convert-to",
                target_extension,
                "--outdir",
                str(outdir),
                str(source),
            ]
            run(command, timeout=timeout)

        generated = outdir / f"{source.stem}.{target_extension.split(':')[0]}"
        if not generated.exists():
            candidates = [
                item
                for item in outdir.iterdir()
                if item.is_file() and item.stem == source.stem
            ]
            if not candidates:
                raise ToolError(
                    f"LibreOffice did not produce {generated.name} for {source.name}"
                )
            generated = candidates[0]

        temp = temp_target(target)
        try:
            shutil.copy2(generated, temp)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    return target


def _markdown_html(
    source: Path, *, title: str | None, toc: bool, css: str | None
) -> str:
    import markdown

    text = source.read_text(encoding="utf-8", errors="replace")
    extensions = ["extra", "sane_lists", "fenced_code", "tables", "footnotes"]
    if toc:
        extensions.append("toc")
    body = markdown.markdown(text, extensions=extensions, output_format="html5")
    heading = html.escape(title or source.stem)
    extra_css = ""
    if css:
        css_path = Path(css).expanduser()
        if not css_path.exists():
            fail(f"CSS file not found: {css_path}")
        extra_css = f"<style>{css_path.read_text(encoding='utf-8')}</style>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{heading}</title>
<style>
@page {{
  size: A4;
  margin: 20mm 18mm 18mm 18mm;
  @bottom-center {{
    content: counter(page) " / " counter(pages);
    font-family: "DejaVu Sans", sans-serif;
    font-size: 8pt;
    color: #777;
  }}
}}
html, body {{ margin: 0; padding: 0; }}
body {{
  font-family: "DejaVu Sans", "Noto Sans", "Noto Sans CJK JP", sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
  color: #111;
}}
h1, h2, h3, h4 {{ line-height: 1.2; page-break-after: avoid; }}
h1 {{ font-size: 22pt; border-bottom: 1.5pt solid #222; padding-bottom: 3mm; }}
h2 {{ font-size: 16pt; margin-top: 8mm; }}
h3 {{ font-size: 13pt; margin-top: 6mm; }}
p {{ margin: 0 0 3mm 0; }}
a {{ color: #0b57d0; }}
pre, code {{
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 9pt;
  background: #f4f4f4;
}}
pre {{ padding: 3mm; border: 0.5pt solid #ddd; overflow-wrap: anywhere; white-space: pre-wrap; }}
code {{ padding: 0.3mm 1mm; }}
table {{ border-collapse: collapse; width: 100%; margin: 3mm 0; }}
th, td {{ border: 0.5pt solid #bbb; padding: 1.5mm 2mm; text-align: left; vertical-align: top; }}
th {{ background: #eee; }}
img {{ max-width: 100%; height: auto; }}
blockquote {{ margin: 3mm 0; padding-left: 4mm; border-left: 2pt solid #bbb; color: #444; }}
hr {{ border: 0; border-top: 0.5pt solid #ccc; margin: 6mm 0; }}
</style>
{extra_css}
</head><body>{body}</body></html>"""


def markdown_to_pdf(
    source: Path,
    target: Path,
    *,
    title: str | None = None,
    toc: bool = False,
    css: str | None = None,
) -> Path:
    html_text = _markdown_html(source, title=title, toc=toc, css=css)
    ensure_parent(target)
    temp = temp_target(target)
    try:
        try:
            from weasyprint import HTML

            HTML(string=html_text, base_url=str(source.parent.resolve())).write_pdf(
                str(temp)
            )
        except Exception as exc:
            warn(
                f"WeasyPrint failed ({exc}); falling back to LibreOffice HTML rendering"
            )
            with workdir() as job:
                html_file = job / f"{source.stem}.html"
                html_file.write_text(html_text, encoding="utf-8")
                libreoffice_convert(html_file, temp, "pdf")
        validate_pdf(temp)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def markdown_to_html(
    source: Path,
    target: Path,
    *,
    title: str | None = None,
    toc: bool = False,
    css: str | None = None,
) -> Path:
    html_text = _markdown_html(source, title=title, toc=toc, css=css)
    ensure_parent(target)
    temp = temp_target(target)
    try:
        temp.write_text(html_text, encoding="utf-8")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def markdown_to_docx(
    source: Path,
    target: Path,
    *,
    title: str | None = None,
    toc: bool = False,
    css: str | None = None,
) -> Path:
    html_text = _markdown_html(source, title=title, toc=toc, css=css)
    ensure_parent(target)
    with workdir() as job:
        html_file = job / f"{source.stem}.html"
        html_file.write_text(html_text, encoding="utf-8")
        libreoffice_convert(html_file, target, "docx:Office Open XML Text")
    validate_docx(target)
    return target


def add_doc2pdf(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="Documents, images or Markdown files.")
    parser.add_argument(
        "-o", "--output", default=None, help="Output PDF or output directory."
    )
    parser.add_argument("-d", "--out-dir", default=None, help="Output directory.")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--preserve-tree", action="store_true")
    parser.add_argument("--no-clobber", action="store_true")
    parser.add_argument("--title", default=None, help="Markdown document title.")
    parser.add_argument("--toc", action="store_true", help="Add a Markdown TOC.")
    parser.add_argument("--css", default=None, help="CSS file for Markdown rendering.")
    parser.add_argument(
        "--all",
        dest="all_files",
        action="store_true",
        help="Accepted for compatibility; every positional file is converted.",
    )


def cmd_doc2pdf(args: argparse.Namespace) -> int:
    # Backwards compatibility: "docx2pdf input.docx output.pdf".
    raw_files = [Path(item) for item in args.files]
    if (
        args.output is None
        and len(raw_files) == 2
        and raw_files[0].suffix.lower() != ".pdf"
        and raw_files[1].suffix.lower() == ".pdf"
        and not raw_files[1].exists()
    ):
        args.output = str(raw_files[1])
        args.files = [str(raw_files[0])]

    inputs = _expand_inputs(args.files, args.recursive)
    multi = len(inputs) > 1
    base = Path.cwd()
    written: list[Path] = []
    skipped_pdf = 0

    for source in inputs:
        suffix = source.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            target = _target_path(
                source,
                explicit=args.output,
                out_dir=args.out_dir,
                suffix=".pdf",
                multi=multi,
                preserve_tree=args.preserve_tree,
                base=base,
            )
            _check_clobber(target, args.no_clobber)
            from . import pdfops

            image_args = argparse.Namespace(
                files=[str(source)],
                output=str(target),
                pagesize="auto",
                fit="into",
                dpi=300,
                border=0.0,
                no_clobber=args.no_clobber,
            )
            pdfops.cmd_images_to_pdf(image_args)
            written.append(target)
            continue

        if suffix in MARKDOWN_SUFFIXES:
            target = _target_path(
                source,
                explicit=args.output,
                out_dir=args.out_dir,
                suffix=".pdf",
                multi=multi,
                preserve_tree=args.preserve_tree,
                base=base,
            )
            _check_clobber(target, args.no_clobber)
            markdown_to_pdf(
                source,
                target,
                title=args.title,
                toc=args.toc,
                css=args.css,
            )
            written.append(target)
            info(f"Wrote {target}")
            continue

        if suffix == ".pdf":
            target = _target_path(
                source,
                explicit=args.output,
                out_dir=args.out_dir,
                suffix=".pdf",
                multi=multi,
                preserve_tree=args.preserve_tree,
                base=base,
            )
            if target.resolve() == source.resolve():
                warn(f"already a PDF; skipping {source}")
                skipped_pdf += 1
                continue
            _check_clobber(target, args.no_clobber)
            ensure_parent(target)
            shutil.copy2(source, target)
            written.append(target)
            info(f"Copied {source} -> {target}")
            continue

        if suffix in OFFICE_SUFFIXES or suffix == "":
            target = _target_path(
                source,
                explicit=args.output,
                out_dir=args.out_dir,
                suffix=".pdf",
                multi=multi,
                preserve_tree=args.preserve_tree,
                base=base,
            )
            _check_clobber(target, args.no_clobber)
            libreoffice_convert(source, target, "pdf")
            validate_pdf(target)
            written.append(target)
            info(f"Wrote {target}")
            continue

        warn(f"unsupported input format: {source}")

    if not written:
        if skipped_pdf:
            info("All inputs were already PDF files.")
            return 0
        fail("no documents were converted")
    info(f"Converted {len(written)} document(s) to PDF.")
    return 0


def add_pdf2docx(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="PDF file(s).")
    parser.add_argument(
        "-o", "--output", default=None, help="Output DOCX or output directory."
    )
    parser.add_argument("-d", "--out-dir", default=None)
    parser.add_argument("--pages", default=None, help="Pages to convert, e.g. 1-5,8.")
    parser.add_argument("--start", type=int, default=None, help="First page (1-based).")
    parser.add_argument("--end", type=int, default=None, help="Last page (1-based).")
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")
    parser.add_argument(
        "--all",
        dest="all_files",
        action="store_true",
        help="Accepted for compatibility; every positional file is converted.",
    )


def _pdf2docx_convert(
    source: Path,
    target: Path,
    *,
    pages: list[int] | None,
    start: int | None,
    end: int | None,
    password: str | None,
) -> None:
    try:
        from pdf2docx import Converter
    except ImportError as exc:
        raise ToolError(
            "pdf2docx is not installed in the repo-local venv. "
            f"Run: {Path(sys.executable).parents[1] / 'setup.sh'} "
            "(or doc-tools/setup.sh)."
        ) from exc

    reader = __import__("pypdf").PdfReader(str(source))
    total = len(reader.pages)
    if reader.is_encrypted and password:
        reader.decrypt(password)

    zero_pages = [page - 1 for page in pages] if pages else None
    start_zero = (start - 1) if start else 0
    end_zero = end if end else None
    if start_zero < 0 or start_zero >= total:
        fail(f"--start must be between 1 and {total}")
    if end_zero is not None and (end_zero < 1 or end_zero > total):
        fail(f"--end must be between 1 and {total}")

    ensure_parent(target)
    temp = temp_target(target)
    try:
        converter = Converter(str(source), password=password)
        try:
            converter.convert(
                str(temp),
                start=start_zero,
                end=end_zero,
                pages=zero_pages,
            )
        finally:
            converter.close()
        validate_docx(temp)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def cmd_pdf2docx(args: argparse.Namespace) -> int:
    # Backwards compatibility: "pdf2docx input.pdf output.docx".
    raw_sources = [Path(item) for item in args.files]
    if (
        args.output is None
        and len(raw_sources) == 2
        and raw_sources[0].suffix.lower() == ".pdf"
        and raw_sources[1].suffix.lower() == ".docx"
    ):
        args.output = str(raw_sources[1])
        args.files = [str(raw_sources[0])]

    sources = [Path(item) for item in args.files]
    multi = len(sources) > 1
    for source in sources:
        if not source.is_file():
            fail(f"PDF not found: {source}")
        from .utils import pdf_reader_for

        reader = pdf_reader_for(source, args.password)
        total = len(reader.pages)
        pages = None
        if args.pages:
            from .utils import expand_pages

            pages = expand_pages(args.pages, total)
        target = _target_path(
            source,
            explicit=args.output,
            out_dir=args.out_dir,
            suffix=".docx",
            multi=multi,
        )
        _check_clobber(target, args.no_clobber)
        _pdf2docx_convert(
            source,
            target,
            pages=pages,
            start=args.start,
            end=args.end,
            password=args.password,
        )
        info(f"Wrote {target} ({human_size(target.stat().st_size)})")

        try:
            import subprocess

            text = subprocess.run(
                ["pdftotext", "-l", "2", str(source), "-"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            if len(text.strip()) < 20:
                warn(
                    f"{source.name} appears to be scanned/image-only; "
                    "run pdfocr first for better DOCX output."
                )
        except FileNotFoundError:
            pass
    return 0


def add_pdf2office(parser: argparse.ArgumentParser, extension: str) -> None:
    parser.add_argument("files", nargs="+", help="PDF file(s).")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("-d", "--out-dir", default=None)
    parser.add_argument("--pages", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")
    parser.set_defaults(office_extension=extension)


def cmd_pdf2office(args: argparse.Namespace) -> int:
    sources = [Path(item) for item in args.files]
    multi = len(sources) > 1
    for source in sources:
        if not source.is_file():
            fail(f"PDF not found: {source}")
        target = _target_path(
            source,
            explicit=args.output,
            out_dir=args.out_dir,
            suffix=f".{args.office_extension}",
            multi=multi,
        )
        _check_clobber(target, args.no_clobber)
        with workdir() as job:
            docx = job / f"{source.stem}.docx"
            from .utils import expand_pages, pdf_reader_for

            reader = pdf_reader_for(source, args.password)
            pages = expand_pages(args.pages, len(reader.pages)) if args.pages else None
            _pdf2docx_convert(
                source,
                docx,
                pages=pages,
                start=None,
                end=None,
                password=args.password,
            )
            libreoffice_convert(docx, target, args.office_extension)
        info(f"Wrote {target}")
    return 0


def add_md2pdf(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="Markdown file(s).")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("-d", "--out-dir", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--toc", action="store_true")
    parser.add_argument("--css", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_md2pdf(args: argparse.Namespace) -> int:
    sources = [Path(item) for item in args.files]
    multi = len(sources) > 1
    for source in sources:
        if source.suffix.lower() not in MARKDOWN_SUFFIXES:
            warn(f"skipping (not Markdown): {source}")
            continue
        target = _target_path(
            source,
            explicit=args.output,
            out_dir=args.out_dir,
            suffix=".pdf",
            multi=multi,
        )
        _check_clobber(target, args.no_clobber)
        markdown_to_pdf(source, target, title=args.title, toc=args.toc, css=args.css)
        info(f"Wrote {target}")
    return 0


def add_md2docx(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="Markdown file(s).")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("-d", "--out-dir", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--toc", action="store_true")
    parser.add_argument("--css", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_md2docx(args: argparse.Namespace) -> int:
    sources = [Path(item) for item in args.files]
    multi = len(sources) > 1
    for source in sources:
        if source.suffix.lower() not in MARKDOWN_SUFFIXES:
            warn(f"skipping (not Markdown): {source}")
            continue
        target = _target_path(
            source,
            explicit=args.output,
            out_dir=args.out_dir,
            suffix=".docx",
            multi=multi,
        )
        _check_clobber(target, args.no_clobber)
        markdown_to_docx(source, target, title=args.title, toc=args.toc, css=args.css)
        info(f"Wrote {target}")
    return 0


def add_md2html(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="Markdown file(s).")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("-d", "--out-dir", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--toc", action="store_true")
    parser.add_argument("--css", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_md2html(args: argparse.Namespace) -> int:
    sources = [Path(item) for item in args.files]
    multi = len(sources) > 1
    for source in sources:
        if source.suffix.lower() not in MARKDOWN_SUFFIXES:
            warn(f"skipping (not Markdown): {source}")
            continue
        target = _target_path(
            source,
            explicit=args.output,
            out_dir=args.out_dir,
            suffix=".html",
            multi=multi,
        )
        _check_clobber(target, args.no_clobber)
        markdown_to_html(source, target, title=args.title, toc=args.toc, css=args.css)
        info(f"Wrote {target}")
    return 0
