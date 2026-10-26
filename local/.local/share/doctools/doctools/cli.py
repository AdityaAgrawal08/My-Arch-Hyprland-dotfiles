"""Command dispatcher for the repo-local document toolkit."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings

# Keep third-party chatter (WeasyPrint/pikepdf/pypdf) out of command output.
logging.disable(logging.INFO)
for _logger in ("pypdf", "weasyprint", "pikepdf", "pdf2docx", "fitz"):
    logging.getLogger(_logger).setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="The `fitz` API is deprecated.*")

from . import convert, doctor, pdfmerge, pdfops
from .utils import ToolError, ensure_runtime_dirs, info


ALIASES = {
    "docx2pdf": "doc2pdf",
    "pdfunlock": "pdfdecrypt",
    "to-pdf": "img2pdf",
    "to-images": "pdf2img",
    "to-text": "pdf2txt",
    "to-html": "pdf2html",
    "info": "pdfinfo",
    "merge": "pdfmerge",
    "split": "pdfsplit",
    "compress": "pdfcompress",
    "select": "pdfselect",
    "rotate": "pdfrotate",
    "encrypt": "pdfencrypt",
    "decrypt": "pdfdecrypt",
    "ocr": "pdfocr",
    "watermark": "pdfwatermark",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docs",
        description="Repo-local document and PDF toolkit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  doc merge\n"
            "  doc merge a.pdf b.pdf --out-dir out\n"
            "  doc to-pdf report.docx\n"
            "  doc to-docx report.pdf\n"
            "  doc split big.pdf --every 10\n"
            "  doc compress big.pdf --preset ebook\n"
            "  doc to-images big.pdf --dpi 150\n"
            "  doc to-pdf images/*.png\n"
            "  doc doctor\n"
        ),
    )
    parser.add_argument("--version", action="version", version="doc-tools 0.1.0")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    merge = sub.add_parser(
        "pdfmerge", help="Merge PDFs into merged.pdf, toc.pdf and merged_toc.pdf."
    )
    pdfmerge.add_arguments(merge)
    merge.set_defaults(func=pdfmerge.main)

    doc2pdf = sub.add_parser(
        "doc2pdf",
        aliases=["docx2pdf"],
        help="Convert Office/Markdown/images to PDF.",
    )
    convert.add_doc2pdf(doc2pdf)
    doc2pdf.set_defaults(func=convert.cmd_doc2pdf)

    pdf2docx = sub.add_parser(
        "pdf2docx",
        help="Convert PDF to DOCX with pdf2docx.",
    )
    convert.add_pdf2docx(pdf2docx)
    pdf2docx.set_defaults(func=convert.cmd_pdf2docx)

    for command, extension, description in (
        ("pdf2doc", "doc", "Convert PDF to legacy DOC via DOCX + LibreOffice."),
        ("pdf2odt", "odt", "Convert PDF to ODT via DOCX + LibreOffice."),
    ):
        sub_parser = sub.add_parser(command, help=description)
        convert.add_pdf2office(sub_parser, extension)
        sub_parser.set_defaults(func=convert.cmd_pdf2office)

    split = sub.add_parser("pdfsplit", help="Split a PDF into page files or ranges.")
    pdfops.add_split(split)
    split.set_defaults(func=pdfops.cmd_split)

    select = sub.add_parser("pdfselect", help="Extract or reorder pages into one PDF.")
    pdfops.add_select(select)
    select.set_defaults(func=pdfops.cmd_select)

    compress = sub.add_parser("pdfcompress", help="Compress PDFs with Ghostscript.")
    pdfops.add_compress(compress)
    compress.set_defaults(func=pdfops.cmd_compress)

    to_images = sub.add_parser(
        "pdf2img",
        aliases=["to-images"],
        help="Render PDF pages to PNG, JPEG or WebP.",
    )
    pdfops.add_to_images(to_images)
    to_images.set_defaults(func=pdfops.cmd_to_images)

    images_to_pdf = sub.add_parser(
        "img2pdf",
        aliases=["to-pdf"],
        help="Convert images to a PDF.",
    )
    pdfops.add_images_to_pdf(images_to_pdf)
    images_to_pdf.set_defaults(func=pdfops.cmd_images_to_pdf)

    to_text = sub.add_parser(
        "pdf2txt",
        aliases=["to-text"],
        help="Extract text from a PDF.",
    )
    pdfops.add_to_text(to_text)
    to_text.set_defaults(func=pdfops.cmd_to_text)

    to_html = sub.add_parser(
        "pdf2html",
        aliases=["to-html"],
        help="Convert a PDF to HTML.",
    )
    pdfops.add_to_html(to_html)
    to_html.set_defaults(func=pdfops.cmd_to_html)

    pdf_info = sub.add_parser(
        "pdfinfo",
        aliases=["info"],
        help="Show PDF metadata, page sizes and bookmarks.",
    )
    pdfops.add_info(pdf_info)
    pdf_info.set_defaults(func=pdfops.cmd_info)

    rotate = sub.add_parser("pdfrotate", help="Rotate pages in a PDF.")
    pdfops.add_rotate(rotate)
    rotate.set_defaults(func=pdfops.cmd_rotate)

    encrypt = sub.add_parser("pdfencrypt", help="Password-protect a PDF.")
    pdfops.add_encrypt(encrypt)
    encrypt.set_defaults(func=pdfops.cmd_encrypt)

    decrypt = sub.add_parser(
        "pdfdecrypt",
        aliases=["pdfunlock"],
        help="Remove a PDF password.",
    )
    pdfops.add_decrypt(decrypt)
    decrypt.set_defaults(func=pdfops.cmd_decrypt)

    watermark = sub.add_parser("pdfwatermark", help="Stamp text over PDF pages.")
    pdfops.add_watermark(watermark)
    watermark.set_defaults(func=pdfops.cmd_watermark)

    extract_images = sub.add_parser(
        "pdfextractimages",
        help="Extract embedded images from a PDF.",
    )
    pdfops.add_extract_images(extract_images)
    extract_images.set_defaults(func=pdfops.cmd_extract_images)

    ocr = sub.add_parser("pdfocr", help="OCR a scanned PDF with Tesseract/OCRmyPDF.")
    pdfops.add_ocr(ocr)
    ocr.set_defaults(func=pdfops.cmd_ocr)

    md2pdf = sub.add_parser("md2pdf", help="Convert Markdown to PDF.")
    convert.add_md2pdf(md2pdf)
    md2pdf.set_defaults(func=convert.cmd_md2pdf)

    md2docx = sub.add_parser("md2docx", help="Convert Markdown to DOCX.")
    convert.add_md2docx(md2docx)
    md2docx.set_defaults(func=convert.cmd_md2docx)

    md2html = sub.add_parser("md2html", help="Convert Markdown to HTML.")
    convert.add_md2html(md2html)
    md2html.set_defaults(func=convert.cmd_md2html)

    doctor_parser = sub.add_parser("doctor", help="Check every backend and dependency.")
    doctor.add_arguments(doctor_parser)
    doctor_parser.set_defaults(func=doctor.main)

    formats = sub.add_parser("formats", help="Print the supported conversion matrix.")
    formats.set_defaults(func=cmd_formats)

    return parser


def print_manual() -> None:
    print(
        """DOC-TOOLS — document and PDF toolkit

