# Terminal, Shell, and Prompt

**Status:** Verified for Kitty configuration, Fish syntax, opacity transitions,
generated Kitty colors, and Neovim transparency integration.

## Purpose

Defines the terminal and shell layer:

- Kitty terminal configuration and remote-control integration.
- Fish shell configuration, functions, and environment.
- Starship prompt.
- Kitty opacity ↔ autotheme ↔ Neovim transparency.

## Scope

In scope:

- `kitty/.config/kitty/kitty.conf`
- `fish/.config/fish/`
- `starship/.config/starship.toml`
- `terminal.fish`, `kitty-opacity.fish`
- `adaptive-font.py` integration
- Autotheme Kitty variants and Neovim’s transparency reader

Out of scope:

- Other terminals or shells.
- Fish plugin managers.
- Starship upstream modules.

## Files and paths

| Path | Role |
| --- | --- |
| `kitty/.config/kitty/kitty.conf` | Static Kitty configuration |
| `fish/.config/fish/config.fish` | Main Fish configuration and custom `cd` |
| `fish/.config/fish/functions/open.fish` | Extension-based opener |
| `fish/.config/fish/functions/terminal.fish` | Kitty opacity toggle |
| `fish/.config/fish/conf.d/fnm.fish` | `fnm env --use-on-cd` |
| `fish/.config/fish/conf.d/kitty-opacity.fish` | Applies saved opacity to new windows |
| `fish/.config/fish/conf.d/opencode-background-subagents.fish` | OpenCode environment |
| `fish/.config/fish/conf.d/trash.fish` | Trash path environment |
| `fish/.config/fish/conf.d/fish_frozen_key_bindings.fish` | Fish 4.3 key-binding migration |
| `fish/.config/fish/fish_variables` | Universal variables (runtime, ignored) |
| `starship/.config/starship.toml` | Prompt configuration |
| `hypr/.config/hypr/scripts/adaptive-font.py` | Adaptive font/padding daemon |
| `~/.cache/autotheme/kitty.conf` | Active generated Kitty include |
| `~/.cache/autotheme/kitty-opaque.conf` | Opaque variant |
| `~/.cache/autotheme/kitty-transparent.conf` | Transparent variant |
| `~/.local/state/kitty-opacity` | Saved opacity |
| `$XDG_RUNTIME_DIR/kitty-mode-<pid>` | Per-instance opacity mode |

## Kitty

### Static configuration

```conf
font_family      JetBrainsMono Nerd Font
bold_font        auto
italic_font      auto
bold_italic_font auto
font_size        10.0

window_padding_width 12
hide_window_decorations yes
confirm_os_window_close 0
scrollback_lines -1

remember_window_size no
initial_window_width 800
initial_window_height 500

background            #000000
background_opacity 1.0
dynamic_background_opacity yes
allow_remote_control yes
listen_on unix:${XDG_RUNTIME_DIR}/kitty
```

All foreground, ANSI, cursor, selection, and tab colors come from the generated
autotheme include. The static file only defines layout, the opaque background,
opacity behavior, and remote control.

Additional settings:

```conf
map ctrl+a launch --type=clipboard --stdin-source=@screen_scrollback

tab_bar_edge            top
tab_bar_background      #000000

include /home/aditya/.cache/autotheme/kitty.conf
```

The generated include overrides foreground, cursor, selection, tab accents,
border colors, background, and ANSI colors. It does not set
`background_opacity`.

`remember_window_size no` prevents Kitty from restoring a cached maximized
state from `~/.cache/kitty/main.json`.

Remote control is required by:

- `adaptive-font.py` (`set-font-size`, `set-spacing`)
- `terminal.fish` / `kitty-opacity.fish` (`set-background-opacity`)
- `wallpaper_switch.sh kitty-mode` (`set-colors`)

### Opacity model

Saved preference:

```text
~/.local/state/kitty-opacity
```

Values: `1.0` (opaque) or `0.2` (transparent).

Per-instance mode:

```text
$XDG_RUNTIME_DIR/kitty-mode-<KITTY_PID>
```

Values: `opaque` or `transparent`.

`terminal.fish`:

1. Reads focused-window opacity with `kitten @ ls`.
2. Chooses target `1.0` or `0.2` from `transparent`, `opaque`, or `toggle`.
3. Fades over 12 frames with 5 ms gaps using
   `kitten @ set-background-opacity --all`.
