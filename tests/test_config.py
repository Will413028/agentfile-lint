import unittest
from pathlib import Path

import helpers
from agentfile_lint import config
import datetime

TODAY = datetime.date(2026, 6, 1)


def run(toml, *extra):
    root = helpers.make_repo({"AGENTS.md": "ok\n", ".agentfile-lint.toml": toml})
    return helpers.run_new(root, "--today", "2026-06-01", *extra)


LIMIT_100 = '[[rules.R1.limits]]\nglob = "AGENTS.md"\nmax_bytes = 100\n'


class ConfigTest(unittest.TestCase):
    def test_no_config_uses_preset(self):
        root = helpers.make_repo({"AGENTS.md": "ok\n"})
        self.assertEqual(helpers.run_new(root).returncode, 0)

    def test_unknown_top_level_key_fails(self):
        r = run("bogus = 1\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown key(s) bogus", r.stderr)

    def test_unknown_rule_key_fails(self):
        r = run("[rules.R1]\nmax_line_char = 400\n")  # typo
        self.assertEqual(r.returncode, 2)
        self.assertIn("max_line_char", r.stderr)

    def test_unknown_rule_id_fails(self):
        r = run("[rules.R99]\nlevel = 'error'\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("R99", r.stderr)

    def test_unknown_tier_key_fails(self):
        r = run("[rules.R1.max_bytes]\nroots = 5\n")
        self.assertEqual(r.returncode, 2)

    def test_unknown_allowlist_key_fails(self):
        r = run("[allowlist]\nmax_day = 5\n")
        self.assertEqual(r.returncode, 2)

    def test_bad_level_fails(self):
        r = run("[rules.R1]\nlevel = 'fatal'\n")
        self.assertEqual(r.returncode, 2)

    def test_invalid_toml_fails(self):
        r = run("this is = = not toml")
        self.assertEqual(r.returncode, 2)

    def test_repo_override_changes_a_single_limit(self):
        root = helpers.make_repo({"AGENTS.md": "x\n" * 60, ".agentfile-lint.toml": LIMIT_100})
        r = helpers.run_new(root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("AGENTS.md: error: R1: file is 120 bytes, limit 100", r.stdout)

    def test_levels_warn_and_off(self):
        files = {"AGENTS.md": "y" * 600 + "\n"}
        warn = helpers.make_repo({**files, ".agentfile-lint.toml": "[rules.R1]\nlevel = 'warn'\nmax_line_chars = 500\n"})
        r = helpers.run_new(warn)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("AGENTS.md:1: warning: R1: line is 600 characters, limit 500", r.stdout)
        off = helpers.make_repo({**files, ".agentfile-lint.toml": "[rules.R1]\nlevel = 'off'\nmax_line_chars = 500\n"})
        r = helpers.run_new(off)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_extends_relative_file_and_cycle(self):
        root = helpers.make_repo({
            "AGENTS.md": "x\n" * 60,
            "base.toml": LIMIT_100,
            ".agentfile-lint.toml": "extends = ['preset:default', 'base.toml']\n",
        })
        self.assertEqual(helpers.run_new(root).returncode, 1)
        cyc = helpers.make_repo({"AGENTS.md": "ok\n", "a.toml": "extends = ['b.toml']\n", "b.toml": "extends = ['a.toml']\n"})
        r = helpers.run_new(cyc, "--config", "a.toml")
        self.assertEqual(r.returncode, 2)
        self.assertIn("cycle", r.stderr)

    def test_unknown_preset_fails(self):
        r = run("extends = ['preset:nope']\n")
        self.assertEqual(r.returncode, 2)

    def test_list_rules_shows_effective_levels(self):
        root = helpers.make_repo({"AGENTS.md": "ok\n", ".agentfile-lint.toml": "[rules.R1]\nlevel = 'warn'\n"})
        r = helpers.run_new(root, "--list-rules")
        self.assertEqual(r.returncode, 0)
        self.assertRegex(r.stdout, r"(?m)^R1  warn +size:")

    def test_legacy_config_name_fails_with_rename_hint(self):
        root = helpers.make_repo({"AGENTS.md": "ok\n", ".instruction-lint.toml": "[rules.R1]\nlevel = 'warn'\n"})
        for args in ((), ("--list-rules",), ("config",), ("check-pins",)):
            r = helpers.run_new(root, *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("rename it to .agentfile-lint.toml", r.stderr)

    def test_new_name_wins_over_legacy_name(self):
        root = helpers.make_repo({"AGENTS.md": "ok\n", ".instruction-lint.toml": "x = 1\n", ".agentfile-lint.toml": ""})
        self.assertEqual(helpers.run_new(root).returncode, 0)

    def test_bad_today_is_usage_error(self):
        root = helpers.make_repo({"AGENTS.md": "ok\n"})
        self.assertEqual(helpers.run_new(root, "--today", "yesterday").returncode, 2)

    def test_config_load_api(self):
        cfg = config.load(None, TODAY)
        self.assertNotIn("max_line_chars", cfg.rules["R1"])  # omitted in the default: no line-length check
        self.assertEqual(cfg.rules["R1"]["path_limits"][0]["max_bytes"], 32768)


if __name__ == "__main__":
    unittest.main()
