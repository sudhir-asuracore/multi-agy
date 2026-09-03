"""Management CLI for Multi-AGY profiles."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from agy_profile.core import (
    ProfileInfo,
    ProfileManager,
    get_base_dir,
    get_config_file,
    get_real_agy_binary,
)
from agy_profile.runner import execute_agy

#Terminal ANSI colors
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def format_table(headers: List[str], rows: List[List[str]]) -> str:
    """Formats rows into an aligned terminal table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            # Strip ANSI escape codes for width calculation
            clean_cell = cell.replace(GREEN, "").replace(CYAN, "").replace(YELLOW, "").replace(RED, "").replace(BOLD, "").replace(DIM, "").replace(RESET, "")
            if len(clean_cell) > widths[i]:
                widths[i] = len(clean_cell)

    header_line = "  ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers))
    sep_line = "  ".join("-" * widths[i] for i in range(len(headers)))
    row_lines = []
    for row in rows:
        formatted_cells = []
        for i, cell in enumerate(row):
            clean_cell = cell.replace(GREEN, "").replace(CYAN, "").replace(YELLOW, "").replace(RED, "").replace(BOLD, "").replace(DIM, "").replace(RESET, "")
            padding = " " * (widths[i] - len(clean_cell))
            formatted_cells.append(cell + padding)
        row_lines.append("  ".join(formatted_cells))

    return f"\n{BOLD}{header_line}{RESET}\n{DIM}{sep_line}{RESET}\n" + "\n".join(row_lines) + "\n"


def cmd_list(manager: ProfileManager, args: argparse.Namespace) -> None:
    current_profile, reason = manager.resolve_profile(cwd=Path.cwd())
    profiles = manager.list_profiles(current_profile_name=current_profile)

    if not profiles:
        print(f"\n{YELLOW}No agy profiles found.{RESET}")
        print("Create one using: agy-profile create <name>")
        print("Or import your existing session: agy-profile import <name>\n")
        return

    headers = ["ACTIVE", "PROFILE", "ACCOUNT EMAIL", "DEFAULT", "STATUS", "LAST USED"]
    rows = []
    for p in profiles:
        active_mark = f"{GREEN}* (current){RESET}" if p.is_current else " "
        name_str = f"{BOLD}{p.name}{RESET}" if p.is_current else p.name
        email_str = p.email or f"{DIM}(not detected){RESET}"
        default_str = f"{CYAN}yes{RESET}" if p.is_default else "no"
        status_str = f"{GREEN}authenticated{RESET}" if p.is_authenticated else f"{YELLOW}needs login{RESET}"
        last_used = p.last_used_at.split("T")[0] if "T" in p.last_used_at else p.last_used_at

        rows.append([active_mark, name_str, email_str, default_str, status_str, last_used])

    print(format_table(headers, rows))
    print(f"{DIM}Current directory resolved to profile '{BOLD}{current_profile}{RESET}{DIM}' via: {reason}{RESET}\n")


