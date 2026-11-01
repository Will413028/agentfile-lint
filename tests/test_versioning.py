"""Version process: every rule not listed as graduated in the CHANGELOG starts at warn."""
import re
import tomllib
import unittest

import helpers

CHANGELOG = (helpers.REPO / "CHANGELOG.md").read_text(encoding="utf-8")
PRESET = tomllib.loads((helpers.REPO / "agentfile_lint" / "presets" / "default.toml").read_text(encoding="utf-8"))


def graduated(text):
    """Rule ids named as bullets under any `### Graduated` heading, e.g. "- `R1`: reason"."""
    ids, inside = set(), False
    for line in text.splitlines():
        if line.startswith("#"):
            inside = line.strip() == "### Graduated"
        elif inside:
            m = re.match(r"- `([A-Za-z0-9]+)`", line)
            if m:
                ids.add(m.group(1))
    return ids


class VersioningTest(unittest.TestCase):
    def test_rules_not_graduated_start_at_warn(self):
        grad = graduated(CHANGELOG)
        for rule_id, params in PRESET["rules"].items():
            if rule_id not in grad:
                self.assertEqual(params["level"], "warn", f"{rule_id} is not listed under Graduated in CHANGELOG.md")

    def test_graduated_rules_exist_in_the_preset(self):
        self.assertTrue(graduated(CHANGELOG) <= set(PRESET["rules"]))

    def test_the_lint_itself_detects_a_violation(self):
        text = "## [1.0.0]\n\n### Graduated\n\n- `R1`: shipped at error\n\n### Added\n\n- `R2` something\n"
        self.assertEqual(graduated(text), {"R1"})

    def test_version_strings_and_changelog_agree(self):
        version_line = (helpers.REPO / "agentfile_lint" / "__init__.py").read_text(encoding="utf-8")
        __version__ = re.search(r'__version__ = "([^"]+)"', version_line).group(1)
        pyproject = tomllib.loads((helpers.REPO / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["version"], __version__)
        released = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", CHANGELOG, re.MULTILINE)
        self.assertEqual(released[0], __version__, "newest CHANGELOG section must be the current version")


if __name__ == "__main__":
    unittest.main()
