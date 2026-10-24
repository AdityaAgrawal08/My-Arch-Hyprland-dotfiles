# Document and File Utilities

**Status:** Source verified. PDF conversion/merge runtime not exercised.

## Purpose

Defines the repository’s document conversion and file-opening utilities:

- `docx2pdf`
- `pdf2docx`
- `pdfmerge`
- Fish `open` function
- Zathura configuration
- XDG MIME and user-directory defaults

## Scope

In scope:

- `.local/bin/` and `local/.local/` utilities.
- `pdfmerge` implementation and Python environment.
- `fish/.config/fish/functions/open.fish`.
- `zathura/.config/zathura/zathurarc`.
- `xdg/.config/mimeapps.list`.
- `xdg/.config/user-dirs.dirs`.

Out of scope:

- LibreOffice internals.
- PDF format specification.
- Desktop environment file-manager integration beyond MIME defaults.

## File duplication

| Path | Status | Role |
| --- | --- | --- |
| `.local/bin/docx2pdf` | Source | DOCX → PDF wrapper |
| `.local/bin/pdf2docx` | Source | PDF → DOCX wrapper |
| `.local/bin/pdfmerge` | Source | PDF merge wrapper |
| `.local/share/pdfmerge/pdfmerge.py` | Source | PDF merge implementation |
| `local/.local/bin/pdfmerge` | Active Stow package | Same wrapper |
| `local/.local/share/pdfmerge/pdfmerge.py` | Active Stow package | Same implementation |

`install.sh` stows `local`, not `.local`. `.local` is an older duplicate.

`install_local_bin_tools()` symlinks only `docx2pdf` and `pdf2docx`.
`pdfmerge` is provided by the `local` Stow package.

## `docx2pdf`

Usage:

```bash
docx2pdf input.docx
docx2pdf input.docx output.pdf
docx2pdf -all file1.docx file2.docx ...
```

Behavior:

- Requires `libreoffice`.
- Runs `libreoffice --headless --convert-to pdf <input>`.
- LibreOffice writes `<input>.pdf` next to the input.
- A custom output path renames the generated file.
- Batch mode skips non-`.docx` and missing files.
- Single mode requires one or two arguments.
- Does not create missing output directories.
- Does not validate the produced PDF.

## `pdf2docx`

Usage:

```bash
pdf2docx input.pdf
pdf2docx input.pdf output.docx
pdf2docx -all file1.pdf file2.pdf ...
```

Behavior:

- Uses `~/.local/share/pdfmerge/venv/bin/pdf2docx`.
- `install.sh` installs `pdf2docx` into the `pdfmerge` venv.
- Single mode executes the venv binary with `convert <input> -o <output>`.
- Batch mode skips non-`.pdf` and missing files.

`scripts/bootstrap-tools.sh` creates a separate
`~/.local/share/pdf2docx/venv`, but `install.sh` does not use it.

## `pdfmerge`

Wrapper:

```bash
exec ~/.local/share/pdfmerge/venv/bin/python \
     ~/.local/share/pdfmerge/pdfmerge.py "$@"
```

Implementation:

- Scans the current working directory for `*.pdf` (case-insensitive).
- Sorts by filename.
- Excludes `final.pdf` and `.__pdfmerge_toc__.pdf`.
- Loads each PDF with `pypdf`.
- Builds an A4 table of contents with ReportLab:
  - Title “Table of Contents”.
  - One line per PDF: filename, dots, page number.
  - New TOC page when y < 50.
- Two-pass TOC:
  1. Build with `toc_pages=0`.
  2. Count generated TOC pages.
  3. Rebuild with the correct offset.
- Writes TOC pages, then all source pages.
- Adds a PDF outline item for each source file.
- Writes `final.pdf`.
- Removes the temporary TOC.
- Prints `final.pdf created`.

Dependencies: `pypdf`, `reportlab`, Python 3, and the venv created by
`install.sh`.

Limitations:

- Always writes `final.pdf` in the current directory; overwrites existing
  output.
- Processes every PDF in the directory, including unrelated files.
- No CLI options, recursion, encryption handling, or page-range selection.
- Page numbers are physical pages; front matter is not offset.
- TOC filenames are not escaped for ReportLab.
- Concurrent runs can race on `final.pdf` and the TOC temporary.
- Does not validate the output PDF.

## `open.fish`

`fish/.config/fish/functions/open.fish`:

- Requires at least one file.
- Skips missing files with a message.
- Chooses by extension:

