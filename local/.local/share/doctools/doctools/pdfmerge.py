"""Merge PDFs and emit final.pdf, toc.pdf and final_toc.pdf."""

from __future__ import annotations

import argparse
import html
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .utils import (
    ROOT,
    ToolError,
    collect_inputs,
    display_name,
    ensure_runtime_dirs,
    fail,
    human_size,
    info,
    pdf_reader_for,
    temp_target,
    validate_pdf,
    warn,
    workdir,
)


@dataclass
class Source:
    path: Path
    display: str
    pages: int
    start_page: int  # 1-based page in the content-only merge


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "files",
        nargs="*",
        help="PDF files in the desired order. With no files, scan the current directory.",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        default=".",
        help="Directory for final.pdf, toc.pdf and final_toc.pdf (default: current directory).",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Prefix for generated file names, e.g. 'q3-'.",
    )
    parser.add_argument(
        "--title",
        default="Table of Contents",
        help="TOC heading (default: Table of Contents).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Scan subdirectories when no input files are given.",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Password used for encrypted input PDFs.",
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Skip unreadable/encrypted PDFs instead of aborting.",
    )
    parser.add_argument(
        "--no-clobber",
        action="store_true",
        help="Refuse to overwrite existing output files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Accepted for compatibility; overwriting is the default.",
    )
    parser.add_argument(
        "--legacy-names",
        action="store_true",
        help="Also write merged.pdf and merged_toc.pdf aliases for old scripts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the input/output plan without writing anything.",
    )


def _looks_generated(path: Path) -> bool:
    """Identify files previously written by this tool."""
    try:
        reader = pdf_reader_for(path)
        metadata = reader.metadata or {}
        creator = str(metadata.get("/Creator", ""))
        return creator.startswith("doc-tools")
    except Exception:
        return False


def _collision_guard(out_dir: Path, outputs: list[Path], inputs: list[Path]) -> None:
    output_set = {path.resolve() for path in outputs}
    for source in inputs:
        if source.resolve() in output_set:
            fail(
                f"input {source.name!r} would be overwritten by an output file. "
                "Use --out-dir or --prefix."
            )


