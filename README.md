# 🌌 Arch Linux Configurations & Custom CAS-Trash System

<div align="center">

![Arch Linux](https://img.shields.io/badge/OS-Arch%20Linux-blue?style=for-the-badge&logo=arch-linux&logoColor=white)
![Compositor](https://img.shields.io/badge/Compositor-Hyprland-85c1e9?style=for-the-badge&logo=wayland&logoColor=white)
![Shell](https://img.shields.io/badge/Shell-Fish-4ea94b?style=for-the-badge&logo=fishshell&logoColor=white)
![Editor](https://img.shields.io/badge/Editor-Neovim-007acc?style=for-the-badge&logo=neovim&logoColor=white)
![Prompt](https://img.shields.io/badge/Prompt-Starship-ff5f00?style=for-the-badge&logo=starship&logoColor=white)
![Status Bar](https://img.shields.io/badge/Status_Bar-Waybar-2c3e50?style=for-the-badge)

A premium, highly-automated dotfiles repository for Arch Linux, featuring a custom **Hyprland Wayland Compositor** desktop, automated hardware and profile-based configuration engines, and a custom **Content-Addressable Storage (CAS) Trash Management System**.

[Overview](#-overview) • [Architecture](#%EF%B8%8F-repository-architecture) • [Components](#-system-components) • [Trash System](#-cas-trash-management-system) • [Installation](#-installation-guide) • [Troubleshooting](#-troubleshooting)

</div>

---

## 🔍 Overview

This repository contains curated, modern dotfiles engineered for performance, minimalism, and aesthetic excellence. It transitions away from standard static dotfiles in favor of an **active, environment-aware configuration suite** that dynamically adapts to hardware (GPUs, Virtual Machines vs. Bare-Metal) and organizes software deployment via clean profiles.

---

## 🛠️ Repository Architecture

Our dotfiles utilize an intelligent, profile-based provisioning system. Rather than linking files blindly, a modular shell runner detects hardware, reconciles package lists, and applies links cleanly.

```
.
├── fish/                       # Fish shell configs & environment wrappers
├── hypr/                       # Hyprland, Hypridle, and Hyprlock suites
├── lid-sounds/                 # Hardware state listening hook scripts
├── local/                      # Document/PDF toolkit Stow package
├── nvim/                       # Extensible Lua-based Neovim development environment
├── packages/                   # Declarative package lists (pacman/aur) divided by profile
│   ├── pacman/
│   └── aur/
├── scripts/                    # Orchestration engines
│   ├── core/
│   │   ├── detect.sh           # Hardware and virtualization sensing
│   │   ├── reconcile.sh        # Profile manifest compiler
│   │   └── apply.sh            # Dynamic Stow-based link applicator
│   └── bootstrap-tools.sh      # Document/PDF toolkit venv setup
├── starship/                   # Starship shell prompt configuration
├── system/                     # Repository declarations
│   └── manifest.yaml           # Active deployment profile definitions
├── trash/                      # Content-Addressable Storage (CAS) Trash System
├── waybar/                     # Rich modern status bar with system monitors
├── wofi/                       # Smooth glassmorphic application launcher
└── zathura/                    # Keyboard-optimized document viewer
```

### ⚙️ Automation Engines

*   **`scripts/core/detect.sh` (Hardware Sensing):** Automatically inspects `lspci` to recognize GPU drivers (`nvidia`, `amd`, `intel`) and queries `systemd-detect-virt` to distinguish between VM guest instances and physical `baremetal` installations, saving state parameters to a JSON object.
*   **`scripts/core/reconcile.sh` (Profile Solver):** Reads [system/manifest.yaml](file:///home/aditya/dotfiles/system/manifest.yaml), extracts targeted profiles (such as `base` and `hyprland`), matches corresponding `.txt` package sheets, merges duplicate packages, and writes resolved files.
*   **`scripts/core/apply.sh` (Link Orchestrator):** Solves system symlinks dynamically using GNU Stow, safely ignoring system files like `state/`, `logs/`, or `.git/`, ensuring custom configurations reside correctly inside `$HOME`.

---

## 🖥️ System Components

### 🪟 Hyprland & Desktop Experience
*   **Hyprland:** A smooth, highly responsive, dynamic tiling Wayland compositor configured with physics-based animations, custom window rules, and a focus-centric workspace layout.
*   **Hyprlock & Hypridle:** Integrated screen locking and power-saving daemons that react immediately to session idle notifications, keeping power consumption minimal.
*   **Waybar:** A top-screen glassmorphic status bar displaying current workspace indicators, resources (CPU, Memory, Disk), dynamic audio volume level, time-date displays, and bluetooth adapter properties via custom background scripts ([waybar/.config/waybar/bluetooth.sh](file:///home/aditya/dotfiles/waybar/.config/waybar/bluetooth.sh)).
*   **Wofi Launcher:** A high-speed application launcher custom-styled with subtle hover highlights, blurred backdrops, and modern list selections.
*   **Autotheme:** `Super + T` opens a Wofi wallpaper picker. Selecting an image regenerates one Material You dark palette from it and renders every themed surface: Waybar, Wofi, Kitty, Dunst, GTK 3/4, Hyprlock and the live Hyprland border colours. See [Autotheme & Wallpapers](#-autotheme--wallpapers) below.

### 🎨 Autotheme & Wallpapers

Wallpapers live in `hypr/.config/hypr/themes/wallpapers/assets/`. Drop a
`.jpg`, `.jpeg`, `.png`, `.webp` or `.gif` in there; it appears in the picker on
the next open. The generated files are outside the repository, under
`~/.cache/autotheme/` and the Dunst drop-in directory, so Stow never conflicts
with them.

For the full engine install `matugen`, `awww` and `python-pillow` (all in the
official `extra` repository; `install.sh` includes them):

```bash
sudo pacman -S --needed matugen awww python-pillow
```

Without `matugen` the scripts still work using the static dark fallback, and
without `awww` they fall back to `hyprpaper` (static images only).

The pipeline is:

1. `awww` paints the wallpaper with a random wave/wipe transition. Animated
   GIFs play normally. `hyprpaper` remains a fallback if `awww` is unavailable.
2. `lib/scene.py` builds a 64×64 attention map, derives tone/colour/structure
   metrics, and selects a palette strategy. It is Pillow-only: no model, no
   daemon, no persistent memory.
3. `lib/vibrant.py` extracts the wallpaper's most vivid hues, weights them by
   attention and region, and writes a scene-selected seed colour. A large
   smooth sky no longer outvotes a small saturated subject; a genuinely
   blue-dominant image still keeps its blue.
4. `matugen` generates the dark Material You surfaces from the seed. Your own
   `~/.config/matugen/config.toml` is never touched.
5. `lib/build_theme.py` merges the two, aligns the surface hue, checks
   contrast and writes `~/.cache/autotheme/theme.json`.
6. `lib/render.py` renders Kitty, Waybar, Wofi, Dunst, GTK and Hyprlock
   templates. The live surfaces are reloaded without restarting Wayland.

Kitty has two generated variants: opaque uses a pure black background, while
transparent uses a wallpaper-derived tint. `terminal opaque|transparent|toggle`
switches between them and both variants are refreshed whenever the wallpaper
changes, so transparency stays live.

Useful commands:

```bash
~/.config/hypr/scripts/wallpaper_switch.sh apply ~/Pictures/wall.png
~/.config/hypr/scripts/wallpaper_switch.sh restore
~/.config/hypr/scripts/wallpaper_switch.sh regenerate
~/.config/hypr/scripts/wallpaper_switch.sh list-json | jq '.[].name'
~/.config/hypr/scripts/wallpaper_switch.sh scene | jq '{tags, strategy, seed}'
~/.config/hypr/scripts/wallpaper_switch.sh explain
~/.config/hypr/scripts/wallpaper_switch.sh doctor
```

Scene analysis is enabled by default. Set `AUTOTHEME_SCENE=off` to restore the
pre-scene statistical palette. The scene layer adds roughly 20–40 ms of CPU
per wallpaper change and no measurable peak memory; it runs in the existing
`vibrant.py` process and exits. It has no model download and no background
service.

If `matugen` is missing or fails, a static dark palette is rendered from the
same templates. Grayscale wallpapers get a neutral monochrome theme instead of
matugen's blue fallback. Neovim, Fish, Starship and Kitty colours all follow the
generated palette; Neovim reloads its highlight groups when the theme changes.

### 🐚 Terminal & Editors
*   **Fish Shell**: Modern, interactive shell equipped with live syntax highlighting, autosuggestions based on command history, and custom functional wrappers.
*   **Starship Prompt**: Fast, sleek cross-shell terminal prompt configured with dynamic Git status tags, runtime environment symbols, and execution timers.
*   **Neovim (with Document Editing Mode)**: A personalized Lua development setup. When you open a Markdown (`.md`) or text (`.txt`) file, Neovim automatically activates a dedicated **Document Editing Mode**:
    *   **Focus/Zen Mode**: Press `<leader>mf` (Space + `m` + `f`) to toggle Focus Mode. This centers your cursor vertically (typewriter style) and dims surrounding text block areas.
    *   **Formatting Toolbar**: Press `<leader>mt` (Space + `m` + `t`) to open the formatting command palette (Bold, Italic, headings, tables, links, lists).
    *   **Formatting Shortcuts**: Select text and press `<C-b>` for Bold, `<C-i>` for Italic, or `<C-Space>` on a line to toggle checklists (`[ ]` <-> `[x]`).
    *   **Image Pasting**: Copy an image to your clipboard and press `<leader>mi` (Space + `m` + `i`) to save it instantly to `assets/` and insert its markdown reference.
    *   **Image Resizing**: Position your cursor on an image line and type `:ImageResize 50` (or `:ImageResize 300x200`) to physically resize the image.
    *   **Live Preview**: Press `<leader>mp` (Space + `m` + `p`) to open a synchronized live preview in your web browser.
    *   **Pandoc Exporting**: Press `<leader>me` (Space + `m` + `e`) to open the export menu and convert your document to PDF, HTML, or DOCX in the background.
*   **Zathura**: A minimalist, keyboard-centric document viewer optimized for rapid PDF browsing. Integrates with a unique Fish shell alias `open` which maps documents directly to Zathura.

### 🔊 Lid-Sound and Hook Triggers
A custom background listener maps physical system triggers:
*   **Lid Closed:** Locks the active session safely utilizing `hyprlock`.
*   **Lid Opened:** Authenticates, plays an initialization audio sound effect (`open.wav`) utilizing `mpv` backgrounds, and wakes displays dynamically.

### 🗃️ Document & PDF Toolkit
The `local` Stow package ships a self-contained document/PDF suite. Wrappers are
linked into `~/.local/bin`; the implementation and Python venv live under
`~/.local/share/doctools/`, with runtime state in `~/.local/state/doctools/`.

*   `docs --help`: structured manual listing every command and its meaning.
*   `pdfmerge`: merges PDFs and writes `final.pdf` (no TOC), `toc.pdf` (TOC only), and `final_toc.pdf` (TOC + content).
*   `docx2pdf` / `doc2pdf`: Office, Markdown, HTML, text and images to PDF.
*   `pdf2docx` / `pdf2doc` / `pdf2odt`: PDF to DOCX, DOC or ODT.
*   `pdfsplit`, `pdfselect`, `pdfcompress`, `pdf2img`, `img2pdf`, `pdf2txt`, `pdf2html`, `pdfinfo`, `pdfrotate`, `pdfwatermark`, `pdfencrypt`, `pdfdecrypt`, `pdfextractimages`, `pdfocr`.
*   `md2pdf` / `md2docx` / `md2html`: Markdown to PDF, DOCX or HTML.

See [`docs/document-and-file-utilities.md`](docs/document-and-file-utilities.md)
for the full command reference and verification steps.

### 🎛️ System Dashboard Widget
A high-performance, Waybar-integrated settings panel (anchored directly under your cursor below the status bar). 

#### 📖 How to Use:
*   **Open/Close**: Click the Settings gear (`⚙`) icon on the right side of Waybar, or press `SUPER + I`. Press it again or click the `×` button in the top-right corner to close.
*   **Peek Hover Expand**: Hover your mouse over the compact widget to expand it into the full dashboard; move your mouse away to collapse it back.
*   **Battery Status Indicator**: The circular battery (`BAT`) ring dynamically changes color:
    *   🟢 **Green** with `BAT⚡`: Charging.
    *   🔴 **Red**: Battery level is low (20% or lower).
    *   🟡 **Amber**: Discharging normally.
*   **Sliders**: Scroll or drag to adjust volume and display brightness.
*   **Power Modes**: Select `Power Saver`, `Balanced`, or `Performance` to dynamically adjust system profiles.
*   **Focus Mode**: Set your session time using the spinbox, click **Start** to begin, and receive a critical notification when the timer finishes. Click **Reset** to cancel.

---

## 🗑️ CAS Trash Management System

The repository features an enterprise-grade, custom **Content-Addressable Storage (CAS)-based Trash System**. Rather than relying on simple, standard file unlinking or standard directories which lead to filename collisions, this system tracks files logically via a SQLite relational catalog and deduplicates physical files in a hashed directory structure.

### 📐 System Architecture & Flow

```mermaid
graph TD
    User["User / Shell Command"] -->|rm file| SafeRM["safe-rm (Interceptor)"]
    SafeRM -->|1. Compute SHA-256| Hash["SHA-256 Hashing"]
    SafeRM -->|2. Record Metadata| SQLite["SQLite DB (trash.db)"]
    SafeRM -->|3. Copy Blob to CAS| CAS["CAS Store (.local/share/trash-system/objects/)"]

    User -->|trash list/restore/delete| TrashCLI["trash (CLI Utility)"]
    TrashCLI -->|Query / Mutate| SQLite
    TrashCLI -->|Extract / Unlink| CAS

    Systemd["Systemd User Services"] -->|Scheduled Cleanup| TrashCLI
```

### 📂 Storage Directory Structure
All deleted objects and SQLite databases reside safely within the user's directory:
```
~/.local/share/trash-system/
├── db/
│   ├── trash.db            # SQLite relational database (WAL mode)
│   └── trash.db.lock       # Multi-process concurrency lock
└── objects/
    └── <hash-prefix>/<hash> # De-duplicated file blobs (Content Addressable)
```

> [!NOTE]
> **Object Paths:** Blobs are stored utilizing the standard Git directory indexing algorithm:
> `~/.local/share/trash-system/objects/${hash:0:2}/${hash:2:2}/${hash}`
> This prevents single-directory folder indexing limits on standard Unix filesystems.

---

### 💾 Relational Data Model

#### 1. Main Directory Catalog (`trash`)
```sql
CREATE TABLE trash (
    id TEXT PRIMARY KEY,            -- Unique UUID identifying the deleted item
    original_path TEXT,            -- Full absolute path prior to deletion
    filename TEXT,                  -- Base name of the file
    extension TEXT,                 -- File extension parsed
    deletion_time INTEGER,          -- Epoch Unix timestamp of deletion
    mime_type TEXT,                 -- Evaluated MIME signature
    category TEXT,                  -- Category flags
    origin_root TEXT,               -- Starting partition mount path
    project_root TEXT,              -- Target git project root (if applicable)
    storage_path TEXT,              -- Path descriptor
    size INTEGER,                   -- Total file size in bytes
    hash TEXT,                      -- SHA-256 hash string for CAS mapping
    is_restored INTEGER DEFAULT 0,  -- Recovery indicator flag
    active_days INTEGER DEFAULT 0,  -- Age counter
    pinned INTEGER DEFAULT 0        -- Exemption status for automatic GC runs
);
```

#### 2. Version Schema Tracker (`meta`)
```sql
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

#### 3. Active Hash Index
```sql
CREATE INDEX idx_hash_active ON trash(hash) WHERE is_restored = 0;
```

---

### 🕹️ Command Interface

#### 🟩 Interceptor: `safe-rm`
Replaces standard destructive `rm` commands for files. It performs transaction-safe operations:
1.  Computes target file SHA-256 checksums.
2.  Pre-stages the payload file into secure system temporary space.
3.  Ensures database entries are saved correctly under SQLite WAL transactions.
4.  Relocates files to deduplicated CAS paths. If the content hash already exists, the storage path is reused immediately, saving disk space.
5.  Triggers safe atomic rollbacks on any environment, lock, or write exceptions.

#### 🎛️ Controller: `trash`
Provides powerful system commands to interact with the repository:

| Command | Action | Flow / Properties |
| :--- | :--- | :--- |
| `trash list` | Displays catalog | Formats logical paths, extensions, sizes, dates, and pin markers. |
| `trash restore <id>` | Restores file | Fetches metadata, pulls CAS target block, validates checksums, and restores it. |
| `trash delete <id>` | Purges item | Cleans database entry and unlinks target CAS block. Supports lists/ranges (`1-5`). |
| `trash clear` | Purges catalog | Performs standard truncation on active DB entries and purges all CAS objects. |
| `trash pin <id>` | Pins item | Marks record as `pinned=1`, exempting it from automatic timers and cleanups. |
| `trash unpin <id>`| Unpins item | Re-enables standard lifespan age limits and general cleanups. |
| `trash cleanup <N>`| Prunes aging | Deletes non-pinned files exceeding `N` storage days. |
| `trash scan` | GC sweeping | Scans object folder and purges orphan blobs unreferenced in `trash.db`. |
| `trash health` | Audit check | Performs SQLite diagnostic checks (`PRAGMA integrity_check`). |

---

### 🛡️ Concurrency & Safety Guarantees

*   **Transactional Durability:** SQLite databases operate inside **Write-Ahead Logging (WAL)** mode coupled with `synchronous = FULL` to resist filesystem corruptions, lockups, and power failures.
*   **Writer Protection:** All operations verify locks utilizing system `flock` boundaries to ensure parallel tasks execute sequentially:
    ```bash
    exec 200>"$LOCK_FILE"
    flock -n 200 || exit 1
    ```
*   **Exclusion Guards:** The interceptor refuses to wipe system critical paths (e.g. `/`, `/usr`, `/var`), skips system directories safely, and protects pinned records from purge scripts.
*   **Systemd Automation:** Three user timers run in the background:
    1.  `trash-age.timer`: Evaluates, increments daily storage ages, and applies notifications.
    2.  `trash-clean.timer`: Automates cleanup of non-pinned, aging files safely.
    3.  `trash-notify.timer`: Alerts user when trash sizes exceed safety parameters.

---

## 🚀 Installation Guide

### 📋 Prerequisites

Ensure you have a freshly installed Arch Linux machine with base tools.
```bash
sudo pacman -S --needed git base-devel stow
```

---

### 📥 1. Automated Setup (Recommended)

Our main script automates hardware checks, installs all dependencies, configures repositories, and hooks system variables seamlessly.

```bash
# Clone the repository to your home folder
git clone https://github.com/AdityaAgrawal08/My-Arch-Linux-Configurations.git ~/dotfiles
cd ~/dotfiles

# Launch the orchestrator
./install.sh
```

#### 🛡️ What `install.sh` performs behind the scenes:
1.  Downloads core utility packages (e.g., Stow, Pacman wrappers).
2.  Runs environment sensing (`detect.sh`) to log custom variables.
3.  Invokes profile compiler (`reconcile.sh`) using the custom manifests.
4.  Installs all Pacman dependencies and provisions `paru` as the AUR helper.
5.  Applies GNU Stow links to set up directories dynamically.
6.  Enables audio support (`pipewire`, `wireplumber`) and initializes systemd trash timers.
7.  Deploys Neovim Lua folders and configures the default shell to Fish.

---

### 📦 2. Manual Custom Stow Setup (Alternative)

If you prefer to configure your environment selectively, you can install GNU Stow and symlink packages manually:

```bash
sudo pacman -S stow

cd ~/dotfiles
# Individual component stowing
stow hypr
stow waybar
stow fish
stow nvim
stow starship
stow wofi
stow zathura
stow trash
```

---

## ⚡ Customization

To tailor components to your personal preferences, modify the following directories:

*   **Hyprland Rules:** Modify [hypr/.config/hypr/hyprland.conf](file:///home/aditya/dotfiles/hypr/.config/hypr/hyprland.conf) for hotkeys and layout options.
*   **Waybar Styling:** Edit [waybar/.config/waybar/config.jsonc](file:///home/aditya/dotfiles/waybar/.config/waybar/config.jsonc) and [style.css](file:///home/aditya/dotfiles/waybar/.config/waybar/style.css).
*   **Fish Shortcuts:** Customize [fish/.config/fish/config.fish](file:///home/aditya/dotfiles/fish/.config/fish/config.fish) to append custom variables and aliases.
*   **Terminal Prompt:** Modify [starship/.config/starship.toml](file:///home/aditya/dotfiles/starship/.config/starship.toml).

---

## 🛠️ System Dashboard Development Guide

If you want to maintain, modify, or replicate this system dashboard widget in the future, follow this architectural blueprint.

### 1. Architecture Overview
The dashboard is split into two clean Python files located in `hypr/.config/hypr/scripts/system-dashboard/`:
1.  **`collectors.py` (Backend):** Contains independent, thread-safe data collector classes (e.g., `CPUCollector`, `NetworkCollector`, `BatteryCollector`). They handle low-level file reading (e.g., `/proc/stat`, `/sys/class/net/`) or process spawning (`journalctl`, `nmcli`) to fetch system state.
2.  **`dashboard.py` (Frontend):** A GTK4 application (`Gtk.Application`) that builds the user interface, manages style sheets, handles user events, and runs a background thread to poll data and update the UI via `GLib.idle_add` (crucial for thread safety in GTK).

### 2. Core Design Patterns to Maintain

#### A. Thread-Safe UI Updates
Never update GTK widgets directly from a background thread. Always collect data in a background thread, and then schedule the UI update on the main GTK thread using `GLib.idle_add`:
```python
def background_worker():
    data = collector.get_data()
    GLib.idle_add(apply_data_to_widgets, data)
```

#### B. Single-Instance Show/Hide Toggle
To make the widget feel instant, the window is kept alive in the background:
1.  **Override Close Signal:** Intercept the `close-request` signal on the window and return `True` to hide it instead of destroying it:
    ```python
    def _on_close_request(self, window):
        self.hide()
        return True
    ```
2.  **Toggle on Activate:** The `Gtk.Application` uses a unique application ID (`com.system.dashboard`). When a second instance is launched, GTK's native IPC activates the primary instance instead of running a new process. We toggle window visibility in `do_activate`:
    ```python
    def do_activate(self):
        if self.window.is_visible():
            self.window.hide()
        else:
            self.window.present()
            self.window.position_window()
    ```

#### C. Wayland Positioning via Hyprland IPC
Under Wayland, windows cannot set their own absolute screen coordinates. We bypass this limitation by using Hyprland's IPC (`hyprctl`):
1.  Get the focused monitor's dimensions and scale: `hyprctl monitors -j`.
2.  Calculate target coordinates in logical pixels: `target_x = (width / scale) - win_width - margin`.
3.  Move, resize, and pin the window using a brief delay to allow the window to map:
    ```python
    subprocess.run(["hyprctl", "dispatch", "resizewindowpixel", "exact 380 590,class:com.system.dashboard"])
    subprocess.run(["hyprctl", "dispatch", "movewindowpixel", f"exact {x} {y},class:com.system.dashboard"])
    subprocess.run(["hyprctl", "dispatch", "pin", "class:com.system.dashboard"])
    ```

#### D. GTK4 CSS Styling without Warnings
*   GTK's CSS engine (`Gtk.CssProvider`) is a subset of web CSS.
*   **No trailing comments:** Never put comments like `/* ... */` on the same line as a property (e.g. `color: red; /* comment */` will fail to parse).
*   **No `!important`:** Do not use `!important`. Instead, increase selector specificity (e.g. `button.profile-btn.active` instead of `.active`) to override default Adwaita theme styling.
*   **Gradients & Backgrounds:** Standard GTK buttons use background gradients. To apply a solid background color, you must clear the gradient first: `background-image: none; background-color: #color;`.

---

## 🔍 Troubleshooting

### 🖼️ Hyprland Core Start-Up Issues
*   Check if correct graphics drivers are installed for your detected GPU type (inspect `state/env.json`).
*   Check instance log files for exceptions:
    ```bash
    cat /tmp/hypr/$HYPRLAND_INSTANCE_SIGNATURE/hyprland.log
    ```

### 🔊 Trash System Locks & Restores
*   If a process hangs, check active filesystem locks:
    ```bash
    ls -l ~/.local/share/trash-system/db/trash.db.lock
    ```
*   If object verification failures occur, run a complete diagnostic sweep:
    ```bash
    trash health
    trash scan
    ```

### 🔡 Missing Nerd Fonts or Broken Symbols
*   Verify your font cache is up to date:
    ```bash
    sudo pacman -S ttf-jetbrains-mono-nerd ttf-nerd-fonts-symbols-common
    fc-cache -fv
    ```
