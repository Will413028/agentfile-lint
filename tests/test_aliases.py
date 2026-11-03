"""Rule aliases: a rule's NAME is accepted wherever a rule id is, resolved per file before merging."""
import json
import re
import unittest

import helpers
from agentfile_lint.rules import RULES


def config_json(toml, *files):
    root = helpers.make_repo({"AGENTS.md": "ok\n", ".agentfile-lint.toml": toml, **dict(files)})
    return helpers.run_new(root, "config", "--today", "2026-06-01")


ENTRY = "[[allowlist.entries]]\nrule = '{rule}'\npath = 'AGENTS.md'\nreason = 'r'\nexpires = 2026-07-01\n"


class AliasTest(unittest.TestCase):
    def test_alias_and_id_give_the_same_effective_config(self):
        by_id = config_json("[rules.R1]\nlevel = 'warn'\n" + ENTRY.format(rule="R5"))
        by_alias = config_json("[rules.size]\nlevel = 'warn'\n" + ENTRY.format(rule="duplicates"))
        self.assertEqual((by_id.returncode, by_alias.returncode), (0, 0), by_alias.stderr)
        self.assertEqual(json.loads(by_alias.stdout), json.loads(by_id.stdout))
        self.assertEqual(json.loads(by_alias.stdout)["rules"]["R1"]["level"], "warn")

    def test_every_rule_alias_is_accepted(self):
        for rule_id, module in RULES.items():
            r = config_json(f"[rules.{module.NAME}]\nlevel = 'off'\n")
            self.assertEqual(r.returncode, 0, (module.NAME, r.stderr))
            self.assertEqual(json.loads(r.stdout)["rules"][rule_id]["level"], "off")

    def test_repo_alias_overrides_preset_id(self):
        # The preset writes [rules.R1]; the repo's [rules.size] must win, not conflict.
        root = helpers.make_repo({
            "AGENTS.md": "x\n" * 60,
            ".agentfile-lint.toml": '[[rules.size.limits]]\nglob = "AGENTS.md"\nmax_bytes = 100\n[rules.size]\nlevel = "off"\n',
        })
        r = helpers.run_new(root)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_alias_across_extends_is_not_a_conflict(self):
        r = config_json("extends = ['base.toml']\n[rules.size]\nlevel = 'off'\n",
                        ("base.toml", "[rules.R1]\nlevel = 'warn'\n"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["rules"]["R1"]["level"], "off")

    def test_id_and_alias_in_one_file_fail(self):
        r = config_json("[rules.R1]\nlevel = 'warn'\n[rules.size]\nlevel = 'off'\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("R1", r.stderr)
        self.assertIn("size", r.stderr)

    def test_allowlist_id_and_alias_for_same_path_fail(self):
        r = config_json(ENTRY.format(rule="R1") + ENTRY.format(rule="size"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("duplicate entry for R1 AGENTS.md", r.stderr)

    def test_alias_before_id_names_both_keys(self):
        r = config_json("[rules.size]\nlevel = 'warn'\n[rules.R1]\nlevel = 'off'\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("rules.size and rules.R1", r.stderr)

    def test_non_string_allowlist_rule_is_a_config_error(self):
        r = config_json("[[allowlist.entries]]\nrule = ['size']\npath = 'AGENTS.md'\nreason = 'r'\nexpires = 2026-07-01\n")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_unknown_key_hint_lists_aliases(self):
        r = config_json("[rules.siz]\nlevel = 'off'\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("size", r.stderr)

    def test_unknown_alias_still_fails(self):
        self.assertEqual(config_json("[rules.sizes]\nlevel = 'off'\n").returncode, 2)
        self.assertEqual(config_json(ENTRY.format(rule="sizes")).returncode, 2)

    def test_list_rules_prints_id_and_alias(self):
        root = helpers.make_repo({"AGENTS.md": "ok\n"})
        r = helpers.run_new(root, "--list-rules")
        self.assertEqual(r.returncode, 0)
        for rule_id, module in RULES.items():
            self.assertRegex(r.stdout, rf"(?m)^{rule_id}  \w+ +{re.escape(module.NAME)}:")

    def test_aliases_are_unique_and_distinct_from_ids(self):
        names = [m.NAME for m in RULES.values()]
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(set(names) & set(RULES))

    def test_rules_doc_lists_every_alias(self):
        doc = (helpers.REPO / "docs" / "rules.md").read_text(encoding="utf-8")
        for rule_id, module in RULES.items():
            self.assertRegex(doc, rf"(?m)^\| \[{rule_id}\]\([^)]+\) \| `{re.escape(module.NAME)}` \|")


if __name__ == "__main__":
    unittest.main()