def _backup_legacy_final(path: Path) -> Path:
    """Preserve the old final.pdf produced by the pre-doctools merger."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.pre-doctools.{stamp}")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.pre-doctools.{stamp}.{counter}")
        counter += 1
    path.rename(backup)
    return backup


def _scan_collision_guard(out_dir: Path, outputs: list[Path], *, dry_run: bool = False) -> None:
    """Reject pre-existing output names that were not created by this tool."""
    for path in outputs:
        if not path.exists():
            continue
        if path.parent.resolve() != out_dir.resolve():
            continue
        if _looks_generated(path):
            continue
        if path.name == "final.pdf":
            if dry_run:
                warn("dry-run: the old final.pdf would be backed up before writing")
            else:
                backup = _backup_legacy_final(path)
                warn(
                    f"old final.pdf was backed up to {backup.name} before the new "
                    "final.pdf is written"
                )
            continue
        fail(
            f"{path.name!r} already exists and does not look like a pdfmerge output. "
            "Use --out-dir or --prefix so a real source file is not overwritten."
        )


def _read_sources(
    inputs: list[Path],
    password: str | None,
    skip_errors: bool,
    base: Path,
) -> tuple[list[Source], list[Path]]:
    sources: list[Source] = []
    skipped: list[Path] = []
    next_page = 1
    for path in inputs:
        try:
            count, _reader = validate_pdf(path, password)
        except ToolError as exc:
            if skip_errors:
                warn(f"skipping {path}: {exc}")
                skipped.append(path)
                continue
            raise
        sources.append(
            Source(
                path=path,
                display=display_name(path, base),
                pages=count,
                start_page=next_page,
            )
        )
        next_page += count
    if not sources:
        fail("no readable PDF files found")
    return sources, skipped


def _toc_html(sources: list[Source], offset: int, title: str) -> str:
    rows = []
    for source in sources:
        page = source.start_page + offset
        rows.append(
            '<div class="entry">'
            f'<span class="name">{html.escape(source.display)}</span>'
            f'<span class="page">{page}</span>'
            "</div>"
        )

    css = """
    @page {
      size: A4;
      margin: 20mm 18mm 18mm 18mm;
      @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: "DejaVu Sans", "Noto Sans", sans-serif;
        font-size: 8pt;
        color: #777;
      }
    }
    html, body { margin: 0; padding: 0; }
    body {
      font-family: "DejaVu Sans", "Noto Sans CJK JP", "Noto Sans", sans-serif;
      font-size: 10.5pt;
      line-height: 1.45;
      color: #111;
    }
    h1 {
      font-size: 20pt;
      line-height: 1.2;
      margin: 0 0 9mm 0;
      padding-bottom: 3mm;
      border-bottom: 1.5pt solid #222;
    }
    .entries { display: block; }
    .entry {
      display: block;
      margin: 0 0 2.4mm 0;
      break-inside: avoid;
    }
    .entry .name {
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .entry .name::after {
      content: leader(".");
      color: #777;
    }
    .entry .page {
      float: right;
      margin-left: 0.5em;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }
    """
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><style>{css}</style></head>"
        f'<body><h1>{html.escape(title)}</h1><div class="entries">'
        + "".join(rows)
        + "</div></body></html>"
    )


def _render_toc_weasyprint(
    sources: list[Source],
    offset: int,
    title: str,
    target: Path,
) -> None:
    from weasyprint import HTML

    HTML(string=_toc_html(sources, offset, title), base_url=str(ROOT)).write_pdf(
        str(target)
    )


def _sanitize_helvetica(text: str) -> str:
    """Keep characters the built-in fonts can encode."""
    try:
        text.encode("cp1252")
        return text
    except UnicodeEncodeError:
        return text.encode("cp1252", "replace").decode("cp1252")


def _render_toc_reportlab(
    sources: list[Source],
    offset: int,
    title: str,
    target: Path,
) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_name = "Helvetica"
    font_path = Path("/usr/share/fonts/TTF/DejaVuSans.ttf")
    if font_path.exists():
        try:
            pdfmetrics.registerFont(TTFont("DocToolsDejaVu", str(font_path)))
            font_name = "DocToolsDejaVu"
        except Exception:
            font_name = "Helvetica"

    c = canvas.Canvas(str(target), pagesize=A4)
    c.setTitle(title)
    width, height = A4
    left, right = 50, width - 50
    y = height - 60

    c.setFont(font_name, 18)
    c.drawString(left, y, _sanitize_helvetica(title))
    y -= 34
    c.setLineWidth(1)
    c.line(left, y, right, y)
    y -= 24
    c.setFont(font_name, 10.5)

    number_width = 34
    for source in sources:
        page = source.start_page + offset
        name = _sanitize_helvetica(source.display)
        max_name_width = right - left - number_width - 18
        while name and pdfmetrics.stringWidth(name, font_name, 10.5) > max_name_width:
            name = name[:-1]
        if name != source.display and name:
            name = name[:-1] + "…"

        page_text = str(page)
        page_width = pdfmetrics.stringWidth(page_text, font_name, 10.5)
        available = (
            right
            - left
            - pdfmetrics.stringWidth(name, font_name, 10.5)
            - page_width
            - 10
        )
        dot_width = max(pdfmetrics.stringWidth(".", font_name, 10.5), 1)
        dots = "." * max(2, int(available / dot_width))
        c.drawString(left, y, name)
        c.drawString(left + pdfmetrics.stringWidth(name, font_name, 10.5) + 4, y, dots)
        c.drawRightString(right, y, page_text)

        y -= 18
        if y < 50:
            c.showPage()
            c.setFont(font_name, 10.5)
            y = height - 50

    c.save()


def _stamp_toc_metadata(path: Path, title: str) -> None:
    from pypdf import PdfReader, PdfWriter
    from pypdf.constants import PageLabelStyle

    reader = PdfReader(str(path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": title,
            "/Creator": "doc-tools pdfmerge",
            "/Producer": "doc-tools (WeasyPrint/ReportLab)",
        }
    )
    _set_page_labels(writer, 0, len(reader.pages) - 1, PageLabelStyle.LOWERCASE_ROMAN)
    temp = temp_target(path)
    try:
        with open(temp, "wb") as handle:
            writer.write(handle)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _render_toc(
    sources: list[Source],
    offset: int,
    title: str,
    target: Path,
) -> None:
    if os.environ.get("DOC_TOOLS_TOC_RENDERER") == "reportlab":
        _render_toc_reportlab(sources, offset, title, target)
    else:
        try:
            _render_toc_weasyprint(sources, offset, title, target)
        except Exception as exc:
            warn(f"WeasyPrint TOC rendering failed ({exc}); using the basic renderer")
            _render_toc_reportlab(sources, offset, title, target)
    count, _ = validate_pdf(target)
    if count < 1:
        raise ToolError("TOC renderer produced an empty PDF")
    _stamp_toc_metadata(target, title)


def _set_page_labels(
    writer, start: int, end: int, style, prefix: str | None = None
) -> None:
    from pypdf.constants import PageLabelStyle

    if end < start:
        return
    writer.set_page_label(start, end, style=style, prefix=prefix, start=1)


def _write_content_pdf(
    sources: list[Source],
    target: Path,
    *,
    password: str | None,
    with_toc: Path | None,
    title: str,
) -> int:
    from pypdf import PdfWriter

    writer = PdfWriter()
    toc_pages = 0
    if with_toc is not None:
        toc_reader = pdf_reader_for(with_toc)
        for page in toc_reader.pages:
            writer.add_page(page)
        toc_pages = len(toc_reader.pages)
        writer.add_outline_item("Table of Contents", 0)

    current_index = toc_pages
    for source in sources:
        reader = pdf_reader_for(source.path, password)
        writer.add_outline_item(source.display, current_index)
        for page in reader.pages:
            writer.add_page(page)
        current_index += len(reader.pages)

    writer.add_metadata(
        {
            "/Title": title,
            "/Creator": "doc-tools pdfmerge",
            "/Producer": "doc-tools (pypdf)",
        }
    )

    from pypdf.constants import PageLabelStyle

    if toc_pages:
        _set_page_labels(writer, 0, toc_pages - 1, PageLabelStyle.LOWERCASE_ROMAN)
        _set_page_labels(writer, toc_pages, current_index - 1, PageLabelStyle.DECIMAL)
    else:
        _set_page_labels(writer, 0, current_index - 1, PageLabelStyle.DECIMAL)

    with open(target, "wb") as handle:
        writer.write(handle)
    return current_index


def _run(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    out_dir = Path(args.out_dir).expanduser()
    if out_dir.exists() and not out_dir.is_dir():
        fail(f"output path is not a directory: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir = out_dir.resolve()

    prefix = args.prefix or ""
    final_path = out_dir / f"{prefix}final.pdf"
    toc_path = out_dir / f"{prefix}toc.pdf"
    final_toc_path = out_dir / f"{prefix}final_toc.pdf"
    legacy_merged = out_dir / f"{prefix}merged.pdf"
    legacy_merged_toc = out_dir / f"{prefix}merged_toc.pdf"
    outputs = [final_path, toc_path, final_toc_path]
    if args.legacy_names:
        outputs.extend([legacy_merged, legacy_merged_toc])

    if args.no_clobber:
        existing = [path for path in outputs if path.exists()]
        if existing:
            fail(
                "refusing to overwrite existing output(s): "
                + ", ".join(path.name for path in existing)
            )

    output_set = {path.resolve() for path in outputs}
    explicit = [Path(item) for item in args.files]
    if explicit:
        inputs = collect_inputs(
            args.files,
            suffix=".pdf",
            recursive=args.recursive,
            excluded=outputs,
        )
        _collision_guard(out_dir, outputs, inputs)
    else:
        _scan_collision_guard(out_dir, outputs, dry_run=args.dry_run)
        candidates = collect_inputs(
            [],
            suffix=".pdf",
            recursive=args.recursive,
        )
        # Never re-merge files this tool produced, even if a different
        # --prefix or --legacy-names was used on the previous run.
        inputs = [
            path
            for path in candidates
            if path.resolve() not in output_set and not _looks_generated(path)
        ]
        _collision_guard(out_dir, outputs, inputs)
    if not inputs:
        fail("no PDF files found")

    sources, skipped = _read_sources(
        inputs,
        password=args.password,
        skip_errors=args.skip_errors,
        base=Path.cwd(),
    )

    total_pages = sum(source.pages for source in sources)
    info(f"Inputs ({len(sources)} file(s), {total_pages} content page(s)):")
    for source in sources:
        info(f"  {source.start_page:>4}  {source.display}  ({source.pages} page(s))")
    if skipped:
        info(f"Skipped: {len(skipped)} file(s)")
    info(f"Output directory: {out_dir}")

    if args.dry_run:
        for path in outputs:
            info(f"  would write: {path}")
        return 0

    with workdir() as job:
        standalone_toc = job / "toc.pdf"
        _render_toc(sources, 0, args.title, standalone_toc)
        toc_page_count, _ = validate_pdf(standalone_toc)

        # Converge on the TOC page count needed by the embedded copy.
        embedded_offset = toc_page_count
        embedded_toc = job / "toc-embedded.pdf"
        for _attempt in range(4):
            if embedded_toc.exists():
                embedded_toc.unlink()
            _render_toc(sources, embedded_offset, args.title, embedded_toc)
            new_count, _ = validate_pdf(embedded_toc)
            if new_count == embedded_offset:
                break
            embedded_offset = new_count
        else:
            raise ToolError("could not stabilise the TOC page count")

        final_tmp = job / "final.pdf"
        final_toc_tmp = job / "final_toc.pdf"
        final_total = _write_content_pdf(
            sources,
            final_tmp,
            password=args.password,
            with_toc=None,
            title=f"Merged PDF ({len(sources)} files)",
        )
        final_toc_total = _write_content_pdf(
            sources,
            final_toc_tmp,
            password=args.password,
            with_toc=embedded_toc,
            title=f"Merged PDF with Table of Contents ({len(sources)} files)",
        )

        expected_final = total_pages
        expected_final_toc = total_pages + embedded_offset
        if final_total != expected_final:
            raise ToolError(
                f"internal check failed: final.pdf has {final_total} pages, expected {expected_final}"
            )
        if final_toc_total != expected_final_toc:
            raise ToolError(
                "internal check failed: final_toc.pdf has "
                f"{final_toc_total} pages, expected {expected_final_toc}"
            )

        # Re-open every output before publishing it.
        validate_pdf(standalone_toc)
        validate_pdf(final_tmp)
        validate_pdf(final_toc_tmp)

        os.replace(standalone_toc, toc_path)
        os.replace(final_tmp, final_path)
        os.replace(final_toc_tmp, final_toc_path)

        if args.legacy_names:
            for source_path, legacy_path in (
                (final_path, legacy_merged),
                (final_toc_path, legacy_merged_toc),
            ):
                legacy_temp = temp_target(legacy_path)
                try:
                    shutil.copy2(source_path, legacy_temp)
                    os.replace(legacy_temp, legacy_path)
                finally:
                    legacy_temp.unlink(missing_ok=True)

    for path in outputs:
        info(f"Wrote {path} ({human_size(path.stat().st_size)})")
    info(
        f"TOC pages: {toc_page_count}; embedded TOC offset: {embedded_offset}; "
        f"content pages: {total_pages}"
    )
    return 0


def main(args: argparse.Namespace) -> int:
    return _run(args)
