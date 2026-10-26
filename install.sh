#!/usr/bin/env bash
#
# Arch Linux + Hyprland dotfiles installer.
#
# Run as your normal user (never with sudo):
#     cd ~/dotfiles
#     ./install.sh
#
# Optional switches:
#     SKIP_PACMAN_UPDATE=1  ./install.sh   # don't run pacman -Syu first
#     SKIP_OPTIONAL=1       ./install.sh   # skip heavy optional apps
#     SKIP_AUR=1            ./install.sh   # skip every AUR package
#     SKIP_STOW=1           ./install.sh   # install packages only
#     NO_SERVICES=1         ./install.sh   # don't enable/start services
#
set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Paths and logging
# ---------------------------------------------------------------------------

DOTFILES_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$DOTFILES_DIR"

LOG_DIR="$DOTFILES_DIR/logs"
LOG_FILE="$LOG_DIR/install.log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'
  C_BLUE=$'\033[1;34m'
  C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m'
else
  C_RESET="" C_BLUE="" C_YELLOW="" C_RED=""
fi

say()  { printf '%s==>%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
warn() { printf '%swarning:%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die()  { printf '%serror:%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

TARGET_USER="$(id -un)"
STAMP="$(date +%Y%m%d-%H%M%S)"
FAILED_ITEMS=()

note_failure() {
  FAILED_ITEMS+=("$1")
  warn "install failed: $1"
}

cleanup() {
  if [[ -n "${SUDO_KEEPALIVE_PID:-}" ]]; then
    kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------

[[ $EUID -ne 0 ]] || die "Run this script as your normal user, not as root."
[[ -f /etc/arch-release ]] || die "This installer targets Arch Linux (or an Arch-based system)."
command -v pacman >/dev/null 2>&1 || die "pacman not found."
command -v sudo   >/dev/null 2>&1 || die "sudo not found. Install sudo or run a minimal bootstrap first."

say "Installing dotfiles from $DOTFILES_DIR"
say "Target user: $TARGET_USER ($HOME)"

sudo -v || die "sudo authentication failed."
# Keep the sudo timestamp alive during long AUR builds.
( while true; do sudo -n true 2>/dev/null; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) \
  >/dev/null 2>&1 &
SUDO_KEEPALIVE_PID=$!

# ---------------------------------------------------------------------------
# Package lists
#
# These mirror the packages that are explicitly installed on the machine this
# repository was built from, plus the runtime dependencies used by the dotfiles
# themselves.  The small packages/*.txt files are still read as well, so adding
# a package there keeps working.
# ---------------------------------------------------------------------------

PACMAN_CORE=(
  # Base system / build tools
  base
  base-devel
  git
  stow
  curl
  wget
  rsync
  jq
  bc
  less
  man-db
  bash-completion
  which
  sudo
  pacman-contrib
  reflector
  archlinux-keyring
  file
  coreutils
  util-linux
  pciutils
  usbutils

  # Networking
  networkmanager
  network-manager-applet
  wpa_supplicant
  wireless-regdb
  openssh
  bind
  net-tools

  # Audio
  pipewire
  pipewire-pulse
  pipewire-alsa
  wireplumber
  alsa-utils
  alsa-tools
  alsa-firmware
  sof-firmware
  pavucontrol
  playerctl

  # Bluetooth
  bluez
  bluez-utils
  blueman

  # Power / hardware
  acpid
  power-profiles-daemon
  upower
  brightnessctl
  udisks2
  gvfs
  gvfs-mtp
  ntfs-3g
  exfatprogs
  dosfstools
  mtools
  mtpfs
  android-udev
  fuse2
  fuse3

  # Polkit / portals / XDG
  polkit
  polkit-gnome
  xdg-utils
  xdg-user-dirs
  xdg-desktop-portal
  xdg-desktop-portal-gtk
  xdg-desktop-portal-hyprland

  # Display manager / boot (only used if present)
  sddm
  grub
  efibootmgr
  os-prober

  # Misc
  libnotify
  sqlite
  linux-firmware
  adwaita-fonts
  adwaita-icon-theme
  adwaita-cursors
)

PACMAN_HYPR=(
  hyprland
  hyprpaper
  hypridle
  hyprlock
  hyprshot
  hyprsunset
  hyprpolkitagent
  matugen
  awww
  python-pillow
  waybar
  wofi
  kitty
  thunar
  thunar-volman
  dunst
  grim
  slurp
  wf-recorder
  wl-clipboard
  cliphist
  gtk4-layer-shell
  qt5-wayland
  qt6-wayland
  qt5-graphicaleffects
  qt5-quickcontrols2
  xorg-xwayland
  xorg-xhost
  xorg-xrandr
  xorg-xrdb
  xorg-xsetroot
  xorg-xprop
  xorg-xwininfo
  xorg-xinput
  xorg-xev
  xorg-setxkbmap
  xorg-xauth
  xorg-xmodmap
  xorg-xkill
  imv
  mpv
  zathura
  zathura-pdf-poppler
  zathura-djvu
  zathura-ps
  gjs
  gnome-font-viewer
  zenity
  noto-fonts
  noto-fonts-cjk
  noto-fonts-emoji
  ttf-dejavu
  ttf-roboto
  ttf-fira-code
  ttf-firacode-nerd
  ttf-jetbrains-mono-nerd
  woff2-font-awesome
)

PACMAN_DEV=(
  neovim
  fish
  starship
  python
  python-pip
  python-virtualenv
  python-matplotlib
  python-numpy
  python-pypdf
  python-reportlab
  python-scipy
  ipython
  nodejs
  npm
  uv
  fnm
  nvm
  pm2
  go
  rust
  clang
  cmake
  bear
  luarocks
  tree-sitter-cli
  maven
  jdk-openjdk
  jdk21-openjdk
  github-cli
  git-lfs
  git-filter-repo
  perl
  bat
  fd
  ripgrep
  fzf
  tree
  fastfetch
  htop
  7zip
  unrar
  ouch
  zip
  unzip
  vim
  nano
  tesseract
  tesseract-data-eng
)

PACMAN_APPS=(
  firefox
  chromium
  libreoffice-fresh
  vlc
  kolourpaint
  gparted
  qalculate-gtk
  speedcrunch
  imagemagick
  ffmpeg
  yt-dlp
  openai-codex
  opencode
  sdl2_gfx
  sdl2_image
  sdl2_mixer
  sdl2_ttf
  gocryptfs
  kwallet
)

# Document/PDF toolkit backends.  Python packages are installed into the
# repo-local venv by install_python_tools(); these are the system backends.
PACMAN_DOCS=(
  poppler
  ghostscript
  qpdf
  python-weasyprint
)

# Optional extras: skip with SKIP_OPTIONAL=1 if you want a lean install.
PACMAN_OPTIONAL=(
  docker
  docker-compose
  mariadb
  valkey
  coturn
  cloudflared
  aircrack-ng
  lynis
  sleuthkit
  nmap
  tcpdump
  whois
  obs-studio
  ollama
  torbrowser-launcher
  pandoc-cli
)

# The full Xorg set that was present on the original machine.  Hyprland uses
# xorg-xwayland at runtime; the rest are kept for compatibility with the
# original setup and older graphical tools.
PACMAN_XORG=(
  xf86-video-vesa
  xorg-bdftopcf
  xorg-docs
  xorg-font-util
  xorg-fonts-100dpi
  xorg-fonts-75dpi
  xorg-fonts-encodings
  xorg-iceauth
  xorg-mkfontscale
  xorg-server
  xorg-server-common
  xorg-server-devel
  xorg-server-xephyr
  xorg-server-xnest
  xorg-server-xvfb
  xorg-sessreg
  xorg-smproxy
  xorg-x11perf
  xorg-xbacklight
  xorg-xcmsdb
  xorg-xcursorgen
  xorg-xdpyinfo
  xorg-xdriinfo
  xorg-xgamma
  xorg-xkbcomp
  xorg-xkbevd
  xorg-xkbutils
  xorg-xlsatoms
  xorg-xlsclients
  xorg-xpr
  xorg-xrefresh
  xorg-xset
  xorg-xvinfo
  xorg-xwd
  xorg-xwud
)

# AUR packages.  The helper itself (paru/yay) is handled separately.
AUR_REQUIRED=(
  brave-bin
  zen-browser-bin
  visual-studio-code-bin
  yay
)

AUR_OPTIONAL=(
  antigravity
  burpsuite
  cloudflare-warp-bin
  dislocker
  dnslookup-bin
  grub-customizer
  gtk2
  gvisor-bin
  inkscape-bin
  simple-mtpfs
  staruml
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

read_pkg_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  sed -e 's/#.*$//' -e 's/[[:space:]]//g' "$file" | awk 'NF'
}

append_from_file() {
  local array_name="$1" file="$2" pkg
  local -n _target="$array_name"
  while IFS= read -r pkg; do
    if [[ -n "$pkg" ]]; then
      _target+=("$pkg")
    fi
  done < <(read_pkg_file "$file")
}

dedup_array() {
  local array_name="$1"
  local -n _arr="$array_name"
  local -a _dedup=()
  mapfile -t _dedup < <(printf '%s\n' "${_arr[@]}" | awk 'NF && !seen[$0]++')
  _arr=("${_dedup[@]}")
}

pacman_installed() {
  pacman -Qq "$1" >/dev/null 2>&1
}

aur_pkg_installed() {
  pacman -Qq "$1" >/dev/null 2>&1 && return 0
  case "$1" in
    yay)  pacman -Qq yay-bin  >/dev/null 2>&1 ;;
    paru) pacman -Qq paru-bin >/dev/null 2>&1 ;;
    *)    return 1 ;;
  esac
}

