# System Overview

**Status:** Verified against the reference deployment on 2026-10-24.

## Purpose

This document defines the system boundary: the host, repository layout,
deployed configuration state, component relationships, runtime flows, and
generated files. Read it before any component-specific document.

## Scope

In scope:

- Repository inventory.
- Reference host and package state.
- Deployed path mapping.
- Component and data-flow architecture.
- Generated/runtime files.
- Legacy and inactive material.

Out of scope:

- Detailed component behavior (covered by component documents).
- Full package-by-package justification (covered by installation document).
- Security hardening recommendations.

## Reference deployment

| Item | Value |
| --- | --- |
| OS | Arch Linux |
| Compositor | Hyprland `0.56.2-4`, Lua configuration |
| Display manager | SDDM `0.21.0-7`, theme `maya` |
| Bootloader | GRUB `2:2.16-1`, no theme configured |
| Shell | Fish `4.9.3-1`, login shell `/usr/bin/fish` |
| Terminal | Kitty `0.49.2-1` |
| Status bar | Waybar `0.15.0-3` |
| Launcher | Wofi `1.5.3-1` |
| Notifications | Dunst `1.13.2-3` |
| Wallpaper | `awww 0.12.1-1`, Hyprpaper `0.8.4-9` fallback |
| Palette engine | `matugen 4.2.0-1`, `python-pillow 13.0.0-1` |
| Editor | Neovim `0.12.6-1` |
| Agent CLI | OpenCode `2.1.3-1` |
| Prompt | Starship `1.27.0-1` |
| User | `aditya`, UID 1000, `HOME=/home/aditya` |

These versions describe the inspected deployment, not pinned requirements.
`install.sh` installs current Arch packages.

## Deployed path mapping

| Deployed path | State on reference deployment |
| --- | --- |
| `~/.config/hypr` | Symlink to `../dotfiles/hypr/.config/hypr` |
| `~/.config/waybar` | Symlink to `../dotfiles/waybar/.config/waybar` |
| `~/.config/wofi` | Symlink to `../dotfiles/wofi/.config/wofi` |
| `~/.config/kitty` | Symlink to `/home/aditya/dotfiles/kitty/.config/kitty` |
| `~/.config/fish` | Symlink to `../dotfiles/fish/.config/fish` |
| `~/.config/nvim` | Symlink to `../dotfiles/nvim/.config/nvim` |
| `~/.config/starship.toml` | Symlink to `../dotfiles/starship/.config/starship.toml` |
| `~/.config/zathura` | Symlink to `../dotfiles/zathura/.config/zathura` |
| `~/.config/opencode` | Real directory, not a Stow symlink |
| `~/.config/gtk-3.0` | Real directory |
| `~/.config/gtk-4.0` | Real directory |
| `~/.config/dunst` | Real directory |
| `~/.config/htop` | Real directory |
| `~/.config/mimeapps.list` | Real file |
| `~/.config/trash-system` | Symlink into the repository |
| `~/.local/share/trash-system` | Absent; trash runtime not initialized |

The mixed state matters for Stow operations. Plain `stow` can conflict with the
real directories and files. `install.sh` handles conflicts by moving existing
targets aside before linking.

## Repository structure

```text
.
├── .local/                  # Older duplicate of local PDF tools
├── dunst/                   # Dunst Stow package
├── docs/                    # Documentation
├── fish/                    # Fish Stow package
├── gtk/                     # GTK 3/4 Stow package
├── htop/                    # htop Stow package
├── hypr/                    # Hyprland, lock, idle, wallpaper, scripts
├── install.sh               # Current installer
├── kitty/                   # Kitty Stow package
├── lid-sounds/              # Standalone lid helpers
├── local/                   # Active Stow package for pdfmerge
├── nvim/                    # Neovim Stow package
├── opencode/                # OpenCode Stow package
├── packages/                # Package lists
├── README.md                # Partially stale overview
├── scripts/                 # Legacy core pipeline and wallpaper generators
├── starship/                # Starship Stow package
├── system/                  # Legacy profile manifests
├── trash/                   # CAS trash system
├── waybar/                  # Waybar Stow package
├── wofi/                    # Wofi Stow package
├── xdg/                     # MIME and user-directory defaults
└── zathura/                 # Zathura Stow package
```

