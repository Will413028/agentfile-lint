"""Overrides: permanent path scopes that lower a rule's level (docs/adr/0004, decision 3).

An override only lowers: for one file and one rule, the lowest of the rule level and every matching
override applies, so entry order does not matter. Each glob of the config file the run loads
directly must match an analyzed instruction file; a glob that matches none is a warning.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from . import discover
from .allowlist import RULE_ID
from .errors import ConfigError, check_keys, expect_str, expect_str_list, require_keys
from .finding import Finding

LOWER = ("warn", "off")  # an override may not raise a level
_RANK = {"error": 2, "warn": 1, "off": 0}


@dataclass(frozen=True)
class Override:
    paths: tuple[str, ...]
    rules: tuple[tuple[str, str], ...]  # (rule id, warn | off)
    reason: str
    source: str  # the config file (or preset) the entry is written in
    index: int  # its position in that file
    direct: bool  # written in the config file the run loads directly; only those are checked for staleness


def parse(raw: Any, known_rules: set[str]) -> list[Override]:
    """`raw` is a list of (entry table, source, index in source, direct), aliases already resolved."""
    out: list[Override] = []
    seen: set[tuple[str, int]] = set()
    for item, source, index, direct in raw:
        if (source, index) in seen:  # a file reached twice through `extends` (a diamond) counts once
            continue
        seen.add((source, index))
        where = f"{source}: overrides[{index}]"
        check_keys(item, {"paths", "rules", "reason"}, where)
        require_keys(item, ("paths", "rules", "reason"), where)
        paths = expect_str_list(item["paths"], f"{where}.paths")
        rules = item["rules"]
        if not isinstance(rules, dict) or not rules:
            raise ConfigError(f"{where}.rules: expected a table of rule = \"warn\" | \"off\"")
        for rule, level in rules.items():
            if rule not in known_rules:
                raise ConfigError(f"{where}.rules: unknown rule {rule!r} (only rules with a [rules] table)")
            if level not in LOWER:
                raise ConfigError(f"{where}.rules.{rule}: expected \"warn\" or \"off\" (an override only lowers)")
        reason = expect_str(item["reason"], f"{where}.reason")
        out.append(Override(tuple(paths), tuple(rules.items()), reason, source, index, direct))
    return out


def apply(findings: list[Finding], overrides: list[Override]) -> list[Finding]:
    """Lower or drop the findings on files an override matches. Rules not in an override pass through."""
    if not overrides:
        return findings
    out: list[Finding] = []
    for f in findings:
        level = f.level
        for o in overrides:
            lowered = dict(o.rules).get(f.rule)
            if lowered is not None and _RANK[lowered] < _RANK[level] and discover.matches(f.path, list(o.paths)):
                level = lowered
        if level != "off":
            out.append(f if level == f.level else replace(f, level=level))
    return out


def stale(overrides: list[Override], present: set[str], root: Path) -> list[Finding]:
    """A warning for each glob of a directly loaded entry that matches no analyzed instruction file."""
    out: list[Finding] = []
    for o in overrides:
        if not o.direct:
            continue
        for glob in o.paths:
            if not any(discover.matches(p, [glob]) for p in present):
                out.append(Finding(
                    _display(o.source, root), 0, RULE_ID,
                    f"overrides[{o.index}]: glob {glob!r} matches no analyzed instruction file; remove it",
                    level="warn",
                ))
    return out


def _display(source: str, root: Path) -> str:
    """Repo-relative inside the repo; as given on the command line outside it."""
    try:
        return Path(source).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return source
