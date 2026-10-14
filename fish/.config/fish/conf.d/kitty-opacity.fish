# Apply the remembered kitty background opacity to new terminal windows.
# New terminals start opaque; they fade to transparent if that is the
# saved preference. The preference is saved by the `terminal` function.
if status is-interactive; and set -q KITTY_WINDOW_ID; and type -q kitten
    set -l pref_file "$HOME/.local/state/kitty-opacity"
    if test -f $pref_file
        set -l pref (cat $pref_file 2>/dev/null)
        if test -n "$pref"; and string match -q -r '^[0-9.]+$' -- $pref
            set -l current (kitten @ ls 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);print(next((w["background_opacity"] for w in d if w.get("is_focused")), d[0]["background_opacity"]))' 2>/dev/null)
            if test -n "$current"
                if test (math "abs($pref - $current)") -lt 0.02
                    kitten @ set-background-opacity --match id:$KITTY_WINDOW_ID $pref 2>/dev/null
                else
                    for i in (seq 1 12)
                        set -l v (math -s2 "$current + ($pref - $current) * $i / 12")
                        kitten @ set-background-opacity --match id:$KITTY_WINDOW_ID $v 2>/dev/null
                        if test $i -lt 12
                            sleep 0.005
                        end
                    end
                end
            end
            if set -q KITTY_PID
                set -l rundir "$XDG_RUNTIME_DIR"
                test -z "$rundir"; and set rundir /tmp
                if test $pref -gt 0.6
                    echo opaque > $rundir/kitty-mode-$KITTY_PID
                else
                    echo transparent > $rundir/kitty-mode-$KITTY_PID
                end
            end
        end
    end
end
