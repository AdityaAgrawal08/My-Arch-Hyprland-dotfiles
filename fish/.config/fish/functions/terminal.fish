function terminal --description "Fade kitty background opacity and sync nvim"
    set -l faint 0.2   # transparent level
    set -l solid 1.0   # opaque level
    set -l frames 12   # animation steps
    set -l gap 0.005   # pause between steps, seconds

    # Current opacity of the focused kitty window (read from kitty itself)
    set -l current (kitten @ ls 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);print(next((w["background_opacity"] for w in d if w.get("is_focused")), d[0]["background_opacity"]))' 2>/dev/null)
    if test -z "$current"
        echo "terminal: cannot talk to kitty (remote control disabled or not inside kitty)" >&2
        return 1
    end

    set -l target
    switch "$argv[1]"
        case transparent
            set target $faint
        case opaque
            set target $solid
        case toggle
            if test $current -gt 0.6
                set target $faint
            else
                set target $solid
            end
        case '*'
            echo "usage: terminal transparent|opaque|toggle" >&2
            return 1
    end

    if test (math "abs($target - $current)") -lt 0.02
        kitten @ set-background-opacity --all $target
    else
        for i in (seq 1 $frames)
            set -l v (math -s2 "$current + ($target - $current) * $i / $frames")
            kitten @ set-background-opacity --all $v; or return 1
            if test $i -lt $frames
                sleep $gap
            end
        end
    end

    # Publish the final state so nvim (and anything else) can follow it
    if test -n "$KITTY_PID"
        set -l rundir "$XDG_RUNTIME_DIR"
        test -z "$rundir"; and set rundir /tmp
        if test $target = $solid
            echo opaque > $rundir/kitty-mode-$KITTY_PID
        else
            echo transparent > $rundir/kitty-mode-$KITTY_PID
        end
    end
end
