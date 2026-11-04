"""`[[overrides]]`: permanent path scopes that only lower rule levels (docs/adr/0004, decision 3)."""
import json
import tomllib
import unittest
from importlib import resources

import helpers

# A translated copy under docs/<lang>/ duplicates the root file: R5b (sibling-duplicates) reports it under preset:strict.
BODY = "# Package\n\n" + "".join(f"- rule number {i}: run the full test suite before every commit\n" for i in range(3))
# Siblings (neither is an ancestor of the other): preset:strict compares them.
TRANSLATED = {"AGENTS.md": "ok\n", "pkg/AGENTS.md": BODY, "docs/zh/AGENTS.md": BODY}
STRICT = 'extends = ["preset:strict"]\n'
OFF_DOCS = '[[overrides]]\npaths = ["docs/**"]\nrules = {{ {rules} }}\nreason = "translations"\n'


def run(files, *args):
    return helpers.run_new(helpers.make_repo(files), "--today", "2026-06-01", *args)


def config_json(toml):
    root = helpers.make_repo({"AGENTS.md": "ok\n", ".agentfile-lint.toml": toml})
    return helpers.run_new(root, "config", "--today", "2026-06-01")


def r5(lines):
    return [line for line in lines if ": R5b: " in line]


class ScopeTest(unittest.TestCase):
    def test_baseline_reports_the_copy(self):
        r = run({**TRANSLATED, ".agentfile-lint.toml": STRICT})
        warnings, errors = helpers.by_severity(r)
        self.assertTrue(any(line.startswith("docs/zh/AGENTS.md") for line in r5(warnings + errors)), r.stdout)

    def test_off_silences_the_path_and_keeps_the_original(self):
        r = run({**TRANSLATED, ".agentfile-lint.toml": STRICT + OFF_DOCS.format(rules='sibling-duplicates = "off"')})
        warnings, errors = helpers.by_severity(r)
        found = r5(warnings + errors)
        self.assertFalse([line for line in found if line.startswith("docs/")], r.stdout)
        # Strict sibling comparison: the original outside docs/** is still reported (D11 scope).
        self.assertTrue([line for line in found if line.startswith("pkg/AGENTS.md")], r.stdout)

    def test_warn_lowers_an_error(self):
        files = {"AGENTS.md": "x\n" * 300, "docs/AGENTS.md": "x\n" * 300}
        rule = '[rules.R1b]\nlevel = "error"\n[[rules.R1b.limits]]\nglob = "**/AGENTS.md"\nmax_lines = 200\n'
        toml = rule + OFF_DOCS.format(rules='R1b = "warn"')
        r = run({**files, ".agentfile-lint.toml": toml})
        warnings, errors = helpers.by_severity(r)
        self.assertEqual([e.split(":")[0] for e in errors if ": R1b: " in e], ["AGENTS.md"], r.stdout)
        self.assertEqual([w.split(":")[0] for w in warnings if ": R1b: " in w], ["docs/AGENTS.md"], r.stdout)
        self.assertEqual(r.returncode, 1)

    def test_lowest_level_wins_regardless_of_order(self):
        warn = '[[overrides]]\npaths = ["docs/**"]\nrules = { R5b = "warn" }\nreason = "a"\n'
        off = '[[overrides]]\npaths = ["docs/zh/*"]\nrules = { sibling-duplicates = "off" }\nreason = "b"\n'
        for toml in (STRICT + warn + off, STRICT + off + warn):
            r = run({**TRANSLATED, ".agentfile-lint.toml": toml})
            warnings, errors = helpers.by_severity(r)
            self.assertFalse([line for line in r5(warnings + errors) if line.startswith("docs/")], (toml, r.stdout))

    def test_allowlist_entry_on_an_overridden_path_is_no_longer_needed(self):
        entry = ('[[allowlist.entries]]\nrule = "R5b"\npath = "docs/zh/AGENTS.md"\ncount = 1\nreason = "r"\n'
                 'expires = 2026-07-01\n')
        r = run({**TRANSLATED, ".agentfile-lint.toml": STRICT + OFF_DOCS.format(rules='R5b = "off"') + entry})
        self.assertIn("docs/zh/AGENTS.md: error: allowlist: entry for R5b is no longer needed", r.stdout)
        self.assertEqual(r.returncode, 1)


