# Verification record

Date: 2026-10-26
Scope: installed `local` Stow package and repo-level integration suite.

## What was exercised

```bash
cd ~/dotfiles
./tests/run_doc_tools.sh
docs doctor
docs --help
docs formats
```

The suite runs the real wrappers through `local/.local/bin` and the installed
venv at `~/.local/share/doctools/venv`.

## Results

| Check | Result |
| --- | --- |
| Stow package links wrappers into `~/.local/bin` | Pass |
| Installed venv imports all Python backends | Pass |
| `docs --help` grouped manual | Pass |
| `docs doctor` | Pass; optional `qpdf`, `pandoc`, `ocrmypdf` not installed in this verification run |
| Full integration suite | Pass; 25 tests |
| `pdfmerge` three outputs (`final.pdf`, `toc.pdf`, `final_toc.pdf`) | Pass |
| `final.pdf` contains no TOC | Pass |
| `toc.pdf` contains only the TOC | Pass |
| `final_toc.pdf` contains TOC + content | Pass |
| TOC page numbers, bookmarks, page labels | Pass |
| Rerun / prefix output exclusion | Pass |
| Old `final.pdf` backup migration | Pass |
| Unicode + long filenames | Pass |
| Encrypted input | Pass |
| Collision protection | Pass |
| `docx2pdf` from another cwd + custom output | Pass |
| `pdf2docx` custom output + legacy positional output | Pass |
| Markdown → PDF / DOCX / HTML | Pass |
| PDF → DOC / ODT | Pass |
| split / select / compress / rotate / watermark | Pass |
| encrypt / decrypt | Pass |
| PDF → images, images → PDF | Pass |
| PDF → text / HTML | Pass |
| metadata info | Pass |
| extract embedded images | Pass |
| OCR with Tesseract | Pass |
| `doc formats` | Pass |

## Isolation and installation

- Wrappers are installed via Stow into `~/.local/bin`.
- Python implementation is in `local/.local/share/doctools/doctools/`.
- Venv is `~/.local/share/doctools/venv`.
- Runtime temp/cache/LibreOffice/Python data is under
  `~/.local/state/doctools/`.
- `install.sh` installs `poppler`, `ghostscript`, `qpdf`, and
  `python-weasyprint`, then creates/verifies the venv.
- The old `.local/` duplicate tree and the old `~/.local/share/pdfmerge`
  installation were replaced; legacy files were backed up during migration.

## Known limitations

- PDF → PPTX/XLSX is intentionally not offered.
- PDF → DOCX is best-effort; scanned PDFs need `pdfocr` first.
- OCR creates an image PDF with a text layer; OCRmyPDF is preferred when
  available.
- `qpdf`, `pandoc`, and `ocrmypdf` are optional; commands report clear
  remediation or use fallbacks.
- PDF forms, attachments, and source bookmarks are not preserved by `pdfmerge`.
