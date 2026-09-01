# Bash completion for agy-profile and agy --profile

_agy_profile_completions() {
    local cur prev words cword
    _init_completion || return

    local commands="list ls whoami create login default bind link unbind unlink delete rm rename mv import import-current sync-config install install-shims"

    # Complete commands if at first position
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return 0
    fi

    local prev_cmd="${words[1]}"
    case "$prev_cmd" in
        login|delete|rm|default|bind|link|sync-config)
            # List available profile names
            local profiles_dir="${AGY_PROFILES_DIR:-$HOME/.local/share/agy-profiles}/profiles"
            if [[ -d "$profiles_dir" ]]; then
                local profile_names=$(ls "$profiles_dir" 2>/dev/null)
                COMPREPLY=( $(compgen -W "$profile_names" -- "$cur") )
            fi
            return 0
            ;;
        *)
            ;;
    esac
}

_agy_wrapper_completions() {
    local cur prev words cword
    _init_completion || return

    if [[ "$prev" == "--profile" || "$prev" == "-P" ]]; then
        local profiles_dir="${AGY_PROFILES_DIR:-$HOME/.local/share/agy-profiles}/profiles"
        if [[ -d "$profiles_dir" ]]; then
            local profile_names=$(ls "$profiles_dir" 2>/dev/null)
            COMPREPLY=( $(compgen -W "$profile_names" -- "$cur") )
        fi
        return 0
    fi
}

complete -F _agy_profile_completions agy-profile
complete -F _agy_wrapper_completions agy
