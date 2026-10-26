# Documentation Portal

**Status:** Living documentation. Component-level verification status is recorded
in each document.

## Purpose

This directory contains the operational documentation for the Arch Linux
Hyprland dotfiles in this repository. Each document describes a component's
purpose, files, behavior, dependencies, reproduction steps, verification, and
known limitations.

## Documentation contract

Every component document is written to satisfy three requirements:

1. **Traceability** — every claim maps to a file, command, or observed runtime
   behavior in this repository or its reference deployment.
2. **Reproducibility** — the document identifies the exact files to install,
   packages to install, commands to run, and expected results.
3. **AI-agent usability** — terminology, paths, and state transitions are
   explicit; no step depends on this conversation or on undocumented context.

The source files are always authoritative. If a document and the repository
disagree, the repository wins. Update the document after changing the source.

## Source-of-truth order

Use this order when resolving inconsistencies:

1. Active source files in the repository.
2. `install.sh` for installation behavior.
3. The relevant document in `docs/`.
4. The repository-level `README.md`.
5. Legacy files such as `hyprland.conf.backup` and `scripts/core/*`.

The repository-level `README.md` is partially stale. It still references a
removed `system-dashboard`, a non-existent `hyprland.conf`, and the legacy
`scripts/core` installer flow. This documentation records the actual state.

## Document map

| Document | Scope |
| --- | --- |
| [system-overview.md](system-overview.md) | Repository inventory, reference deployment state, architecture, generated files, legacy material |
| [installation-and-package-management.md](installation-and-package-management.md) | `install.sh`, package groups, AUR bootstrap, Stow behavior, services, legacy `scripts/core` pipeline |
| [hyprland-configuration.md](hyprland-configuration.md) | `hyprland.lua`, monitor/environment/autostart, appearance, keybindings, window rules, Hypridle, Hyprlock, Hyprpaper |
| [hyprland-automation-scripts.md](hyprland-automation-scripts.md) | Battery notifier, adaptive font, UI scaling, Waybar scaling, workspace helpers, power menu, close confirmation, night light |
| [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md) | Wallpaper backends, palette extraction, Matugen, theme construction, templates, per-surface integration, picker, state, fallbacks |
| [scene-aware-theming.md](scene-aware-theming.md) | Pillow-only attention map, metrics, tags, strategy, seed selection, resource budget, scene regression tests |
| [waybar-status-bar.md](waybar-status-bar.md) | Module layout, active/inactive modules, styling tokens, scaling, Bluetooth provider |
| [wofi-launcher.md](wofi-launcher.md) | Launcher, browser picker, power menu, confirmation dialog, generated styles |
| [terminal-shell-and-prompt.md](terminal-shell-and-prompt.md) | Kitty, Fish, Starship, opacity model, adaptive font integration, encrypted-vault `cd` |
| [notifications-gtk-and-lock-screen.md](notifications-gtk-and-lock-screen.md) | Dunst, GTK 3/4, Hyprlock, observed SDDM Maya/GRUB state |
| [trash-management-system.md](trash-management-system.md) | CAS trash architecture, SQLite schema, `safe-rm`, CLI, manifests, timers, installation, risks |
| [neovim-configuration.md](neovim-configuration.md) | Core options/keymaps/autocommands, wallpaper-derived colorscheme, LSP, AutoImport, completion, document mode, plugins |
| [opencode-agent-configuration.md](opencode-agent-configuration.md) | Provider, MCP servers, Omo-Slim presets, `AGENTS.md`, skills, secrets |
| [document-and-file-utilities.md](document-and-file-utilities.md) | `docs`/`doc` toolkit, `pdfmerge` three-output contract, conversions, PDF operations, `open.fish`, Zathura, XDG defaults |
| [supporting-tools.md](supporting-tools.md) | Lid scripts, wallpaper generators, htop |
| [reproduction-and-verification.md](reproduction-and-verification.md) | Clean-machine rebuild order, per-component verification, troubleshooting, hardcoded paths |

## Reading paths

### Rebuild the system

1. [system-overview.md](system-overview.md)
2. [installation-and-package-management.md](installation-and-package-management.md)
3. [reproduction-and-verification.md](reproduction-and-verification.md)
4. The component documents for each surface being enabled.

### Maintain a component

1. Read the component document.
2. Read every file listed under “Files and Paths”.
3. Check “Runtime Behavior”, “Integration Points”, and “Known Limitations”.
4. Use the verification section before and after changes.

### Use an AI agent

Provide the agent with:

- This portal.
- `system-overview.md`.
- The target component document.
- The actual source files named by that document.

Instruct the agent to:

1. Read the complete files, not only the changed sections.
2. Treat source files as authoritative.
3. Preserve hardcoded paths unless the deployment user changes.
4. Run the verification steps before declaring completion.
5. Report unverified behavior and remaining limitations explicitly.

## Conventions

### Paths

- Repository paths are written relative to the repository root, for example
  `hypr/.config/hypr/hyprland.lua`.
- Deployed paths are written with `~`, for example
  `~/.config/hypr/hyprland.lua`.
- The reference deployment uses `HOME=/home/aditya`. Some scripts hardcode that
  path; each document identifies them.

### Status labels

- **Verified** — exercised on the reference deployment or validated with the
  relevant parser/tool.
- **Partially verified** — source and configuration were inspected, but at
  least one runtime path was not exercised.
- **Documentation only** — the implementation exists in the repository but is
  not active or initialized on the reference deployment.

### Runtime terminology

- **Reference deployment** — the inspected Arch/Hyprland machine described in
  `system-overview.md`.
- **Generated file** — produced at runtime and safe to recreate.
- **Tracked file** — stored in the repository.
- **Legacy** — present in the repository but not used by `install.sh` or the
  active desktop path.
- **Inactive** — configured but not reached by the active runtime path.

### Code blocks

Commands and configuration examples use explicit language tags. Placeholders
are written as `<value>` or `<path>` and must be replaced before execution.

## Verification status

The documentation was prepared with the following checks:

| Check | Result |
| --- | --- |
| Repository inventory and file review | Complete |
| Reference deployment inspection | Complete |
| Bash syntax (`bash -n`) | Pass |
| Fish syntax (`fish -n`) | Pass |
| Python syntax (`py_compile`) | Pass |
| GTK3/GTK4 CSS parsing | Pass |
| Waybar/Wofi generated CSS parsing | Pass |
| Autotheme `doctor`, `apply`, `restore`, `regenerate`, `init`, `kitty-mode`, border apply | Exercised |
| Scene unit tests (`test_scene.py`) | Pass |
| Scene `scene` / `explain` commands | Exercised |
| `AUTOTHEME_SCENE=off` regression | Pass |
| Scene CPU/RSS budget | Pass |
| Document/PDF toolkit integration (`tests/test_doc_tools.py`) | Pass; 25 tests |
| `docs --help` manual and `docs doctor` | Exercised |
| Neovim dynamic colorscheme loading | Pass |
| Hyprlock visual override | Not exercised |
| SDDM Maya deployment | Not implemented |
| Trash runtime | Not initialized |
| Full Neovim plugin synchronization | Not exercised |
| OpenCode MCP/provider startup | Not exercised |

Component documents repeat their own verification status and limitations.

## Documentation maintenance

When a source file changes:

1. Update the corresponding component document.
2. Update cross-references if a file was renamed or removed.
3. Re-run the verification steps in the document.
4. Update the status label if verification coverage changed.
5. Keep the document direct and factual; remove stale claims rather than
   preserving them for history.

Do not add unrelated system facts, opinions, or speculative behavior. If a
behavior could not be verified, state exactly what is known and what remains
unverified.
