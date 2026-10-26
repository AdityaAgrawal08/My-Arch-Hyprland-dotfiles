# Neovim Configuration

**Status:** Configuration, syntax, and dynamic colorscheme loading verified.
Full plugin synchronization and runtime LSP startup were not exercised.

## Purpose

Provides a Lua-based Neovim environment built on `lazy.nvim`, with LSP,
completion, AutoImport, formatting, document editing, Markdown tooling, Git
integration, and a wallpaper-derived colorscheme that follows Kitty transparency.

## Scope

In scope:

- `nvim/.config/nvim/init.lua`
- `lua/core/*`
- `lua/plugins/*`
- `lazy-lock.json`
- Kitty transparency integration
- Markdown/text document mode

Out of scope:

- External language-server installation details.
- External formatter installation details.
- Neovim upstream behavior.

## Files and paths

```text
nvim/.config/nvim/
├── init.lua
├── lazy-lock.json
└── lua/
    ├── core/
    │   ├── autocmds.lua
    │   ├── autotheme.lua
    │   ├── autoimport.lua
    │   ├── document.lua
    │   ├── keymaps.lua
    │   ├── lsp.lua
    │   ├── options.lua
    │   ├── completion/neighbors.lua
    │   └── imports/{go,java,ts}.lua
    └── plugins/
        ├── init.lua
        ├── ui.lua
        ├── editor.lua
        ├── files.lua
        ├── git.lua
        ├── lsp.lua
        ├── document.lua
        ├── navigation.lua   # not imported
        └── dap.lua          # not imported
```

## Load order

`init.lua`:

```lua
require("core.options")
require("core.keymaps")
require("core.autoimport").setup({
  auto_import_while_typing = false,
  auto_import_on_diagnostics = false,
  auto_import_on_save = true,
  organize_imports_on_save = true,
})
require("core.autocmds")
require("core.autotheme").setup()
require("plugins.init")
```

`plugins/init.lua` bootstraps `lazy.nvim` into
`stdpath("data") .. "/lazy/lazy.nvim"` if missing, then imports:

```lua
spec = {
  { import = "plugins.ui" },
  { import = "plugins.editor" },
  { import = "plugins.files" },
  { import = "plugins.git" },
  { import = "plugins.lsp" },
  { import = "plugins.document" },
}
```

`plugins/navigation.lua` and `plugins/dap.lua` are not imported. Their plugins
are also absent from `lazy-lock.json`.

## Core options

`core/options.lua`:

