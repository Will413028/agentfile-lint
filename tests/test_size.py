"""R1 limits by path glob: first match wins, max_lines, no match, old keys, preset values."""
import unittest

import helpers

CFG = ".agentfile-lint.toml"


def limits(*entries):
    return "".join(
        "[[rules.R1.limits]]\n" + "".join(f"{k} = {v!r}\n".replace("'", '"') for k, v in e.items()) for e in entries
    )


def run(files, toml):
    return helpers.run_new(helpers.make_repo({**files, CFG: toml}))


class SizeLimitsTest(unittest.TestCase):
    def test_first_match_wins_in_order(self):
        toml = limits({"glob": "**/AGENTS.md", "max_bytes": 50}, {"glob": "sub/AGENTS.md", "max_bytes": 1000})
        r = run({"sub/AGENTS.md": "x\n" * 60}, toml)  # 120 bytes; the first (tight) entry matches
        self.assertEqual(r.returncode, 1)
        self.assertIn("sub/AGENTS.md:0: R1: file is 120 bytes, limit 50", r.stderr)
        swapped = limits({"glob": "sub/AGENTS.md", "max_bytes": 1000}, {"glob": "**/AGENTS.md", "max_bytes": 50})
        self.assertEqual(run({"sub/AGENTS.md": "x\n" * 60}, swapped).returncode, 0)

    def test_star_does_not_cross_slash(self):
        toml = limits({"glob": "*/AGENTS.md", "max_bytes": 10})
        self.assertEqual(run({"a/b/AGENTS.md": "x\n" * 60}, toml).returncode, 0)
        self.assertEqual(run({"a/AGENTS.md": "x\n" * 60}, toml).returncode, 1)

    def test_max_lines(self):
        toml = limits({"glob": "AGENTS.md", "max_lines": 3})
        r = run({"AGENTS.md": "a\nb\nc\nd\n"}, toml)
        self.assertEqual(r.returncode, 1)
        self.assertIn("AGENTS.md:0: R1: file is 4 lines, limit 3", r.stderr)
        self.assertEqual(run({"AGENTS.md": "a\nb\nc\n"}, toml).returncode, 0)  # equal passes

    def test_both_limits_report_both(self):
        toml = limits({"glob": "AGENTS.md", "max_bytes": 5, "max_lines": 1})
        err = run({"AGENTS.md": "aaaa\nbbbb\n"}, toml).stderr
        self.assertIn("file is 10 bytes, limit 5", err)
        self.assertIn("file is 2 lines, limit 1", err)

    def test_excluded_blocks_apply_before_both_measures(self):
        toml = limits({"glob": "AGENTS.md", "max_bytes": 10, "max_lines": 2}) + (
            '[[rules.R1.excluded_blocks]]\nbegin = "<!-- B -->"\nend = "<!-- E -->"\n'
        )
        text = "a\n<!-- B -->\n" + "zzzz\n" * 30 + "<!-- E -->\nb\n"
        self.assertEqual(run({"AGENTS.md": text}, toml).returncode, 0)

    def test_no_matching_entry_means_no_size_limit(self):
        toml = limits({"glob": "other/AGENTS.md", "max_bytes": 5, "max_lines": 1})
        self.assertEqual(run({"AGENTS.md": "x\n" * 5000}, toml).returncode, 0)

    def test_empty_limits_means_no_size_limit(self):
        self.assertEqual(run({"AGENTS.md": "x\n" * 5000}, "[rules.R1]\nlimits = []\n").returncode, 0)

    def test_old_max_bytes_key_fails_with_migration_hint(self):
        r = run({"AGENTS.md": "ok\n"}, "[rules.R1.max_bytes]\nroot = 100\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("rules.R1.max_bytes", r.stderr)
        self.assertIn("[[rules.R1.limits]]", r.stderr)
        self.assertIn("CHANGELOG", r.stderr)

    def test_entry_validation(self):
        for bad in (
            '[[rules.R1.limits]]\nglob = "AGENTS.md"\n',                       # no limit at all
            '[[rules.R1.limits]]\nmax_bytes = 5\n',                            # no glob
            '[[rules.R1.limits]]\nglob = "A"\nmax_bytes = 5\nmax_line = 3\n',  # typo
            '[[rules.R1.limits]]\nglob = "A"\nmax_lines = 0\n',                # not positive
        ):
            self.assertEqual(run({"AGENTS.md": "ok\n"}, bad).returncode, 2, bad)

    def test_preset_values(self):
        entries = _preset_limits()
        self.assertEqual(
            entries,
            [
                {"glob": "**/AGENTS.md", "max_bytes": 32768, "max_lines": 200, "lines_level": "warn"},
                {"glob": "**/CLAUDE.md", "max_lines": 200, "lines_level": "warn"},
            ],
        )

    def test_default_preset_covers_every_discovered_file(self):
        files = {"AGENTS.md": "x\n" * 201, "CLAUDE.md": "x\n" * 201, "sub/CLAUDE.md": "x\n" * 201, "a/b/AGENTS.md": "x\n" * 201}
        r = helpers.run_new(helpers.make_repo(files))
        self.assertEqual((r.returncode, r.stderr), (0, ""))  # 200 lines is guidance, not a hard limit: warn
        for p in files:
            self.assertIn(f"{p}:0: R1: file is 201 lines, limit 200", r.stdout)


class LimitLevelsTest(unittest.TestCase):
    """`bytes_level` / `lines_level` per limits entry, capped by the rule level; optional `max_line_chars`."""

    def test_lines_level_warn_reports_on_stdout_and_exits_0(self):
        toml = limits({"glob": "AGENTS.md", "max_lines": 2, "lines_level": "warn"})
        r = run({"AGENTS.md": "a\nb\nc\n"}, toml)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("AGENTS.md:0: R1: file is 3 lines, limit 2", r.stdout)

    def test_levels_are_per_measure(self):
        toml = limits({"glob": "AGENTS.md", "max_bytes": 5, "max_lines": 1, "lines_level": "warn"})
        r = run({"AGENTS.md": "aaaa\nbbbb\n"}, toml)
        self.assertEqual(r.returncode, 1)
        self.assertIn("file is 10 bytes, limit 5", r.stderr)
        self.assertIn("file is 2 lines, limit 1", r.stdout)
        self.assertNotIn("lines", r.stderr)

    def test_bytes_level_warn(self):
        toml = limits({"glob": "AGENTS.md", "max_bytes": 5, "bytes_level": "warn"})
        r = run({"AGENTS.md": "aaaa\nbbbb\n"}, toml)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("file is 10 bytes, limit 5", r.stdout)

    def test_off_skips_that_measure(self):
        toml = limits({"glob": "AGENTS.md", "max_bytes": 5, "max_lines": 1, "bytes_level": "off", "lines_level": "off"})
        r = run({"AGENTS.md": "aaaa\nbbbb\n"}, toml)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_entry_level_never_exceeds_rule_level(self):
        toml = "[rules.R1]\nlevel = 'warn'\n" + limits({"glob": "AGENTS.md", "max_bytes": 5, "bytes_level": "error"})
        r = run({"AGENTS.md": "aaaa\nbbbb\n"}, toml)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("file is 10 bytes, limit 5", r.stdout)

    def test_omitted_entry_level_follows_rule_level(self):
        toml = limits({"glob": "AGENTS.md", "max_lines": 1})
        self.assertIn("file is 2 lines, limit 1", run({"AGENTS.md": "a\nb\n"}, toml).stderr)

    def test_bad_entry_level_fails(self):
        for key in ("bytes_level", "lines_level"):
            r = run({"AGENTS.md": "ok\n"}, limits({"glob": "AGENTS.md", "max_bytes": 5, key: "fatal"}))
            self.assertEqual(r.returncode, 2, key)
            self.assertIn(f"rules.R1.limits[0].{key}", r.stderr)

    def test_omitted_max_line_chars_checks_no_line_length(self):
        r = run({"AGENTS.md": "y" * 5000 + "\n"}, "")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_max_line_chars_still_works_when_set(self):
        r = run({"AGENTS.md": "y" * 600 + "\n"}, "[rules.R1]\nmax_line_chars = 500\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("AGENTS.md:1: R1: line is 600 characters, limit 500", r.stderr)


class DefaultLimitsTest(unittest.TestCase):
    """The default preset uses only limits with an external source (Codex 32 KiB, Claude Code 200 lines)."""

    def test_agents_md_over_32_kib_is_an_error_at_any_depth(self):
        big = "x" * 99 + "\n"
        for path in ("AGENTS.md", "a/b/AGENTS.md"):
            r = helpers.run_new(helpers.make_repo({path: big * 328}))  # 32800 bytes
            self.assertEqual(r.returncode, 1, path)
            self.assertIn(f"{path}:0: R1: file is 32800 bytes, limit 32768", r.stderr)
        self.assertEqual(helpers.run_new(helpers.make_repo({"AGENTS.md": "x" * 32767 + "\n"})).returncode, 0)

    def test_claude_md_has_no_byte_limit(self):
        r = helpers.run_new(helpers.make_repo({"CLAUDE.md": ("x" * 99 + "\n") * 199 + "y" * 40000 + "\n"}))
        self.assertEqual(r.returncode, 0)
        self.assertNotIn(": R1:", r.stdout + r.stderr)  # neither a byte limit nor a line-length limit


def _preset_limits():
    from importlib import resources
    import tomllib
    text = (resources.files("agentfile_lint") / "presets" / "default.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)["rules"]["R1"]["limits"]


if __name__ == "__main__":
    unittest.main()
