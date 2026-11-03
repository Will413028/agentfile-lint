"""Symlinked instruction files (e.g. CLAUDE.md -> AGENTS.md) are aliases of their target, not copies."""
import tempfile
import unittest
from pathlib import Path

import helpers

LONG = "# Project\n\n" + "".join(f"- Rule {i} keeps the build reproducible on every machine we use.\n" for i in range(230))
ARGS = ("--today", "2026-06-01")


def lint(files, symlinks, config=""):
    files = dict(files)
    if config:
        files[".agentfile-lint.toml"] = config
    r = helpers.run_new(helpers.make_repo(files, symlinks=symlinks), *ARGS)
    return r.returncode, r.stdout.splitlines() + r.stderr.splitlines()


def on(path, lines):
    return [line for line in lines if line.startswith(f"{path}:")]


class SymlinkAliasTest(unittest.TestCase):
    def test_claude_md_symlink_to_agents_md_is_not_checked_again(self):
        _, lines = lint({"AGENTS.md": LONG}, {"CLAUDE.md": "AGENTS.md"}, '[rules.C1]\nlevel = "error"\n')
        self.assertEqual(on("CLAUDE.md", lines), [])                       # no R1, R5 or C1 on the alias
        self.assertEqual(len([x for x in on("AGENTS.md", lines) if ": R1: " in x]), 2)  # target still checked once

    def test_nested_symlink_to_parent_file_is_an_alias(self):
        _, lines = lint({"AGENTS.md": LONG}, {"sub/AGENTS.md": "../AGENTS.md"})
        self.assertEqual(on("sub/AGENTS.md", lines), [])

    def test_agents_md_symlink_to_claude_md_checks_claude_md_as_the_real_file(self):
        _, lines = lint({"CLAUDE.md": LONG}, {"AGENTS.md": "CLAUDE.md"}, '[rules.C1]\nlevel = "error"\n')
        self.assertEqual(on("AGENTS.md", lines), [])
        self.assertIn("CLAUDE.md:0: C1: CLAUDE.md must contain only the line '@AGENTS.md'", lines)

    def test_forbid_still_reports_a_symlinked_claude_md(self):
        _, lines = lint({"AGENTS.md": "ok\n"}, {"CLAUDE.md": "AGENTS.md"}, '[rules.C1]\nlevel = "error"\nmode = "forbid"\n')
        self.assertEqual([x for x in lines if ": C1: " in x], ["CLAUDE.md:0: C1: CLAUDE.md must not exist (mode forbid); keep the instructions in AGENTS.md"])

    def test_symlink_to_a_file_outside_the_repo_is_checked_as_its_own_file(self):
        outside = Path(tempfile.mkdtemp(prefix="il-outside-")) / "shared.md"
        outside.write_text(LONG, encoding="utf-8")
        _, lines = lint({}, {"AGENTS.md": str(outside)})
        self.assertEqual(len([x for x in on("AGENTS.md", lines) if ": R1: " in x]), 2)

    def test_dangling_symlink_is_skipped(self):
        rc, lines = lint({"AGENTS.md": "ok\n"}, {"CLAUDE.md": "missing.md"})
        self.assertEqual((rc, on("CLAUDE.md", lines)), (0, []))


if __name__ == "__main__":
    unittest.main()