class ValidationTest(unittest.TestCase):
    def assert_config_error(self, toml, *needles):
        r = config_json(toml)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        for needle in needles:
            self.assertIn(needle, r.stderr)

    def test_error_level_fails(self):
        self.assert_config_error(OFF_DOCS.format(rules='R5b = "error"'), "overrides[0].rules.R5b")

    def test_missing_reason_fails(self):
        self.assert_config_error('[[overrides]]\npaths = ["docs/**"]\nrules = { R5b = "off" }\n', "overrides[0]", "reason")

    def test_unknown_key_fails(self):
        self.assert_config_error(OFF_DOCS.format(rules='R5b = "off"') + 'expires = 2026-07-01\n', "expires")

    def test_unknown_rule_fails(self):
        self.assert_config_error(OFF_DOCS.format(rules='R99 = "off"'), "R99")

    def test_pseudo_rules_cannot_be_overridden(self):
        self.assert_config_error(OFF_DOCS.format(rules='E0 = "off"'), "E0")
        self.assert_config_error(OFF_DOCS.format(rules='allowlist = "off"'), "allowlist")

    def test_empty_paths_or_rules_fail(self):
        self.assert_config_error('[[overrides]]\npaths = []\nrules = { R5b = "off" }\nreason = "r"\n', "paths")
        self.assert_config_error('[[overrides]]\npaths = ["docs/**"]\nrules = {}\nreason = "r"\n', "rules")

    def test_id_and_alias_in_one_entry_fail(self):
        self.assert_config_error(OFF_DOCS.format(rules='R5b = "off", sibling-duplicates = "warn"'), "R5b", "sibling-duplicates")

    def test_alias_resolves_in_effective_config(self):
        r = config_json(OFF_DOCS.format(rules='sibling-duplicates = "off"'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["overrides"],
                         [{"paths": ["docs/**"], "rules": {"R5b": "off"}, "reason": "translations"}])

    def test_shipped_presets_carry_no_overrides(self):
        presets = resources.files("agentfile_lint") / "presets"
        names = [p.name for p in presets.iterdir() if p.name.endswith(".toml")]
        self.assertIn("default.toml", names)
        for name in names:
            self.assertNotIn("overrides", tomllib.loads((presets / name).read_text(encoding="utf-8")), name)


class StaleGlobTest(unittest.TestCase):
    TOML = '[[overrides]]\npaths = ["docs/**", "gone/**"]\nrules = { R5b = "off" }\nreason = "r"\n'

    def test_unmatched_glob_warns(self):
        r = run({**TRANSLATED, ".agentfile-lint.toml": self.TOML})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            r.stdout,
            ".agentfile-lint.toml: warning: allowlist: overrides[0]: glob 'gone/**' matches no analyzed "
            "instruction file; remove it\n",
        )

    def test_warn_as_error_fails(self):
        r = run({**TRANSLATED, ".agentfile-lint.toml": self.TOML}, "--warn-as-error")
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: allowlist: overrides[0]: glob 'gone/**'", r.stdout)

    def test_index_counts_within_the_file(self):
        first = '[[overrides]]\npaths = ["docs/**"]\nrules = { R5b = "off" }\nreason = "r"\n'
        r = run({**TRANSLATED, ".agentfile-lint.toml": first + self.TOML.replace('"docs/**", ', "")})
        self.assertIn("overrides[1]: glob 'gone/**'", r.stdout)

    def test_inherited_entries_are_not_checked(self):
        r = run({**TRANSLATED, ".agentfile-lint.toml": 'extends = ["shared.toml"]\n', "shared.toml": self.TOML})
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_config_outside_repo_is_named_as_given(self):
        outside = helpers.make_repo({"lint.toml": self.TOML})
        r = run(TRANSLATED, "--config", str(outside / "lint.toml"))
        self.assertTrue(r.stdout.startswith(f"{outside / 'lint.toml'}: warning: allowlist: overrides[0]"), r.stdout)

    def test_config_inside_repo_is_repo_relative(self):
        root = helpers.make_repo({**TRANSLATED, "ci/lint.toml": self.TOML})
        r = helpers.run_new(root, "--config", str(root / "ci" / "lint.toml"))
        self.assertTrue(r.stdout.startswith("ci/lint.toml: warning: allowlist: overrides[0]"), r.stdout)


class ExtendsTest(unittest.TestCase):
    def test_overrides_concatenate(self):
        shared = '[[overrides]]\npaths = ["docs/**"]\nrules = { R5b = "off" }\nreason = "shared"\n'
        own = '[[overrides]]\npaths = ["examples/**"]\nrules = { R1b = "warn" }\nreason = "own"\n'
        root = helpers.make_repo({"AGENTS.md": "ok\n", ".agentfile-lint.toml": 'extends = ["s.toml"]\n' + own,
                                  "s.toml": shared})
        r = helpers.run_new(root, "config")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([o["reason"] for o in json.loads(r.stdout)["overrides"]], ["shared", "own"])

    def test_inherited_override_applies(self):
        r = run({**TRANSLATED, ".agentfile-lint.toml": 'extends = ["preset:strict", "s.toml"]\n',
                 "s.toml": 'extends = []\n' + OFF_DOCS.format(rules='R5b = "off"')})
        warnings, errors = helpers.by_severity(r)
        self.assertFalse([line for line in r5(warnings + errors) if line.startswith("docs/")], r.stdout)


class ReviewFixesTest(unittest.TestCase):
    def test_inherited_error_names_its_file(self):
        root = helpers.make_repo({"AGENTS.md": "ok\n", ".agentfile-lint.toml": 'extends = ["shared.toml"]\n',
                                  "shared.toml": '[[overrides]]\npaths = ["docs/**"]\nrules = { R5b = "off" }\n'})
        r = helpers.run_new(root)
        self.assertEqual(r.returncode, 2)
        self.assertIn("shared.toml: overrides[0]: missing key reason", r.stderr)

    def test_diamond_extends_counts_a_shared_override_once(self):
        shared = '[[overrides]]\npaths = ["docs/**"]\nrules = { R5b = "off" }\nreason = "shared"\n'
        root = helpers.make_repo({"AGENTS.md": "ok\n", ".agentfile-lint.toml": 'extends = ["a.toml", "b.toml"]\n',
                                  "a.toml": 'extends = ["s.toml"]\n', "b.toml": 'extends = ["s.toml"]\n', "s.toml": shared})
        r = helpers.run_new(root, "config")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.loads(r.stdout)["overrides"]), 1)


if __name__ == "__main__":
    unittest.main()
