# Reproduction and Verification

**Status:** Procedural guide. Runtime results depend on the target machine and
package availability.

## Purpose

Defines the end-to-end procedure for rebuilding the system on a clean Arch Linux
installation and verifying each component.

## Scope

In scope:

- Prerequisites.
- Automated and manual installation.
- Autotheme seeding and first switch.
- Per-component verification.
- Troubleshooting.
- Hardcoded paths and known gaps.

Out of scope:

- Filesystem, kernel, bootloader, or Secure Boot installation.
- Hardware-specific driver tuning beyond `install.sh` detection.
- Optional SDDM/GRUB/video features that are not implemented.

## Assumptions

- Arch Linux or an Arch-based system.
- Non-root user with `sudo`.
- Network access.
- Wayland-capable graphics stack.
- Repository at `~/dotfiles`.
- Reference user `aditya`; adjust hardcoded paths if different.

## Prerequisites

```bash
sudo pacman -S --needed git base-devel stow
```

`install.sh` expects `/etc/arch-release`, `pacman`, and `sudo`.

## Reproduction

### Automated installation

```bash
git clone https://github.com/AdityaAgrawal08/My-Arch-Linux-Configurations.git ~/dotfiles
cd ~/dotfiles
./install.sh
```

Options:

```bash
SKIP_PACMAN_UPDATE=1 ./install.sh
SKIP_OPTIONAL=1 ./install.sh
SKIP_AUR=1 ./install.sh
SKIP_STOW=1 ./install.sh
NO_SERVICES=1 ./install.sh
```

After completion:

1. Log out and back in.
2. Start Hyprland.
3. Open a new terminal.
4. Set OpenCode secrets.
5. Run the verification matrix.

The installer seeds autotheme generated files with:

```bash
~/.config/hypr/scripts/wallpaper_switch.sh init
```

If that step failed, run it manually.

### Manual installation

#### Desktop packages

```bash
sudo pacman -S --needed \
  hyprland hyprpaper hypridle hyprlock hyprshot hyprsunset hyprpolkitagent \
  matugen awww python-pillow \
  waybar wofi kitty thunar dunst \
  grim slurp wl-clipboard cliphist \
  fish starship jq python3 \
  ttf-jetbrains-mono-nerd ttf-firacode-nerd \
  imagemagick ffmpeg \
  gtk3 gtk4 adwaita-icon-theme adwaita-fonts \
  sddm grub efibootmgr os-prober
```

#### Trash system

```bash
sudo pacman -S --needed sqlite3 file util-linux jq fzf libnotify
```

#### PDF tools

```bash
sudo pacman -S --needed libreoffice-fresh python
```

#### Neovim

```bash
sudo pacman -S --needed neovim git ripgrep fd nodejs npm go rust clang \
  jdk-openjdk pandoc
```

#### OpenCode

```bash
sudo pacman -S --needed opencode nodejs npm uv
```

#### Stow

```bash
cd ~/dotfiles
stow --target="$HOME" --no-folding --restow \
  hypr waybar wofi kitty fish starship dunst gtk htop zathura \
  trash xdg local nvim opencode
```

If Stow conflicts with an existing real file, move it aside or use
`install.sh`’s conflict-safe Stow wrapper.

#### Seed autotheme

```bash
~/.config/hypr/scripts/wallpaper_switch.sh init
```

#### Services

```bash
systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service
systemctl --user enable --now trash-age.timer trash-clean.timer trash-notify.timer
```

Enable system services (NetworkManager, Bluetooth, SDDM) manually if not using
`install.sh`.

#### OpenCode secrets

Set `AIHUBMIX_API_KEY` and `GITHUB_PERSONAL_ACCESS_TOKEN` in the environment, or
add them to the ignored `fish/.config/fish/conf.d/secrets.fish`.

### Autotheme first switch