def cmd_create(manager: ProfileManager, args: argparse.Namespace) -> None:
    name = args.name.strip().lower()
    desc = args.description or ""
    try:
        p = manager.create_profile(name, description=desc)
        print(f"{GREEN}[OK] Created profile '{BOLD}{name}{RESET}{GREEN}'.{RESET}")
        install_shims(manager)
        print(f"\nTo log in to this account, run:\n  {CYAN}agy-profile login {name}{RESET}  or  {CYAN}agy --profile {name}{RESET}\n")
    except Exception as e:
        print(f"{RED}Error creating profile: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_login(manager: ProfileManager, args: argparse.Namespace) -> None:
    name = args.name.strip().lower()
    if not manager.profile_exists(name):
        print(f"{RED}Error: Profile '{name}' does not exist.{RESET}", file=sys.stderr)
        print("Create it first with: agy-profile create " + name)
        sys.exit(1)

    print(f"\n{CYAN}Starting agy authentication session for profile '{BOLD}{name}{RESET}{CYAN}'...{RESET}")
    print("Follow any browser login prompts that appear.\n")
    execute_agy(name, [], manager=manager)


def cmd_whoami(manager: ProfileManager, args: argparse.Namespace) -> None:
    current_profile, reason = manager.resolve_profile(cwd=Path.cwd())
    p = manager.get_profile(current_profile)
    print(f"\n{BOLD}Resolved Profile:{RESET} {CYAN}{current_profile}{RESET}")
    print(f"{BOLD}Resolution Source:{RESET} {reason}")
    if p:
        print(f"{BOLD}Account Email:{RESET}    {p.email or '(not detected)'}")
        print(f"{BOLD}Authenticated:{RESET}    {p.is_authenticated}")
        print(f"{BOLD}Default Profile:{RESET}  {p.is_default}")
        print(f"{BOLD}Gemini Directory:{RESET} {p.gemini_dir}\n")


def cmd_default(manager: ProfileManager, args: argparse.Namespace) -> None:
    if args.name:
        name = args.name.strip().lower()
        try:
            manager.set_default_profile(name)
            print(f"{GREEN}[OK] Default profile set to '{BOLD}{name}{RESET}{GREEN}'.{RESET}")
        except Exception as e:
            print(f"{RED}Error: {e}{RESET}", file=sys.stderr)
            sys.exit(1)
    else:
        current_default = manager.get_default_profile_name()
        print(f"Current default profile: {CYAN}{current_default}{RESET}")


def cmd_bind(manager: ProfileManager, args: argparse.Namespace) -> None:
    target_dir = Path(args.path).resolve() if args.path else Path.cwd().resolve()
    profile_name = args.name.strip().lower()

    if not manager.profile_exists(profile_name):
        print(f"{RED}Error: Profile '{profile_name}' does not exist.{RESET}", file=sys.stderr)
        sys.exit(1)

    try:
        manager.bind_directory(target_dir, profile_name, create_file=not args.no_file)
        print(f"{GREEN}[OK] Bound directory '{BOLD}{target_dir}{RESET}{GREEN}' to profile '{BOLD}{profile_name}{RESET}{GREEN}'.{RESET}")
        if not args.no_file:
            print(f"{DIM}Created .agyprofile marker in {target_dir}{RESET}")
    except Exception as e:
        print(f"{RED}Error binding directory: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_unbind(manager: ProfileManager, args: argparse.Namespace) -> None:
    target_dir = Path(args.path).resolve() if args.path else Path.cwd().resolve()
    success = manager.unbind_directory(target_dir)
    if success:
        print(f"{GREEN}[OK] Unbound directory '{BOLD}{target_dir}{RESET}{GREEN}'.{RESET}")
    else:
        print(f"{YELLOW}No profile binding found for '{target_dir}'.{RESET}")


def cmd_delete(manager: ProfileManager, args: argparse.Namespace) -> None:
    name = args.name.strip().lower()
    if not manager.profile_exists(name):
        print(f"{RED}Error: Profile '{name}' does not exist.{RESET}", file=sys.stderr)
        sys.exit(1)

    if not args.force:
        confirm = input(f"Are you sure you want to delete profile '{name}'? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Deletion cancelled.")
            return

    try:
        manager.delete_profile(name, create_backup=not args.no_backup)
        print(f"{GREEN}[OK] Deleted profile '{BOLD}{name}{RESET}{GREEN}'.{RESET}")
        # Refresh shims
        install_shims(manager)
    except Exception as e:
        print(f"{RED}Error deleting profile: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_rename(manager: ProfileManager, args: argparse.Namespace) -> None:
    old_name = args.old_name.strip().lower()
    new_name = args.new_name.strip().lower()
    try:
        manager.rename_profile(old_name, new_name)
        print(f"{GREEN}[OK] Renamed profile '{old_name}' to '{BOLD}{new_name}{RESET}{GREEN}'.{RESET}")
        install_shims(manager)
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_import(manager: ProfileManager, args: argparse.Namespace) -> None:
    name = args.name.strip().lower()
    desc = args.description or "Imported from ~/.gemini"
    try:
        p = manager.import_current_gemini(name, description=desc)
        print(f"{GREEN}[OK] Successfully imported existing ~/.gemini into profile '{BOLD}{name}{RESET}{GREEN}'.{RESET}")
        if p.email:
            print(f"  Account email: {CYAN}{p.email}{RESET}")
        install_shims(manager)
    except Exception as e:
        print(f"{RED}Error importing: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_sync_config(manager: ProfileManager, args: argparse.Namespace) -> None:
    src_name = args.source.strip().lower()
    src_profile = manager.get_profile(src_name)
    if not src_profile:
        print(f"{RED}Error: Source profile '{src_name}' does not exist.{RESET}", file=sys.stderr)
        sys.exit(1)

    targets = [t.strip().lower() for t in args.targets] if args.targets else [
        p for p in manager.list_profile_names() if p != src_name
    ]

    src_settings = src_profile.gemini_dir / "antigravity-cli" / "settings.json"
    src_mcp = src_profile.gemini_dir / "antigravity-cli" / "mcp.json"

    count = 0
    for t_name in targets:
        t_profile = manager.get_profile(t_name)
        if not t_profile:
            continue
        dest_cli_dir = t_profile.gemini_dir / "antigravity-cli"
        dest_cli_dir.mkdir(parents=True, exist_ok=True)
        if src_settings.exists():
            shutil.copy2(src_settings, dest_cli_dir / "settings.json")
        if src_mcp.exists():
            shutil.copy2(src_mcp, dest_cli_dir / "mcp.json")
        count += 1

    print(f"{GREEN}[OK] Synchronized configurations from '{src_name}' to {count} profile(s).{RESET}")


def install_shims(manager: ProfileManager) -> None:
    """Creates symlinks in ~/.local/bin for agy_<name> and agy-<name>."""
    bin_dir = Path(os.path.expanduser("~/.local/bin")).resolve()
    bin_dir.mkdir(parents=True, exist_ok=True)
    agy_wrapper = bin_dir / "agy"

    if not agy_wrapper.exists():
        return

    profiles = manager.list_profile_names()
    for name in profiles:
        for shim_name in (f"agy_{name}", f"agy-{name}"):
            shim_path = bin_dir / shim_name
            if shim_path.is_symlink() or not shim_path.exists():
                try:
                    if shim_path.is_symlink() or shim_path.is_file():
                        shim_path.unlink()
                    shim_path.symlink_to(agy_wrapper)
                except Exception:
                    pass


def cmd_install(manager: ProfileManager, args: argparse.Namespace) -> None:
    """Installs the wrapper and management CLI into ~/.local/bin."""
    bin_dir = Path(os.path.expanduser("~/.local/bin")).resolve()
    bin_dir.mkdir(parents=True, exist_ok=True)

    # 1. Check existing agy in ~/.local/bin
    current_agy = bin_dir / "agy"
    real_agy = bin_dir / "agy-real"

    if current_agy.exists() and not current_agy.is_symlink():
        # Check if it's the real binary (large binary)
        try:
            with open(current_agy, "rb") as f:
                header = f.read(512)
                if b"agy_profile" not in header and b"MULTI_AGY" not in header:
                    print(f"Preserving real agy binary as {real_agy}...")
                    if real_agy.exists():
                        real_agy.unlink()
                    shutil.move(str(current_agy), str(real_agy))
        except Exception as e:
            print(f"{YELLOW}Warning moving agy: {e}{RESET}")

    # 2. Write executable launcher scripts into ~/.local/bin
    wrapper_script_path = bin_dir / "agy"
    manager_script_path = bin_dir / "agy-profile"

    # Python executable path
    py_exec = sys.executable

    # Project directory
    project_root = Path(__file__).resolve().parent.parent

    wrapper_content = f"""#!/usr/bin/env bash
#Multi-AGY Smart Wrapper
AGY_COMMAND_NAME="${{AGY_COMMAND_NAME:-$0}}" PYTHONPATH="{project_root}:${{PYTHONPATH}}" exec "{py_exec}" -m agy_profile.wrapper "$@"
"""

    manager_content = f"""#!/usr/bin/env bash
#Multi-AGY Profile Manager CLI
PYTHONPATH="{project_root}:${{PYTHONPATH}}" exec "{py_exec}" -m agy_profile.cli "$@"
"""

    with open(wrapper_script_path, "w", encoding="utf-8") as f:
        f.write(wrapper_content)
    wrapper_script_path.chmod(0o755)

    with open(manager_script_path, "w", encoding="utf-8") as f:
        f.write(manager_content)
    manager_script_path.chmod(0o755)

    # 3. Auto-import existing ~/.gemini if first time
    if not manager.list_profile_names():
        gemini_dir = Path(os.path.expanduser("~/.gemini"))
        if gemini_dir.is_dir():
            print("Importing existing account into 'personal' profile...")
            manager.import_current_gemini("personal", description="Initial personal account")
            manager.set_default_profile("personal")

    # 4. Install profile shims
    install_shims(manager)

    print(f"\n{GREEN}{BOLD}[OK] Multi-AGY successfully installed!{RESET}")
    print(f"  - Wrapper installed to: {CYAN}{wrapper_script_path}{RESET}")
    print(f"  - Profile manager:      {CYAN}{manager_script_path}{RESET}")
    print(f"\nYou can now run:\n  {BOLD}agy-profile list{RESET}       - See all accounts and profiles\n  {BOLD}agy-profile create <name>{RESET} - Add another work or personal account\n  {BOLD}agy --profile <name>{RESET}     - Start agy with that specific profile\n  {BOLD}agy_<name>{RESET}               - Direct shortcut command\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agy-profile",
        description="Multi-AGY Profile Manager: Manage and switch between multiple Antigravity CLI accounts."
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list / ls
    subparsers.add_parser("list", aliases=["ls"], help="List all configured profiles")

    # whoami
    subparsers.add_parser("whoami", help="Display resolved profile and account for current directory")

    # create
    p_create = subparsers.add_parser("create", help="Create a new profile")
    p_create.add_argument("name", help="Name of the new profile (e.g. work, client-a, personal)")
    p_create.add_argument("-d", "--description", default="", help="Optional description for the profile")

    # login
    p_login = subparsers.add_parser("login", help="Log in to a profile via browser OAuth")
    p_login.add_argument("name", help="Profile name to log in to")

    # default
    p_default = subparsers.add_parser("default", help="Get or set the default profile")
    p_default.add_argument("name", nargs="?", help="Profile name to set as default")

    # bind
    p_bind = subparsers.add_parser("bind", aliases=["link"], help="Bind current directory to a profile")
    p_bind.add_argument("name", help="Profile name to bind to")
    p_bind.add_argument("-p", "--path", help="Target directory (defaults to current directory)")
    p_bind.add_argument("--no-file", action="store_true", help="Don't create .agyprofile marker file")

    # unbind
    p_unbind = subparsers.add_parser("unbind", aliases=["unlink"], help="Unbind current directory")
    p_unbind.add_argument("-p", "--path", help="Target directory (defaults to current directory)")

    # delete
    p_del = subparsers.add_parser("delete", aliases=["rm"], help="Delete a profile")
    p_del.add_argument("name", help="Profile name to delete")
    p_del.add_argument("-f", "--force", action="store_true", help="Skip confirmation prompt")
    p_del.add_argument("--no-backup", action="store_true", help="Do not create backup archive before deleting")

    # rename
    p_ren = subparsers.add_parser("rename", aliases=["mv"], help="Rename a profile")
    p_ren.add_argument("old_name", help="Old profile name")
    p_ren.add_argument("new_name", help="New profile name")

    # import
    p_imp = subparsers.add_parser("import", aliases=["import-current"], help="Import ~/.gemini into a named profile")
    p_imp.add_argument("name", help="Name for the imported profile")
    p_imp.add_argument("-d", "--description", default="", help="Description")

    # sync-config
    p_sync = subparsers.add_parser("sync-config", help="Sync settings and MCP servers from one profile to others")
    p_sync.add_argument("source", help="Source profile name")
    p_sync.add_argument("targets", nargs="*", help="Target profile names (defaults to all other profiles)")

    # install
    subparsers.add_parser("install", help="Install multi-agy wrapper and shims into ~/.local/bin")

    # install-shims
    subparsers.add_parser("install-shims", help="Regenerate agy_<name> alias symlinks in ~/.local/bin")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    manager = ProfileManager()

    if not args.command or args.command in ("list", "ls"):
        cmd_list(manager, args)
    elif args.command == "whoami":
        cmd_whoami(manager, args)
    elif args.command == "create":
        cmd_create(manager, args)
    elif args.command == "login":
        cmd_login(manager, args)
    elif args.command == "default":
        cmd_default(manager, args)
    elif args.command in ("bind", "link"):
        cmd_bind(manager, args)
    elif args.command in ("unbind", "unlink"):
        cmd_unbind(manager, args)
    elif args.command in ("delete", "rm"):
        cmd_delete(manager, args)
    elif args.command in ("rename", "mv"):
        cmd_rename(manager, args)
    elif args.command in ("import", "import-current"):
        cmd_import(manager, args)
    elif args.command == "sync-config":
        cmd_sync_config(manager, args)
    elif args.command == "install":
        cmd_install(manager, args)
    elif args.command == "install-shims":
        install_shims(manager)
        print(f"{GREEN}[OK] Refreshed profile shims in ~/.local/bin{RESET}")


if __name__ == "__main__":
    main()
