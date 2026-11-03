import unittest

import helpers


class SelfCheckTest(unittest.TestCase):
    def test_this_repos_own_instruction_files_pass(self):
        r = helpers.run_new(helpers.REPO)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_own_agents_md_passes_in_a_tracked_copy(self):
        # Non-vacuous even before the file is committed: analyze a tracked copy of it.
        text = (helpers.REPO / "AGENTS.md").read_text(encoding="utf-8")
        # R3b needs the other tracked files to resolve paths; this copy has none, so it is switched off.
        root = helpers.make_repo({"AGENTS.md": text, ".agentfile-lint.toml": "[rules.R3b]\nlevel = 'off'\n"})
        r = helpers.run_new(root, "--warn-as-error")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        # ...and the same copy fails when it is made too large (the check is really running).
        big = helpers.make_repo({"AGENTS.md": text + "x\n" * 17000})  # past the 32 KiB error limit
        self.assertEqual(helpers.run_new(big).returncode, 1)

    def test_version_guard_message(self):
        # Only checks the guard is wired; behaviour on <3.11 cannot be exercised on this interpreter.
        text = (helpers.REPO / "agentfile_lint" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("needs Python >= 3.11", text)


if __name__ == "__main__":
    unittest.main()