1. Create the library:
   ```bash
   mkdir -p ~/.config/hypr/themes/wallpapers/{assets,thumbs}
   cp <wallpaper-file> ~/.config/hypr/themes/wallpapers/assets/
   ```
2. Ensure scripts and templates are installed and executable.
3. Ensure `kitty.conf` ends with:
   ```conf
   include /home/aditya/.cache/autotheme/kitty.conf
   ```
4. Ensure Waybar uses `waybar-scale.py`.
5. Ensure `wofi/config` has:
   ```ini
   style=/home/aditya/.cache/autotheme/wofi.css
   ```
6. Ensure `confirm_close.sh` uses the generated confirmation stylesheet.
7. Ensure both GTK CSS files import:
   ```css
   @import url("file:///home/aditya/.cache/autotheme/gtk.css");
   ```
8. Ensure `hyprlock.conf` ends with:
   ```conf
   source = /home/aditya/.cache/autotheme/hyprlock-colors.conf
   ```
9. Ensure `hyprland.lua` has the `SUPER+T` bind, `restore` autostart, and
   `config.reloaded` border hook.
10. Run the scene regression tests:
    ```bash
    python3 -m unittest discover \
      -s tests -p 'test_*.py' -v
    ```
11. Apply:
    ```bash
    ~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file>
    ```

## Component map

| Component | Source | Deployed/generated |
| --- | --- | --- |
| Hyprland | `hypr/.config/hypr/hyprland.lua` | `~/.config/hypr/hyprland.lua` |
| Hypridle | `hypridle.conf` | `~/.config/hypr/hypridle.conf` |
| Hyprlock | `hyprlock.conf` | `~/.config/hypr/hyprlock.conf` + cache source |
| Hyprpaper | `hyprpaper.conf` | `~/.config/hypr/hyprpaper.conf` |
| Autotheme | `scripts/autotheme.conf`, `wallpaper_switch.sh`, `lib/*`, `templates/*` | same + `~/.cache/autotheme/*` |
| Waybar | `waybar/config.jsonc`, `style.css` | same + `~/.cache/waybar/style.css` |
| Wofi | `wofi/config`, templates | same + cache styles |
| Kitty | `kitty.conf` | same + generated include |
| Fish | `fish/.config/fish/*` | same |
| Starship | `starship.toml` | same |
| Dunst | `dunstrc` | same + `dunstrc.d/autotheme.conf` |
| GTK | `gtk-3.0/4.0` | same |
| Trash | `trash/*` | `~/.local/bin/*`, `~/.local/share/trash-system/*` |
| Neovim | `nvim/.config/nvim/*` | same + `~/.local/share/nvim/lazy/*` |
| OpenCode | `opencode/.config/opencode/*` | same |
| PDF tools | `.local/bin/*`, `local/.local/*` | `~/.local/bin/*`, `~/.local/share/pdfmerge/*` |
| XDG | `xdg/.config/*` | `~/.config/mimeapps.list`, `user-dirs.dirs` |
| Zathura | `zathurarc` | `~/.config/zathura/zathurarc` |
| htop | `htoprc` | `~/.config/htop/htoprc` |

## Verification matrix

### Hyprland

```bash
Hyprland --version
hyprctl configerrors
hyprctl binds -j | jq '.[] | select(.key=="T")'
hyprctl getoption general:col.active_border -j
```

Expected:

- No config errors.
- `SUPER+T` present.
- Generated accent gradient after autotheme has run.

### Autotheme

```bash
~/.config/hypr/scripts/wallpaper_switch.sh doctor
jq . ~/.cache/autotheme/theme.json
jq '{seed, scene}' ~/.cache/autotheme/accents.json
~/.config/hypr/scripts/wallpaper_switch.sh scene
~/.config/hypr/scripts/wallpaper_switch.sh explain
readlink ~/.cache/autotheme/kitty.conf
awww query
```

Expected:

- Backend reported.
- Theme contains `bg`, `accent`, `fg`, and `scene.version`.
- `accents.json` contains a seed and the scene metrics/tags/strategy.
- `scene` prints valid JSON; `explain` prints seed, scheme, contrast, and
  lightness.
