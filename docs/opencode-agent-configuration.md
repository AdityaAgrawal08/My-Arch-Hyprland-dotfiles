# OpenCode Agent Configuration

**Status:** Configuration inspected. Provider/MCP startup was not exercised.

## Purpose

Configures the OpenCode CLI/agent environment: providers, MCP servers, the
`oh-my-opencode-slim` plugin preset, global agent instructions, skills, secrets,
formatter, LSP, compaction, and workspace permissions.

## Scope

In scope:

- `opencode.jsonc`
- `oh-my-opencode-slim.json`
- `AGENTS.md`
- `skills/deep-researcher`
- `skills/github-repo-explorer`
- Stale nested configuration

Out of scope:

- OpenCode upstream behavior.
- External model/provider availability.
- MCP server implementations.

## Files and paths

| Repository path | Deployed path | Role |
| --- | --- | --- |
| `opencode/.config/opencode/opencode.jsonc` | `~/.config/opencode/opencode.jsonc` | Main configuration |
| `opencode/.config/opencode/oh-my-opencode-slim.json` | `~/.config/opencode/oh-my-opencode-slim.json` | Plugin presets |
| `opencode/.config/opencode/AGENTS.md` | `~/.config/opencode/AGENTS.md` | Global agent instructions |
| `opencode/.config/opencode/README.md` | `~/.config/opencode/README.md` | Package notes |
| `opencode/.config/opencode/skills/deep-researcher/SKILL.md` | `~/.config/opencode/skills/deep-researcher/SKILL.md` | Research skill |
| `opencode/.config/opencode/skills/github-repo-explorer/SKILL.md` | `~/.config/opencode/skills/github-repo-explorer/SKILL.md` | Repository exploration skill |
| `opencode/.config/opencode/.config/opencode/opencode.json` | not loaded | Stale nested configuration |

