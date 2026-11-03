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
                {"glob": "**/AGENTS.md", "max_lines": 200, "lines_level": "warn"},
                {"glob": "**/CLAUDE.md", "max_lines": 200, "lines_level": "warn"},
            ],
        )

    def test_preset_path_limits(self):
        self.assertEqual(_preset_r1()["path_limits"], [{"glob": "**/AGENTS.md", "max_bytes": 32768}])

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


def kb(n):
    """A file of exactly n bytes, in 100-byte lines."""
    return ("x" * 99 + "\n") * (n // 100) + "y" * (n % 100)


PATH_32K = '[[rules.R1.path_limits]]\nglob = "**/AGENTS.md"\nmax_bytes = 32768\n'


class PathLimitsTest(unittest.TestCase):
    """`path_limits`: a file plus the files matching the same glob in its ancestor directories (Codex
    reads AGENTS.md from the root down to the working directory and stops at 32 KiB in total)."""

    def run_files(self, files, toml=PATH_32K):
        return run(files, "[rules.R1]\nlimits = []\n" + toml)

    def test_combined_overflow_is_reported_where_it_starts(self):
        r = self.run_files({"AGENTS.md": kb(20000), "a/AGENTS.md": kb(10000), "a/b/AGENTS.md": kb(5000), "a/b/c/AGENTS.md": kb(10)})
        self.assertEqual(r.returncode, 1)
        self.assertEqual([x for x in r.stderr.splitlines() if ": R1: " in x],
                         ["a/b/AGENTS.md:0: R1: file and its ancestors (AGENTS.md, a/AGENTS.md) total 35000 bytes, limit 32768"])

    def test_under_the_combined_limit_passes(self):
        r = self.run_files({"AGENTS.md": kb(20000), "a/AGENTS.md": kb(12768), "b/AGENTS.md": kb(12768)})
        self.assertEqual((r.returncode, r.stderr), (0, ""))  # siblings are separate paths; equal passes

    def test_a_single_file_over_the_limit(self):
        r = self.run_files({"AGENTS.md": kb(40000), "a/AGENTS.md": kb(10)})
        self.assertEqual([x for x in r.stderr.splitlines() if ": R1: " in x],
                         ["AGENTS.md:0: R1: file is 40000 bytes, limit 32768"])

    def test_only_files_matching_the_glob_count(self):
        r = self.run_files({"AGENTS.md": kb(20000), "a/CLAUDE.md": kb(20000), "a/AGENTS.md": kb(100)})
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_level_and_empty_list(self):
        files = {"AGENTS.md": kb(20000), "a/AGENTS.md": kb(20000)}
        r = self.run_files(files, PATH_32K + 'level = "warn"\n')
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("a/AGENTS.md:0: R1: file and its ancestors (AGENTS.md) total 40000 bytes, limit 32768", r.stdout)
        self.assertEqual(run(files, "[rules.R1]\nlimits = []\npath_limits = []\n").returncode, 0)

    def test_combined_size_counts_raw_bytes(self):
        # Codex counts the file as stored: neither excluded_blocks nor CRLF -> LF lower the total.
        block = '[[rules.R1.excluded_blocks]]\nbegin = "<!-- B -->"\nend = "<!-- E -->"\n'
        files = {"AGENTS.md": "<!-- B -->\n" + kb(20000) + "<!-- E -->\n", "a/AGENTS.md": kb(13000)}
        r = self.run_files(files, PATH_32K + block)
        self.assertIn("a/AGENTS.md:0: R1: file and its ancestors (AGENTS.md) total 33022 bytes, limit 32768", r.stderr)
        crlf = {"AGENTS.md": ("x" * 98 + "\r\n") * 200, "a/AGENTS.md": ("y" * 98 + "\r\n") * 128}
        r = self.run_files(crlf)
        self.assertIn("a/AGENTS.md:0: R1: file and its ancestors (AGENTS.md) total 32800 bytes, limit 32768", r.stderr)

    def test_entry_validation(self):
        for bad in (
            '[[rules.R1.path_limits]]\nglob = "**/AGENTS.md"\n',                          # no max_bytes
            '[[rules.R1.path_limits]]\nmax_bytes = 5\n',                                  # no glob
            '[[rules.R1.path_limits]]\nglob = "A"\nmax_bytes = 5\nmax_lines = 3\n',      # unknown key
            '[[rules.R1.path_limits]]\nglob = "A"\nmax_bytes = 5\nlevel = "fatal"\n',    # bad level
        ):
            self.assertEqual(run({"AGENTS.md": "ok\n"}, bad).returncode, 2, bad)

    def test_default_checks_the_combined_size(self):
        r = helpers.run_new(helpers.make_repo({"AGENTS.md": kb(20000), "pkg/AGENTS.md": kb(15000)}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("pkg/AGENTS.md:0: R1: file and its ancestors (AGENTS.md) total 35000 bytes, limit 32768", r.stderr)


def _preset_r1():
    from importlib import resources
    import tomllib
    text = (resources.files("agentfile_lint") / "presets" / "default.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)["rules"]["R1"]


def _preset_limits():
    return _preset_r1()["limits"]


if __name__ == "__main__":
    unittest.main()
