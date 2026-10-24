# Trash Management System

**Status:** Documentation only on the reference deployment. The repository
implementation exists, but the runtime database/object store is absent and the
user timers are disabled.

## Purpose

Implements a content-addressable storage (CAS) trash system. Deletions are
recorded in SQLite and stored as SHA-256-addressed blobs, enabling
deduplication, restore, permanent delete, pinning, age cleanup, orphan scanning,
and health checks.

## Scope

In scope:

- `safe-rm` interceptor.
- `trash` CLI.
- `trash-ui` fzf interface.
- SQLite schema and object layout.
- Directory manifests.
- Systemd user timers and installer integration.

Out of scope:

- Desktop trash specification compatibility (`~/.local/share/Trash`).
- Secure erasure.
- Cross-device or remote storage.
- File metadata preservation beyond basic copy behavior.

## Architecture

```text
safe-rm / trash
       │
       ├── flock ($BASE/.lock)
       ├── SQLite catalog ($TRASH_DB)
       │     ├── meta
       │     └── trash
       └── CAS object store ($TRASH_OBJECTS)
             ├── <2>/<2>/<sha256>
             └── manifests/<uuid>.json
```

The CLI and interceptor share the same lock and database. Objects are
deduplicated by SHA-256: if the object already exists, the new logical deletion
references the existing blob.

## Files and paths

| Path | Role |
| --- | --- |
| `trash/bin/safe-rm` | Interceptor |
| `trash/bin/trash` | CLI |
| `trash/bin/trash-ui` | fzf UI |
| `trash/scripts/init-db.sh` | Schema creation |
| `trash/scripts/migrate.sh` | Schema version check |
| `trash/config/env.example` | Path variables |
| `trash/.config/trash-system/env` | Deployed env file |
| `trash/.config/systemd/user/trash-*.service` | User services |
| `trash/.config/systemd/user/trash-*.timer` | User timers |
| `trash/systemd/trash-cleanup.*` | Legacy units |
| `trash/install.sh` | Standalone installer |
| `trash/uninstall.sh` | Standalone uninstaller |
| `trash/.stow-local-ignore` | Stow-local ignore |
| `trash/.gitignore` | Runtime ignore rules |

`install.sh` stows the `trash` package but ignores `bin`, `scripts`, `systemd`,
`config`, `install.sh`, `uninstall.sh`, `.gitignore`, `.stow-local-ignore`, and
`graphical-session.target.wants`. It creates its own symlinks and wrappers.

## Storage layout

Default paths:

```text
~/.local/share/trash-system/
├── db/
│   ├── trash.db
│   └── trash.db.lock
├── objects/
│   ├── <2 hex>/<2 hex>/<sha256>
│   └── manifests/<uuid>.json
└── .lock
```

Environment:

```bash
TRASH_BASE="$HOME/.local/share/trash-system"
TRASH_DB="$TRASH_BASE/db/trash.db"
TRASH_OBJECTS="$TRASH_BASE/objects"
```

`trash/config/env.example` and `trash/.config/trash-system/env` contain the same
values. `fish/.config/fish/conf.d/trash.fish` exports them to Fish.

## SQLite schema

`init-db.sh` enables:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
```

Tables:

```sql
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE trash (
    id TEXT PRIMARY KEY,
    original_path TEXT,
    filename TEXT,
    extension TEXT,
    deletion_time INTEGER,
    mime_type TEXT,
    category TEXT,
    origin_root TEXT,
    project_root TEXT,
    storage_path TEXT,
    size INTEGER,
    hash TEXT,
    is_restored INTEGER DEFAULT 0,
    active_days INTEGER DEFAULT 0,
    pinned INTEGER DEFAULT 0
);