## Provider configuration

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "providers": {
    "shooterdelta1": {
      "name": "AiHubMix",
      "package": "aisdk:@ai-sdk/openai-compatible",
      "settings": { "baseURL": "https://aihubmix.com/v1" },
      "headers": {
        "Authorization": "Bearer {env:AIHUBMIX_API_KEY}"
      },
      "models": {
        "coding-glm-5.3-flash-free": { "name": "GLM Flash" },
        "coding-glm-5.3-free": { "name": "GLM" }
      }
    }
  }
}
```

`{env:NAME}` is resolved at load time. If `AIHUBMIX_API_KEY` is unset, the
header becomes `Bearer ` and requests fail.

## MCP servers

```jsonc
"mcp": {
  "servers": {
    "playwright": {
      "type": "local",
      "command": ["npx", "-y", "@playwright/mcp@latest", "--headless", "--isolated"]
    },
    "github": {
      "type": "remote",
      "url": "https://api.githubcopilot.com/mcp/",
      "oauth": false,
      "headers": {
        "Authorization": "Bearer {env:GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    },
    "searxng": {
      "type": "local",
      "command": ["npx", "-y", "@kevinwatt/mcp-server-searxng"]
    },
    "serena": {
      "type": "local",
      "command": ["uvx", "--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--context", "ide-assistant"],
      "timeout": 30000
    },
    "memory": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-memory"]
    },
    "deepwiki": {
      "type": "remote",
      "url": "https://mcp.deepwiki.com/mcp"
    }
  }
}
```

Requirements:

- `npx`/Node.js for Playwright, SearXNG, and Memory.
- `uvx`/uv for Serena; first use downloads from Git and has a 30 s timeout.
- Network access for remote MCPs and package downloads.
- `GITHUB_PERSONAL_ACCESS_TOKEN` for GitHub MCP.
- GitHub MCP uses a bearer token with `oauth: false`.

## Permissions

```jsonc
"permissions": [
  { "action": "external_directory", "resource": "/tmp/opencode/*", "effect": "allow" },
  { "action": "read", "resource": "/tmp/opencode/*", "effect": "allow" },
  { "action": "edit", "resource": "/tmp/opencode/*", "effect": "allow" }
]
```

Only `/tmp/opencode/*` is explicitly allowed for these actions. Other
permissions follow OpenCode defaults.

## Plugin and features

```jsonc
"plugins": ["oh-my-opencode-slim"],
"formatter": true,
"compaction": {
  "auto": true,
  "keep": { "tokens": 15000 },
  "buffer": 20000
},
"websearch": { "provider": "random" },
"lsp": true,
"experimental": {
  "todo": true,
  "background_compaction": true
}
```

| Setting | Effect |
| --- | --- |
| `plugins` | Loads `oh-my-opencode-slim` |
| `formatter` | Enables built-in formatting |
| `compaction.auto` | Automatic context compaction |
| `compaction.keep.tokens` | Keep 15,000 tokens |
| `compaction.buffer` | 20,000-token buffer |
| `websearch.provider` | Random configured provider |
| `lsp` | Enables built-in LSP integration |
| `experimental.todo` | Enables TODO list |
| `experimental.background_compaction` | Background compaction |

## Omo-Slim presets

Active preset:

```json
"preset": "opencode-go"
```

### `opencode-go`

| Agent | Model | Variant | Skills | MCPs |
| --- | --- | --- | --- | --- |
| orchestrator | `opencode-go/muse-spark-1.3-contributor` | xhigh | `*` | `*` except `context7` |
| oracle | `opencode-go/mimo-v2.6-pro` | — | `simplify` | none |
| explorer | `opencode-go/deepseek-v4.1-flash` | max | none | `serena`, `github` |
| librarian | `opencode-go/muse-spark-1.3-contributor` | high | none | `context7`, `gh_grep`, `searxng`, `deepwiki` |
| designer | `opencode-go/mimo-v2.6-flash` | high | none | `playwright` |
| fixer | `opencode-go/deepseek-v4.1-flash` | max | none | `playwright`, `github`, `serena` |
| observer | `opencode-go/mimo-v2.5` | — | none | none |

### `openai`

| Agent | Model | Variant | Skills | MCPs |
| --- | --- | --- | --- | --- |
| orchestrator | `openai/gpt-6-sol` | high | `*` | `*` except `context7` |
| oracle | `openai/gpt-6-astra` | high | `simplify` | none |
| librarian | `openai/gpt-6-luna` | low | none | `context7`, `gh_grep` |
| explorer | `openai/gpt-6-luna` | low | none | none |
| designer | `openai/gpt-6-luna` | medium | none | none |
| fixer | `openai/gpt-6-luna` | high | none | none |

## Global instructions

`AGENTS.md` is the global instruction file. Its primary directives:

- Detailed analysis is the default unless the user explicitly requests a
  concise answer.
- Findings include file paths, line numbers, code snippets, exact problem, root
  cause, and concrete fix.
- Findings are categorized by severity and grouped logically.
- Default report structure: overview, bugs, warnings/anti-patterns,
  architecture, performance, missing configuration, edge cases, cleanup.
- Tone is direct and factual.
- Review methodology includes premise validation, full-file reading, call-chain
  tracing, external documentation research, reproducibility checks, constraint
  awareness, root-cause completeness, assumption analysis, invariant checking,
  temporal and coupling analysis, lifecycle and trust-boundary review,
  specification compliance, edge cases, failure simulation, dependency and API
  analysis, version compatibility, security, regression, consistency,
  scalability, observability, maintainability, and production readiness.
- Evidence hierarchy: runtime behavior, source, tests, configuration, official
  documentation, framework implementation, community guidance.
- Confidence must be calibrated and uncertainty stated.

The full `AGENTS.md` is authoritative; this is a structural summary.

## Skills

### `deep-researcher`

Triggers on deep research, investigation, comprehensive analysis, intelligence
briefing, exhaustive search, and similar requests.

Workflow:

- Broad recursive search across search engines, official records, academic
  sources, technical sources, investigative journalism, industry sources,
  community discussion, and multimedia.
- Trace claims to primary sources.
- Cross-verify and report conflicts.
- Produce a structured report: executive summary, background, chronology,
  technical analysis, evidence, primary sources, cross-verification, conflicting
  evidence, expert opinions, industry perspective, security/legal/economic
  implications, open questions, uncertainties, confidence assessment, and
  references.
- Use confidence tags: `[VERIFIED]`, `[STRONG]`, `[MODERATE]`, `[WEAK]`,
  `[INFERENCE]`, `[OPINION]`.

### `github-repo-explorer`

Triggers on GitHub repository URLs and exploration requests.

Workflow:

1. Parse `github.com/{owner}/{repo}[/tree/{branch}][/path]`.
2. Try GitHub MCP.
3. Fall back to GitHub REST API.
4. Fall back to HTML/raw URLs.
5. Detect language/framework and navigate likely directories.
6. Find files by name, content, and imports; read key files fully.
7. Report architecture, entry point, key modules, relevant files, and
   `{path}:{line}` references.

## Secrets

| Variable | Consumer |
| --- | --- |
| `AIHUBMIX_API_KEY` | `providers.shooterdelta1` bearer auth |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | `mcp.servers.github` bearer auth |

Recommended:

Set `AIHUBMIX_API_KEY` and `GITHUB_PERSONAL_ACCESS_TOKEN` in the environment, or
add them to the ignored `fish/.config/fish/conf.d/secrets.fish`.

The stale nested config also references `GITHUB_READ_ONLY=1`; the active config
does not.

## Stale nested configuration

`opencode/.config/opencode/.config/opencode/opencode.json` is an old-schema
file:

- `default_agent: "plan"`
- Singular `permission` object
- Inline `mcp.github` local server using
  `@modelcontextprotocol/server-github`
- `GITHUB_PERSONAL_ACCESS_TOKEN` and `GITHUB_READ_ONLY=1`

It is one nested `.config/opencode` level too deep and is not loaded by the
active config. The package README identifies it as stale.

## Installation and Stow

`install.sh` includes `opencode` in its Stow package list.

```bash
sudo pacman -S --needed opencode nodejs npm uv
cd ~/dotfiles
stow --target="$HOME" --no-folding opencode
```

On the reference deployment, `~/.config/opencode` is a real directory, not a
Stow symlink. Plain `stow opencode` reports conflicts. Options:

- `stow --adopt opencode`, then review with `git diff`.
- Move existing files aside first.
- Use `--no-folding` if `npm install` runs inside `~/.config/opencode`.

## Reproduction

1. Install OpenCode, Node.js/npm, and uv.
2. Set `AIHUBMIX_API_KEY` and `GITHUB_PERSONAL_ACCESS_TOKEN`.
3. Stow or copy the package.
4. Start OpenCode.
5. Verify:
   - Provider `shooterdelta1` lists the GLM models.
   - MCP servers start.
   - `opencode-go` preset is active.
   - `/tmp/opencode/*` modifications are allowed.
   - Skills are discoverable.

First launch may be slow because MCPs download packages and Serena fetches from
Git.

## Verification

- Configuration files are valid JSON/JSONC by inspection.
- `opencode` 2.1.3-1 is installed on the reference deployment.
- `~/.config/opencode` is a real directory; the repository package was not
  adopted by Stow.
- Provider/MCP startup was not exercised.

## Known limitations

- Secrets are required for provider and GitHub MCP auth.
- Model IDs and provider availability are external.
- MCP dependencies are downloaded at runtime.
- GitHub MCP uses a bearer token, not OAuth.
- `~/.config/opencode` is a real directory on the reference deployment.
- The nested `opencode.json` is stale.
- `AGENTS.md` defaults to long, detailed answers.
- The plugin preset references skills and MCPs by name.
- Formatter/LSP features may require external tools.
- `/tmp/opencode/*` is deliberately writable for agent workflows.

## Related documentation

- [installation-and-package-management.md](installation-and-package-management.md)
- [system-overview.md](system-overview.md)
- [reproduction-and-verification.md](reproduction-and-verification.md)