4. Writes the per-instance mode file.
5. Writes `~/.local/state/kitty-opacity`.
6. Calls:
   ```fish
   ~/.config/hypr/scripts/wallpaper_switch.sh kitty-mode --pid $KITTY_PID <mode>
   ```
   or without `--pid` when `KITTY_PID` is unset.

`kitty-opacity.fish` (new windows):

- Runs only in interactive Kitty shells.
- Reads the saved preference.
- Fades to the preference using
  `kitten @ set-background-opacity --match id:$KITTY_WINDOW_ID`.
- Writes the per-instance mode file based on `pref > 0.6`.
- Does not switch the active generated variant.

`wallpaper_switch.sh kitty-mode`:

- `opaque`: symlink `kitty-opaque.conf` as the active include and apply it with
  `kitten @ set-colors --all --configured`.
- `transparent`: same with `kitty-transparent.conf`.
- `auto`: choose the include from the saved opacity; apply per-instance mode
  files to live sockets.
- Never changes opacity.

### Autotheme variants

Opaque:

```conf
background              #000000
tab_bar_background      #000000
inactive_tab_background #000000
```

Transparent:

```conf
background              <theme.kitty_bg_transparent>
tab_bar_background      <same>
inactive_tab_background <same>
```

Shared:

```conf
foreground              <theme.fg>
cursor                  <theme.accent>
cursor_text_color       <theme.onAccent>
selection_foreground    <theme.onAccent>
selection_background    <theme.accent>
url_color               <theme.accentSoft>
active_tab_background   <theme.accent>
active_tab_foreground   <theme.onAccent>
inactive_tab_foreground <theme.muted>
active_border_color     <theme.accent>
inactive_border_color   <theme.border>
color0..color15         extracted ANSI palette
```

### Adaptive font

`adaptive-font.py` adjusts font and padding from tiled window size.

Tuning:

| Setting | Value |
| --- | --- |
| Base font | 10.0 |
| Min font | 7.0 |
| Max font | 14.0 |
| Base padding | 12.0 |
| Min padding | 6.0 |
| Max padding | 12.0 |
| Base area | 1276 × 674 |
| Base scale | 1.5 |
| Debounce | 0.3 s |

Formula:

```text
scale = sqrt(window_area / BASE_AREA) * monitor_scale / BASE_SCALE
font  = clamp(BASE_FONT * scale, MIN_FONT, MAX_FONT)
pad   = clamp(BASE_PADDING * scale, MIN_PADDING, MAX_PADDING)
```

It sends:

```bash
kitten @ --to unix:$XDG_RUNTIME_DIR/kitty-<pid> set-font-size --all <font>
kitten @ --to unix:$XDG_RUNTIME_DIR/kitty-<pid> set-spacing --all padding=<pad>
```

Full daemon behavior is in
[hyprland-automation-scripts.md](hyprland-automation-scripts.md).

### Neovim transparency integration

`nvim/.config/nvim/lua/core/autotheme.lua` reads:

```text
$XDG_RUNTIME_DIR/kitty-mode-$KITTY_PID
~/.cache/autotheme/theme.json
```

- `transparent` → generated palette with a transparent `Normal` background.
- `opaque` → generated palette with a solid background.
- Missing mode file → transparent.
- Polls both files every two seconds and reapplies highlight groups when either
  changes.

## Fish

### Main configuration

- `fish_color_command green`
- `fish_color_error red`
- `fish_color_match cyan`
- `fish_color_autosuggestion brgrey`
- `fish_greeting ""`
- `EDITOR`/`VISUAL` = `nvim`
- Adds `~/.local/bin` to `fish_user_paths` if missing.
- `PAGER=less`, `LESS=-R`, `MANPAGER=less -R`, `LESSHISTFILE=-`
- Sources `starship init fish` if Starship exists.
- Warns if `zathura`, `imv`, `mpv`, `libreoffice`, or `xdg-open` is missing.
- Adds `~/.opencode/bin` to PATH.

### Encrypted-vault `cd`

`config.fish` overrides `cd` for a gocryptfs vault:

- Mount point: `$HOME/.important`
- Encrypted vault: `$HOME/.important.encrypted`

Behavior:

1. Resolve target with `realpath -m`.
2. If target is inside or equal to `.important`:
   - If not mounted, verify both paths exist.
   - Run `gocryptfs -- "$vault" "$important"`.
