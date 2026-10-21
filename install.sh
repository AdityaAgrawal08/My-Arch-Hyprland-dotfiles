#!/usr/bin/env bash
set -euo pipefail

# Always operate from the dotfiles checkout, no matter where the script is invoked from.
DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCODE_BIN="$HOME/.opencode/bin"
cd "$DOTFILES_DIR"

# Append a line to a file once, identified by a literal marker.
append_line_once() {
  local file="$1" marker="$2" line="$3"

  if ! grep -Fq -- "$marker" "$file" 2>/dev/null; then
    # Avoid gluing the new line onto a file that lacks a trailing newline.
    if [ -s "$file" ] && [ -n "$(tail -c 1 "$file")" ]; then
      printf '\n' >> "$file"
    fi
    printf '%s\n' "$line" >> "$file"
  fi
}

# Stow a package, backing up any pre-existing regular files that would conflict.
# The stowed copy wins, while the previous file is preserved next to it.
stow_package() {
  local pkg="$1" attempt conflicts target backup stamp
  stamp="$(date +%Y%m%d-%H%M%S)"

  for attempt in 1 2 3; do
    if stow "$pkg" 2>/dev/null; then
      return 0
    fi

    conflicts="$(stow -n -v "$pkg" 2>&1 | sed -n \
      -e 's/.*over existing target \(.*\) since neither a link nor a directory.*/\1/p' \
      -e 's/.*existing target is neither a link nor a directory: \(.*\)/\1/p' \
      -e 's/.*existing target is not owned by stow: \(.*\)/\1/p' || true)"

    if [ -z "$conflicts" ]; then
      break
    fi

    while IFS= read -r target; do
      [ -n "$target" ] || continue
      target="$HOME/$target"
      if [ -e "$target" ] || [ -L "$target" ]; then
        backup="$target.pre-dotfiles.$stamp"
        mv -- "$target" "$backup"
        echo "Backed up existing $target -> $backup"
      fi
    done <<< "$conflicts"
  done

  echo "ERROR: could not stow $pkg; unresolved conflicts:" >&2
  stow -n -v "$pkg" >&2 || true
  return 1
}

# Ensure required tools
sudo pacman -S --needed stow git base-devel

# Core scripts
chmod +x scripts/core/*.sh
mkdir -p state
./scripts/core/detect.sh > state/env.json
./scripts/core/apply.sh

# Pacman packages
sudo pacman -S --needed - < packages/pacman/base.txt
sudo pacman -S --needed - < packages/pacman/hyprland.txt

# Zathura (explicit)
sudo pacman -S --needed \
  zathura \
  zathura-pdf-poppler \
  zathura-djvu \
  zathura-ps

# AUR helper (yay)
if ! command -v yay >/dev/null 2>&1; then
  git clone https://aur.archlinux.org/yay.git /tmp/yay
  cd /tmp/yay
  makepkg -si --noconfirm
  cd -
fi

# AUR packages
if [ -f packages/aur/aur.txt ]; then
  yay -S --needed - < packages/aur/aur.txt
fi

# Stow all configs (your structure is valid)
cd "$DOTFILES_DIR"
stow_package fish
stow nvim
stow hypr
stow waybar
stow wofi
stow starship
stow zathura
stow trash
stow opencode

# Ensure local binaries executable + PATH
chmod +x "$HOME/.local/bin/"* 2>/dev/null || true
export PATH="$OPENCODE_BIN:$HOME/.local/bin:$PATH"

# Systemd user services (trash system)
systemctl --user daemon-reexec
systemctl --user enable --now trash-age.timer
systemctl --user enable --now trash-clean.timer
systemctl --user enable --now trash-notify.timer

# --- Shell configuration (zsh + fish) ---
# zsh: create a minimal ~/.zshrc if this is a fresh account, then persist OpenCode.
ZSHRC="$HOME/.zshrc"
if [ -L "$ZSHRC" ] && [ ! -e "$ZSHRC" ]; then
  rm -f "$ZSHRC"
fi
if [ ! -e "$ZSHRC" ]; then
  cat > "$ZSHRC" << 'EOF'
# ~/.zshrc - created by dotfiles/install.sh
EOF
fi
append_line_once "$ZSHRC" '.opencode/bin' 'export PATH="$HOME/.opencode/bin:$PATH"'

# fish: the stowed config normally exists, but create a minimal one as a fallback.
FISH_CONFIG="$HOME/.config/fish/config.fish"
mkdir -p "$(dirname "$FISH_CONFIG")"
if [ -L "$FISH_CONFIG" ] && [ ! -e "$FISH_CONFIG" ]; then
  rm -f "$FISH_CONFIG"
fi
if [ ! -e "$FISH_CONFIG" ]; then
  printf '# Fish shell configuration\n' > "$FISH_CONFIG"
fi
append_line_once "$FISH_CONFIG" '.opencode/bin' 'fish_add_path $HOME/.opencode/bin'

# Fish open command (idempotent)
if ! grep -q "function open" "$FISH_CONFIG" 2>/dev/null; then
  cat >> "$FISH_CONFIG" << 'EOF'

function open
    zathura $argv
end
EOF
fi

# Bootstrap additional tools
./scripts/bootstrap-tools.sh

# Set fish as default shell
if command -v fish >/dev/null 2>&1; then
  chsh -s "$(command -v fish)" || echo "warning: could not change the default shell to fish" >&2
else
  echo "warning: fish is not installed; skipping chsh" >&2
fi

echo "Setup complete"
echo "Run 'exec \$SHELL' (or restart your terminal) to pick up the new PATH."
