# OpenCode config (dotfiles package)

Stow package layout: this directory is `dotfiles/opencode/.config/opencode/`, so
`stow opencode` (run from `~/dotfiles`) links it to `~/.config/opencode/`.

## What lives here

| File | Purpose |
| --- | --- |
| `opencode.jsonc` | Providers, **MCP servers**, **plugins (`oh-my-opencode-slim`)**, **TODO list (`experimental.todo: true`)**, formatter, compaction, websearch, LSP, `/tmp/opencode/*` permissions |
| `oh-my-opencode-slim.json` | Omo-Slim presets (`preset: "opencode-go"`) |
| `AGENTS.md` | Global agent instructions |
| `skills/` | Global skills (`deep-researcher`, `github-repo-explorer`) |

The TODO list toggle is `experimental.todo: true` in `opencode.jsonc` — same file
as MCP and Omo-Slim, so a fresh install gets all three together.

## Required environment variables (secrets are NOT committed)

`opencode.jsonc` contains no tokens. OpenCode substitutes `{env:NAME}` at load time.
Export these before starting OpenCode:

| Variable | Used by |
| --- | --- |
| `AIHUBMIX_API_KEY` | `providers.shooterdelta1` — `Authorization: Bearer {env:AIHUBMIX_API_KEY}` |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | `mcp.servers.github` — `Authorization: Bearer {env:GITHUB_PERSONAL_ACCESS_TOKEN}` |

Set them in your shell (fish example, matches existing secret handling):

```fish
set -Ux AIHUBMIX_API_KEY 'sk-...'
set -Ux GITHUB_PERSONAL_ACCESS_TOKEN 'github_pat_...'
```

or add them to the gitignored `fish/.config/fish/conf.d/secrets.fish`.
If a variable is unset the header becomes `Bearer ` and the provider/MCP auth fails,
so set both on a new machine. To recover the real values, copy them from the live
config on the old machine (`~/.config/opencode/opencode.jsonc`).

## Notes / known issues

- `~/.config/opencode` is currently a real directory, not a stow symlink, so plain
  `stow opencode` will report conflicts and refuse to overwrite existing files.
  On a fresh machine it stows cleanly. To adopt existing files: `stow --adopt opencode`
  (review with `git diff` afterwards), or move the old files aside first.
- Prefer `stow --no-folding opencode` on machines that will run `npm install` inside
  `~/.config/opencode`: with directory folding, `node_modules/`, `package.json` and
  `*-lock.json` are written *into this repo*. `--no-folding` keeps them local.
- `opencode/.config/opencode/.config/opencode/opencode.json` is a stale nested
  artifact (old schema: singular `permission`, inline `mcp.github`). It is not
  referenced by `~/.config/opencode` and should be removed once confirmed — kept
  here deliberately, not deleted automatically.
