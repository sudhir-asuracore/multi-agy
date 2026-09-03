"""Unit tests for agy wrapper argument parsing."""

import unittest

from agy_profile.wrapper import parse_profile_arguments


class TestWrapper(unittest.TestCase):
    def test_parse_profile_flags(self):
        # 1. Standard --profile <name>
        prof, args = parse_profile_arguments(["--profile", "work", "-p", "hello"])
        self.assertEqual(prof, "work")
        self.assertEqual(args, ["-p", "hello"])

        # 2. Key-value style --profile=<name>
        prof, args = parse_profile_arguments(["--profile=personal", "--continue"])
        self.assertEqual(prof, "personal")
        self.assertEqual(args, ["--continue"])

        # 3. Short flag -P <name>
        prof, args = parse_profile_arguments(["-P", "client1", "--model", "pro"])
        self.assertEqual(prof, "client1")
        self.assertEqual(args, ["--model", "pro"])

        # 4. Short flag attached -P=<name> or -Pname
        prof, args = parse_profile_arguments(["-P=client2", "-i"])
        self.assertEqual(prof, "client2")
        self.assertEqual(args, ["-i"])

        prof, args = parse_profile_arguments(["-Pclient3", "-i"])
        self.assertEqual(prof, "client3")
        self.assertEqual(args, ["-i"])

        # 5. No profile flag
        prof, args = parse_profile_arguments(["-p", "check code", "--continue"])
        self.assertIsNone(prof)
        self.assertEqual(args, ["-p", "check code", "--continue"])

    def test_command_name_resolution(self):
        from unittest.mock import MagicMock
        from agy_profile.core import ProfileManager
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            pm = ProfileManager(base_dir=base)
            pm.create_profile("work")
            pm.create_profile("personal")

            # Resolves from command name alias
            name, reason = pm.resolve_profile(command_name="agy-work")
            self.assertEqual(name, "work")
            self.assertIn("Command alias", reason)

            name, reason = pm.resolve_profile(command_name="/home/user/.local/bin/agy_work")
            self.assertEqual(name, "work")

            name, reason = pm.resolve_profile(command_name="agy-personal")
            self.assertEqual(name, "personal")


if __name__ == "__main__":
    unittest.main()