USAGE
  docs <command> [options]
  docs <command> --help
  docs doctor
  docs formats

Every command is also available as its own executable in ~/.local/bin.

PDF MERGE
  pdfmerge [files...]
      Merge PDFs in the current directory, or the files you list.
      Always writes:
        final.pdf       merged PDFs only, no TOC
        toc.pdf         TOC only, numbered for final.pdf
        final_toc.pdf   TOC followed by the merged PDFs
      Useful options: --out-dir DIR, --prefix NAME, --password PW,
      --skip-errors, --no-clobber, --legacy-names (also writes the old
      merged.pdf and merged_toc.pdf names).

DOCUMENT CONVERSION
  doc2pdf / docx2pdf [files...]
      Office documents, HTML, CSV, Markdown/TXT and images -> PDF.
      Options: -o/--output, -d/--out-dir, --no-clobber.
  pdf2docx [files...]
      PDF -> DOCX with layout reconstruction.
      Options: -o, --pages, --start, --end, --password.
  pdf2doc / pdf2odt
      PDF -> legacy DOC or ODT through DOCX + LibreOffice.
  md2pdf / md2docx / md2html
      Markdown -> PDF, DOCX or HTML, with --toc, --title and --css.
  img2pdf / to-pdf
      Images -> one PDF; --pagesize, --fit, --dpi, --border.

