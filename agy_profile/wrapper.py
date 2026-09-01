"""Smart CLI wrapper for agy that intercepts profile flags and shims."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from agy_profile.core import ProfileManager
from agy_profile.runner import execute_agy


def parse_profile_arguments(args: List[str]) -> Tuple[Optional[str], List[str]]:
    """
    Extracts --profile <name>, --profile=<name>, -P <name>, or -P=<name>
    from the argument list, returning (profile_name, remaining_args).
    """
    profile_name = None
    remaining_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--profile" or arg == "-P":
            if i + 1 < len(args):
                profile_name = args[i + 1]
                i += 2
                continue
            else:
                remaining_args.append(arg)
                i += 1
                continue
        elif arg.startswith("--profile="):
            profile_name = arg.split("=", 1)[1]
            i += 1
            continue
        elif arg.startswith("-P=") or (arg.startswith("-P") and len(arg) > 2 and not arg.startswith("-P-")):
            if arg.startswith("-P="):
                profile_name = arg.split("=", 1)[1]
            else:
                profile_name = arg[2:]
            i += 1
            continue
        else:
            remaining_args.append(arg)
            i += 1

    return profile_name, remaining_args


def ensure_initial_setup(manager: ProfileManager) -> None:
    """If no profiles exist yet, automatically import current ~/.gemini as 'personal'."""
    existing = manager.list_profile_names()
    if not existing:
        gemini_dir = Path(os.path.expanduser("~/.gemini"))
        if gemini_dir.is_dir():
            try:
                manager.import_current_gemini("personal", description="Initial personal account imported from ~/.gemini")
                manager.set_default_profile("personal")
            except Exception:
                manager.create_profile("personal", description="Default personal account")
        else:
            manager.create_profile("personal", description="Default personal account")


def main() -> None:
    manager = ProfileManager()
    ensure_initial_setup(manager)

    raw_args = sys.argv[1:]
    command_name = sys.argv[0]

    # Check for direct agy-profile delegation if called as `agy profile ...`
    if raw_args and raw_args[0] in ("profile", "profiles"):
        from agy_profile.cli import main as cli_main
        sys.argv = ["agy-profile"] + raw_args[1:]
        cli_main()
        return

    explicit_profile, agy_args = parse_profile_arguments(raw_args)

    try:
        profile_name, reason = manager.resolve_profile(
            explicit_profile=explicit_profile,
            command_name=command_name,
            cwd=Path.cwd()
        )
    except Exception as e:
        sys.stderr.write(f"[multi-agy Error] {e}\n")
        sys.exit(1)

    execute_agy(profile_name, agy_args, manager=manager)


if __name__ == "__main__":
    main()
