function terminal --description "Control kitty background transparency"
    switch "$argv[1]"
        case transparent
            kitten @ set-background-opacity --all 0.2
        case opaque
            kitten @ set-background-opacity --all 1.0
        case toggle
            kitten @ set-background-opacity --all --toggle 1.0
        case '*'
            echo "usage: terminal transparent|opaque|toggle" >&2
            return 1
    end
end
