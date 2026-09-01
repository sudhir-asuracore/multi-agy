"""Core profile management logic for Multi-AGY."""

from __future__ import annotations

import base64
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def get_base_dir() -> Path:
    """Returns the base storage directory for agy profiles."""
    override = os.environ.get("AGY_PROFILES_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(os.path.expanduser("~/.local/share/agy-profiles")).resolve()


def get_config_file() -> Path:
    """Returns the global config file path."""
    return get_base_dir() / "config.json"


def get_profiles_dir() -> Path:
    """Returns the directory containing all profile subfolders."""
    return get_base_dir() / "profiles"


def get_real_agy_binary() -> Path:
    """Finds the real agy binary."""
    override = os.environ.get("AGY_REAL_BIN")
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        return Path(override).resolve()

    # Look for agy-real first (if renamed by installer)
    local_bin = Path(os.path.expanduser("~/.local/bin"))
    real_candidate = local_bin / "agy-real"
    if real_candidate.is_file() and os.access(real_candidate, os.X_OK):
        return real_candidate

    # Search PATH for agy, skipping any wrapper in ~/.local/bin if named agy
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for p in path_dirs:
        candidate = Path(p) / "agy"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            # Check if this candidate is our own wrapper
            try:
                with open(candidate, "rb") as f:
                    content = f.read(512)
                    if b"agy_profile" in content or b"MULTI_AGY" in content:
                        continue
            except Exception:
                pass
            return candidate.resolve()

    # Default fallback to ~/.local/bin/agy-real or ~/.local/bin/agy
    if real_candidate.exists():
        return real_candidate
    return local_bin / "agy"


@dataclass
class ProfileInfo:
    name: str
    gemini_dir: Path
    created_at: str
    last_used_at: str
    description: str
    email: Optional[str]
    is_authenticated: bool
    is_default: bool
    is_current: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["gemini_dir"] = str(self.gemini_dir)
        return d


class ProfileManager:
    """Manages profile creation, listing, switching, and directory binding."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or get_base_dir()
        self.profiles_dir = self.base_dir / "profiles"
        self.config_file = self.base_dir / "config.json"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_file.exists():
            self._save_config({
                "default_profile": "personal",
                "directory_bindings": {},
                "settings": {
                    "auto_create_shims": True,
                    "use_bwrap": True
                }
            })

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_file.exists():
            return {"default_profile": "personal", "directory_bindings": {}, "settings": {}}
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"default_profile": "personal", "directory_bindings": {}, "settings": {}}

    def _save_config(self, config: Dict[str, Any]) -> None:
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def get_default_profile_name(self) -> str:
        config = self._load_config()
        default = config.get("default_profile")
        if default and self.profile_exists(default):
            return default
        # If default doesn't exist, pick the first existing profile
        existing = self.list_profile_names()
        if existing:
            return existing[0]
        return "personal"

    def set_default_profile(self, name: str) -> bool:
        if not self.profile_exists(name):
            raise ValueError(f"Profile '{name}' does not exist.")
        config = self._load_config()
        config["default_profile"] = name
        self._save_config(config)
        return True

    def profile_exists(self, name: str) -> bool:
        p_dir = self.profiles_dir / name
        return p_dir.is_dir() and (p_dir / "gemini").is_dir()

    def list_profile_names(self) -> List[str]:
        if not self.profiles_dir.exists():
            return []
        profiles = []
        for item in sorted(self.profiles_dir.iterdir()):
            if item.is_dir() and (item / "gemini").is_dir():
                profiles.append(item.name)
        return profiles

    def _extract_account_email(self, gemini_dir: Path) -> Optional[str]:
        """Extracts the active Google account email from logs or credentials files."""
        import glob
        import re

        # 1. Check the most recent CLI log files (authoritative runtime authentication)
        log_pattern = str(gemini_dir / "antigravity-cli" / "log" / "cli-*.log")
        log_files = sorted(glob.glob(log_pattern), reverse=True)
        for lf in log_files[:5]:
            try:
                with open(lf, "r", encoding="utf-8", errors="ignore") as f:
                    # Scan backwards or read lines
                    for line in f:
                        m = re.search(r"OAuth:\s+authenticated successfully as\s+([^\s,]+)", line)
                        if m and "@" in m.group(1):
                            return m.group(1).strip()
                        m_apply = re.search(r"applyAuthResult:\s+email=([^\s,]+)", line)
                        if m_apply and "@" in m_apply.group(1):
                            return m_apply.group(1).strip()
            except Exception:
                pass

        # 2. Check oauth_creds.json (decode id_token JWT payload if available)
        oauth_file = gemini_dir / "oauth_creds.json"
        if oauth_file.exists():
            try:
                with open(oauth_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    id_token = data.get("id_token")
                    if id_token and isinstance(id_token, str):
                        parts = id_token.split(".")
                        if len(parts) >= 2:
                            payload_b64 = parts[1] + "=="
                            payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8", errors="ignore")
                            payload = json.loads(payload_json)
                            if "email" in payload and "@" in str(payload["email"]):
                                return str(payload["email"]).strip()
            except Exception:
                pass

        # 3. Check google_accounts.json
        ga_file = gemini_dir / "google_accounts.json"
        if ga_file.exists():
            try:
                with open(ga_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and data.get("active") and "@" in str(data["active"]):
                        return str(data["active"]).strip()
            except Exception:
                pass

        return None

    def _is_authenticated(self, gemini_dir: Path) -> bool:
        # 1. Check antigravity-oauth-token (primary file token used by Antigravity CLI)
        token_file = gemini_dir / "antigravity-cli" / "antigravity-oauth-token"
        if token_file.exists():
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    tok = data.get("token", {})
                    if isinstance(tok, dict) and (tok.get("access_token") or tok.get("refresh_token")):
                        return True
                    if data.get("access_token") or data.get("refresh_token"):
                        return True
            except Exception:
                if token_file.stat().st_size > 10:
                    return True

        # 2. Check oauth_creds.json
        oauth_file = gemini_dir / "oauth_creds.json"
        if oauth_file.exists():
            try:
                with open(oauth_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("access_token") or data.get("refresh_token"):
                        return True
            except Exception:
                pass

        # 3. Check recent CLI log files
        import glob
        log_pattern = str(gemini_dir / "antigravity-cli" / "log" / "cli-*.log")
        log_files = sorted(glob.glob(log_pattern), reverse=True)
        for lf in log_files[:3]:
            try:
                with open(lf, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "OAuth: authenticated successfully" in line:
                            return True
            except Exception:
                pass

        return False

    def get_profile(self, name: str, current_profile_name: Optional[str] = None) -> Optional[ProfileInfo]:
        p_dir = self.profiles_dir / name
        gemini_dir = p_dir / "gemini"
        if not (p_dir.is_dir() and gemini_dir.is_dir()):
            return None

        meta_file = p_dir / "meta.json"
        meta: Dict[str, Any] = {}
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass

        created_at = meta.get("created_at", datetime.now(timezone.utc).isoformat())
        last_used_at = meta.get("last_used_at", "Never")
        description = meta.get("description", "")

        is_auth = self._is_authenticated(gemini_dir)
        email = self._extract_account_email(gemini_dir) if is_auth else None
        # Update cached email if discovered
        if is_auth and email and email != meta.get("cached_email"):
            meta["cached_email"] = email
            try:
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass
        elif not is_auth and meta.get("cached_email"):
            meta["cached_email"] = None
            try:
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass
        is_default = (name == self.get_default_profile_name())
        is_current = (name == current_profile_name)

        return ProfileInfo(
            name=name,
            gemini_dir=gemini_dir,
            created_at=created_at,
            last_used_at=last_used_at,
            description=description,
            email=email,
            is_authenticated=is_auth,
            is_default=is_default,
            is_current=is_current
        )

    def list_profiles(self, current_profile_name: Optional[str] = None) -> List[ProfileInfo]:
        names = self.list_profile_names()
        results = []
        for name in names:
            p = self.get_profile(name, current_profile_name=current_profile_name)
            if p:
                results.append(p)
        return results

    def create_profile(self, name: str, description: str = "", copy_settings: bool = True) -> ProfileInfo:
        # Validate profile name
        cleaned_name = name.strip().lower()
        if not cleaned_name:
            raise ValueError("Profile name cannot be empty.")
        if not all(c.isalnum() or c in ("-", "_") for c in cleaned_name):
            raise ValueError(f"Invalid profile name '{cleaned_name}'. Use only letters, numbers, hyphens, and underscores.")

        p_dir = self.profiles_dir / cleaned_name
        if p_dir.exists():
            raise ValueError(f"Profile '{cleaned_name}' already exists.")

        gemini_dir = p_dir / "gemini"
        gemini_dir.mkdir(parents=True, exist_ok=True)
        (gemini_dir / "antigravity-cli").mkdir(parents=True, exist_ok=True)

        now_str = datetime.now(timezone.utc).isoformat()
        meta = {
            "name": cleaned_name,
            "created_at": now_str,
            "last_used_at": "Never",
            "description": description,
            "cached_email": None
        }
        with open(p_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # Optionally copy default settings.json and mcp.json from default profile or ~/.gemini
        if copy_settings:
            source_gemini = Path(os.path.expanduser("~/.gemini"))
            if source_gemini.exists():
                src_settings = source_gemini / "antigravity-cli" / "settings.json"
                if src_settings.exists():
                    dst_settings = gemini_dir / "antigravity-cli" / "settings.json"
                    try:
                        shutil.copy2(src_settings, dst_settings)
                    except Exception:
                        pass
                src_mcp = source_gemini / "antigravity-cli" / "mcp.json"
                if src_mcp.exists():
                    dst_mcp = gemini_dir / "antigravity-cli" / "mcp.json"
                    try:
                        shutil.copy2(src_mcp, dst_mcp)
                    except Exception:
                        pass

        # If this is the only profile, make it the default
        if len(self.list_profile_names()) == 1:
            self.set_default_profile(cleaned_name)

        p = self.get_profile(cleaned_name)
        assert p is not None
        return p

    def import_current_gemini(self, name: str, description: str = "Imported from ~/.gemini") -> ProfileInfo:
        """Imports the current active ~/.gemini folder into a new or updated profile."""
        source_gemini = Path(os.path.expanduser("~/.gemini")).resolve()
        if not source_gemini.exists():
            raise FileNotFoundError("No existing ~/.gemini directory found to import.")

        cleaned_name = name.strip().lower()
        if not all(c.isalnum() or c in ("-", "_") for c in cleaned_name):
            raise ValueError(f"Invalid profile name '{cleaned_name}'.")

        p_dir = self.profiles_dir / cleaned_name
        gemini_dir = p_dir / "gemini"

        if gemini_dir.exists():
            shutil.rmtree(gemini_dir)
        gemini_dir.parent.mkdir(parents=True, exist_ok=True)

        # Copy the directory tree
        shutil.copytree(source_gemini, gemini_dir, symlinks=True)

        # Update metadata
        email = self._extract_account_email(gemini_dir)
        now_str = datetime.now(timezone.utc).isoformat()
        meta = {
            "name": cleaned_name,
            "created_at": now_str,
            "last_used_at": now_str,
            "description": description,
            "cached_email": email
        }
        with open(p_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        p = self.get_profile(cleaned_name)
        assert p is not None
        return p

    def delete_profile(self, name: str, create_backup: bool = True) -> bool:
        if not self.profile_exists(name):
            raise ValueError(f"Profile '{name}' does not exist.")

        p_dir = self.profiles_dir / name
        if create_backup:
            backup_dir = self.base_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_zip = backup_dir / f"profile_{name}_{timestamp}"
            shutil.make_archive(str(backup_zip), "zip", p_dir)

        shutil.rmtree(p_dir)

        # If deleted profile was default, update default to another profile
        config = self._load_config()
        if config.get("default_profile") == name:
            remaining = self.list_profile_names()
            config["default_profile"] = remaining[0] if remaining else "personal"
            self._save_config(config)

        # Remove any directory bindings pointing to this profile
        bindings = config.get("directory_bindings", {})
        keys_to_remove = [k for k, v in bindings.items() if v == name]
        if keys_to_remove:
            for k in keys_to_remove:
                del bindings[k]
            config["directory_bindings"] = bindings
            self._save_config(config)

        return True

    def rename_profile(self, old_name: str, new_name: str) -> ProfileInfo:
        if not self.profile_exists(old_name):
            raise ValueError(f"Profile '{old_name}' does not exist.")
        cleaned_new = new_name.strip().lower()
        if self.profile_exists(cleaned_new):
            raise ValueError(f"Profile '{cleaned_new}' already exists.")

        src_dir = self.profiles_dir / old_name
        dst_dir = self.profiles_dir / cleaned_new
        src_dir.rename(dst_dir)

        # Update meta.json
        meta_file = dst_dir / "meta.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["name"] = cleaned_new
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass

        # Update config.json
        config = self._load_config()
        if config.get("default_profile") == old_name:
            config["default_profile"] = cleaned_new
        bindings = config.get("directory_bindings", {})
        for k, v in bindings.items():
            if v == old_name:
                bindings[k] = cleaned_new
        config["directory_bindings"] = bindings
        self._save_config(config)

        p = self.get_profile(cleaned_new)
        assert p is not None
        return p

    def record_profile_used(self, name: str) -> None:
        p_dir = self.profiles_dir / name
        meta_file = p_dir / "meta.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["last_used_at"] = datetime.now(timezone.utc).isoformat()
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass

    def bind_directory(self, target_dir: Path, profile_name: str, create_file: bool = True) -> None:
        if not self.profile_exists(profile_name):
            raise ValueError(f"Profile '{profile_name}' does not exist.")
        target_dir = target_dir.expanduser().resolve()
        if not target_dir.is_dir():
            raise NotADirectoryError(f"Directory '{target_dir}' does not exist.")

        if create_file:
            profile_file = target_dir / ".agyprofile"
            with open(profile_file, "w", encoding="utf-8") as f:
                f.write(f"{profile_name}\n")

        config = self._load_config()
        bindings = config.setdefault("directory_bindings", {})
        bindings[str(target_dir)] = profile_name
        self._save_config(config)

    def unbind_directory(self, target_dir: Path) -> bool:
        target_dir = target_dir.expanduser().resolve()
        profile_file = target_dir / ".agyprofile"
        file_removed = False
        if profile_file.exists():
            try:
                profile_file.unlink()
                file_removed = True
            except Exception:
                pass

        config = self._load_config()
        bindings = config.get("directory_bindings", {})
        bound = bindings.pop(str(target_dir), None)
        if bound or file_removed:
            self._save_config(config)
            return True
        return False

    def find_project_profile_file(self, start_dir: Path) -> Optional[Tuple[str, Path]]:
        """Traverses up from start_dir looking for a .agyprofile file."""
        current = start_dir.expanduser().resolve()
        while True:
            candidate = current / ".agyprofile"
            if candidate.is_file():
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        name = f.read().strip()
                        if name:
                            return (name, candidate)
                except Exception:
                    pass
            # Also check if candidate has .git
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    def resolve_profile(
        self,
        explicit_profile: Optional[str] = None,
        command_name: Optional[str] = None,
        cwd: Optional[Path] = None
    ) -> Tuple[str, str]:
        """
        Resolves which profile should be active.
        Returns: (profile_name, resolution_source_reason)
        """
        # 1. Explicit CLI option: --profile or -P
        if explicit_profile:
            p_name = explicit_profile.strip().lower()
            if not self.profile_exists(p_name):
                raise ValueError(f"Specified profile '{p_name}' does not exist.")
            return (p_name, f"CLI argument --profile {p_name}")

        # 2. Command name alias (e.g. agy_work, agy-personal)
        if command_name:
            base_cmd = os.path.basename(command_name)
            for prefix in ("agy_", "agy-"):
                if base_cmd.startswith(prefix) and len(base_cmd) > len(prefix):
                    candidate = base_cmd[len(prefix):].strip().lower()
                    if candidate and candidate not in ("profile", "profiles", "manager", "real", "wrap"):
                        if self.profile_exists(candidate):
                            return (candidate, f"Command alias {base_cmd}")

        # 3. Environment variable AGY_PROFILE
        env_profile = os.environ.get("AGY_PROFILE", "").strip().lower()
        if env_profile:
            if not self.profile_exists(env_profile):
                raise ValueError(f"Environment variable AGY_PROFILE='{env_profile}' specifies a non-existent profile.")
            return (env_profile, f"Environment variable AGY_PROFILE={env_profile}")

        # 4. Project .agyprofile file
        work_dir = (cwd or Path.cwd()).resolve()
        file_match = self.find_project_profile_file(work_dir)
        if file_match:
            p_name, path = file_match
            if self.profile_exists(p_name):
                return (p_name, f"Project config file {path}")

        # 5. Directory path binding in config.json
        config = self._load_config()
        bindings = config.get("directory_bindings", {})
        str_work_dir = str(work_dir)
        # Check exact or parent directory bindings
        best_match = None
        best_len = 0
        for bound_path, p_name in bindings.items():
            if str_work_dir == bound_path or str_work_dir.startswith(bound_path.rstrip("/") + "/"):
                if len(bound_path) > best_len and self.profile_exists(p_name):
                    best_match = (p_name, bound_path)
                    best_len = len(bound_path)
        if best_match:
            p_name, bound_path = best_match
            return (p_name, f"Registered directory binding for {bound_path}")

        # 6. Global default profile
        default_p = self.get_default_profile_name()
        if self.profile_exists(default_p):
            return (default_p, f"Default profile ({default_p})")

        # 7. First available or fallback
        all_profiles = self.list_profile_names()
        if all_profiles:
            return (all_profiles[0], f"First available profile ({all_profiles[0]})")

        return ("personal", "Fallback (no profiles configured yet)")