PDF OPERATIONS
  pdfsplit
      Split every N pages or by ranges: --every N, --pages RANGES.
  pdfselect
      Extract/reorder pages into one PDF: --pages 3,1-2.
  pdfcompress
      Ghostscript compression: --preset screen|ebook|printer|prepress.
  pdf2img / to-images
      Render pages to PNG/JPEG/WebP: --dpi, --format, --pages.
  pdf2txt / to-text
      Extract text with poppler; --layout, --pages.
  pdf2html / to-html
      Convert a PDF to HTML with poppler.
  pdfinfo
      Show pages, page sizes, metadata, encryption and bookmarks; --json.
      (docs info is an alias inside the umbrella command.)
  pdfrotate
      Rotate selected pages: --pages, --angle 90|180|270.
  pdfwatermark
      Stamp text over pages: --text, --pages, --opacity, --angle.
  pdfencrypt / pdfdecrypt / pdfunlock
      Add or remove a password; AES-256 by default.
  pdfextractimages
      Extract embedded images from a PDF.
  pdfocr
      OCR a scanned PDF with Tesseract (or OCRmyPDF if installed).

MAINTENANCE
  doctor
      Check Python modules, system commands and repo/user writable paths.
      --json for machine-readable output, --strict to fail on optional gaps.
  formats
      Print the supported conversion matrix.

EXAMPLES
  docs pdfmerge
  docs pdfmerge a.pdf b.pdf --prefix q3-
  docs docx2pdf report.docx -o build/report.pdf
  docs pdf2docx report.pdf --pages 1-10 -o report.docx
  docs pdfsplit big.pdf --every 10 -o parts
  docs pdfcompress big.pdf --preset ebook -o small.pdf
  docs pdf2img big.pdf --dpi 150 -o pages
  docs img2pdf pages/*.png -o pages.pdf
  docs pdfinfo --json big.pdf
  docs md2pdf README.md --toc -o README.pdf

Use "docs <command> --help" for the complete option list of a command.
"""
    )


def cmd_formats(_args: argparse.Namespace) -> int:
    info(
        """
Supported conversions
=====================
  DOCX/DOC/ODT/RTF/HTML/PPTX/XLSX/CSV      ->  PDF      (LibreOffice)
  Markdown/TXT                             ->  PDF      (WeasyPrint)
  Markdown                                 ->  DOCX     (LibreOffice HTML import)
  Markdown                                 ->  HTML     (Markdown + toolkit CSS)
  Images (PNG/JPEG/WebP/TIFF/BMP/GIF)      ->  PDF      (img2pdf)
  PDF                                      ->  DOCX     (pdf2docx)
  PDF                                      ->  DOC/ODT  (pdf2docx + LibreOffice)
  PDF                                      ->  TXT      (poppler pdftotext)
  PDF                                      ->  HTML     (poppler pdftohtml)
  PDF                                      ->  PNG/JPEG/WebP (poppler pdftoppm)

PDF operations
==============
  merge       merged.pdf + toc.pdf + merged_toc.pdf
  split       page files or page ranges
  select      extract/reorder pages into one PDF
  compress    Ghostscript screen/ebook/printer/prepress
  rotate      selected pages
  encrypt     AES-256/AES-128/RC4-128
  decrypt     remove a password
  info        pages, sizes, metadata, bookmarks
  extract     embedded images
  watermark   stamp text over selected pages
  ocr         scanned PDF -> image PDF with a text layer

Not offered
===========
  PDF -> PPTX/XLSX is not reliable. Convert to DOCX first, then use
  LibreOffice only if the layout is simple.
"""
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_runtime_dirs()
    parser = build_parser()
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        print_manual()
        return 0

    if args[0] in {"doc", "docs"}:
        args = args[1:]
        if not args:
            print_manual()
            return 0

    # The old wrappers used "-all"; argparse spells the same option "--all".
    args = ["--all" if item == "-all" else item for item in args]

    if args[0] in {"-h", "--help", "help", "list", "commands"}:
        if args[0] == "help" and len(args) > 1:
            args = [args[1], "--help"]
        else:
            print_manual()
            return 0
    if args[0] in {"-V", "--version"}:
        print("doc-tools 0.1.0")
        return 0

    command = args[0]
    if command in ALIASES:
        command = ALIASES[command]
        args[0] = command

    try:
        namespace = parser.parse_args(args)
        if not hasattr(namespace, "func"):
            parser.print_help()
            return 1
        return int(namespace.func(namespace) or 0)
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0
    except Exception as exc:
        if os.environ.get("DOC_TOOLS_DEBUG") == "1":
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("hint: set DOC_TOOLS_DEBUG=1 to see the full traceback", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
