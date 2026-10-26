# Installation and Package Management

**Status:** Verified against `install.sh` and the reference deployment.

## Purpose

This document describes how the repository is installed: package groups, AUR
handling, Stow behavior, service setup, generated-file seeding, verification,
and the legacy profile pipeline that remains in the tree.

## Scope

In scope:

- `install.sh` and its environment switches.
- Inline package groups and `packages/*.txt`.
- AUR helper bootstrap.
- GPU/CPU package detection.
- GNU Stow application and conflict handling.
- Installer side effects: local binaries, trash, shells, Python tools, XDG
  directories, services, groups, autotheme seed.
- Legacy `scripts/core/*`, `system/*`, and `state/*`.

Out of scope:

- Individual application configuration (covered by component documents).
- Package version pinning; `install.sh` installs current Arch packages.
- Secure boot, filesystem, kernel, or bootloader installation.

## Installer modes

`install.sh` is controlled by environment variables:

| Variable | Effect |
| --- | --- |
| `SKIP_PACMAN_UPDATE=1` | Skip `pacman -Syu` |
| `SKIP_OPTIONAL=1` | Skip optional Pacman group and optional AUR group |
| `SKIP_AUR=1` | Skip AUR helper bootstrap and all AUR packages |
| `SKIP_STOW=1` | Skip Stow, trash setup, shell setup, and autotheme seed |
| `NO_SERVICES=1` | Do not enable or start services |

Run as a normal user:

```bash
cd ~/dotfiles
./install.sh
```

The script refuses root, requires Arch Linux, `pacman`, and `sudo`, and keeps a
sudo timestamp alive during AUR builds.

## Package model

`install.sh` defines package groups as Bash arrays, then appends optional entries
from the package files.

| Group | Scope | Representative packages |
| --- | --- | --- |
| `PACMAN_CORE` | Base system, networking, audio, Bluetooth, power, portals, display manager, fonts | `base-devel`, `git`, `stow`, `networkmanager`, `pipewire`, `bluez`, `sddm`, `grub`, `sqlite`, `adwaita-*` |
| `PACMAN_HYPR` | Hyprland desktop and theming | `hyprland`, `hyprpaper`, `hypridle`, `hyprlock`, `hyprshot`, `hyprsunset`, `hyprpolkitagent`, `matugen`, `awww`, `python-pillow`, `waybar`, `wofi`, `kitty`, `thunar`, `dunst`, `grim`, `slurp`, `wl-clipboard`, `cliphist`, `imv`, `mpv`, `zathura*`, fonts |
| `PACMAN_DEV` | Development toolchain | `neovim`, `fish`, `starship`, `python`, `nodejs`, `npm`, `go`, `rust`, `clang`, `cmake`, `jdk-openjdk`, `maven`, `ripgrep`, `fd`, `fzf`, `htop`, `7zip`, `tesseract` |
| `PACMAN_APPS` | User applications | `firefox`, `chromium`, `libreoffice-fresh`, `vlc`, `gparted`, `imagemagick`, `ffmpeg`, `yt-dlp`, `opencode`, `gocryptfs`, `kwallet` |
| `PACMAN_DOCS` | Document/PDF toolkit backends | `poppler`, `ghostscript`, `qpdf`, `python-weasyprint` |
| `PACMAN_OPTIONAL` | Optional workloads | Docker, MariaDB, Valkey, Coturn, Cloudflared, security tools, OBS, Ollama, Tor Browser, `pandoc-cli` |
| `PACMAN_XORG` | Xorg/XWayland compatibility | `xorg-server`, XWayland helpers, legacy X utilities |
| `AUR_REQUIRED` | AUR essentials | `brave-bin`, `zen-browser-bin`, `visual-studio-code-bin`, `yay` |
| `AUR_OPTIONAL` | Optional AUR apps | `antigravity`, `burpsuite`, `cloudflare-warp-bin`, `dislocker`, `grub-customizer`, `gtk2`, `gvisor-bin`, `inkscape-bin`, `staruml` |

`install.sh` appends:

```bash
append_from_file PACMAN_CORE packages/pacman/base.txt
append_from_file PACMAN_HYPR packages/pacman/hyprland.txt
append_from_file AUR_OPTIONAL packages/aur/aur.txt
```

Then deduplicates each array. If no kernel package is present, `linux` is added
to `PACMAN_CORE`.

## AUR helper bootstrap

When neither `paru` nor `yay` is available and AUR is not skipped:

1. Clone `https://aur.archlinux.org/paru-bin.git` into
   `${XDG_CACHE_HOME:-$HOME/.cache}/dotfiles-aur`.
2. Build with `makepkg -si --noconfirm`.
3. Fall back to `yay-bin`.
4. If both fail, warn and skip AUR packages.

`install_aur_group()` prefers `paru`, then `yay`, and uses non-interactive
flags (`--skipreview` for Paru; answer flags for Yay).

