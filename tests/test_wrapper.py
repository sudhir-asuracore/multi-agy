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


if __name__ == "__main__":
    unittest.main()
