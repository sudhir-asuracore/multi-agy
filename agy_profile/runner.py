"""Process execution runner with bubblewrap isolation and fallback overlay."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from agy_profile.core import ProfileManager, get_real_agy_binary


def is_bwrap_available() -> bool:
    """Checks if bwrap (bubblewrap) is installed and functional."""
    bwrap_path = shutil.which("bwrap")
    if not bwrap_path:
        return False
    return True


def ensure_symlink_overlay(profile_gemini_dir: Path, overlay_home: Path, real_home: Path) -> None:
    """
    Creates a fake home directory overlay where all files/dirs in real_home
    are symlinked, EXCEPT .gemini which points to profile_gemini_dir.
    """
    overlay_home.mkdir(parents=True, exist_ok=True)
    target_gemini = overlay_home / ".gemini"
    if target_gemini.is_symlink() or target_gemini.exists():
        if target_gemini.resolve() != profile_gemini_dir.resolve():
            if target_gemini.is_symlink() or target_gemini.is_file():
                target_gemini.unlink()
            else:
                shutil.rmtree(target_gemini)
            target_gemini.symlink_to(profile_gemini_dir)
    else:
        target_gemini.symlink_to(profile_gemini_dir)

    # Mirror entries from real_home as symlinks
    try:
        for entry in real_home.iterdir():
            if entry.name in (".gemini", ".local-agy-profiles"):
                continue
            overlay_entry = overlay_home / entry.name
            if not overlay_entry.exists() and not overlay_entry.is_symlink():
                try:
                    overlay_entry.symlink_to(entry)
                except Exception:
                    pass
    except Exception:
        pass


def build_bwrap_command(
    real_agy_bin: Path,
    profile_gemini_dir: Path,
    real_home: Path,
    args: List[str]
) -> List[str]:
    """Builds the bubblewrap command line for mounting the profile's .gemini dir and isolating keyrings."""
    target_gemini = real_home / ".gemini"
    cmd = [
        "bwrap",
        "--dev-bind", "/", "/",
    ]

    # Mask user dbus and gnome-keyring sockets to force profile-isolated file OAuth storage
    try:
        uid = os.getuid()
        user_run_dir = Path(f"/run/user/{uid}")
        dbus_socket = user_run_dir / "bus"
        keyring_dir = user_run_dir / "keyring"

        if keyring_dir.exists():
            cmd.extend(["--tmpfs", str(keyring_dir)])
        if dbus_socket.exists():
            cmd.extend(["--bind", "/dev/null", str(dbus_socket)])
    except Exception:
        pass

    cmd.extend([
        "--bind", str(profile_gemini_dir), str(target_gemini),
        str(real_agy_bin),
        *args
    ])
    return cmd


def execute_agy(
    profile_name: str,
    agy_args: List[str],
    manager: Optional[ProfileManager] = None,
    real_bin: Optional[Path] = None
) -> None:
    """
    Executes the real agy binary under the given profile using bubblewrap
    or home overlay. Replaces the current process via os.execvpe.
    """
    mgr = manager or ProfileManager()
    profile = mgr.get_profile(profile_name)
    if not profile:
        raise ValueError(f"Profile '{profile_name}' does not exist.")

    mgr.record_profile_used(profile_name)

    real_agy = real_bin or get_real_agy_binary()
    if not real_agy.exists():
        sys.stderr.write(f"\n[multi-agy Error] Real agy binary not found at: {real_agy}\n")
        sys.stderr.write("Please ensure Antigravity CLI is installed or set AGY_REAL_BIN.\n")
        sys.exit(1)

    real_home = Path(os.path.expanduser("~")).resolve()
    env = dict(os.environ)
    env["AGY_ACTIVE_PROFILE"] = profile_name
    env["AGY_REAL_BIN"] = str(real_agy)
    # Bypass single global OS keyring to ensure independent file-based credentials per profile
    env["DBUS_SESSION_BUS_ADDRESS"] = "disabled:"

    use_bwrap = is_bwrap_available() and mgr._load_config().get("settings", {}).get("use_bwrap", True)

    if use_bwrap:
        # Check that target ~/.gemini mount point exists on host so bwrap can bind over it
        host_gemini = real_home / ".gemini"
        if not host_gemini.exists():
            host_gemini.mkdir(parents=True, exist_ok=True)

        cmd = build_bwrap_command(real_agy, profile.gemini_dir, real_home, agy_args)
        # Execute directly, replacing process
        try:
            os.execvpe("bwrap", cmd, env)
        except FileNotFoundError:
            # Fallback if bwrap execution fails
            pass

    # Fallback to symlink overlay
    overlay_home = profile.gemini_dir.parent / "home_overlay"
    ensure_symlink_overlay(profile.gemini_dir, overlay_home, real_home)
    env["HOME"] = str(overlay_home)

    cmd = [str(real_agy)] + agy_args
    os.execvpe(str(real_agy), cmd, env)