## GPU and CPU package detection

`detect_gpu_packages()` scans `lspci -nn`:

| Detected vendor | Additional packages |
| --- | --- |
| NVIDIA | Kernel-matched `nvidia-open*`, kernel headers, `nvidia-utils`, `nvidia-settings`, `egl-wayland` |
| AMD | `mesa`, `vulkan-radeon`, `libva-utils` |
| Intel | `mesa`, `vulkan-intel`, `intel-media-driver`, `libva-intel-driver`, `libva-utils`, `intel-gpu-tools` |
| Always | `mesa`, `vulkan-icd-loader`, `libva` |

CPU microcode is added from `/proc/cpuinfo`: `intel-ucode` or `amd-ucode`.

## Stow behavior

`stow_all()` applies these packages to `$HOME`:

```text
dunst fish gtk htop hypr kitty local nvim opencode starship trash
waybar wofi xdg zathura
```

`stow_package()` executes:

```bash
stow --dir="$DOTFILES_DIR" --target="$HOME" --no-folding --restow <package>
```

Ignore patterns:

| Package | Ignored entries |
| --- | --- |
| `fish` | `fish_variables`, `secrets.fish`, `.gitignore` |
| `hypr` | `__pycache__`, `*.pyc`, `*.backup`, `battery-notify` |
| `trash` | `bin`, `scripts`, `systemd`, `config`, `install.sh`, `uninstall.sh`, `.gitignore`, `.stow-local-ignore`, `graphical-session.target.wants` |
| `xdg` | `user-dirs.dirs` |
| `local` | `venv`, `_run`, `__pycache__`, `*.pyc` (the installed toolkit venv lives under `~/.local/share/doctools/venv`) |

On conflict, the installer moves the existing target to
`<target>.pre-dotfiles.<timestamp>[.N]`, then retries up to five times. It
refuses to back up paths outside `$HOME`. If conflicts remain, it prints the
Stow dry-run output and records a failure.

Notes:

- `hypr/.config/hypr/themes/wallpapers/thumbs/` is not Stow-ignored. It is
  gitignored but can be linked by a Stow run.
- `local` is the active Stow package for the document/PDF toolkit. It contains
  `local/.local/bin/` (wrappers) and `local/.local/share/doctools/` (Python
  implementation and setup script). The old `.local/` duplicate was removed.
- `opencode`, `gtk-*`, `dunst`, `htop`, and `mimeapps.list` can remain real
  files/directories on an existing machine; `install.sh` backs them up, while
  plain `stow` aborts on conflicts.

## Installer side effects

### Local binaries

`install_local_bin_tools()` iterates over every executable in
`local/.local/bin/` (except `_run`) and symlinks it into `~/.local/bin`. This
includes `docs`, `doc`, `pdfmerge`, `docx2pdf`, `pdf2docx`, and the rest of the
toolkit. Existing files are backed up with the normal conflict mechanism.

`pdfmerge` and all other toolkit commands are therefore available directly on
`PATH` after installation. Run `docs --help` for the grouped command manual.
The shared `_run` launcher resolves the source code from the Stow package and
uses the venv at `~/.local/share/doctools/venv`; runtime state goes to
`~/.local/state/doctools/`.

### Trash runtime

`install_trash_system()`:

- Creates `~/.local/share/trash-system/{db,objects}`.
- Symlinks `safe-rm`, `trash`, and `trash-ui` into `~/.local/bin`.
- Creates `trash-age`, `trash-clean`, and `trash-notify` wrapper scripts.
- Initializes the SQLite database if missing.
- Writes systemd user drop-ins replacing hardcoded `ExecStart` paths.
- The installer later enables the timers when a user D-Bus session exists.

See [trash-management-system.md](trash-management-system.md).

### Shells

`configure_shells()`:

- Provides fallback `config.fish` and `open.fish` if Stow failed.
- Ensures `/usr/bin/fish` is in `/etc/shells`.
- Runs `chsh -s /usr/bin/fish` for the target user.
- If `zsh` exists, creates a minimal `~/.zshrc` with an OpenCode/local PATH
  line.

### Python document/PDF tooling

`install_python_tools()` creates:

```text
~/.local/share/doctools/venv
```

and installs:

```text
pypdf, reportlab, pdf2docx, img2pdf, weasyprint, markdown,
python-docx, pillow, cryptography
```

It verifies every import afterward and records `python:doc-tools` or
`python:doc-tools-verify` as an install failure if anything is missing.
The `python-weasyprint` system package supplies the Pango/Cairo runtime needed
by the venv's WeasyPrint.

### XDG user directories

`install_xdg_user_dirs()` copies `xdg/.config/user-dirs.dirs` to
`~/.config/user-dirs.dirs` as a real file, then creates `~/Downloads` and
`~/Pictures`.