CREATE INDEX idx_hash_active ON trash(hash) WHERE is_restored = 0;
```

`schema_version = 1` is inserted into `meta`. `init-db.sh` also touches
`trash.db.lock`.

`migrate.sh` supports only schema version 1; it exits 0 if the database does not
exist.

## `safe-rm`

### Invocation

`safe-rm` is not wired into `rm` automatically. There is no alias or Fish
function in the repository. To use it as the default delete command:

```fish
alias rm='~/.local/bin/safe-rm'
```

or invoke it explicitly.

### Dependencies

`sqlite3`, `file`, `flock`, `sha256sum`, `realpath`, `stat`, `du`, `cp`, `mv`,
`sync`, `mktemp`, `date`, `cut`, `awk`, `sed`.

### Locking

```bash
exec 200>"$LOCK"
flock -n 200 || { echo "ERROR: another operation is in progress"; exit 1; }
```

The lock is non-blocking; concurrent deletes fail immediately.

### Safety guards

For each argument:

- Skip missing paths.
- Resolve with `realpath`.
- Record base name, timestamp, first path component, and project root if the
  target’s parent contains `.git`.
- Skip exact paths `/`, `/home`, `/usr`, `/etc`.
- Skip anything under `$BASE`.

The guard list does not cover every system path.

### File ingestion

1. Detect MIME with `file --mime-type -b`; fallback
   `application/octet-stream`.
2. Categorize:
   - `image/*` → image
   - `text/*` → document
   - `video/*` → video
   - `application/zip` / `application/x-tar` → archive
   - other → other
3. Read size from `stat -c%s`; fallback `du -sb`.
4. Compute SHA-256.
5. Copy to a temporary file.
6. CAS path: `$OBJ/${hash:0:2}/${hash:2:2}/$hash`.
7. `mv -n` for deduplication. If the object exists, delete the temporary copy.
8. Insert a row in a SQLite transaction.
9. On database failure, attempt to copy the object back to the original path.
10. On success, remove the original and run `sync`.

Rollback is best-effort. It does not restore original metadata and does not
remove a partially committed row.

### Directory ingestion

1. Copy the directory with `cp -a` to a temporary tree.
2. Walk regular files; compute SHA-256; ingest each into CAS.
3. Build manifest lines: `<relative-path>|<hash>`.
4. Write JSON:

```json
{
  "type": "directory",
  "version": 1,
  "original_path": "/absolute/path",
  "files": [
    {"path": "rel/path", "hash": "..."}
  ]
}
```

5. Write `objects/manifests/<uuid>.json`.
6. Insert a row with `hash = 'DIR'` and `storage_path = <manifest>`.
7. Delete the original directory only after the database insert succeeds.

Directory manifest limitations:

- `original_path` uses SQL escaping, not JSON escaping.
- File paths are written with `awk` without JSON escaping.
- Paths containing `"` or `\` can produce invalid JSON.
- Only regular files are recorded. Empty directories, symlinks, sockets,
  devices, and special files are not represented.
- Restore recreates directories and copies files but does not restore
  permissions, ownership, timestamps, or symlinks.

## `trash` CLI

### Startup checks

- Source env file.
- Create base, object, and database parent directories.
- Run `PRAGMA integrity_check`.
- On corruption, move the database to `trash.db.corrupt.<epoch>`, run
  `~/.local/share/.../init-db.sh`, and exit 1.
- Acquire `$BASE/.lock` with `flock -w 2`.

### Commands

| Command | Behavior |
| --- | --- |
| `trash list` | Active items: number, 8-char ID, filename, date, time, category |
| `trash search <term> [-desc]` | Filter by filename; `-desc` reverses order |
| `trash delete <id>` | Prefix lookup, pinned check, prompt, delete row, remove unreferenced object |
| `trash delete <start>-<end>` | Range by row number; prompt; skip pinned |
| `trash restore <id>` | Prefix lookup; verify hash; restore file or directory manifest; mark restored |
| `trash undo` | Restore the most recent active item |
| `trash stats` | Count and total MiB |
| `trash group` | Counts by extension |
| `trash pin <id>` | Mark pinned |
| `trash unpin <id>` | Clear pinned |
| `trash cleanup [days]` | Delete non-pinned items older than `days` (default 100) |
| `trash health` | Integrity check and object-store accessibility |
| `trash clear` | Prompt; delete all rows and objects |
| `trash scan` | Remove objects with no active row |

Restore behavior:

- File: verify SHA-256, fail if target exists, copy from CAS, mark restored.
- Directory: read manifest with `jq`, recreate the original path, copy listed
  files, mark restored; remove partial restore on failure.
- Missing object message suggests `trash repair`, but no `repair` command exists.

### Safety behavior

- Most errors print to stderr and exit 1.
- `delete` and `clear` require `y` at the prompt.
- Pinned items are skipped by cleanup and deletion.
- `pin`/`unpin` do not validate the second argument. Bare `trash pin` fails under
  `set -u`; `trash pin ""` produces `LIKE '%'` and pins all rows.
- SQL is built by interpolation; `sql_escape` is not applied everywhere. Treat
  the CLI as a trusted local tool.
- `scan` deletes orphan objects without a prompt.

## `trash-ui`

`trash-ui` lists active rows and pipes them to fzf:

```bash
sqlite3 -separator '|' "$DB" \
  "SELECT id, filename, original_path, datetime(deletion_time,'unixepoch')
   FROM trash WHERE is_restored=0 ORDER BY deletion_time DESC;" |
fzf --ansi --multi --delimiter='|' --with-nth=2,3,4 \
    --preview 'echo -e "\nFILE:\n{2}\n\nPATH:\n{3}\n\nDELETED:\n{4}"'
```

Actions:

- `o` — attempt to open a path under the CAS store.
- `r` — `trash restore <id>`.
- `d` — `trash delete <id>`.
- anything else — exit.

The `o` implementation uses
`~/.local/share/trash-system/objects/*/*/*/*${id}*`, which does not match the
CAS layout and uses the row ID instead of the content hash. The open action is
therefore not reliable.

## Systemd automation

Checked-in units:

| Unit | Schedule/ExecStart |
| --- | --- |
| `trash-age.service` | `/home/aditya/.local/bin/trash-age` |
| `trash-clean.service` | `/home/aditya/.local/bin/trash-clean` |
| `trash-notify.service` | `/home/aditya/.local/bin/trash-notify` |
| `trash-age.timer` | daily, persistent |
| `trash-clean.timer` | daily |
| `trash-notify.timer` | `OnBootSec=30` |

`install.sh` writes user-specific overrides:

```ini
[Service]
ExecStart=
ExecStart="<user>/.local/bin/trash-age"
```

for each service, then enables the timers when a user D-Bus session exists.

`trash/systemd/trash-cleanup.service` and `.timer` are legacy and not installed
by `install.sh`.

`trash/.config/systemd/user/graphical-session.target.wants/warp-taskbar.service`
is a tracked symlink to `/usr/lib/systemd/user/warp-taskbar.service`. It is
unrelated to trash and is ignored during Stow.

Generated wrappers:

| Wrapper | Behavior |
| --- | --- |
| `trash-age` | Update `active_days` from `deletion_time` |
| `trash-clean` | `trash cleanup ${TRASH_RETENTION_DAYS:-100}` |
| `trash-notify` | Send notification with active count |

## Installation

### Current installer

`install.sh`:

- Symlinks `safe-rm`, `trash`, `trash-ui` into `~/.local/bin`.
- Initializes the database if missing.
- Creates wrappers and systemd overrides.
- Enables timers when a user bus exists.

### Standalone installer

`trash/install.sh`:

- Copies `bin/*` into `~/.local/bin`.
- Makes them executable.
- Initializes the database if missing.
- Appends a PATH line to Fish config if `.local/bin` is missing.
- Does not install systemd units.

### Uninstaller

`trash/uninstall.sh`:

- Removes `safe-rm`, `trash`, `trash-ui`.
- Removes the trash data directory.
- Disables/removes the legacy `trash-cleanup.timer`.
- Does not remove the current `trash-age`/`trash-clean`/`trash-notify` timers,
  overrides, or wrappers.

## Reproduction

```bash
sudo pacman -S --needed sqlite3 file util-linux jq fzf libnotify

cd ~/dotfiles
stow --target="$HOME" --no-folding trash
./install.sh

# or standalone:
bash trash/install.sh

# manual initialization:
export TRASH_BASE="$HOME/.local/share/trash-system"
export TRASH_DB="$TRASH_BASE/db/trash.db"
export TRASH_OBJECTS="$TRASH_BASE/objects"
bash trash/scripts/init-db.sh
```

Enable timers after a graphical login:

```bash
systemctl --user daemon-reload
systemctl --user enable --now trash-age.timer trash-clean.timer trash-notify.timer
```

Functional test:

```bash
touch <test-file>
~/.local/bin/safe-rm <test-file>
~/.local/bin/trash list
~/.local/bin/trash restore <id>
~/.local/bin/trash health
```

## Verification

- `init-db.sh` creates the schema with WAL.
- File and directory ingestion paths are implemented.
- CLI commands are implemented.
- The reference deployment was not initialized, so runtime paths were not
  exercised.
- Checked-in units and installer overrides were inspected.

## Known limitations

- No automatic `rm` alias.
- Reference deployment has no database/object store and timers are disabled.
- `trash pin ""` and `trash unpin ""` pin/unpin all rows.
- `trash repair` is referenced but absent.
- Directory manifests are not JSON-safe for quotes/backslashes.
- Directory restore does not preserve metadata, symlinks, or empty directories.
- Symlinks deleted as files may be dereferenced.
- `safe-rm` guards only `/`, `/home`, `/usr`, `/etc`.
- Rollback does not restore metadata.
- SQL is interpolated, not fully parameterized.
- `trash-ui` open action does not match the CAS layout.
- Two installers behave differently.
- `uninstall.sh` is incomplete for current timers/services.
- `safe-rm` uses `$BASE/.lock`; `init-db.sh` touches `$DB.lock`; these differ.
- Database recovery replaces the database and exits instead of salvaging rows.

## Related documentation

- [installation-and-package-management.md](installation-and-package-management.md)
- [system-overview.md](system-overview.md)
- [reproduction-and-verification.md](reproduction-and-verification.md)
