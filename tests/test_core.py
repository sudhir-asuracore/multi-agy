"""Unit tests for Multi-AGY core profile management."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from agy_profile.core import ProfileManager


class TestProfileManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir) / "agy-profiles"
        self.manager = ProfileManager(base_dir=self.base_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_and_list_profile(self):
        self.manager.create_profile("work", description="Work account", copy_settings=False)
        self.assertTrue(self.manager.profile_exists("work"))
        self.assertFalse(self.manager.profile_exists("nonexistent"))

        profiles = self.manager.list_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].name, "work")
        self.assertEqual(profiles[0].description, "Work account")
        # Since it's the first profile, it becomes default
        self.assertTrue(profiles[0].is_default)

    def test_invalid_profile_names(self):
        with self.assertRaises(ValueError):
            self.manager.create_profile("invalid name with spaces")
        with self.assertRaises(ValueError):
            self.manager.create_profile("invalid/slash")
        with self.assertRaises(ValueError):
            self.manager.create_profile("")

    def test_duplicate_profile_error(self):
        self.manager.create_profile("personal", copy_settings=False)
        with self.assertRaises(ValueError):
            self.manager.create_profile("personal", copy_settings=False)

    def test_set_default_profile(self):
        self.manager.create_profile("personal", copy_settings=False)
        self.manager.create_profile("work", copy_settings=False)
        self.assertEqual(self.manager.get_default_profile_name(), "personal")

        self.manager.set_default_profile("work")
        self.assertEqual(self.manager.get_default_profile_name(), "work")

    def test_delete_profile_with_backup(self):
        self.manager.create_profile("temp-work", copy_settings=False)
        self.assertTrue(self.manager.profile_exists("temp-work"))

        self.manager.delete_profile("temp-work", create_backup=True)
        self.assertFalse(self.manager.profile_exists("temp-work"))

        backup_dir = self.base_dir / "backups"
        self.assertTrue(backup_dir.exists())
        backups = list(backup_dir.glob("profile_temp-work_*.zip"))
        self.assertEqual(len(backups), 1)

    def test_rename_profile(self):
        self.manager.create_profile("old-name", copy_settings=False)
        self.manager.rename_profile("old-name", "new-name")
        self.assertFalse(self.manager.profile_exists("old-name"))
        self.assertTrue(self.manager.profile_exists("new-name"))

    def test_bind_and_unbind_directory(self):
        project_dir = Path(self.temp_dir) / "my_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        self.manager.create_profile("client-a", copy_settings=False)
        self.manager.bind_directory(project_dir, "client-a", create_file=True)

        marker_file = project_dir / ".agyprofile"
        self.assertTrue(marker_file.exists())
        self.assertEqual(marker_file.read_text().strip(), "client-a")

        # Test resolve profile from project dir
        resolved, reason = self.manager.resolve_profile(cwd=project_dir)
        self.assertEqual(resolved, "client-a")
        self.assertIn(".agyprofile", reason)

        # Test sub-directory inheritance
        subdir = project_dir / "src" / "pkg"
        subdir.mkdir(parents=True, exist_ok=True)
        resolved_sub, reason_sub = self.manager.resolve_profile(cwd=subdir)
        self.assertEqual(resolved_sub, "client-a")

        # Unbind
        self.manager.unbind_directory(project_dir)
        self.assertFalse(marker_file.exists())

    def test_resolution_hierarchy(self):
        self.manager.create_profile("default-prof", copy_settings=False)
        self.manager.create_profile("env-prof", copy_settings=False)
        self.manager.create_profile("cli-prof", copy_settings=False)
        self.manager.create_profile("alias-prof", copy_settings=False)
        self.manager.create_profile("proj-prof", copy_settings=False)
        self.manager.set_default_profile("default-prof")

        proj_dir = Path(self.temp_dir) / "proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / ".agyprofile").write_text("proj-prof")

        # 1. Base case: default profile
        empty_dir = Path(self.temp_dir) / "empty"
        empty_dir.mkdir()
        resolved, _ = self.manager.resolve_profile(cwd=empty_dir)
        self.assertEqual(resolved, "default-prof")

        # 2. Project file overrides default
        resolved, _ = self.manager.resolve_profile(cwd=proj_dir)
        self.assertEqual(resolved, "proj-prof")

        # 3. Env var overrides project file
        os.environ["AGY_PROFILE"] = "env-prof"
        try:
            resolved, _ = self.manager.resolve_profile(cwd=proj_dir)
            self.assertEqual(resolved, "env-prof")
        finally:
            del os.environ["AGY_PROFILE"]

        # 4. Command alias overrides env var
        os.environ["AGY_PROFILE"] = "env-prof"
        try:
            resolved, _ = self.manager.resolve_profile(command_name="agy_alias-prof", cwd=proj_dir)
            self.assertEqual(resolved, "alias-prof")
        finally:
            del os.environ["AGY_PROFILE"]

        # 5. Explicit CLI flag overrides everything
        os.environ["AGY_PROFILE"] = "env-prof"
        try:
            resolved, _ = self.manager.resolve_profile(
                explicit_profile="cli-prof",
                command_name="agy_alias-prof",
                cwd=proj_dir
            )
            self.assertEqual(resolved, "cli-prof")
        finally:
            del os.environ["AGY_PROFILE"]


if __name__ == "__main__":
    unittest.main()