### Services

System units, when present:

```text
NetworkManager bluetooth power-profiles-daemon acpid
systemd-timesyncd sshd valkey warp-svc
```

Display manager:

- Keep an already-enabled display manager.
- Otherwise enable `sddm` if available.

User units:

```text
pipewire.socket pipewire-pulse.socket wireplumber.service
xdg-user-dirs.service warp-taskbar.service
trash-age.timer trash-clean.timer trash-notify.timer
```

Docker and MariaDB are installed but intentionally left stopped.

### Groups

Adds the user to any existing group from:

```text
wheel audio video storage power docker procview adbusers
```

### Autotheme seed

After Stow, `install.sh` runs:

```bash
~/.config/hypr/scripts/wallpaper_switch.sh init
```

This creates the initial palette and generated surface files without touching
the live session. See
[autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md).

## Legacy pipeline

These files remain in the repository but are not called by `install.sh`.

### `scripts/core/detect.sh`

Prints JSON describing GPU and virtualization:

```json
{"gpu":"intel","env":"baremetal"}
```

GPU is detected by `lspci`; environment by `systemd-detect-virt`.

### `scripts/core/reconcile.sh`

Parses profile names from `system/manifest.yaml`, reads
`packages/pacman/<profile>.txt` and `packages/aur/<profile>.txt`, and writes
sorted unique package lists under `state/`.

The profile YAML files themselves are not read by this script.

### `scripts/core/apply.sh`

- Installs Paru if missing.
- Runs `reconcile.sh`.
- Installs resolved Pacman/AUR packages.
- Stows top-level directories containing `.config`, `.local`, `.cache`, or
  `.themes`.
- Enables PipeWire/WirePlumber.

It does not use the conflict-safe `stow_package()` from `install.sh`, so an
existing real configuration file can abort the Stow step.

### `scripts/bootstrap-tools.sh`

A convenience wrapper around
`local/.local/share/doctools/setup.sh`. It refreshes the toolkit venv and
Python dependencies without running the full installer. `install.sh` calls the
same setup logic directly through `install_python_tools()`.

## Reproduction

### Full automated installation

```bash
git clone https://github.com/AdityaAgrawal08/My-Arch-Linux-Configurations.git ~/dotfiles
cd ~/dotfiles
./install.sh
```

Then log out and back in.

### Lean installation

```bash
SKIP_PACMAN_UPDATE=1 SKIP_OPTIONAL=1 ./install.sh
```

### Packages only

```bash
SKIP_STOW=1 ./install.sh
```

### Manual Stow

```bash
cd ~/dotfiles
stow --target="$HOME" --no-folding --restow --ignore='venv$' --ignore='^_run$' \
  hypr waybar wofi kitty fish starship dunst gtk htop zathura \
  trash xdg local nvim opencode

~/.config/hypr/scripts/wallpaper_switch.sh init
```

## Verification

`install.sh` checks that these commands exist and exits non-zero if any are
missing:

```text
Hyprland hyprctl hyprpaper hypridle hyprlock hyprshot hyprsunset
hyprpolkitagent matugen awww awww-daemon waybar wofi kitty thunar dunst
cliphist wl-copy nm-applet blueman-applet pavucontrol fish nvim git stow
sqlite3 notify-send playerctl brightnessctl wpctl grim slurp zathura imv mpv
starship jq python3 gcc pkg-config magick ffmpeg ffprobe
doc docs pdfmerge docx2pdf pdf2docx pdftotext pdftoppm gs
```

It also runs `doc doctor` after installation and warns if required toolkit
backends are missing. It warns about missing `~/Downloads/open.wav`/`close.wav`
and notes that Neovim's pandoc fallback for PDF export still needs a LaTeX
engine; the preferred `docs` export path uses WeasyPrint and does not.

## Known limitations

- Several files hardcode `/home/aditya`: `hyprpaper.conf`, `hyprland.lua`,
  `power-menu.sh`, autotheme includes, `lid-sounds/*`, and Hyprlock’s source.
- `install.sh` does not Stow-ignore the wallpaper thumbnail cache.
- Plain `stow` conflicts with real `~/.config/opencode`, `gtk-*`, `dunst`,
  `htop`, and `mimeapps.list` on the reference deployment.
- `scripts/core/apply.sh` is not conflict-safe and can abort on an existing
  Dunst configuration file.
- `AUR_OPTIONAL` includes packages that may be unavailable or require
  interactive builds; use `SKIP_OPTIONAL=1` for a lean install.
- The full `PACMAN_XORG` group is installed even on a Wayland-only machine.
- The legacy `system/profiles/*.yaml` files are not used by the current
  installer.

## Related documentation

- [system-overview.md](system-overview.md)
- [reproduction-and-verification.md](reproduction-and-verification.md)
- [trash-management-system.md](trash-management-system.md)
- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
