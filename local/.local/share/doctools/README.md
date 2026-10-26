# doc-tools

Repository-managed document and PDF toolkit.

The implementation lives in this directory
(`local/.local/share/doctools/`). The `local` Stow package links the command
wrappers into `~/.local/bin`; `install.sh` creates the Python venv at
`~/.local/share/doctools/venv`. Runtime state is kept in
`~/.local/state/doctools/`.

## Commands

```bash
docs --help                 # grouped manual for every command
docs <command> --help       # complete options for one command
docs doctor                 # dependency/health check
docs formats                # supported conversion matrix
```

The main command set:

```text
pdfmerge
doc2pdf / docx2pdf
pdf2docx / pdf2doc / pdf2odt
md2pdf / md2docx / md2html
pdfsplit / pdfselect / pdfcompress
pdf2img / img2pdf / pdf2txt / pdf2html / pdfinfo
pdfrotate / pdfwatermark / pdfencrypt / pdfdecrypt
pdfextractimages / pdfocr
```

## pdfmerge output

```text
final.pdf       merged PDFs only, no TOC
toc.pdf         TOC only, numbered for final.pdf
final_toc.pdf   TOC followed by the merged PDFs
```

`--legacy-names` additionally writes `merged.pdf` and `merged_toc.pdf` for old
scripts.

## Environment

`install.sh` installs the system backends and calls `setup.sh`. To refresh only
the Python environment:

```bash
cd ~/dotfiles
./scripts/bootstrap-tools.sh
```

Manual setup:

```bash
~/.local/share/doctools/setup.sh
```

The venv contains `pypdf`, `reportlab`, `pdf2docx`, `img2pdf`, `weasyprint`,
`markdown`, `python-docx`, `pillow`, and `cryptography`.

## Verification

```bash
docs doctor
cd ~/dotfiles
./tests/run_doc_tools.sh
```

The integration suite covers all commands, including the three `pdfmerge`
outputs, Unicode filenames, encrypted PDFs, conversions, page/image operations,
watermarking, encryption, and OCR.

## Documentation

The authoritative component documentation is
[`docs/document-and-file-utilities.md`](../../../../docs/document-and-file-utilities.md).