## Architecture

```text
                    install.sh
        packages, AUR, Stow, services, seed
                         │
        ┌────────────────┼────────────────┐
        │                │                │
  Hyprland Lua     Stow packages     Runtime state
  hyprland.lua     fish/kitty/       ~/.cache/autotheme
  hypridle         waybar/wofi/      ~/.local/state
  hyprlock         dunst/gtk/        ~/.config/dunst/dunstrc.d
  hyprpaper        nvim/opencode/
        │                │
        ├── Hyprland automation scripts
        │   adaptive-font, ui-scale, waybar-scale,
        │   battery-notify, workspace helpers,
        │   power menu, close confirmation
        │
        └── Autotheme
            wallpaper_switch.sh, wallpaper_picker.sh,
            scene.py, vibrant.py, build_theme.py, render.py,
            templates/*; repo-root tests/test_scene.py
```

### Runtime flows

| Flow | Trigger | Result |
| --- | --- | --- |
| Login | `hyprland.start` | Battery notifier, adaptive font, NetworkManager applet, Waybar, wallpaper restore, PolicyKit, Bluetooth applet, clipboard watchers |
| Wallpaper switch | `SUPER+T` or CLI | Paint wallpaper, analyse scene, extract a weighted seed/palette, run Matugen, render surfaces, reload Waybar/Kitty/Dunst, update borders |
| Terminal opacity | `terminal` function | Fade Kitty opacity, write per-instance mode, switch generated Kitty variant, update Neovim transparency |
| UI scale | `SUPER+=` / `SUPER+-` | Change focused monitor scale, regenerate Waybar CSS |
| Trash | `safe-rm` / `trash` | Hash content, store blob, update SQLite catalog, restore/purge/clean |
| Editor | `nvim` | Load core modules, LSP, completion, document mode, pinned plugins, and the wallpaper-derived colorscheme |
| Agent CLI | `opencode` | Load provider/MCP/plugin config, secrets from environment, skills and global instructions |

## Generated and runtime files

| Path | Producer | Purpose |
| --- | --- | --- |
| `~/.cache/autotheme/theme.json` | `build_theme.py` | Canonical palette |
| `~/.cache/autotheme.json` | `build_theme.py --compat` | Legacy palette copy |
| `~/.cache/autotheme/accents.json` | `vibrant.py` | Extracted seed, accents, ANSI colors, and scene document |
| `~/.cache/autotheme/seed.png` | `vibrant.py` | 64×64 solid seed for Matugen |
| `~/.cache/autotheme/matugen-roles.json` | `matugen` | Raw Material You roles |
| `~/.cache/autotheme/kitty-*.conf` | `render.py` | Kitty variants |
| `~/.cache/autotheme/kitty.conf` | symlink | Active Kitty variant |
| `~/.cache/autotheme/waybar.css` | `render.py` | Waybar color block |
| `~/.cache/autotheme/wofi.css` | `render.py` | Wofi stylesheet |
| `~/.cache/autotheme/wofi-confirm.css` | `render.py` | Confirmation stylesheet |
| `~/.cache/autotheme/gtk.css` | `render.py` | GTK color definitions |
| `~/.cache/autotheme/hyprlock-colors.conf` | `render.py` | Lock input-field colors |
| `~/.config/dunst/dunstrc.d/autotheme.conf` | `render.py` | Dunst drop-in |
| `~/.cache/autotheme/samples/` | `extract_middle_frame` | GIF frame samples |
| `~/.cache/autotheme/last.log` | scripts | Runtime log |
| `~/.cache/autotheme/lock` | `flock` | Serializes wallpaper operations |
| `~/.cache/autotheme/wallpaper` | `wallpaper_switch.sh` | Current wallpaper |
| `~/.cache/wallpaper_state` | `wallpaper_switch.sh` | Legacy current-wallpaper file |
| `~/.local/state/kitty-opacity` | `terminal.fish` | Saved Kitty opacity |
| `$XDG_RUNTIME_DIR/kitty-mode-<pid>` | Fish/terminal | Per-instance opacity mode |
| `~/.cache/waybar/style.css` | `waybar-scale.py` | Scaled and themed Waybar CSS |
| `hypr/.config/hypr/themes/wallpapers/thumbs/` | `ensure_thumb` | Thumbnail cache (ignored) |
| `~/.config/systemd/user/trash-*.service.d/override.conf` | `install.sh` | User-specific trash ExecStart |
| `~/.local/share/pdfmerge/venv/` | `install.sh` | Python PDF tooling |

