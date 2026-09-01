"""Unit tests for execution runner and bubblewrap command builder."""

import tempfile
import unittest
from pathlib import Path

from agy_profile.runner import build_bwrap_command, ensure_symlink_overlay


class TestRunner(unittest.TestCase):
    def test_build_bwrap_command(self):
        real_bin = Path("/usr/local/bin/agy-real")
        profile_gemini = Path("/home/user/.local/share/agy-profiles/profiles/work/gemini")
        real_home = Path("/home/user")
        args = ["-p", "test prompt", "--mode", "plan"]

        cmd = build_bwrap_command(real_bin, profile_gemini, real_home, args)
        self.assertEqual(cmd[0], "bwrap")
        self.assertIn("--dev-bind", cmd)
        self.assertIn("/", cmd)
        self.assertIn("--bind", cmd)
        self.assertIn(str(profile_gemini), cmd)
        self.assertIn(str(real_home / ".gemini"), cmd)
        self.assertIn(str(real_bin), cmd)
        self.assertIn("-p", cmd)
        self.assertIn("test prompt", cmd)

    def test_ensure_symlink_overlay(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            real_home = tmp / "real_home"
            real_home.mkdir()
            (real_home / ".gitconfig").write_text("[user]\nname = Test")
            (real_home / ".ssh").mkdir()

            profile_gemini = tmp / "profiles" / "work" / "gemini"
            profile_gemini.mkdir(parents=True)
            (profile_gemini / "google_accounts.json").write_text('{"active":"work@corp.com"}')

            overlay_home = tmp / "overlay_home"
            ensure_symlink_overlay(profile_gemini, overlay_home, real_home)

            # Check .gemini in overlay points to profile_gemini
            overlay_gemini = overlay_home / ".gemini"
            self.assertTrue(overlay_gemini.is_symlink())
            self.assertEqual(overlay_gemini.resolve(), profile_gemini.resolve())

            # Check other files are mirrored
            self.assertTrue((overlay_home / ".gitconfig").exists())
            self.assertTrue((overlay_home / ".ssh").exists())


if __name__ == "__main__":
    unittest.main()
