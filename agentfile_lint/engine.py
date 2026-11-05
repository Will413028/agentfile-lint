"""Run the enabled rules over the full instruction-file set."""
from __future__ import annotations

import datetime
from dataclasses import replace
from pathlib import Path

from . import allowlist, discover, overrides
from .config import Config
from .context import Context
from .finding import INPUT_RULE, Finding
from .rules import MODULES


def _level(rule_level: str, finding: Finding) -> str:
    """The rule level caps a finding: a rule at `warn` never produces an error. R6 emits warnings only."""
    return "warn" if rule_level == "warn" or finding.level == "warn" else "error"


def analyze(root: Path, config: Config, today: datetime.date, warn_as_error: bool = False) -> list[Finding]:
    paths = discover.instruction_files(root, config.globs)
    alias = discover.aliases(root, paths)
    paths = [p for p in paths if p not in alias]
    findings: list[Finding] = []
    raw: dict[str, str] = {}
    for path in paths:
        try:
            raw[path] = (root / path).read_bytes().decode("utf-8")  # read once, as stored (docs/design.md, R1a to R1d)
        except UnicodeDecodeError:
            findings.append(Finding(path, 0, INPUT_RULE, "file is not valid UTF-8"))
    ctx = Context(root, discover.tracked_files(root), raw)
    for module in MODULES:
        levels = {rule_id: config.rules[rule_id]["level"] for rule_id, _, _ in module.CHECKS}
        if all(level == "off" for level in levels.values()):
            continue
        params = config.params[module.__name__]
        found: list[Finding] = []
        if hasattr(module, "check"):
            for path, text in ctx.files.items():
                found.extend(module.check(path, text, params, levels))
        if hasattr(module, "check_repo"):
            found.extend(module.check_repo(ctx, params, levels))
        findings.extend(replace(f, level=_level(levels[f.rule], f)) for f in found if levels[f.rule] != "off")
    # Overrides before the allowlist: an entry for a path an override silences is no longer needed.
    findings = overrides.apply(findings, config.overrides)
    findings = allowlist.apply(findings, config.entries, config.allowlist, set(paths), today)
    findings += overrides.stale(config.overrides, set(paths), root)
    if warn_as_error:
        findings = [replace(f, level="error") for f in findings]
    return sorted(findings, key=Finding.sort_key)