## Legacy and inactive components

The following items are present but must not be treated as active:

- `system-dashboard` — removed in commit `3643ad5`. The repository README and
  `hyprland.conf.backup` still reference it.
- `hyprland.conf` — does not exist. The active file is `hyprland.lua`.
- `scripts/core/*` — legacy installer pipeline, not called by `install.sh`.
- `system/manifest.yaml`, `system/profiles/*.yaml` — legacy profile inputs.
- `.local/` — older duplicate of `local/`; only `local/` is stowed.
- SDDM Maya `theme.conf` — empty template; greeter uses defaults.
- Trash runtime — repository code exists, but the reference deployment has no
  database/object store and disabled timers.
- Video wallpapers — not implemented; `AUTOTHEME_VIDEO` is reserved and unused.

## Inspection commands

```bash
# Package versions
pacman -Q hyprland hyprpaper hypridle hyprlock waybar wofi kitty fish \
         starship dunst sddm grub matugen awww python-pillow

# Deployed config state
for p in ~/.config/{hypr,waybar,wofi,kitty,fish,nvim,opencode,gtk-3.0,gtk-4.0,dunst,htop}; do
  printf '%-24s ' "$p"
  if [ -L "$p" ]; then echo "-> $(readlink "$p")"; else echo real; fi
done

# Autotheme state
~/.config/hypr/scripts/wallpaper_switch.sh doctor
jq . ~/.cache/autotheme/theme.json

# Display manager and boot theme
cat /etc/sddm.conf.d/theme.conf 2>/dev/null
grep -E '^GRUB_(THEME|BACKGROUND)' /etc/default/grub 2>/dev/null

# Trash state
systemctl --user is-enabled trash-age.timer trash-clean.timer trash-notify.timer
ls -l ~/.local/share/trash-system 2>/dev/null
```

## Reproduction

Use [reproduction-and-verification.md](reproduction-and-verification.md) for the
clean-machine sequence and per-component checks.

## Verification

- The repository inventory, deployed path mapping, and runtime state were
  inspected.
- Package versions and service state in the reference deployment table were
  read from the live system.
- Autotheme, Hyprland, Waybar, Kitty, GTK, Dunst, Neovim, OpenCode, and trash
  details are verified to the extent stated in their component documents.
- Hyprlock visual behavior, SDDM Maya deployment, trash runtime, full Neovim
  plugin sync, and OpenCode MCP startup were not exercised.

## Known limitations

- The reference deployment uses a mix of Stow symlinks and real configuration
  copies.
- The trash runtime is not initialized.
- SDDM Maya and GRUB are not themed.
- Video wallpapers are not implemented.
- Several components hardcode `/home/aditya`.
- The repository-level `README.md` contains stale references.

## Related documentation

- [installation-and-package-management.md](installation-and-package-management.md)
- [reproduction-and-verification.md](reproduction-and-verification.md)
- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [trash-management-system.md](trash-management-system.md)
