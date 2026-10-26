"""PDF manipulation commands built on pypdf, poppler, Ghostscript and Tesseract."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .utils import (
    ensure_parent,
    expand_pages,
    fail,
    have,
    human_size,
    info,
    parse_page_ranges,
    pdf_reader_for,
    require,
    run,
    temp_target,
    validate_pdf,
    warn,
    workdir,
)


def _write_pdf(writer, target: Path) -> None:
    ensure_parent(target)
    temp = temp_target(target)
    try:
        with open(temp, "wb") as handle:
            writer.write(handle)
        validate_pdf(temp)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def _check_clobber(path: Path, no_clobber: bool) -> None:
    if no_clobber and path.exists():
        fail(f"refusing to overwrite existing file: {path}")


def add_split(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="PDF file(s) to split.")
    parser.add_argument(
        "--every",
        type=int,
        default=1,
        help="Split into chunks of N pages (default: 1 page per file).",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="Split by ranges instead, e.g. 1-3,5,7-9.",
    )
    parser.add_argument("-o", "--out-dir", default=None, help="Output directory.")
    parser.add_argument("--prefix", default="", help="Prefix for output names.")
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_split(args: argparse.Namespace) -> int:
    from pypdf import PdfWriter

    if args.every < 1:
        fail("--every must be at least 1")
    written: list[Path] = []
    for source in [Path(item) for item in args.files]:
        reader = pdf_reader_for(source, args.password)
        total = len(reader.pages)
        if args.pages:
            ranges = parse_page_ranges(args.pages, total)
        else:
            ranges = [
                (start, min(start + args.every - 1, total))
                for start in range(1, total + 1, args.every)
            ]

        out_dir = Path(args.out_dir).expanduser() if args.out_dir else source.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        for first, last in ranges:
            if first == last:
                name = f"{args.prefix}{source.stem}-p{first:03d}.pdf"
            else:
                name = f"{args.prefix}{source.stem}-p{first:03d}-p{last:03d}.pdf"
            target = out_dir / name
            _check_clobber(target, args.no_clobber)
            writer = PdfWriter()
            for page in range(first, last + 1):
                writer.add_page(reader.pages[page - 1])
            _write_pdf(writer, target)
            written.append(target)
            info(f"Wrote {target}")
    if not written:
        fail("no pages were written")
    info(f"Split into {len(written)} PDF file(s).")
    return 0


def add_select(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Source PDF.")
    parser.add_argument(
        "--pages",
        required=True,
        help="Pages to extract/reorder, e.g. 3,1-2. Order is preserved.",
    )
    parser.add_argument("-o", "--output", default=None, help="Output PDF.")
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_select(args: argparse.Namespace) -> int:
    from pypdf import PdfWriter

    source = Path(args.input)
    reader = pdf_reader_for(source, args.password)
    total = len(reader.pages)
    pages = expand_pages(args.pages, total)
    target = (
        Path(args.output).expanduser()
        if args.output
        else source.with_name(f"{source.stem}-selected.pdf")
    )
    _check_clobber(target, args.no_clobber)
    writer = PdfWriter()
    for page in pages:
        writer.add_page(reader.pages[page - 1])
    _write_pdf(writer, target)
    info(f"Wrote {target} ({len(pages)} page(s))")
    return 0


def add_compress(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="PDF file(s) to compress.")
    parser.add_argument(
        "--preset",
        choices=["screen", "ebook", "printer", "prepress", "default"],
        default="ebook",
        help="Ghostscript PDFSETTINGS preset (default: ebook).",
    )
    parser.add_argument("--dpi", type=int, default=None, help="Image downsampling DPI.")
    parser.add_argument("-o", "--out-dir", default=None)
    parser.add_argument("--suffix", default="-compressed")
    parser.add_argument("--linearize", action="store_true")
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_compress(args: argparse.Namespace) -> int:
    gs = require("gs", "pacman -S ghostscript")
    explicit = Path(args.out_dir).expanduser() if args.out_dir else None
    single_output = (
        explicit is not None
        and len(args.files) == 1
        and explicit.suffix.lower() == ".pdf"
        and not explicit.is_dir()
    )
    for source in [Path(item) for item in args.files]:
        # Validate first so encrypted/corrupt inputs fail before writing.
        pdf_reader_for(source, args.password)
        if single_output:
            target = explicit
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_dir = explicit if explicit else source.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"{source.stem}{args.suffix}.pdf"
        _check_clobber(target, args.no_clobber)
        temp = temp_target(target)
        cmd = [
            gs,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7",
            f"-dPDFSETTINGS=/{args.preset}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={temp}",
        ]
        if args.dpi:
            cmd.extend(
                [
                    "-dDownsampleColorImages=true",
                    "-dDownsampleGrayImages=true",
                    "-dDownsampleMonoImages=true",
                    f"-dColorImageResolution={args.dpi}",
                    f"-dGrayImageResolution={args.dpi}",
                    f"-dMonoImageResolution={args.dpi}",
                ]
            )
        if args.password:
            cmd.append(f"-sPDFPassword={args.password}")
        cmd.append(str(source))
        try:
            run(cmd)
            validate_pdf(temp)
            if args.linearize:
                if not have("qpdf"):
                    warn("qpdf is missing; writing a non-linearized compressed PDF")
                else:
                    linear = temp_target(target)
                    try:
                        run(["qpdf", "--linearize", str(temp), str(linear)])
                        os.replace(linear, temp)
                    finally:
                        linear.unlink(missing_ok=True)
            before = source.stat().st_size
            os.replace(temp, target)
            after = target.stat().st_size
            info(
                f"Wrote {target} ({human_size(before)} -> {human_size(after)}, "
                f"preset={args.preset})"
            )
        finally:
            temp.unlink(missing_ok=True)
    return 0


def add_to_images(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="PDF file(s).")
    parser.add_argument(
        "--format",
        choices=["png", "jpeg", "jpg", "webp"],
        default="png",
        help="Image format (default: png).",
    )
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--pages", default=None, help="Pages to render, e.g. 1-3,5.")
    parser.add_argument("-o", "--out-dir", default=None)
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def _find_images(directory: Path, prefix: str) -> list[Path]:
    candidates = []
    for path in directory.iterdir():
        if path.is_file() and path.name.startswith(prefix):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                candidates.append(path)
    return sorted(candidates)


def cmd_to_images(args: argparse.Namespace) -> int:
    pdftoppm = require("pdftoppm", "pacman -S poppler")
    written: list[Path] = []
    for source in [Path(item) for item in args.files]:
        reader = pdf_reader_for(source, args.password)
        total = len(reader.pages)
        ranges = parse_page_ranges(args.pages, total) if args.pages else [(1, total)]
        out_dir = Path(args.out_dir).expanduser() if args.out_dir else source.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = args.prefix or source.stem
        fmt = "jpeg" if args.format in {"jpeg", "jpg"} else args.format
        format_flag = "-png" if fmt == "png" else "-jpeg"
        for first, last in ranges:
            stem = f"{prefix}-p{first:03d}" if args.pages else prefix
            target_prefix = out_dir / stem
            existing = _find_images(out_dir, stem)
            if args.no_clobber and existing:
                fail(f"refusing to overwrite existing images: {existing[0]}")
            if fmt == "webp":
                with workdir() as job:
                    command = [
                        pdftoppm,
                        "-r",
                        str(args.dpi),
                        "-png",
                        "-f",
                        str(first),
                        "-l",
                        str(last),
                    ]
                    if args.password:
                        command.extend(["-upw", args.password])
                    command.extend([str(source), str(job / stem)])
                    run(command)
                    pngs = sorted(job.glob(f"{stem}*.png"))
                    if not pngs:
                        fail(f"no images produced for {source} pages {first}-{last}")
                    from PIL import Image

                    for png in pngs:
                        target = out_dir / f"{png.stem}.webp"
                        _check_clobber(target, args.no_clobber)
                        with Image.open(png) as image:
                            image.save(target, "WEBP", quality=90)
                        written.append(target)
                        info(f"Wrote {target}")
            else:
                before = set(out_dir.glob(f"{stem}*.{fmt}"))
                command = [
                    pdftoppm,
                    "-r",
                    str(args.dpi),
                    format_flag,
                    "-f",
                    str(first),
                    "-l",
                    str(last),
                ]
                if args.password:
                    command.extend(["-upw", args.password])
                command.extend([str(source), str(target_prefix)])
                run(command)
                produced = sorted(set(out_dir.glob(f"{stem}*.{fmt}")) - before)
                if not produced:
                    fail(f"no images produced for {source} pages {first}-{last}")
                written.extend(produced)
                for path in produced:
                    info(f"Wrote {path}")
    if not written:
        fail("no images were written")
    return 0


def add_images_to_pdf(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="Image file(s).")
    parser.add_argument("-o", "--output", default=None, help="Output PDF.")
    parser.add_argument(
        "--pagesize",
        choices=["A4", "A3", "A5", "LETTER", "LEGAL", "auto"],
        default="auto",
    )
    parser.add_argument("--fit", choices=["into", "fill"], default="into")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--border", type=float, default=0.0, help="Border in points.")
    parser.add_argument("--no-clobber", action="store_true")


def cmd_images_to_pdf(args: argparse.Namespace) -> int:
    inputs = [Path(item) for item in args.files]
    for path in inputs:
        if not path.is_file():
            fail(f"image not found: {path}")
    target = (
        Path(args.output).expanduser() if args.output else Path.cwd() / "images.pdf"
    )
    _check_clobber(target, args.no_clobber)
    ensure_parent(target)

    try:
        import img2pdf

        pagesize = (
            None
            if args.pagesize == "auto"
            else img2pdf.parse_pagesize_rectarg(args.pagesize)
        )
        fit = img2pdf.FitMode.into if args.fit == "into" else img2pdf.FitMode.fill
        border = (args.border, args.border) if args.border else None
        layout = img2pdf.get_layout_fun(
            pagesize=pagesize,
            border=border,
            fit=fit,
        )
        data = img2pdf.convert([str(path) for path in inputs], layout_fun=layout)
        temp = temp_target(target)
        try:
            temp.write_bytes(data)
            validate_pdf(temp)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    except ImportError:
        # Pillow fallback: one image per page, no lossless JPEG passthrough.
        from PIL import Image

        images = [Image.open(path).convert("RGB") for path in inputs]
        temp = temp_target(target)
        try:
            images[0].save(temp, "PDF", save_all=True, append_images=images[1:])
            validate_pdf(temp)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    info(f"Wrote {target} ({len(inputs)} image(s))")
    return 0


def add_to_text(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Source PDF.")
    parser.add_argument(
        "-o", "--output", default=None, help="Output .txt file, or - for stdout."
    )
    parser.add_argument("--pages", default=None)
    parser.add_argument(
        "--no-layout", action="store_true", help="Do not preserve layout."
    )
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_to_text(args: argparse.Namespace) -> int:
    pdftotext = require("pdftotext", "pacman -S poppler")
    source = Path(args.input)
    reader = pdf_reader_for(source, args.password)
    total = len(reader.pages)
    ranges = parse_page_ranges(args.pages, total) if args.pages else [(1, total)]

    chunks: list[str] = []
    for first, last in ranges:
        cmd = [pdftotext]
        if not args.no_layout:
            cmd.append("-layout")
        cmd.extend(["-f", str(first), "-l", str(last)])
        if args.password:
            cmd.extend(["-upw", args.password])
        cmd.extend([str(source), "-"])
        result = run(cmd)
        chunks.append(result.stdout or "")
    text = "\n\f\n".join(chunks)

    if args.output == "-":
        sys.stdout.write(text)
        return 0

    target = (
        Path(args.output).expanduser() if args.output else source.with_suffix(".txt")
    )
    _check_clobber(target, args.no_clobber)
    ensure_parent(target)
    temp = temp_target(target)
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    if not text.strip():
        warn("the extracted text is empty; this PDF may be scanned (try pdfocr)")
    info(f"Wrote {target} ({human_size(target.stat().st_size)})")
    return 0


def add_to_html(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Source PDF.")
    parser.add_argument("-o", "--output", default=None, help="Output .html file.")
    parser.add_argument("--pages", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_to_html(args: argparse.Namespace) -> int:
    pdftohtml = require("pdftohtml", "pacman -S poppler")
    source = Path(args.input)
    reader = pdf_reader_for(source, args.password)
    total = len(reader.pages)
    ranges = parse_page_ranges(args.pages, total) if args.pages else [(1, total)]
    target = (
        Path(args.output).expanduser() if args.output else source.with_suffix(".html")
    )
    _check_clobber(target, args.no_clobber)
    ensure_parent(target)
    first, last = ranges[0][0], ranges[-1][1]
    with workdir() as job:
        stem = "document"
        cmd = [
            pdftohtml,
            "-s",
            "-noframes",
            "-f",
            str(first),
            "-l",
            str(last),
        ]
        if args.password:
            cmd.extend(["-upw", args.password])
        cmd.extend([str(source), str(job / stem)])
        run(cmd)
        produced = job / f"{stem}.html"
        if not produced.exists():
            fail("pdftohtml did not produce an HTML file")
        html_text = produced.read_text(encoding="utf-8", errors="replace")
        for asset in job.iterdir():
            if asset.name == produced.name:
                continue
            if asset.is_file():
                renamed = f"{target.stem}_{asset.name}"
                html_text = html_text.replace(asset.name, renamed)
                shutil.copy2(asset, target.parent / renamed)
        temp = temp_target(target)
        try:
            temp.write_text(html_text, encoding="utf-8")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    info(f"Wrote {target}")
    return 0


def _outline_count(items) -> int:
    count = 0
    for item in items or []:
        if isinstance(item, list):
            count += _outline_count(item)
        else:
            count += 1
    return count


def add_info(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Source PDF.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--password", default=None)


def cmd_info(args: argparse.Namespace) -> int:
    source = Path(args.input)
    reader = pdf_reader_for(source, args.password)
    metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items()}
    page_sizes = []
    for page in reader.pages:
        box = page.mediabox
        width = float(box.width)
        height = float(box.height)
        page_sizes.append(
            {
                "width_pt": round(width, 2),
                "height_pt": round(height, 2),
                "width_mm": round(width * 25.4 / 72, 1),
                "height_mm": round(height * 25.4 / 72, 1),
            }
        )

    payload = {
        "file": str(source),
        "pages": len(reader.pages),
        "encrypted": bool(reader.is_encrypted),
        "metadata": metadata,
        "outline_items": _outline_count(reader.outline),
        "page_sizes": page_sizes,
        "size_bytes": source.stat().st_size,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    info(f"File: {source}")
    info(f"Pages: {payload['pages']}")
    info(f"Size: {human_size(payload['size_bytes'])}")
    info(f"Encrypted: {'yes' if payload['encrypted'] else 'no'}")
    info(f"Outline items: {payload['outline_items']}")
    if metadata:
        info("Metadata:")
        for key, value in metadata.items():
            info(f"  {key}: {value}")
    unique_sizes = {(item["width_mm"], item["height_mm"]) for item in page_sizes}
    info("Page sizes (mm):")
    for width, height in sorted(unique_sizes):
        info(f"  {width} x {height}")
    return 0


def add_rotate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Source PDF.")
    parser.add_argument("--pages", default=None, help="Pages to rotate (default: all).")
    parser.add_argument("--angle", type=int, choices=[90, 180, 270], required=True)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_rotate(args: argparse.Namespace) -> int:
    from pypdf import PdfWriter

    source = Path(args.input)
    reader = pdf_reader_for(source, args.password)
    total = len(reader.pages)
    selected = (
        set(expand_pages(args.pages, total)) if args.pages else set(range(1, total + 1))
    )
    target = (
        Path(args.output).expanduser()
        if args.output
        else source.with_name(f"{source.stem}-rotated.pdf")
    )
    _check_clobber(target, args.no_clobber)
    writer = PdfWriter()
    for index, page in enumerate(reader.pages, start=1):
        if index in selected:
            page.rotate(args.angle)
        writer.add_page(page)
    _write_pdf(writer, target)
    info(f"Wrote {target} (rotated {len(selected)} page(s) by {args.angle} degrees)")
    return 0


def add_encrypt(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Source PDF.")
    parser.add_argument("-p", "--password", required=True, help="User password.")
    parser.add_argument("--owner-password", default=None)
    parser.add_argument(
        "--input-password", default=None, help="Password of the source PDF."
    )
    parser.add_argument(
        "--algorithm",
        choices=["AES-256", "AES-128", "RC4-128"],
        default="AES-256",
    )
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_encrypt(args: argparse.Namespace) -> int:
    from pypdf import PdfWriter

    source = Path(args.input)
    reader = pdf_reader_for(source, args.input_password)
    target = (
        Path(args.output).expanduser()
        if args.output
        else source.with_name(f"{source.stem}-encrypted.pdf")
    )
    _check_clobber(target, args.no_clobber)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(
        user_password=args.password,
        owner_password=args.owner_password or args.password,
        algorithm=args.algorithm,
    )
    ensure_parent(target)
    temp = temp_target(target)
    try:
        with open(temp, "wb") as handle:
            writer.write(handle)
        if temp.stat().st_size == 0:
            fail("encryption produced an empty file")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    info(f"Wrote {target} (encrypted with {args.algorithm})")
    return 0


def add_decrypt(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Encrypted source PDF.")
    parser.add_argument("-p", "--password", required=True)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_decrypt(args: argparse.Namespace) -> int:
    from pypdf import PdfWriter

    source = Path(args.input)
    reader = pdf_reader_for(source, args.password)
    target = (
        Path(args.output).expanduser()
        if args.output
        else source.with_name(f"{source.stem}-decrypted.pdf")
    )
    _check_clobber(target, args.no_clobber)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    _write_pdf(writer, target)
    info(f"Wrote {target}")
    return 0


def add_watermark(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Source PDF.")
    parser.add_argument("--text", required=True, help="Watermark text.")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--pages", default=None, help="Pages to stamp (default: all).")
    parser.add_argument("--opacity", type=float, default=0.15)
    parser.add_argument("--angle", type=float, default=45)
    parser.add_argument("--font-size", type=int, default=60)
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def cmd_watermark(args: argparse.Namespace) -> int:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.colors import Color
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    source = Path(args.input)
    reader = pdf_reader_for(source, args.password)
    total = len(reader.pages)
    selected = (
        set(expand_pages(args.pages, total)) if args.pages else set(range(1, total + 1))
    )
    target = (
        Path(args.output).expanduser()
        if args.output
        else source.with_name(f"{source.stem}-watermarked.pdf")
    )
    _check_clobber(target, args.no_clobber)

    font_name = "Helvetica"
    font_path = Path("/usr/share/fonts/TTF/DejaVuSans.ttf")
    if font_path.exists():
        try:
            pdfmetrics.registerFont(TTFont("DocToolsWatermark", str(font_path)))
            font_name = "DocToolsWatermark"
        except Exception:
            font_name = "Helvetica"

    writer = PdfWriter()
    with workdir() as job:
        for index, page in enumerate(reader.pages, start=1):
            if index in selected:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                overlay_path = job / f"watermark-{index}.pdf"
                c = canvas.Canvas(str(overlay_path), pagesize=(width, height))
                c.saveState()
                c.setFillColor(
                    Color(0.4, 0.4, 0.4, alpha=max(0.0, min(1.0, args.opacity)))
                )
                c.setFont(font_name, args.font_size)
                c.translate(width / 2, height / 2)
                c.rotate(args.angle)
                text_width = c.stringWidth(args.text, font_name, args.font_size)
                c.drawString(-text_width / 2, 0, args.text)
                c.restoreState()
                c.showPage()
                c.save()
                overlay = PdfReader(str(overlay_path))
                page.merge_page(overlay.pages[0])
            writer.add_page(page)

    _write_pdf(writer, target)
    info(f"Wrote {target} (watermark on {len(selected)} page(s))")
    return 0


def add_extract_images(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Source PDF.")
    parser.add_argument("-o", "--out-dir", default=None)
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--pages", default=None)
    parser.add_argument("--password", default=None)


def cmd_extract_images(args: argparse.Namespace) -> int:
    pdfimages = require("pdfimages", "pacman -S poppler")
    source = Path(args.input)
    reader = pdf_reader_for(source, args.password)
    total = len(reader.pages)
    ranges = parse_page_ranges(args.pages, total) if args.pages else [(1, total)]
    out_dir = (
        Path(args.out_dir).expanduser()
        if args.out_dir
        else source.parent / f"{source.stem}-images"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or "image"
    written = []
    for first, last in ranges:
        before = set(out_dir.iterdir())
        command = [
            pdfimages,
            "-all",
            "-f",
            str(first),
            "-l",
            str(last),
        ]
        if args.password:
            command.extend(["-upw", args.password])
        command.extend([str(source), str(out_dir / prefix)])
        run(command)
        produced = sorted(set(out_dir.iterdir()) - before)
        written.extend(produced)
        for path in produced:
            info(f"Wrote {path}")
    if not written:
        warn("no embedded images were found")
    return 0


def add_ocr(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", help="Scanned PDF file(s).")
    parser.add_argument("-o", "--out-dir", default=None)
    parser.add_argument("--suffix", default="-ocr")
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--pages", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--no-clobber", action="store_true")


def _tesseract_has_language(lang: str) -> bool:
    if not have("tesseract"):
        return False
    result = run(["tesseract", "--list-langs"], check=False)
    languages = set((result.stdout or "").splitlines())
    languages.update((result.stderr or "").splitlines())
    return lang in languages or lang.split("+")[0] in languages


def cmd_ocr(args: argparse.Namespace) -> int:
    from pypdf import PdfWriter

    explicit = Path(args.out_dir).expanduser() if args.out_dir else None
    single_output = (
        explicit is not None
        and len(args.files) == 1
        and explicit.suffix.lower() == ".pdf"
        and not explicit.is_dir()
    )

    if have("ocrmypdf"):
        # Prefer the specialist tool when it is present.
        for source in [Path(item) for item in args.files]:
            if single_output:
                target = explicit
                target.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_dir = explicit if explicit else source.parent
                out_dir.mkdir(parents=True, exist_ok=True)
                target = out_dir / f"{source.stem}{args.suffix}.pdf"
            _check_clobber(target, args.no_clobber)
            temp = temp_target(target)
            try:
                run(
                    [
                        "ocrmypdf",
                        "--skip-text",
                        "--language",
                        args.lang,
                        str(source),
                        str(temp),
                    ]
                )
                validate_pdf(temp)
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
            info(f"Wrote {target} (ocrmypdf)")
        return 0

    pdftoppm = require("pdftoppm", "pacman -S poppler")
    tesseract = require("tesseract", "pacman -S tesseract tesseract-data-eng")
    if not _tesseract_has_language(args.lang):
        fail(
            f"Tesseract language data for {args.lang!r} is missing. "
            f"Install tesseract-data-{args.lang.split('+')[0]}."
        )

    for source in [Path(item) for item in args.files]:
        reader = pdf_reader_for(source, args.password)
        total = len(reader.pages)
        pages = (
            expand_pages(args.pages, total) if args.pages else list(range(1, total + 1))
        )
        if single_output:
            target = explicit
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_dir = explicit if explicit else source.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"{source.stem}{args.suffix}.pdf"
        _check_clobber(target, args.no_clobber)

        writer = PdfWriter()
        with workdir() as job:
            for page in pages:
                stem = f"page-{page:04d}"
                command = [
                    pdftoppm,
                    "-r",
                    str(args.dpi),
                    "-png",
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                ]
                if args.password:
                    command.extend(["-upw", args.password])
                command.extend([str(source), str(job / stem)])
                run(command)
                images = sorted(job.glob(f"{stem}*.png"))
                if not images:
                    fail(f"could not render page {page} of {source}")
                ocr_base = job / f"{stem}-ocr"
                run([tesseract, str(images[0]), str(ocr_base), "-l", args.lang, "pdf"])
                ocr_pdf = ocr_base.with_suffix(".pdf")
                if not ocr_pdf.exists():
                    fail(f"tesseract did not produce a PDF for page {page}")
                page_reader = pdf_reader_for(ocr_pdf)
                for ocr_page in page_reader.pages:
                    writer.add_page(ocr_page)
                info(f"OCR page {page}/{total}")
            temp = temp_target(target)
            try:
                with open(temp, "wb") as handle:
                    writer.write(handle)
                validate_pdf(temp)
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        info(f"Wrote {target} ({len(pages)} page(s), lang={args.lang})")
    return 0
