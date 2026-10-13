function terminal --description "Fade kitty background opacity"
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

    # Already there? Just set it, no animation needed.
    if test (math "abs($target - $current)") -lt 0.02
        kitten @ set-background-opacity --all $target
        return $status
    end

    # Fade: step the opacity toward the target
    for i in (seq 1 $frames)
        set -l v (math -s2 "$current + ($target - $current) * $i / $frames")
        kitten @ set-background-opacity --all $v; or return 1
        test $i -lt $frames; and sleep $gap
    end
end