3. Run `builtin cd` with original arguments.
4. If leaving `.important`, run `fusermount3 -u -- "$important"`.
5. If unmount fails because files are open, warn and still return success.
6. `lock_important_on_exit` unmounts on `fish_exit`.

Assumptions:

- `gocryptfs`, `fusermount3`, `mountpoint`, `realpath -m` are installed.
- Both vault paths exist.
- The vault can be unlocked interactively or is already mounted.

### `open.fish`

| Extension | Application |
| --- | --- |
| `.pdf` | `zathura` |
| `.png .jpg .jpeg .webp .gif` | `imv` |
| `.mp4 .mkv .webm .mp3` | `mpv` |
| `.docx .pptx .xlsx` | `libreoffice` |
| other | `xdg-open` |

Missing files are skipped with a message. Commands run in the background.

### Other Fish snippets

`fnm.fish`:

```fish
fnm env --use-on-cd | source
```

`opencode-background-subagents.fish`:

```fish
set -gx OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS true
set -gx OPENCODE_ENABLE_EXA 1
```

`trash.fish`:

```fish
set -gx TRASH_BASE "$HOME/.local/share/trash-system"
set -gx TRASH_DB "$TRASH_BASE/db/trash.db"
set -gx TRASH_OBJECTS "$TRASH_BASE/objects"
```

`fish_frozen_key_bindings.fish` erases the universal `fish_key_bindings`
variable for the Fish 4.3 migration.

## Starship

`starship.toml`:

- `add_newline = false`
- Format:
  `username directory git_branch git_status python nodejs rust c cmd_duration character`
- Username always shown, bold cyan.
- Character `>` green on success, `x` red on error.
- Directory bold blue, truncate 3, truncate to repo, home `~`.
- Git branch with Nerd Font symbol, bold yellow; `git_status` disabled.
- Python/Node/Rust/C modules configured but disabled.
- `cmd_duration` disabled.
- `time` disabled.

Starship uses ANSI names, so it follows Kitty’s generated palette.

## Dependencies

- `kitty` with remote control enabled
- `fish` as login shell
- `starship`
- `python3` for inline JSON parsing in Fish functions
- `fnm` for `fnm.fish`
- `gocryptfs`, `fuse3`, `mountpoint`, `realpath` for vault `cd`
- `zathura`, `imv`, `mpv`, `libreoffice`, `xdg-utils` for `open`
- `kitten` for font, opacity, and color updates

## Reproduction

```bash
sudo pacman -S --needed kitty fish starship python \
  gocryptfs fuse3 zathura imv mpv libreoffice-fresh xdg-utils

cd ~/dotfiles
stow --target="$HOME" --no-folding kitty fish starship hypr
chsh -s /usr/bin/fish

~/.config/hypr/scripts/wallpaper_switch.sh init
kitty
```

Vault setup:

```text
~/.important
~/.important.encrypted
```

or edit the paths at the top of the custom `cd` function.

## Verification

```bash
fish -n ~/.config/fish/config.fish
fish -n ~/.config/fish/functions/terminal.fish
fish -n ~/.config/fish/functions/open.fish
kitty --config ~/.config/kitty/kitty.conf sh -c 'sleep 1'
kitten @ ls | jq '.[0].background_opacity'
kitten @ get-colors | head
```

Verified:

- New Kitty instances load the generated include.
- `kitten @ set-colors` preserves opacity.
- `terminal transparent` writes opacity `0.2`, mode `transparent`, and the
  generated tinted background.
- `terminal opaque` restores opacity `1.0` and black background.
- Fish and Python syntax checks pass.

Not verified:

- Vault `cd` with a real gocryptfs mount.
- `open.fish` with every extension.
- Starship rendering in a non-Kitty terminal.

## Known limitations

- `terminal` fades only the current Kitty instance.
- `kitty-opacity.fish` applies the global preference but does not switch the
  active generated variant.
- Mixed Kitty instances can have different modes until `terminal` or
  `kitty-mode` runs for each.
- `open.fish` uses extension mapping, not MIME detection.
- The vault `cd` requires existing vault paths and installed FUSE tooling.
- `fnm.fish` prints an error if `fnm` is absent.
- `terminal.fish` requires Python.
- Starship colors depend on Kitty’s ANSI palette.
- Neovim creates `transparent` mode if the mode file is missing.

## Related documentation

- [hyprland-automation-scripts.md](hyprland-automation-scripts.md)
- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [neovim-configuration.md](neovim-configuration.md)
- [document-and-file-utilities.md](document-and-file-utilities.md)