- Leader: `Space`; local leader: `\`.
- Line numbers, relative numbers, mouse, autoread, termguicolors, sign column,
  cursorline, no wrap.
- Scrolloff 8, sidescrolloff 8.
- Tabstop 2, shiftwidth 2, expandtab, autoindent, smartindent.
- Ignorecase, smartcase.
- `updatetime=300`, `timeoutlen=400`.
- Split below/right.
- Persistent undo.
- Clipboard `unnamedplus`.
- Completion `menu, menuone, noselect`.

## Core keymaps

| Key | Action |
| --- | --- |
| `<leader>a` | Select all |
| `<leader>w` / `<leader>q` | Save / quit |
| `Ctrl+h/j/k/l` | Window navigation |
| `Ctrl+Up/Down/Left/Right` | Resize windows |
| `<Esc><Esc>` | Clear search highlight |
| `]b` / `[b` | Next/previous buffer |
| `<leader>bd` | Delete buffer |
| `]d` / `[d` | Next/previous diagnostic |
| `<leader>e` | Diagnostic float |
| `<` / `>` (visual) | Indent and keep selection |
| `J` / `K` (visual) | Move selection down/up |
| `Ctrl+p` | Telescope find files |
| `<leader>fg/fw/fb/fh/fr` | Telescope live grep/grep string/buffers/help/recent |
| `<leader>sw/sd/sr/sD/sc/sk` | Telescope symbols/references/diagnostics/commands/keymaps |
| `<leader>gs/gc` | Telescope git status/commits |
| `Ctrl+n` | Neo-tree toggle |
| `<leader>xx/xb/xq` | Trouble diagnostics/buffer diagnostics/quickfix |
| `<leader>ha/hm` | Harpoon add/menu (plugin not installed) |
| `Ctrl+1..4` | Harpoon select (plugin not installed) |
| `<leader>o` | Aerial toggle (plugin not installed) |
| `<leader>qs/ql` | Persistence restore/last session |

## Autocommands

`core/autocmds.lua`:

- `TextYankPost`: highlight yanked text for 120 ms.
- Diagnostics: virtual text off; custom signs; rounded float; no insert
  updates; severity sorting.
- `CursorHold`: show diagnostic float without focus.
- `VimResized`: equalize windows.
- `BufReadPost`: restore last cursor position if valid and visible.
- `FileType markdown,text`: call `core.document.setup(buf)`.
- `BufNewFile *.java`: generate a package/class template using the project root
  (`.git`, `pom.xml`, `build.gradle`, `settings.gradle`, `.project`) and source
  prefixes (`src/main/java/`, `src/test/java/`, `src/`, `lib/`).
- No trailing-whitespace `BufWritePre` hook.

## LSP

`plugins/lsp.lua`:

- `mason.nvim` with rounded UI and status icons.
- `mason-lspconfig.nvim` with `automatic_enable = false`.
- `nvim-lspconfig`:
  - Loads `plugin/lspconfig.lua` early.
  - Uses `blink.cmp` capabilities.
  - Adds workspace symbol, semantic token, and inlay hint capabilities.
  - `fidget` progress and `trouble` diagnostics.
  - `LspAttach` calls `core.lsp.on_attach`.
- Servers enabled manually:
  `lua_ls`, `html`, `cssls`, `jsonls`, `vtsls`, `clangd`, `pyright`, `gopls`,
  `jdtls`, `kotlin_language_server`, `texlab`, `rust_analyzer`, `zls`,
  `intelephense`, `omnisharp`.
- Server overrides:
  - `lua_ls`: `vim` global, runtime library, no telemetry.
  - `gopls`: unimported completion, placeholders, analyses, staticcheck,
    gofumpt.
  - `pyright`: workspace diagnostics, auto import, basic type checking.
  - `clangd`: background index, clang-tidy, IWYU, detailed completion.
  - `vtsls`: non-relative imports, inlay hints.
  - `rust_analyzer`: autoimport, all features, proc macros.
  - `zls`: autobuild.
  - `intelephense`: fully qualify globals.
  - `jdtls`: signature help, fernflower, static imports, import order,
    organize-import thresholds, code generation, custom root detection.
- `flutter-tools.nvim` for Dart/Flutter with the same capabilities/on_attach.

`core/lsp.on_attach`:

| Key | Action |
| --- | --- |
| `gd` | Definition |
| `gr` | References |
| `K` | Hover |
| `<leader>ca` | Code action |
| `<leader>rn` | Incremental rename or LSP rename |
| `gI` | Implementation |
| `gy` | Type definition |
| `<leader>li/lo/lh` | Incoming/outgoing calls, type hierarchy |
| `<leader>lf` | Format |
| `<leader>th` | Toggle inlay hints |
| `<M-CR>` / `<leader>ai` | AutoImport |
| `<leader>f` | Format, organize imports, auto-import |

TypeScript/`ts_ls` formatting is disabled in favor of Conform.

## AutoImport

`core/autoimport.lua`:

Default configuration:

```lua
organize_imports_on_save = false,
auto_import_on_save = false,
auto_import_on_diagnostics = false,
auto_import_while_typing = false,
max_diagnostics = 8,
ui = { prefer_telescope = true },
```

`init.lua` overrides `auto_import_on_save` and `organize_imports_on_save` to
`true`, but `M.setup()` does not register save hooks. Those two flags currently
have no effect. Formatting still runs through Conform.

`DiagnosticChanged` is registered only when `auto_import_on_diagnostics` or
`auto_import_while_typing` is true; both are false in `init.lua`.

Functions:

- `trigger_auto_import()`:
  - Requires a named buffer and an LSP code-action client.
  - Collects diagnostics at the cursor, then all diagnostics.
  - Requests `textDocument/codeAction`.
  - Filters import actions by server-specific title patterns and
    `source.addMissingImports`.
  - Applies one action or shows a Telescope/`vim.ui.select` picker.
- `auto_import_all_unresolved()`:
  - Scans up to 8 unresolved diagnostics and applies import actions.
- `run_organize_imports()`:
  - TS/JS → `core/imports/ts.lua`
  - Go → `core/imports/go.lua`
  - Java → `core/imports/java.lua`
  - Other → `source.organizeImports`
- `format_and_organize()`:
  - Organizes imports.
  - Auto-imports unresolved symbols.
  - Formats through Conform with LSP fallback.

Commands: `:AutoImport`, `:OrganizeImports`, `:FormatAndOrganize`.

## Completion

`plugins/editor.lua` configures `blink.cmp`:

- Loaded early (`lazy = false`).
- Version `v0.*`, pinned in `lazy-lock.json`.
- Keymaps:
  - `<CR>` accept/fallback.
  - `<Tab>`/`<S-Tab>` select/snippet.
  - `<C-b>`/`<C-f>` scroll documentation.
- Sources: LSP, path, snippets, buffer, neighbors.
- `neighbors` provider:
  - Reads sibling files with the same extension.
  - Parses with Treesitter `tags`, then `locals`, then `(identifier) @name`.
  - Adds symbols as completion items with “Auto-import from <file>”.
  - On execute, inserts the symbol and requests LSP code actions after 500 ms.
- LuaSnip + friendly-snippets.
- nvim-autopairs.

## Formatting

`conform.nvim` formatters:

| Filetype | Formatter |
| --- | --- |
| markdown/html/css/json/yaml/js/ts/jsx/tsx | `prettier` |
| lua | `stylua` |
| c/cpp | `clang-format` |
| python | `black` |
| go | `gofumpt` |
| java | `google-java-format` |
| kotlin | `ktlint` |
| dart | `dart_format` |
| tex | `latexindent` |
| rust | `rustfmt` |
| zig | `zigfmt` |
| sh/bash | `shfmt` |

`format_on_save = { timeout_ms = 2000, lsp_fallback = true }`.

External formatters must be installed separately.

## Treesitter and navigation

`nvim-treesitter` parsers:

```text
lua vim vimdoc query regex
markdown markdown_inline html css json yaml toml latex
c cpp java kotlin dart python go gomod gosum
javascript typescript tsx
bash dockerfile gitignore
```

`nvim-treesitter-textobjects` provides select/move/swap mappings:
`af/if/ac/ic/aP/iP`, `]]`, `[m`, `<leader>xn/xp`.

`plugins/navigation.lua` would add treesitter-context, Flash, Aerial, and
Harpoon, but it is not imported. Harpoon/Aerial keymaps in `core/keymaps.lua`
will error if used.

`nvim-ufo` provides folding: `zR`, `zM`, `zK`.

## Files and Git

Files:

- `neo-tree.nvim` `v3.x`: left sidebar width 35, preview, git status,
  diagnostics, follow current file, libuv watcher.
- `telescope.nvim` + `telescope-fzf-native`: prompt/selection, ascending sort,
  55% preview, 87% width/80% height, ignore patterns for `node_modules`,
  `.git/`, `build/`, `dist/`, `__pycache__`, `.class`.

Git:

- `gitsigns.nvim`: hunk navigation `]c/[c`; stage/reset/preview/blame/diff.
- `vim-fugitive`: `:Git`/`:G`.

## UI and theme

`core/autotheme.lua`:

- Reads `~/.cache/autotheme/theme.json`.
- Defines Neovim highlight groups from `bg`, `surface`, `border`, `fg`,
  `muted`, `accent`, `accentSoft`, `critical`, `warning`, `success`, and the
  ANSI palette.
- Reads `$XDG_RUNTIME_DIR/kitty-mode-$KITTY_PID`:
  - `transparent` → transparent `Normal` background.
  - `opaque` → solid `bg` background.
  - Missing mode file → transparent.
- Polls `theme.json` and the Kitty mode file every two seconds and reapplies
  highlights when either changes.
- Falls back to a neutral dark palette if `theme.json` is missing or invalid.

`plugins/ui.lua`:

- `nvim-web-devicons`
- `lualine.nvim`: `auto` theme (derived from current highlight groups), global
  status, mode/branch/diff/diagnostics/filename/encoding/fileformat/filetype/
  progress/location.
- `nvim-notify`: background uses `core.autotheme` surface color; replaces
  `vim.notify`.
- `noice.nvim`: bottom search, command palette, long-message split,
  inc-rename.
- `inc-rename.nvim`
- `indent-blankline.nvim`
- `dashboard-nvim`: hyper theme; shortcuts f/g/n.

## Markdown and text document mode

Activated by `FileType markdown,text`.

Buffer-local keymaps:

| Key | Action |
| --- | --- |
| `<C-b>` | Toggle bold `**` |
| `<C-i>` | Toggle italic `*` |
| `<C-Space>` | Toggle checkbox |
| `<leader>mt` | Formatting toolbar |
| `<leader>mi` | `:PasteImage` |
| `<leader>ml` | Insert link |
| `<leader>mp` | `:MarkdownPreviewToggle` |
| `<leader>me` | Export menu |
| `<leader>mf` | Focus mode |

Buffer settings: wrap, linebreak, spell.

Toolbar:

- Bold, italic, underline, strikethrough.
- Bullet list, numbered list, quote.
- Heading 1/2/3.
- Code block.
- Horizontal rule.
- Link.
- Table.
- Checkbox.

Focus mode:

- `scrolloff=999`, wrap, linebreak, spell.
- Enables `zen-mode.nvim` and `twilight.nvim` if available.
- Restores scrolloff/spell and disables Zen/Twilight on exit.
- Sends a notification.

Images:

- `img-clip.nvim`: clipboard images under `assets/`, names
  `image_%Y-%m-%d_%H-%M-%S.png`, prompts for filename, supports drag/drop,
  inserts `![[$FILE_NAME]]($FILE_PATH)` for Markdown.
- `image.nvim`: Kitty graphics protocol inline images.
- `:ImageResize 50` or `:ImageResize 300x200`:
  - Finds `![...](path)` on the current line.
  - Resolves relative to the buffer directory.
  - Backs up to `.bak`.
  - Runs `mogrify -resize 50%` or `300x200!`.
  - Restores on failure.

Preview/export:

- `markdown-preview.nvim`: build with `cd app && ./install.sh`; commands
  `MarkdownPreviewToggle`, `MarkdownPreview`, `MarkdownPreviewStop`.
- Document export prefers the installed `docs` toolkit:
  `md2pdf`, `md2html`, or `md2docx` with `-o <outfile>`.
  - `:ExportPDF`, `:ExportHTML`, `:ExportDOCX`, `:ExportMenu`.
  - Without the toolkit, it falls back to
    `pandoc <infile> -o <outfile>.<pdf|html|docx>`.
  - The toolkit's PDF path uses WeasyPrint, so it does not require LaTeX.

Other document plugins:

- `zen-mode.nvim`: backdrop 0.95, width 120, no numbers/signs/cursorline/
  foldcolumn.
- `twilight.nvim`
- `neoscroll.nvim`: smooth `<C-u>/<C-d>/<C-b>/<C-f>/<C-y>/<C-e>/zt/zz/zb`.
- `render-markdown.nvim`
- `vimtex`: Zathura viewer, `latexmk` compiler.
- `persistence.nvim`
- `todo-comments.nvim`

## Dependencies

Core:

- Neovim 0.11+ (0.12.6 on reference deployment)
- Git
- `lazy.nvim` (auto-bootstrapped)
- `ripgrep`, `fd`, `fzf` for Telescope
- Nerd Font for icons
- `node`/`npm` for some LSPs, Prettier, markdown-preview
- `python3` + `pyright`/`black`
- `go`/`gopls`/`gofumpt`
- `rust`/`rust-analyzer`/`rustfmt`
- `clang`/`clangd`/`clang-format`
- `jdk`/`jdtls`/`google-java-format`
- `kotlin`/`ktlint`/`kotlin_language_server`
- `zls`/`zig`
- `texlab`/`latexmk`/`latexindent`/TeX distribution
- `imagemagick` (`mogrify`)
- `docs` toolkit (preferred) or `pandoc`; LaTeX only for the pandoc fallback PDF path
- Kitty graphics protocol for `image.nvim`

## Reproduction

```bash
sudo pacman -S --needed neovim git ripgrep fd fzf nodejs npm python \
  go rust clang jdk-openjdk imagemagick pandoc

cd ~/dotfiles
stow --target="$HOME" --no-folding nvim

nvim --headless "+Lazy! sync" +qa
```

Inside Neovim:

```vim
:Lazy
:Mason
:TSUpdate
:checkhealth
```

`lazy-lock.json` pins plugin versions. The first launch clones `lazy.nvim` into
`~/.local/share/nvim/lazy/lazy.nvim`.

## Verification

- Lua files are syntactically valid.
- `lazy-lock.json` pins plugin commits.
- `nvim --headless "+Lazy! sync" +qa` installs pinned plugins.
- `vim.g.colors_name` is `autotheme`, and `Normal` matches
  `~/.cache/autotheme/theme.json`.
- The colorscheme watcher reapplies highlights after `theme.json` or the Kitty
  mode file changes.
- `:checkhealth` reports missing external tools.
- `:Mason` shows LSP server state.
- `:LspInfo` / `:checkhealth lsp` shows attached clients.
- Markdown: wrap/spell enabled; `<leader>mt`, `<leader>mf` work.
- `:PasteImage` requires clipboard image support.
- `:MarkdownPreviewToggle` requires the markdown-preview build.
- `:ExportPDF` uses the `docs` toolkit (WeasyPrint) when installed; the
  pandoc fallback still needs LaTeX. HTML/DOCX use `md2html`/`md2docx` or
  Pandoc.

## Known limitations

- `plugins/navigation.lua` is not imported; Harpoon, Aerial, Flash, and
  treesitter-context are absent.
- `plugins/dap.lua` is not imported; DAP and its dependencies are absent from
  the lock file.
- AutoImport save flags have no effect without save hooks.
- Conform formatters must exist on `PATH`.
- `image.nvim` requires Kitty graphics.
- Markdown-preview needs its app build.
- Vimtex PDF output needs `latexmk` and a TeX distribution.
- `lazy-lock.json` pins versions; updates require `:Lazy update` and a lockfile
  commit.
- Neovim colors depend on `~/.cache/autotheme/theme.json`; if the file is
  missing or malformed, the neutral fallback is used.
- The watcher applies changes on a two-second poll. A Neovim process started
  before the integration was installed must be restarted once.
- Adding `navigation`/`dap` requires importing them in `plugins/init.lua`.

## Related documentation

- [terminal-shell-and-prompt.md](terminal-shell-and-prompt.md)
- [document-and-file-utilities.md](document-and-file-utilities.md)
- [system-overview.md](system-overview.md)
