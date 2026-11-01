"""Run the enabled rules over the full instruction-file set."""
from __future__ import annotations

import datetime
from dataclasses import replace
from pathlib import Path

from . import allowlist, discover
from .config import Config
from .context import Context
from .finding import Finding
from .rules import RULES


def _level(rule_level: str, finding: Finding) -> str:
    """The rule level caps a finding: a rule at `warn` never produces an error.

    A rule may emit a finding at `warn` on its own (R4 narrative words, R5 siblings, R6); those stay
    warnings when the rule is at `error`.
    """
    return "warn" if rule_level == "warn" or finding.level == "warn" else "error"


def analyze(root: Path, config: Config, today: datetime.date, warn_as_error: bool = False) -> list[Finding]:
    paths = discover.instruction_files(root, config.globs)
    findings: list[Finding] = []
    texts: dict[str, str] = {}
    for path in paths:
        try:
            texts[path] = (root / path).read_text(encoding="utf-8")  # text mode, like the legacy checker
        except UnicodeDecodeError:
            findings.append(Finding(path, 0, "input", "file is not valid UTF-8"))
    ctx = Context(root, discover.tracked_files(root), texts)
    for rule_id, module in RULES.items():
        params = config.rules[rule_id]
        level = params["level"]
        if level == "off":
            continue
        raw: list[Finding] = []
        if hasattr(module, "check"):
            for path, text in texts.items():
                raw.extend(module.check(path, text, params))
        if hasattr(module, "check_repo"):
            raw.extend(module.check_repo(ctx, params))
        findings.extend(replace(f, level=_level(level, f)) for f in raw)
    findings = allowlist.apply(findings, config.entries, config.allowlist, set(paths), today)
    if warn_as_error:
        findings = [replace(f, level="error") for f in findings]
    return sorted(findings, key=Finding.sort_key)