- Active Kitty variant exists.
- Current wallpaper path reported.

Scene regression:

```bash
AUTOTHEME_SCENE=off AUTOTHEME_FORCE=1 \
  ~/.config/hypr/scripts/wallpaper_switch.sh regenerate
jq '{scene, seed}' ~/.cache/autotheme/theme.json
~/.config/hypr/scripts/wallpaper_switch.sh regenerate
```

Expected: the off run has no scene/seed and uses the original Matugen
invocation; the second run restores the scene theme. The scene layer adds
roughly 20–40 ms of CPU and no measurable peak RSS on the reference wallpaper.

Switch test:

```bash
~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file>
```

Check:

- Wallpaper changes.
- Waybar reloads.
- Kitty colors update.
- Wofi next launch is themed.
- Dunst next notification is themed.
- Hyprland border changes.

Same-wallpaper test:

```bash
~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file>
```

Expected: `last.log` reports “palette unchanged ... skipping matugen”; wallpaper
is repainted.

Fallback test:

```bash
AUTOTHEME_MATUGEN=never AUTOTHEME_FORCE=1 \
  ~/.config/hypr/scripts/wallpaper_switch.sh apply <wallpaper-file>
jq '.bg' ~/.cache/autotheme/theme.json
```

Expected: `#121212` fallback surface and a complete theme.

### Kitty, Fish, Starship

```bash
kitty --config ~/.config/kitty/kitty.conf sh -c 'sleep 1'
kitten @ ls | jq '.[0].background_opacity'
fish -n ~/.config/fish/config.fish
```

In a Kitty/Fish window:

```fish
terminal transparent
terminal opaque
```

Expected:

- Opacity 0.2 / 1.0.
- Background switches between tinted and black.
- `~/.local/state/kitty-opacity` updates.
- Neovim applies the generated palette and follows the per-instance
  transparent/opaque mode.

### Waybar

```bash
pgrep -a waybar
head -20 ~/.cache/waybar/style.css
```

Expected:

- Waybar uses `-s /home/aditya/.cache/waybar/style.css`.
- Cache starts with `@define-color bg`.

### Wofi

```bash
wofi --show drun
```

Expected: themed launcher. `SUPER+T` opens the wallpaper picker with thumbnails.

### Dunst

```bash
dunstctl reload
notify-send "Theme test" "This should use the current palette."
journalctl --user -u dunst -n 20 --no-pager
```

Expected: themed notification; no new color/parse errors. The pre-existing
`show_age_threshold` warning is expected.

### GTK

```bash
python3 - <<'PY'
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
p = Gtk.CssProvider()
p.load_from_path("/home/aditya/.config/gtk-3.0/gtk.css")
print("gtk3 ok")
PY
```

Expected: no CSS parse error. Restart a GTK application to see the colors.

### Hyprlock

```bash
hyprlock
```

Expected: input ring/check uses the current accent. If not, review the source
ordering described in
[notifications-gtk-and-lock-screen.md](notifications-gtk-and-lock-screen.md).

### Trash

If initialized:

```bash
~/.local/bin/trash health
~/.local/bin/trash list
```

Expected: `OK` and a table. If not initialized, see
[trash-management-system.md](trash-management-system.md).

### Neovim

```bash
nvim --headless "+Lazy! sync" +qa
nvim --headless "+checkhealth" +qa
nvim --headless "+lua print(vim.g.colors_name, vim.inspect(vim.api.nvim_get_hl(0, { name = 'Normal' })))" +qa
```

Expected: pinned plugins install; `colors_name` is `autotheme`; `Normal` colors
match `theme.json`; checkhealth reports missing external tools. Open a Markdown
file and test `<leader>mt` and `<leader>mf`.

### OpenCode

Start `opencode` in a scratch directory and verify:

