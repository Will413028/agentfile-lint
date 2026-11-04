import datetime
import unittest

import helpers
from agentfile_lint import allowlist, config
from agentfile_lint.errors import ConfigError

TODAY = "2026-06-01"
BIG = "x" * 600 + "\n"  # one line over the 500-char limit (R1_LINE) -> an R1d finding on line 1
R1_LINE = "[rules.R1d]\nlevel = \"error\"\nmax_chars = 500\n"  # the default checks no line length


def entry(path="AGENTS.md", expires="2026-06-30", rule="R1d", reason="cleanup tracked elsewhere"):
    return f'[[allowlist.entries]]\nrule = "{rule}"\npath = "{path}"\nreason = "{reason}"\nexpires = {expires}\n'


def run(files, toml, *extra):
    root = helpers.make_repo({**files, ".agentfile-lint.toml": R1_LINE + toml})
    return helpers.run_new(root, "--today", TODAY, *extra)


class AllowlistTest(unittest.TestCase):
    def test_live_entry_suppresses_violation(self):
        r = run({"AGENTS.md": BIG}, entry(expires="2026-08-01"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")

    def test_expired_entry_fails_and_does_not_suppress(self):
        r = run({"AGENTS.md": BIG}, entry(expires="2026-05-31"))  # yesterday
        self.assertEqual(r.returncode, 1)
        self.assertIn("AGENTS.md: error: allowlist: entry for R1d expired on 2026-05-31", r.stdout)
        self.assertIn("AGENTS.md:1: error: R1d: line is 600 characters, limit 500", r.stdout)

    def test_entry_expiring_today_is_still_live(self):
        r = run({"AGENTS.md": BIG}, entry(expires="2026-06-01"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("expires in 0 days", r.stdout)

    def test_unneeded_entry_fails_when_file_is_clean(self):
        r = run({"AGENTS.md": "fine\n"}, entry(expires="2026-08-01"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("AGENTS.md: error: allowlist: entry for R1d is no longer needed", r.stdout)

    def test_unneeded_entry_fails_when_file_is_missing(self):
        r = run({"AGENTS.md": "fine\n"}, entry(path="gone/AGENTS.md", expires="2026-08-01"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("gone/AGENTS.md: error: allowlist: entry for R1d is no longer needed", r.stdout)

    def test_expiry_beyond_max_days_is_a_config_failure(self):
        r = run({"AGENTS.md": BIG}, entry(expires="2026-09-30"))  # 121 days
        self.assertEqual(r.returncode, 2)
        self.assertIn("more than 90 days", r.stderr)

    def test_max_days_is_configurable(self):
        toml = "[allowlist]\nmax_days = 200\n" + entry(expires="2026-09-30")
        r = run({"AGENTS.md": BIG}, toml)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_more_than_ten_entries_is_a_config_failure(self):
        toml = "".join(entry(path=f"d{i}/AGENTS.md", expires="2026-08-01") for i in range(11))
        r = run({"AGENTS.md": "fine\n"}, toml)
        self.assertEqual(r.returncode, 2)
        self.assertIn("11 entries exceed the limit of 10", r.stderr)

    def test_ten_entries_are_accepted_by_the_config(self):
        toml = "".join(entry(path=f"d{i}/AGENTS.md", expires="2026-08-01") for i in range(10))
        r = run({"AGENTS.md": "fine\n"}, toml)
        self.assertEqual(r.returncode, 1)  # unneeded entries, but the config itself loaded
        self.assertNotIn("exceed the limit", r.stderr)

    def test_warns_within_14_days_of_expiry(self):
        r = run({"AGENTS.md": BIG}, entry(expires="2026-06-15"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("AGENTS.md: warning: allowlist: entry for R1d expires in 14 days", r.stdout)

    def test_no_warning_at_15_days(self):
        r = run({"AGENTS.md": BIG}, entry(expires="2026-06-16"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")

    def test_warn_as_error_promotes_the_expiry_warning(self):
        r = run({"AGENTS.md": BIG}, entry(expires="2026-06-15"), "--warn-as-error")
        self.assertEqual(r.returncode, 1)

    def test_missing_reason_is_a_config_failure(self):
        toml = '[[allowlist.entries]]\nrule = "R1d"\npath = "AGENTS.md"\nexpires = 2026-06-30\n'
        r = run({"AGENTS.md": BIG}, toml)
        self.assertEqual(r.returncode, 2)
        self.assertIn("missing key reason", r.stderr)

    def test_unknown_rule_in_entry_is_a_config_failure(self):
        r = run({"AGENTS.md": BIG}, entry(rule="R99"))
        self.assertEqual(r.returncode, 2)

    def test_apply_unit(self):
        s = allowlist.Settings(90, 10, 14)
        today = datetime.date(2026, 6, 1)
        e = allowlist.Entry("R1d", "a/AGENTS.md", "why", datetime.date(2026, 5, 31))
        out = allowlist.apply([], [e], s, {"a/AGENTS.md"}, today)
        self.assertEqual([f.rule for f in out], ["allowlist"])


class ParseTest(unittest.TestCase):
    def test_parse_rejects_non_list(self):
        with self.assertRaises(ConfigError):
            allowlist.parse({}, allowlist.Settings(90, 10, 14), {"R1d"}, datetime.date(2026, 6, 1))


if __name__ == "__main__":
    unittest.main()
