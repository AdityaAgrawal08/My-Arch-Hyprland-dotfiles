#!/usr/bin/env python3
"""Integration tests for the repo-local document toolkit."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "local" / ".local" / "bin"
TMP = ROOT / "state" / "doc-tools-tests"
FIXTURES = ROOT / "state" / "doc-tools-fixtures"
VENV_PY = (
    Path(
        os.environ.get(
            "DOC_TOOLS_VENV",
            Path.home() / ".local" / "share" / "doctools" / "venv",
        )
    )
    / "bin"
    / "python"
)


def page_count(path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)


def page_labels(path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [reader.page_labels[index] for index in range(len(reader.pages))]


def layout_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout


def toc_page_for(text: str, name: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith(name):
            return line.rsplit(None, 1)[-1]
    raise AssertionError(f"{name!r} not found in TOC text:\n{text}")


class DocToolsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TMP.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [str(VENV_PY), str(ROOT / "tests" / "make_doc_fixtures.py"), str(FIXTURES)],
            cwd=ROOT,
            check=True,
        )

    def setUp(self) -> None:
        self.case = Path(tempfile.mkdtemp(prefix="case-", dir=TMP))

    def tearDown(self) -> None:
        shutil.rmtree(self.case, ignore_errors=True)

    def copy(self, *names: str) -> None:
        for name in names:
            shutil.copy2(FIXTURES / name, self.case / name)

    def run_tool(
        self,
        tool: str,
        *args: str,
        cwd: Path | None = None,
        expect: int = 0,
        timeout: int = 300,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [str(BIN / tool), *map(str, args)],
            cwd=str(cwd or self.case),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != expect:
            self.fail(
                f"{tool} returned {result.returncode}, expected {expect}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result


class TestPdfMerge(DocToolsTestCase):
    def test_three_outputs_and_toc(self) -> None:
        self.copy("alpha.pdf", "beta.pdf", "gamma.pdf")
        self.run_tool("pdfmerge")

        for name in ("final.pdf", "toc.pdf", "final_toc.pdf"):
            self.assertTrue((self.case / name).is_file(), name)

        merged = page_count(self.case / "final.pdf")
        toc = page_count(self.case / "toc.pdf")
        combined = page_count(self.case / "final_toc.pdf")
        self.assertEqual(merged, 6)
        self.assertGreaterEqual(toc, 1)
        self.assertEqual(combined, merged + toc)

        from pypdf import PdfReader

        toc_text = layout_text(self.case / "toc.pdf")
        self.assertEqual(toc_page_for(toc_text, "alpha.pdf"), "1")
        self.assertEqual(toc_page_for(toc_text, "beta.pdf"), "3")
        self.assertEqual(toc_page_for(toc_text, "gamma.pdf"), "6")

        embedded_text = layout_text(self.case / "final_toc.pdf")
        self.assertEqual(toc_page_for(embedded_text, "alpha.pdf"), "2")
        self.assertEqual(toc_page_for(embedded_text, "beta.pdf"), "4")
        self.assertEqual(toc_page_for(embedded_text, "gamma.pdf"), "7")

        labels = page_labels(self.case / "final_toc.pdf")
        self.assertEqual(labels[0], "i")
        self.assertEqual(labels[1], "1")
        self.assertEqual(labels[-1], "6")

        outline = PdfReader(str(self.case / "final_toc.pdf")).outline
        titles = [item.get("/Title") for item in outline if isinstance(item, dict)]
        self.assertIn("Table of Contents", titles)
        self.assertIn("alpha.pdf", titles)
        self.assertIn("beta.pdf", titles)
        self.assertIn("gamma.pdf", titles)

    def test_rerun_and_prefix_do_not_merge_prior_outputs(self) -> None:
        self.copy("alpha.pdf", "beta.pdf", "gamma.pdf")
        self.run_tool("pdfmerge")
        self.run_tool("pdfmerge")
        self.assertEqual(page_count(self.case / "final.pdf"), 6)

        self.run_tool("pdfmerge", "--prefix", "leg-")
        self.assertEqual(page_count(self.case / "leg-final.pdf"), 6)
        self.assertEqual(page_count(self.case / "leg-final_toc.pdf"), 7)

    def test_explicit_order_is_preserved(self) -> None:
        self.copy("alpha.pdf", "beta.pdf", "gamma.pdf")
        self.run_tool(
            "pdfmerge",
            "beta.pdf",
            "alpha.pdf",
            "gamma.pdf",
            "--prefix",
            "ordered-",
        )
        text = layout_text(self.case / "ordered-toc.pdf")
        beta_at = text.index("beta.pdf")
        alpha_at = text.index("alpha.pdf")
        gamma_at = text.index("gamma.pdf")
        self.assertLess(beta_at, alpha_at)
        self.assertLess(alpha_at, gamma_at)
        self.assertEqual(toc_page_for(text, "beta.pdf"), "1")
        self.assertEqual(toc_page_for(text, "alpha.pdf"), "4")
        self.assertEqual(toc_page_for(text, "gamma.pdf"), "6")

    def test_unicode_and_long_filenames(self) -> None:
        self.copy(
            "résumé.pdf",
            "日本語のファイル.pdf",
            "a-very-long-filename-that-should-not-overflow-the-table-of-contents-line-in-a4-page.pdf",
        )
        self.run_tool("pdfmerge")
        self.assertEqual(page_count(self.case / "final.pdf"), 3)
        labels = page_labels(self.case / "final_toc.pdf")
        self.assertEqual(labels, ["i", "1", "2", "3"])

        text = layout_text(self.case / "toc.pdf")
        self.assertIn("résumé.pdf", text)
        self.assertIn("日本語のファイル.pdf", text)

    def test_encrypted_input(self) -> None:
        self.copy("encrypted.pdf")
        result = self.run_tool("pdfmerge", expect=1)
        self.assertIn("password", result.stderr.lower())

        self.run_tool("pdfmerge", "--password", "secret")
        self.assertEqual(page_count(self.case / "final.pdf"), 2)

    def test_skip_errors_and_dry_run(self) -> None:
        self.copy("alpha.pdf", "broken.pdf")
        result = self.run_tool("pdfmerge", "--skip-errors")
        self.assertIn("skipping", result.stderr.lower())
        self.assertEqual(page_count(self.case / "final.pdf"), 2)

        dry = self.case / "dry"
        dry.mkdir()
        self.run_tool("pdfmerge", "--dry-run", "--skip-errors", "--out-dir", str(dry))
        self.assertFalse((dry / "final.pdf").exists())

    def test_collision_with_real_source_name(self) -> None:
        self.copy("alpha.pdf")
        shutil.copy2(self.case / "alpha.pdf", self.case / "toc.pdf")
        result = self.run_tool("pdfmerge", expect=1)
        self.assertIn("toc.pdf", result.stderr)
        self.assertIn("does not look like a pdfmerge output", result.stderr)

    def test_dry_run_does_not_move_old_final(self) -> None:
        self.copy("alpha.pdf")
        shutil.copy2(self.case / "alpha.pdf", self.case / "final.pdf")
        self.run_tool("pdfmerge", "--dry-run", "--skip-errors")
        self.assertTrue((self.case / "final.pdf").is_file())
        self.assertFalse(list(self.case.glob("final.pdf.pre-doctools.*")))

    def test_old_final_pdf_is_not_remerged(self) -> None:
        self.copy("alpha.pdf")
        shutil.copy2(self.case / "alpha.pdf", self.case / "final.pdf")
        result = self.run_tool("pdfmerge")
        self.assertIn("backed up", result.stderr.lower())
        self.assertEqual(page_count(self.case / "final.pdf"), 2)
        self.assertTrue(list(self.case.glob("final.pdf.pre-doctools.*")))

    def test_no_clobber_and_legacy_names(self) -> None:
        self.copy("alpha.pdf", "beta.pdf")
        self.run_tool("pdfmerge")
        self.run_tool("pdfmerge", "--no-clobber", expect=1)
        self.run_tool("pdfmerge", "--legacy-names", "--prefix", "legacy-")
        self.assertTrue((self.case / "legacy-merged.pdf").is_file())
        self.assertTrue((self.case / "legacy-merged_toc.pdf").is_file())
        self.assertEqual(
            (self.case / "legacy-final.pdf").read_bytes(),
            (self.case / "legacy-merged.pdf").read_bytes(),
        )
        self.assertEqual(
            (self.case / "legacy-final_toc.pdf").read_bytes(),
            (self.case / "legacy-merged_toc.pdf").read_bytes(),
        )


class TestConversions(DocToolsTestCase):
    def test_docx2pdf_from_other_directory(self) -> None:
        source_dir = self.case / "src"
        other = self.case / "other"
        source_dir.mkdir()
        other.mkdir()
        shutil.copy2(FIXTURES / "sample.docx", source_dir / "sample.docx")

        self.run_tool("docx2pdf", "../src/sample.docx", cwd=other)
        self.assertTrue((source_dir / "sample.pdf").is_file())
        self.assertGreaterEqual(page_count(source_dir / "sample.pdf"), 1)

        self.run_tool("docx2pdf", "../src/sample.docx", "-o", "deep/out.pdf", cwd=other)
        self.assertTrue((other / "deep" / "out.pdf").is_file())

    def test_docx2pdf_legacy_forms(self) -> None:
        self.copy("sample.docx")
        shutil.copy2(self.case / "sample.docx", self.case / "second.docx")

        self.run_tool("docx2pdf", "sample.docx", "legacy.pdf")
        self.assertTrue((self.case / "legacy.pdf").is_file())

        self.run_tool("docx2pdf", "-all", "sample.docx", "second.docx")
        self.assertTrue((self.case / "sample.pdf").is_file())
        self.assertTrue((self.case / "second.pdf").is_file())

    def test_pdf2docx_custom_output(self) -> None:
        self.copy("alpha.pdf")
        self.run_tool("pdf2docx", "alpha.pdf", "-o", "custom.docx")
        self.assertTrue((self.case / "custom.docx").is_file())
        with zipfile.ZipFile(self.case / "custom.docx") as archive:
            self.assertIn("word/document.xml", archive.namelist())

    def test_pdf2docx_legacy_positional_output(self) -> None:
        self.copy("alpha.pdf")
        self.run_tool("pdf2docx", "alpha.pdf", "legacy.docx")
        self.assertTrue((self.case / "legacy.docx").is_file())

    def test_markdown_to_pdf_and_docx(self) -> None:
        self.copy("sample.md")
        self.run_tool("md2pdf", "sample.md", "-o", "sample.pdf")
        self.assertGreaterEqual(page_count(self.case / "sample.pdf"), 1)

        self.run_tool("md2docx", "sample.md", "-o", "sample.docx")
        with zipfile.ZipFile(self.case / "sample.docx") as archive:
            self.assertIn("word/document.xml", archive.namelist())

        self.run_tool("md2html", "sample.md", "-o", "sample.html")
        html_text = (self.case / "sample.html").read_text(encoding="utf-8")
        self.assertIn("Doc-tools Markdown", html_text)
        self.assertIn("<h1", html_text)

    def test_doc2pdf_image_and_markdown(self) -> None:
        self.copy("scan.png", "sample.md")
        self.run_tool("doc2pdf", "scan.png", "-o", "scan.pdf")
        self.assertEqual(page_count(self.case / "scan.pdf"), 1)

        self.run_tool("doc2pdf", "sample.md", "-o", "sample.pdf")
        self.assertGreaterEqual(page_count(self.case / "sample.pdf"), 1)

    def test_pdf_to_doc_and_odt(self) -> None:
        self.copy("gamma.pdf")
        self.run_tool("pdf2doc", "gamma.pdf", "-o", "gamma.doc")
        self.assertTrue((self.case / "gamma.doc").is_file())
        self.run_tool("pdf2odt", "gamma.pdf", "-o", "gamma.odt")
        self.assertTrue((self.case / "gamma.odt").is_file())


class TestPdfOperations(DocToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.copy("alpha.pdf", "beta.pdf")

    def test_split_and_select(self) -> None:
        self.run_tool("pdfsplit", "alpha.pdf", "--every", "1", "-o", "split")
        self.assertEqual(len(list((self.case / "split").glob("*.pdf"))), 2)

        self.run_tool("pdfsplit", "alpha.pdf", "--pages", "1-2", "-o", "ranges")
        self.assertEqual(
            len(list((self.case / "ranges").glob("*.pdf"))),
            1,
        )

        self.run_tool("pdfselect", "beta.pdf", "--pages", "3,1", "-o", "selected.pdf")
        self.assertEqual(page_count(self.case / "selected.pdf"), 2)

    def test_compress_rotate_encrypt_decrypt(self) -> None:
        self.run_tool(
            "pdfcompress", "alpha.pdf", "--preset", "ebook", "-o", "compressed.pdf"
        )
        self.assertTrue((self.case / "compressed.pdf").is_file())

        self.run_tool("pdfrotate", "alpha.pdf", "--angle", "90", "-o", "rotated.pdf")
        from pypdf import PdfReader

        self.assertEqual(
            PdfReader(str(self.case / "rotated.pdf")).pages[0].rotation, 90
        )

        self.run_tool(
            "pdfencrypt", "rotated.pdf", "-p", "secret", "-o", "encrypted.pdf"
        )
        self.run_tool(
            "pdfdecrypt",
            "encrypted.pdf",
            "-p",
            "secret",
            "-o",
            "decrypted.pdf",
        )
        self.assertEqual(page_count(self.case / "decrypted.pdf"), 2)

    def test_watermark(self) -> None:
        self.run_tool(
            "pdfwatermark",
            "alpha.pdf",
            "--text",
            "CONFIDENTIAL",
            "--pages",
            "1",
            "-o",
            "watermarked.pdf",
        )
        self.assertEqual(page_count(self.case / "watermarked.pdf"), 2)
        from pypdf import PdfReader

        pages = PdfReader(str(self.case / "watermarked.pdf")).pages
        self.assertIn("CONFIDENTIAL", pages[0].extract_text())
        self.assertNotIn("CONFIDENTIAL", pages[1].extract_text())

    def test_images_text_html_info(self) -> None:
        self.run_tool("pdf2img", "alpha.pdf", "--dpi", "72", "-o", "pngs")
        self.assertEqual(len(list((self.case / "pngs").glob("*.png"))), 2)

        self.run_tool(
            "pdf2img", "alpha.pdf", "--dpi", "72", "--format", "webp", "-o", "webp"
        )
        self.assertEqual(len(list((self.case / "webp").glob("*.webp"))), 2)

        pngs = sorted((self.case / "pngs").glob("*.png"))
        self.run_tool("img2pdf", *map(str, pngs), "-o", "images.pdf")
        self.assertEqual(page_count(self.case / "images.pdf"), 2)

        self.run_tool(
            "img2pdf",
            str(pngs[0]),
            "--pagesize",
            "A4",
            "--fit",
            "fill",
            "-o",
            "a4.pdf",
        )
        from pypdf import PdfReader

        box = PdfReader(str(self.case / "a4.pdf")).pages[0].mediabox
        self.assertAlmostEqual(float(box.width), 595.28, delta=1.0)
        self.assertAlmostEqual(float(box.height), 841.89, delta=1.0)

        self.run_tool("pdf2txt", "alpha.pdf", "-o", "alpha.txt")
        self.assertIn("alpha page 1", (self.case / "alpha.txt").read_text())

        self.run_tool("pdf2html", "alpha.pdf", "-o", "alpha.html")
        self.assertTrue((self.case / "alpha.html").is_file())

        result = self.run_tool("pdfinfo", "--json", "alpha.pdf")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["pages"], 2)

    def test_extract_images_and_ocr(self) -> None:
        self.run_tool("doc2pdf", str(FIXTURES / "scan.png"), "-o", "scan.pdf")
        self.run_tool("pdfextractimages", "scan.pdf", "-o", "extracted")
        self.assertGreaterEqual(len(list((self.case / "extracted").iterdir())), 1)

        if not shutil.which("tesseract"):
            self.skipTest("tesseract is not installed")
        self.run_tool("pdfocr", "scan.pdf", "-o", "ocr.pdf", timeout=300)
        text = subprocess.run(
            ["pdftotext", str(self.case / "ocr.pdf"), "-"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout
        self.assertIn("OCR", text)


class TestDoctorAndFormats(DocToolsTestCase):
    def test_docs_help_lists_commands(self) -> None:
        result = self.run_tool("docs", "--help")
        for token in (
            "final.pdf",
            "toc.pdf",
            "final_toc.pdf",
            "doc2pdf",
            "pdf2docx",
            "md2html",
            "pdfsplit",
            "pdfcompress",
            "pdfocr",
            "doctor",
        ):
            self.assertIn(token, result.stdout)

    def test_doctor(self) -> None:
        result = self.run_tool("doc", "doctor")
        self.assertIn("required", result.stdout)
        self.assertIn("writable", result.stdout.lower())

    def test_formats(self) -> None:
        result = self.run_tool("doc", "formats")
        self.assertIn("PDF", result.stdout)
        self.assertIn("DOCX", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