- Provider `AiHubMix`/`shooterdelta1` lists GLM models.
- MCP servers start.
- `/tmp/opencode/*` edits are allowed.
- `opencode-go` preset is active.
- Skills are discoverable.

## Recommended rebuild order

1. Base Arch, networking, sudo.
2. `install.sh` or manual packages.
3. Stow all packages.
4. `wallpaper_switch.sh init`.
5. Log out/in.
6. Verify Hyprland, Waybar, Kitty, Wofi, Dunst.
7. Add wallpapers and test `SUPER+T`.
8. Verify Hyprlock.
9. Verify trash if required.
10. Bootstrap Neovim (`:Lazy sync`, `:Mason`, `:TSUpdate`).
11. Set OpenCode secrets and verify.
12. Commit local changes.

## Troubleshooting

### Stow conflicts

Real directories/files on existing machines:

```text
~/.config/gtk-3.0
~/.config/gtk-4.0
~/.config/dunst
~/.config/htop
~/.config/mimeapps.list
~/.config/opencode
```

Options:

- Use `install.sh` (backs up conflicts).
- Move the existing target aside.
- `stow --adopt` and review the diff.
- Copy the new files manually for GTK.

### Waybar has no colors

- Confirm it was started with `waybar-scale.py start`.
- Check `~/.cache/autotheme/waybar.css`.
- Regenerate:
  ```bash
  ~/.config/hypr/scripts/wallpaper_switch.sh init
  ~/.config/hypr/scripts/waybar-scale.py apply
  ```

### Wofi is unstyled

- Check `style=` in `wofi/config`.
- Check `~/.cache/autotheme/wofi.css`.
- Reopen Wofi; it does not live-reload.

### Kitty has no theme

- Check `~/.cache/autotheme/kitty.conf`.
- Check the `include` line in `kitty.conf`.
- Run:
  ```bash
  ~/.config/hypr/scripts/wallpaper_switch.sh kitty-mode auto
  ```

### Hyprland borders do not change

- Hyprland 0.56 requires `hyprctl eval`, not `hyprctl keyword`.
- Check:
  ```bash
  hyprctl getoption general:col.active_border -j
  ~/.config/hypr/scripts/wallpaper_switch.sh borders
  ```

### Hyprlock input ring is not themed

- Verify the generated source file exists.
- Verify the `source` line is at the end of `hyprlock.conf`.
- If ordering is wrong, move the source before the `input-field` block or use a
  generated full config.

### Dunst reload message

“Reloading settings (with the old files)” is normal for argument-less
`dunstctl reload`; it reloads the same paths, including the drop-in.

### Trash not initialized

```bash
ls ~/.local/share/trash-system
```

If absent, run the installer’s trash step or `trash/install.sh`, then
`bash trash/scripts/init-db.sh`.

## Hardcoded paths

Review these when the user or home directory differs:

```text
hypr/.config/hypr/hyprpaper.conf
hypr/.config/hypr/hyprland.lua
hypr/.config/hypr/hyprlock.conf
hypr/.config/hypr/scripts/lib/autotheme.sh
kitty/.config/kitty/kitty.conf
wofi/.config/wofi/config
gtk/.config/gtk-3.0/gtk.css
gtk/.config/gtk-4.0/gtk.css
hypr/.config/hypr/scripts/power-menu.sh
lid-sounds/*.sh
trash/.config/systemd/user/*.service
scripts/process_wallpaper.py
```

## Known limitations

- SDDM Maya remains at default colors.
- GRUB is not themed.
- Video wallpapers are unsupported.
- Trash is not initialized by default.
- `plugins/navigation.lua` and `plugins/dap.lua` are not loaded.
- OpenCode MCP/model availability depends on network and credentials.
- Package versions change over time.
- The repository-level `README.md` contains stale references.

## Related documentation

- [system-overview.md](system-overview.md)
- [installation-and-package-management.md](installation-and-package-management.md)
- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [trash-management-system.md](trash-management-system.md)
