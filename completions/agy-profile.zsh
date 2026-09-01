#compdef agy-profile agy

_agy_profile() {
    local -a commands
    commands=(
        'list:List all configured profiles'
        'ls:List all configured profiles'
        'whoami:Display resolved profile and account for current directory'
        'create:Create a new profile'
        'login:Log in to a profile via browser OAuth'
        'default:Get or set the default profile'
        'bind:Bind current directory to a profile'
        'unbind:Unbind current directory'
        'delete:Delete a profile'
        'rename:Rename a profile'
        'import:Import ~/.gemini into a named profile'
        'sync-config:Sync settings and MCP servers across profiles'
        'install:Install multi-agy wrapper and shims into ~/.local/bin'
        'install-shims:Regenerate agy_<name> alias symlinks'
    )

    local profiles_dir="${AGY_PROFILES_DIR:-$HOME/.local/share/agy-profiles}/profiles"
    local -a profile_list
    if [[ -d "$profiles_dir" ]]; then
        profile_list=($(ls "$profiles_dir" 2>/dev/null))
    fi

    if (( CURRENT == 2 )); then
        _describe -t commands 'agy-profile command' commands
    elif (( CURRENT == 3 )); then
        case "$words[2]" in
            login|delete|rm|default|bind|link|sync-config)
                _describe -t profiles 'profile name' profile_list
                ;;
        esac
    fi
}

_agy_profile "$@"