install_pacman_group() {
  local label="$1"
  shift
  local -a wanted=()
  local pkg

  for pkg in "$@"; do
    [[ -n "$pkg" ]] || continue
    pacman_installed "$pkg" || wanted+=("$pkg")
  done

  ((${#wanted[@]})) || { say "$label: already installed"; return 0; }

  say "Installing $label (${#wanted[@]} packages)"
  if sudo pacman -S --needed --noconfirm --noprogressbar "${wanted[@]}"; then
    return 0
  fi

  warn "Batch install for $label failed; retrying package by package"
  for pkg in "${wanted[@]}"; do
    if ! sudo pacman -S --needed --noconfirm --noprogressbar "$pkg"; then
      note_failure "pacman:$pkg"
    fi
  done
}

pacman_upgrade() {
  if [[ ${SKIP_PACMAN_UPDATE:-0} == 1 ]]; then
    say "Skipping full system upgrade (SKIP_PACMAN_UPDATE=1)"
    return 0
  fi

  say "Updating package databases and system"
  if sudo pacman -Syu --needed --noconfirm --noprogressbar; then
    return 0
  fi

  warn "Full upgrade failed; retrying after refreshing the keyring"
  sudo pacman-key --init || true
  sudo pacman-key --populate archlinux || true
  sudo pacman -Sy --needed --noconfirm --noprogressbar || true
  sudo pacman -Syu --needed --noconfirm --noprogressbar || \
    warn "System upgrade still failed; continuing with installed databases"
}

aur_helper() {
  if command -v paru >/dev/null 2>&1; then
    printf 'paru'
    return 0
  fi
  if command -v yay >/dev/null 2>&1; then
    printf 'yay'
    return 0
  fi
  return 1
}

bootstrap_aur_helper() {
  if aur_helper >/dev/null 2>&1; then
    return 0
  fi

  local cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/dotfiles-aur"
  local repo builddir
  mkdir -p "$cache_dir"

  for repo in paru-bin yay-bin; do
    builddir="$cache_dir/$repo"
    say "Bootstrapping AUR helper: $repo"
    rm -rf "$builddir"
    if ! git clone --depth 1 "https://aur.archlinux.org/${repo}.git" "$builddir"; then
      warn "Could not clone $repo"
      continue
    fi
    if ( cd "$builddir" && makepkg -si --noconfirm ); then
      rm -rf "$builddir"
      if aur_helper >/dev/null 2>&1; then
        return 0
      fi
    else
      warn "Could not build $repo"
    fi
    rm -rf "$builddir"
  done

  return 1
}

install_aur_group() {
  local label="$1"
  shift
  local -a wanted=()
  local pkg helper
  local -a helper_args=(-S --needed --noconfirm)

  helper="$(aur_helper)" || { warn "No AUR helper available; skipping $label"; return 1; }

  for pkg in "$@"; do
    [[ -n "$pkg" ]] || continue
    aur_pkg_installed "$pkg" || wanted+=("$pkg")
  done

  ((${#wanted[@]})) || { say "$label: already installed"; return 0; }

  if [[ $helper == paru ]]; then
    helper_args+=(--skipreview)
  else
    helper_args+=(--answerclean None --answerdiff None --answeredit None --answerupgrade None)
  fi

  say "Installing $label (${#wanted[@]} AUR packages)"
  if "$helper" "${helper_args[@]}" "${wanted[@]}"; then
    return 0
  fi

  warn "Batch AUR install for $label failed; retrying package by package"
  for pkg in "${wanted[@]}"; do
    if ! "$helper" "${helper_args[@]}" "$pkg"; then
      note_failure "aur:$pkg"
    fi
  done
}

backup_path() {
  local target="$1" backup counter=1

  [[ -n "$target" && "$target" == "$HOME"/* ]] || {
    warn "Refusing to back up path outside HOME: $target"
    return 1
  }

  backup="${target}.pre-dotfiles.${STAMP}"
  while [[ -e "$backup" || -L "$backup" ]]; do
    backup="${target}.pre-dotfiles.${STAMP}.${counter}"
    counter=$((counter + 1))
  done

  mv -- "$target" "$backup"
  warn "Backed up $target -> $backup"
}

stow_package() {
  local pkg="$1"
  local -a extra_ignores=()
  local attempt conflicts target

  case "$pkg" in
    fish)
      extra_ignores+=(
        --ignore='fish_variables$'
        --ignore='secrets\.fish$'
        --ignore='\.gitignore$'
      )
      ;;
    hypr)
      extra_ignores+=(
        --ignore='__pycache__'
        --ignore='\.pyc$'
        --ignore='\.backup$'
        --ignore='battery-notify$'
      )
      ;;
    trash)
      extra_ignores+=(
        --ignore='^(bin|scripts|systemd|config|install\.sh|uninstall\.sh|\.gitignore|\.stow-local-ignore)$'
        # This tracked symlink points at /usr/lib and makes stow abort on the
        # whole package.  systemctl --user enable recreates it at login.
        --ignore='graphical-session\.target\.wants$'
      )
      ;;
    xdg)
      # xdg-user-dirs-update rewrites this file; keep the real copy in $HOME
      # so the repository never gets modified by the service.
      extra_ignores+=(
        --ignore='user-dirs\.dirs$'
      )
      ;;
    local)
      extra_ignores+=(
        --ignore='venv$'
        --ignore='^_run$'
        --ignore='__pycache__'
        --ignore='\.pyc$'
      )
      ;;
  esac

  for attempt in 1 2 3 4 5; do
    if LC_ALL=C stow --dir="$DOTFILES_DIR" --target="$HOME" --no-folding --restow "${extra_ignores[@]}" "$pkg"; then
      say "Stowed $pkg"
      return 0
    fi

    conflicts="$(LC_ALL=C stow --dir="$DOTFILES_DIR" --target="$HOME" -n -v --no-folding "${extra_ignores[@]}" "$pkg" 2>&1 | sed -n \
      -e 's/.*over existing target \(.*\) since neither a link nor a directory.*/\1/p' \
      -e 's/.*existing target is neither a link nor a directory: \(.*\)/\1/p' \
      -e 's/.*existing target is not owned by stow: \(.*\)/\1/p' \
      -e 's/.*existing target is not a directory: \(.*\)/\1/p' || true)"

    if [[ -z "$conflicts" ]]; then
      break
    fi

    while IFS= read -r target; do
      [[ -n "$target" ]] || continue
      if [[ -e "$HOME/$target" || -L "$HOME/$target" ]]; then
        backup_path "$HOME/$target" || true
      fi
    done <<< "$conflicts"
  done

  warn "Could not stow $pkg; unresolved conflicts:"
  LC_ALL=C stow --dir="$DOTFILES_DIR" --target="$HOME" -n -v --no-folding "${extra_ignores[@]}" "$pkg" >&2 || true
  return 1
}

stow_all() {
  local -a packages=(
    dunst
    fish
    gtk
    htop
    hypr
    kitty
    local
    nvim
    opencode
    starship
    trash
    waybar
    wofi
    xdg
    zathura
  )
  local pkg

  say "Applying dotfiles with GNU Stow"
  for pkg in "${packages[@]}"; do
    if [[ -d "$DOTFILES_DIR/$pkg" ]]; then
      stow_package "$pkg" || note_failure "stow:$pkg"
    else
      warn "Stow package missing: $pkg"
    fi
  done
}

install_local_bin_tools() {
  local src_dir="$DOTFILES_DIR/local/.local/bin"
  local src name dest
  local bin="$HOME/.local/bin"

  [[ -d "$src_dir" ]] || return 0
  mkdir -p "$bin"
  for src in "$src_dir"/*; do
    name="$(basename -- "$src")"
    [[ "$name" == "_run" ]] && continue
    [[ -e "$src" || -L "$src" ]] || continue
    dest="$bin/$name"

    if [[ -L "$dest" && "$(readlink -f "$dest")" == "$(readlink -f "$src")" ]]; then
      continue
    fi
    if [[ -e "$dest" || -L "$dest" ]]; then
      backup_path "$dest" || true
    fi
    ln -sfn "$src" "$dest" || note_failure "local-bin:$name"
  done
}

cleanup_runtime_links() {
  local target
  for target in \
    "$HOME/.config/fish/fish_variables" \
    "$HOME/.config/hypr/scripts/battery-notify"; do
    if [[ -L "$target" && "$(readlink -f "$target")" == "$DOTFILES_DIR"/* ]]; then
      rm -f "$target"
    fi
  done
}

# ---------------------------------------------------------------------------
# Trash system
# ---------------------------------------------------------------------------

install_trash_system() {
  local base="$HOME/.local/share/trash-system"
  local db="$base/db/trash.db"
  local bin="$HOME/.local/bin"
  local name

  say "Setting up the CAS trash system"
  mkdir -p "$bin" "$base/db" "$base/objects"

  for name in safe-rm trash trash-ui; do
    if [[ -L "$bin/$name" && "$(readlink -f "$bin/$name")" == "$(readlink -f "$DOTFILES_DIR/trash/bin/$name")" ]]; then
      continue
    fi
    if [[ -e "$bin/$name" || -L "$bin/$name" ]]; then
      backup_path "$bin/$name" || true
    fi
    ln -sfn "$DOTFILES_DIR/trash/bin/$name" "$bin/$name" || \
      note_failure "trash:link:$name"
  done

  for name in trash-age trash-clean trash-notify; do
    if [[ -L "$bin/$name" ]]; then
      rm -f "$bin/$name"
    fi
  done

  cat > "$bin/trash-age" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[ -f "$HOME/.config/trash-system/env" ] && source "$HOME/.config/trash-system/env"
BASE="${TRASH_BASE:-$HOME/.local/share/trash-system}"
DB="${TRASH_DB:-$BASE/db/trash.db}"
[ -f "$DB" ] || exit 0
sqlite3 "$DB" "UPDATE trash SET active_days = MAX(0, CAST((strftime('%s','now') - deletion_time) / 86400 AS INTEGER)) WHERE is_restored = 0;"
EOF

  cat > "$bin/trash-clean" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec "$HOME/.local/bin/trash" cleanup "${TRASH_RETENTION_DAYS:-100}"
EOF

  cat > "$bin/trash-notify" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[ -f "$HOME/.config/trash-system/env" ] && source "$HOME/.config/trash-system/env"
BASE="${TRASH_BASE:-$HOME/.local/share/trash-system}"
DB="${TRASH_DB:-$BASE/db/trash.db}"
[ -f "$DB" ] || exit 0
count="$(sqlite3 "$DB" "SELECT COUNT(*) FROM trash WHERE is_restored = 0;")"
if [[ "${count:-0}" -gt 0 ]] && command -v notify-send >/dev/null 2>&1; then
  notify-send --app-name=Trash "Trash" "$count item(s) are in the trash." || true
fi
EOF

  chmod 755 "$bin/trash-age" "$bin/trash-clean" "$bin/trash-notify"

  export TRASH_BASE="$base"
  export TRASH_DB="$db"
  export TRASH_OBJECTS="$base/objects"

  if [[ ! -f "$db" ]]; then
    ( cd "$DOTFILES_DIR/trash" && bash scripts/init-db.sh ) || \
      note_failure "trash:database"
  fi

  # The checked-in units contain the original machine's absolute HOME.
  # Override them so the timers work for whichever user runs this script.
  local unit
  for unit in trash-age trash-clean trash-notify; do
    mkdir -p "$HOME/.config/systemd/user/${unit}.service.d"
    cat > "$HOME/.config/systemd/user/${unit}.service.d/override.conf" <<EOF
[Service]
ExecStart=
ExecStart="$bin/$unit"
EOF
  done
}

# ---------------------------------------------------------------------------
# Shells
# ---------------------------------------------------------------------------

append_line_once() {
  local file="$1" marker="$2" line="$3"

  if ! grep -Fq -- "$marker" "$file" 2>/dev/null; then
    if [[ -s "$file" ]] && [[ -n "$(tail -c 1 "$file")" ]]; then
      printf '\n' >> "$file"
    fi
    printf '%s\n' "$line" >> "$file"
  fi
}

configure_shells() {
  say "Configuring shells"

  mkdir -p "$HOME/.config/fish"

  # Stow normally provides this; keep a fallback for a failed/partial stow.
  if [[ -L "$HOME/.config/fish/config.fish" && ! -e "$HOME/.config/fish/config.fish" ]]; then
    rm -f "$HOME/.config/fish/config.fish"
  fi
  if [[ ! -e "$HOME/.config/fish/config.fish" ]]; then
    cat > "$HOME/.config/fish/config.fish" <<'EOF'
# Created by dotfiles/install.sh
fish_add_path $HOME/.local/bin
fish_add_path $HOME/.opencode/bin
EOF
  fi

  if [[ -L "$HOME/.config/fish/functions/open.fish" && ! -e "$HOME/.config/fish/functions/open.fish" ]]; then
    rm -f "$HOME/.config/fish/functions/open.fish"
  fi
  if [[ ! -e "$HOME/.config/fish/functions/open.fish" ]]; then
    # The repository provides functions/open.fish; this fallback is only for
    # installations where the fish package could not be stowed.
    mkdir -p "$HOME/.config/fish/functions"
    cat > "$HOME/.config/fish/functions/open.fish" <<'EOF'
function open
    if test (count $argv) -eq 0
        echo "open: missing file operand"
        return 1
    end
    for file in $argv
        if not test -e "$file"
            echo "open: file not found -> $file"
            continue
        end
        set ext (string lower (path extension $file))
        switch $ext
            case ".pdf"
                zathura "$file" >/dev/null 2>&1 &
            case ".png" ".jpg" ".jpeg" ".webp" ".gif"
                imv "$file" >/dev/null 2>&1 &
            case ".mp4" ".mkv" ".webm" ".mp3"
                mpv "$file" >/dev/null 2>&1 &
            case ".docx" ".pptx" ".xlsx"
                libreoffice "$file" >/dev/null 2>&1 &
            case "*"
                xdg-open "$file" >/dev/null 2>&1 &
        end
    end
end
EOF
  fi

  # Make fish the login shell.  This is safe to repeat.
  if command -v fish >/dev/null 2>&1; then
    if ! grep -qx '/usr/bin/fish' /etc/shells 2>/dev/null; then
      printf '%s\n' '/usr/bin/fish' | sudo tee -a /etc/shells >/dev/null
    fi
    if [[ "$(getent passwd "$TARGET_USER" | awk -F: '{print $7}')" != "/usr/bin/fish" ]]; then
      sudo chsh -s /usr/bin/fish "$TARGET_USER" || \
        warn "Could not change the login shell to fish"
    fi
  else
    warn "fish is not installed; skipping chsh"
  fi

  # zsh is not part of this setup, but preserve the old installer behaviour if
  # somebody has it installed already.
  if command -v zsh >/dev/null 2>&1; then
    local zshrc="$HOME/.zshrc"
    if [[ -L "$zshrc" && ! -e "$zshrc" ]]; then
      rm -f "$zshrc"
    fi
    [[ -e "$zshrc" ]] || printf '%s\n' '# ~/.zshrc - created by dotfiles/install.sh' > "$zshrc"
    append_line_once "$zshrc" '.opencode/bin' 'export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$PATH"'
  fi
}

# ---------------------------------------------------------------------------
# User-local Python tools
# ---------------------------------------------------------------------------

install_python_tools() {
  local venv="$HOME/.local/share/doctools/venv"

  say "Installing document/PDF Python tools into $venv"
  mkdir -p "$HOME/.local/share/doctools"

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is missing; skipping Python document tools"
    note_failure "python:missing"
    return 0
  fi

  if [[ ! -x "$venv/bin/python" ]]; then
    python3 -m venv "$venv" || { note_failure "python:venv"; return 0; }
  fi

  "$venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip >/dev/null 2>&1 || true
  if ! "$venv/bin/python" -m pip install \
      --disable-pip-version-check \
      'pypdf>=5' \
      'reportlab>=4' \
      'pdf2docx>=0.5.13' \
      'img2pdf>=0.5' \
      'weasyprint>=62' \
      'markdown>=3.5' \
      'python-docx>=1.1' \
      'pillow>=10' \
      'cryptography>=3.1'; then
    warn "Could not install one or more Python document packages"
    note_failure "python:doc-tools"
  fi

  if ! "$venv/bin/python" - <<'PY'
import importlib
import logging
import warnings

logging.disable(logging.INFO)
warnings.filterwarnings("ignore", message="The `fitz` API is deprecated.*")

checks = {
    "pypdf": "pypdf",
    "reportlab": "reportlab",
    "pdf2docx": "pdf2docx",
    "img2pdf": "img2pdf",
    "weasyprint": "weasyprint",
    "markdown": "markdown",
    "docx": "docx",
    "PIL": "PIL",
    "cryptography": "cryptography",
}
failed = []
for label, module in checks.items():
    try:
        importlib.import_module(module)
    except Exception as exc:
        failed.append(f"{label}: {exc}")
if failed:
    print("\n".join(failed))
    raise SystemExit(1)
PY
  then
    note_failure "python:doc-tools-verify"
  fi
}

install_xdg_user_dirs() {
  local target="$HOME/.config/user-dirs.dirs"
  local source="$DOTFILES_DIR/xdg/.config/user-dirs.dirs"

  mkdir -p "$HOME/.config"
  if [[ -L "$target" && ! -e "$target" ]]; then
    rm -f "$target"
  fi
  if [[ -L "$target" && "$(readlink -f "$target")" == "$(readlink -f "$source")" ]]; then
    # Older installs linked this file directly into the repository.  Replace
    # the link with a real copy so xdg-user-dirs-update cannot dirty the repo.
    rm -f "$target"
  fi
  if [[ ! -e "$target" && -f "$source" ]]; then
    cp "$source" "$target"
  fi
  mkdir -p "$HOME/Downloads" "$HOME/Pictures"
}

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

system_enable() {
  local unit="$1" mode="${2:-now}"
  systemctl list-unit-files "$unit" >/dev/null 2>&1 || return 0
  if [[ $mode == now ]]; then
    sudo systemctl enable --now "$unit" || warn "Could not enable/start $unit"
  else
    sudo systemctl enable "$unit" || warn "Could not enable $unit"
  fi
}

enable_services() {
  if [[ ${NO_SERVICES:-0} == 1 ]]; then
    say "Skipping service configuration (NO_SERVICES=1)"
    return 0
  fi

  say "Enabling system services"
  system_enable NetworkManager.service
  system_enable bluetooth.service
  system_enable power-profiles-daemon.service
  system_enable acpid.service
  system_enable systemd-timesyncd.service
  system_enable sshd.service
  system_enable valkey.service
  system_enable warp-svc.service

  # Docker and MariaDB are installed but deliberately left stopped, matching
  # the original machine.  Start them yourself when needed.

  # Only choose SDDM when no other display manager is already active.
  local dm enabled_dm=""
  for dm in gdm.service lightdm.service ly.service greetd.service sddm.service; do
    if systemctl is-enabled --quiet "$dm" 2>/dev/null; then
      enabled_dm="$dm"
      break
    fi
  done

  if [[ -z "$enabled_dm" ]]; then
    if systemctl list-unit-files sddm.service >/dev/null 2>&1; then
      say "Enabling SDDM (no existing display manager found)"
      system_enable sddm.service enable
    fi
  elif [[ "$enabled_dm" == sddm.service ]]; then
    system_enable sddm.service enable
  else
    say "Keeping existing display manager: $enabled_dm"
  fi

  # User services.  They need a live user D-Bus session; on a fresh TTY this
  # may not exist yet, so failure is non-fatal.
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  if [[ -S "$XDG_RUNTIME_DIR/bus" ]]; then
    say "Enabling user services"
    systemctl --user daemon-reload || true
    for dm in pipewire.socket pipewire-pulse.socket wireplumber.service \
              xdg-user-dirs.service warp-taskbar.service; do
      if systemctl --user cat "$dm" >/dev/null 2>&1; then
        systemctl --user enable --now "$dm" || warn "Could not enable user unit $dm"
      fi
    done

    # The trash timers only exist after the trash package has been stowed.
    for dm in trash-age.timer trash-clean.timer trash-notify.timer; do
      if systemctl --user cat "$dm" >/dev/null 2>&1; then
        systemctl --user enable --now "$dm" || warn "Could not enable user timer $dm"
      fi
    done
  else
    warn "No user D-Bus session found; log in graphically and run:"
    warn "  systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service"
    warn "  systemctl --user enable --now trash-age.timer trash-clean.timer trash-notify.timer"
  fi
}

add_user_groups() {
  local group
  for group in wheel audio video storage power docker procview adbusers; do
    if getent group "$group" >/dev/null 2>&1; then
      sudo usermod -aG "$group" "$TARGET_USER" || true
    fi
  done
}

# ---------------------------------------------------------------------------
# Hardware detection
# ---------------------------------------------------------------------------

detect_gpu_packages() {
  local -a gpu_pkgs=()
  local gpu="unknown"

  if command -v lspci >/dev/null 2>&1; then
    if lspci -nn 2>/dev/null | grep -iE 'nvidia.*(vga|3d|display)|(vga|3d|display).*nvidia' >/dev/null; then
      gpu="nvidia"
      local kernel
      for kernel in linux linux-lts linux-zen linux-hardened linux-rt; do
        if pacman -Qq "$kernel" >/dev/null 2>&1; then
          case "$kernel" in
            linux)     gpu_pkgs+=(nvidia-open) ;;
            linux-lts) gpu_pkgs+=(nvidia-open-lts) ;;
            *)         gpu_pkgs+=(nvidia-open-dkms) ;;
          esac
          gpu_pkgs+=("${kernel}-headers")
          break
        fi
      done
      gpu_pkgs+=(nvidia-utils nvidia-settings egl-wayland)
    fi
    if lspci -nn 2>/dev/null | grep -iE '(amd|ati).*(vga|3d|display)|(vga|3d|display).*(amd|ati)' >/dev/null; then
      [[ $gpu == unknown ]] && gpu="amd"
      gpu_pkgs+=(mesa vulkan-radeon libva-utils)
    fi
    if lspci -nn 2>/dev/null | grep -iE 'intel.*(vga|3d|display)|(vga|3d|display).*intel' >/dev/null; then
      [[ $gpu == unknown ]] && gpu="intel"
      gpu_pkgs+=(mesa vulkan-intel intel-media-driver libva-intel-driver libva-utils intel-gpu-tools)
    fi
  fi

  # Always useful on a Wayland desktop.
  gpu_pkgs+=(mesa vulkan-icd-loader libva)

  if grep -qi 'GenuineIntel' /proc/cpuinfo; then
    gpu_pkgs+=(intel-ucode)
  elif grep -qi 'AuthenticAMD' /proc/cpuinfo; then
    gpu_pkgs+=(amd-ucode)
  fi

  dedup_array gpu_pkgs
  say "Detected GPU: $gpu"
  install_pacman_group "graphics/CPU support" "${gpu_pkgs[@]}"
}

# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

main() {
  pacman_upgrade

  say "Installing bootstrap tools"
  install_pacman_group "bootstrap tools" base-devel git stow curl wget rsync jq less unzip zip tar xz which sudo

  # Add packages maintained in the repository's declarative list files.
  append_from_file PACMAN_CORE packages/pacman/base.txt
  append_from_file PACMAN_HYPR packages/pacman/hyprland.txt
  append_from_file AUR_OPTIONAL packages/aur/aur.txt
  dedup_array PACMAN_CORE
  dedup_array PACMAN_HYPR
  dedup_array PACMAN_DEV
  dedup_array PACMAN_APPS
  dedup_array PACMAN_DOCS
  dedup_array PACMAN_OPTIONAL
  dedup_array PACMAN_XORG
  dedup_array AUR_REQUIRED
  dedup_array AUR_OPTIONAL

  # A new Arch installation normally already has a kernel.  Don't pull a
  # second one if the user is running linux-lts/zen/hardened.
  if ! pacman -Qq linux >/dev/null 2>&1 \
     && ! pacman -Qq linux-lts >/dev/null 2>&1 \
     && ! pacman -Qq linux-zen >/dev/null 2>&1 \
     && ! pacman -Qq linux-hardened >/dev/null 2>&1 \
     && ! pacman -Qq linux-rt >/dev/null 2>&1; then
    PACMAN_CORE+=(linux)
  fi

  install_pacman_group "system packages" "${PACMAN_CORE[@]}"
  install_pacman_group "Xorg/XWayland packages" "${PACMAN_XORG[@]}"
  detect_gpu_packages
  install_pacman_group "Hyprland desktop packages" "${PACMAN_HYPR[@]}"
  install_pacman_group "development tools" "${PACMAN_DEV[@]}"
  install_pacman_group "applications" "${PACMAN_APPS[@]}"
  install_pacman_group "document/PDF tools" "${PACMAN_DOCS[@]}"

  if [[ ${SKIP_OPTIONAL:-0} == 1 ]]; then
    say "Skipping optional packages (SKIP_OPTIONAL=1)"
  else
    install_pacman_group "optional packages" "${PACMAN_OPTIONAL[@]}"
  fi

  if [[ ${SKIP_AUR:-0} == 1 ]]; then
    say "Skipping AUR packages (SKIP_AUR=1)"
  else
    if bootstrap_aur_helper; then
      install_aur_group "AUR essentials" "${AUR_REQUIRED[@]}"
      if [[ ${SKIP_OPTIONAL:-0} != 1 ]]; then
        install_aur_group "optional AUR applications" "${AUR_OPTIONAL[@]}"
      fi
    else
      warn "No AUR helper could be built; AUR packages were skipped"
    fi
  fi

  if [[ ${SKIP_STOW:-0} == 1 ]]; then
    say "Skipping stow (SKIP_STOW=1)"
  else
    stow_all
    cleanup_runtime_links
    install_trash_system
    configure_shells

    if [[ -x "$HOME/.config/hypr/scripts/wallpaper_switch.sh" ]]; then
      say "Seeding autotheme generated files"
      "$HOME/.config/hypr/scripts/wallpaper_switch.sh" init || \
        warn "Could not seed autotheme; run wallpaper_switch.sh init after first login"
    fi
  fi

  install_local_bin_tools
  install_python_tools
  install_xdg_user_dirs

  # Keep a compatibility path for the trash CLI's recovery code and for the
  # wallpaper path used by hyprpaper.conf.
  if [[ "$DOTFILES_DIR" != "$HOME/dotfiles" && ! -e "$HOME/dotfiles" ]]; then
    ln -s "$DOTFILES_DIR" "$HOME/dotfiles" 2>/dev/null || \
      warn "Could not create compatibility symlink $HOME/dotfiles"
  fi

  if [[ ${SKIP_STOW:-0} != 1 ]]; then
    mkdir -p "$HOME/.local/state"
    fc-cache -f >/dev/null 2>&1 || true
  fi

  add_user_groups
  enable_services

  # -------------------------------------------------------------------------
  # Verification
  # -------------------------------------------------------------------------

  local -a critical_cmds=(
    Hyprland hyprctl hyprpaper hypridle hyprlock hyprshot hyprsunset hyprpolkitagent
    matugen awww awww-daemon
    waybar wofi kitty thunar dunst cliphist wl-copy
    nm-applet blueman-applet pavucontrol
    fish nvim git stow sqlite3
    notify-send playerctl brightnessctl wpctl grim slurp zathura imv mpv
    starship jq python3 gcc pkg-config magick ffmpeg ffprobe
    doc docs pdfmerge docx2pdf pdf2docx pdftotext pdftoppm gs
  )
  local cmd missing=()

  for cmd in "${critical_cmds[@]}"; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done

  if ((${#missing[@]})); then
    warn "These critical commands are still missing: ${missing[*]}"
    warn "Review the package errors above and rerun ./install.sh"
  fi

  if [[ -x "$HOME/.local/bin/doc" ]]; then
    say "Checking document/PDF toolkit backends"
    if ! "$HOME/.local/bin/doc" doctor; then
      warn "doc-tools reported missing required backends; run:"
      warn "  $HOME/.local/bin/doc doctor"
    fi
  fi

  echo
  say "Installation complete"
  echo
  echo "Next steps:"
  echo "  1. Log out and back in (or reboot) so group and shell changes apply,"
  echo "     then start Hyprland (or the SDDM Hyprland session)."
  echo "  2. Open a new terminal so fish picks up the new PATH."
  echo "  3. Set the secrets expected by ~/.config/opencode/opencode.jsonc:"
  echo "       AIHUBMIX_API_KEY"
  echo "       GITHUB_PERSONAL_ACCESS_TOKEN"
  echo "     Put them in the gitignored fish/.config/fish/conf.d/secrets.fish"
  echo "     or set them with 'set -Ux'."
  echo
  echo "Log file: $LOG_FILE"

  if [[ ! -f "$HOME/Downloads/open.wav" || ! -f "$HOME/Downloads/close.wav" ]]; then
    warn "~/Downloads/open.wav and/or close.wav are missing; the lock sounds"
    warn "used by power-menu.sh and the lid hooks will be silent."
  fi
  if command -v pandoc >/dev/null 2>&1 && ! command -v pdflatex >/dev/null 2>&1; then
    warn "Neovim's PDF export needs a LaTeX engine; HTML and DOCX export work"
    warn "with pandoc.  Install texlive-basic and texlive-latex if you need PDF."
  fi
  if [[ "$DOTFILES_DIR" != "/home/aditya/dotfiles" ]]; then
    warn "Some checked-in configs contain /home/aditya paths (hyprpaper.conf,"
    warn "hyprland.lua, power-menu.sh, autotheme includes).  If your username"
    warn "differs, update those paths after the first login."
  fi

  if ((${#FAILED_ITEMS[@]})); then
    echo
    warn "Items that failed to install (the desktop may still be usable):"
    printf '  - %s\n' "${FAILED_ITEMS[@]}" >&2
  fi

  if ((${#missing[@]})); then
    exit 1
  fi
}

main "$@"
