# Turn on useful features
set -g fish_color_command green
set -g fish_color_error red
set -g fish_color_match cyan
set -g fish_color_autosuggestion brgrey
set -g fish_greeting ""

# Set editor
set -gx EDITOR nvim
set -gx VISUAL nvim

# PATH (deduplicated + persistent)
if test -d ~/.local/bin
    if not contains -- ~/.local/bin $fish_user_paths
        set -U fish_user_paths ~/.local/bin $fish_user_paths
    end
end

# Pager
set -gx PAGER less
set -gx LESS "-R"
set -gx MANPAGER "less -R"
set -gx LESSHISTFILE "-"

# Starship prompt (optional, recommended)
if type -q starship
    starship init fish | source
end

# Dependency check
for bin in zathura imv mpv libreoffice xdg-open
    if not type -q $bin
        echo "warning: missing dependency -> $bin"
    end
end

function cd
    # ASSUMPTION: gocryptfs(1) and fusermount(1) are on PATH.
    # ASSUMPTION: realpath(1) supports -m (GNU coreutils ≥8.15).
    # ASSUMPTION: $HOME is always set and non-empty (Fish guarantees this on login shells).
    # ASSUMPTION: The encrypted vault path is $HOME/.important.encrypted and the
    #             mount-point is $HOME/.important. Both are configurable via the two
    #             variables below; change here if your layout differs.

    set -l important      "$HOME/.important"
    set -l vault          "$HOME/.important.encrypted"

    # ── 1. Capture current working directory ────────────────────────────────
    # PWD may be stale if the directory was deleted under us; fall back to
    # builtin pwd which queries the kernel, then fall back to $PWD.
    set -l oldpwd (builtin pwd 2>/dev/null; or echo "$PWD")

    # ── 2. Resolve the target path ──────────────────────────────────────────
    # Determine the logical destination BEFORE touching the filesystem so that
    # the mount/unmount decision is based on the resolved path, not the raw arg.
    set -l target
    if test (count $argv) -eq 0
        set target "$HOME"
    else if test "$argv[1]" = "-"
        # $OLDPWD may be unset on the very first invocation; default to $HOME.
        if set -q OLDPWD
            set target "$OLDPWD"
        else
            set target "$HOME"
        end
    else
        set target "$argv[1]"
    end

    # realpath -m resolves without requiring the path to exist yet.
    # If realpath is unavailable, fall through with the raw target; the
    # subsequent builtin cd will fail naturally with a useful error message.
    set -l resolved_target (realpath -m -- "$target" 2>/dev/null)
    if test -z "$resolved_target"
        set resolved_target "$target"
    end

    # Resolve important and oldpwd as well so all comparisons use canonical paths.
    set -l resolved_important (realpath -m -- "$important" 2>/dev/null)
    if test -z "$resolved_important"
        set resolved_important "$important"
    end

    set -l resolved_oldpwd (realpath -m -- "$oldpwd" 2>/dev/null)
    if test -z "$resolved_oldpwd"
        set resolved_oldpwd "$oldpwd"
    end

    # ── 3. Unlock vault if the target is inside (or equal to) .important ────
    # The trailing "/" in the prefix check prevents false matches such as
    # ~/.important-extra matching ~/.important.
    set -l entering_important 0
    if test "$resolved_target" = "$resolved_important"; \
       or string match -q -- "$resolved_important/*" "$resolved_target"
        set entering_important 1
    end

    if test $entering_important -eq 1
        if not mountpoint -q -- "$important" 2>/dev/null
            # Vault is not mounted; attempt to unlock.
            if not test -d "$important"
                echo "cd: mount-point '$important' does not exist." >&2
                return 1
            end
            if not test -d "$vault"
                echo "cd: vault '$vault' does not exist." >&2
                return 1
            end
            echo "Unlocking .important..."
            if not gocryptfs -- "$vault" "$important"
                echo "cd: gocryptfs failed; aborting navigation." >&2
                return 1
            end
        end
        # If already mounted, proceed silently.
    end

    # ── 4. Perform the actual directory change ──────────────────────────────
    # Pass all original arguments so options like -P (physical) are preserved.
    if not builtin cd $argv
        # cd failed (permission denied, non-existent path, etc.).
        # Do NOT lock the vault here: the user is still in $oldpwd, which may
        # itself be inside .important.
        return 1
    end

    set -l newpwd (builtin pwd 2>/dev/null; or echo "$PWD")
    set -l resolved_newpwd (realpath -m -- "$newpwd" 2>/dev/null)
    if test -z "$resolved_newpwd"
        set resolved_newpwd "$newpwd"
    end

    # ── 5. Lock vault only when fully leaving .important ────────────────────
    set -l was_inside 0
    if test "$resolved_oldpwd" = "$resolved_important"; \
       or string match -q -- "$resolved_important/*" "$resolved_oldpwd"
        set was_inside 1
    end

    set -l is_inside 0
    if test "$resolved_newpwd" = "$resolved_important"; \
       or string match -q -- "$resolved_important/*" "$resolved_newpwd"
        set is_inside 1
    end

    if test $was_inside -eq 1; and test $is_inside -eq 0
        if mountpoint -q -- "$important" 2>/dev/null
            echo "Locking .important..."
            if not fusermount3 -u -- "$important" 2>/dev/null
                # FUSE unmount failed; most likely cause is a process still
                # holding an open file descriptor inside the mount.
                echo "cd: .important is still busy; vault not locked. Close any open files inside it." >&2
                # Navigation already succeeded; return 0 so the caller is not
                # misled into thinking cd failed.
            end
        end
    end

    return 0
end

function lock_important_on_exit --on-event fish_exit
    set -l important "$HOME/.important"

    if mountpoint -q -- "$important" 2>/dev/null
        echo "Locking .important on shell exit..."

        fusermount3 -u -- "$important" 2>/dev/null

        if test $status -ne 0
            echo ".important is busy; could not auto-lock on exit." >&2
        end
    end
end

# opencode
fish_add_path $HOME/.opencode/bin