| Extension | Application |
| --- | --- |
| `.pdf` | `zathura` |
| `.png .jpg .jpeg .webp .gif` | `imv` |
| `.mp4 .mkv .webm .mp3` | `mpv` |
| `.docx .pptx .xlsx` | `libreoffice` |
| other | `xdg-open` |

- Runs each command in the background with stdout/stderr suppressed.
- Uses extension mapping, not MIME detection.

## Zathura

`zathura/.config/zathura/zathurarc`:

```conf
set adjust-open "best-fit"
set scroll-page-aware true
set guioptions "s"
set scroll-step 50
set page-padding 10
set scroll-full-overlap 0.01
```

Behavior:

- Best-fit opening.
- Page-aware scrolling.
- Status bar visible.
- 50 px scroll steps.
- 10 px page padding.
- 1% full-page overlap.

Dependencies: `zathura` plus `zathura-pdf-poppler`, `zathura-djvu`, and
`zathura-ps` for supported formats.

## XDG MIME defaults

`xdg/.config/mimeapps.list`:

```ini
[Default Applications]
text/html=zen.desktop
x-scheme-handler/http=zen.desktop
x-scheme-handler/https=zen.desktop
x-scheme-handler/about=zen.desktop
x-scheme-handler/unknown=zen.desktop
x-scheme-handler/antigravity=antigravity.desktop

[Added Associations]
font/woff2=brave-browser.desktop;
```

- Zen is the default browser for HTML/HTTP/HTTPS/about/unknown.
- Antigravity handles its custom URI scheme.
- Brave is associated with WOFF2 fonts.
- Desktop files must exist:
  - `zen.desktop` from `zen-browser-bin`
  - `brave-browser.desktop` from `brave-bin`
  - `antigravity.desktop` from optional AUR `antigravity`

On the reference deployment, `~/.config/mimeapps.list` is a real file.

## XDG user directories

`xdg/.config/user-dirs.dirs`:

```bash
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_MUSIC_DIR="$HOME/"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_DESKTOP_DIR="$HOME/"
XDG_TEMPLATES_DIR="$HOME/"
XDG_PUBLICSHARE_DIR="$HOME/"
XDG_DOCUMENTS_DIR="$HOME/"
XDG_VIDEOS_DIR="$HOME/"
XDG_PROJECTS_DIR="$HOME/"
```

Only Downloads and Pictures are separate. `install.sh`:

- Copies the file to `~/.config/user-dirs.dirs` as a real file.
- Creates `~/Downloads` and `~/Pictures`.
- Ignores the file during Stow so `xdg-user-dirs-update` cannot dirty the
  repository.

## Dependencies

- `libreoffice-fresh` for `docx2pdf`
- Python + `pypdf`, `reportlab`, `pdf2docx`
- `zathura` and format plugins
- `imv`, `mpv`, `xdg-utils`
- Desktop files for Zen/Brave/Antigravity
- Font packages for document rendering

## Reproduction

```bash
sudo pacman -S --needed libreoffice-fresh python imagemagick \
  zathura zathura-pdf-poppler zathura-djvu zathura-ps \
  imv mpv xdg-utils

cd ~/dotfiles
stow --target="$HOME" --no-folding local xdg zathura

mkdir -p ~/.local/share/pdfmerge
python3 -m venv ~/.local/share/pdfmerge/venv
~/.local/share/pdfmerge/venv/bin/pip install pypdf reportlab pdf2docx

ln -sfn ~/dotfiles/.local/bin/docx2pdf ~/.local/bin/docx2pdf
ln -sfn ~/dotfiles/.local/bin/pdf2docx ~/.local/bin/pdf2docx
```

## Verification

```bash
command -v docx2pdf pdf2docx pdfmerge zathura imv mpv libreoffice xdg-open
~/.local/share/pdfmerge/venv/bin/python -c 'import pypdf, reportlab, pdf2docx'
zathura --version
```

Do not run `pdfmerge --help` in a directory containing PDFs. The script ignores
arguments, scans the current directory, and writes `final.pdf`.

## Known limitations

- `.local/` and `local/` duplicate the PDF tools; only `local/` is stowed.
- `docx2pdf` depends on LibreOffice output behavior and does not validate
  conversion.
- `pdf2docx` relies on the venv created by `install.sh`.
- `pdfmerge` always scans the current directory and overwrites `final.pdf`.
- `open.fish` uses extension mapping.
- MIME associations depend on optional desktop files.
- Most XDG user directories point at `$HOME`.

## Related documentation

- [terminal-shell-and-prompt.md](terminal-shell-and-prompt.md)
- [system-overview.md](system-overview.md)
- [installation-and-package-management.md](installation-and-package-management.md)
