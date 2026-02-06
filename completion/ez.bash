# EZ bash completion
# Install: ez completion bash > ~/.bash_completion.d/ez && source ~/.bash_completion.d/ez
# Or: eval "$(ez completion bash)"

_ez_complete() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    case $COMP_CWORD in
        1)
            local cmds="list show new check browse plan template plugin log server client help version run completion"
            local tasks=$(_ez_task_names 2>/dev/null)
            COMPREPLY=($(compgen -W "$cmds $tasks" -- "$cur"))
            ;;
        2)
            case "$prev" in
                show|check|run)
                    COMPREPLY=($(compgen -W "$(_ez_task_names)" -- "$cur"))
                    ;;
                plan)
                    COMPREPLY=($(compgen -W "list new add show build check run $(_ez_plan_names)" -- "$cur"))
                    ;;
                template|tpl)
                    COMPREPLY=($(compgen -W "list show use" -- "$cur"))
                    ;;
                plugin)
                    COMPREPLY=($(compgen -W "list show run install" -- "$cur"))
                    ;;
                log)
                    COMPREPLY=($(compgen -W "list show clean" -- "$cur"))
                    ;;
                server)
                    COMPREPLY=($(compgen -W "start docker status" -- "$cur"))
                    ;;
                client)
                    COMPREPLY=($(compgen -W "start" -- "$cur"))
                    ;;
                completion)
                    COMPREPLY=($(compgen -W "bash zsh" -- "$cur"))
                    ;;
                new)
                    # 不补全，用户需要输入新名称
                    ;;
            esac
            ;;
        3)
            local pprev="${COMP_WORDS[COMP_CWORD-2]}"
            case "$pprev" in
                plan)
                    case "$prev" in
                        show|build|check|run)
                            COMPREPLY=($(compgen -W "$(_ez_plan_names)" -- "$cur"))
                            ;;
                        add)
                            COMPREPLY=($(compgen -W "$(_ez_plan_names)" -- "$cur"))
                            ;;
                    esac
                    ;;
            esac
            ;;
    esac
}

_ez_task_names() {
    local ez_bin="${COMP_WORDS[0]}"
    "$ez_bin" list -f 2>/dev/null | awk '{print $1}'
}

_ez_plan_names() {
    local ez_bin="${COMP_WORDS[0]}"
    "$ez_bin" plan list 2>/dev/null | awk 'NF>0 && !/^Plans/ && !/^\(/ {print $1}'
}

complete -F _ez_complete ez
complete -F _ez_complete ./ez
