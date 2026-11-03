"""Rule registry. Each rule module exposes ID, NAME, DESCRIPTION, validate() and check() and/or check_repo().

`check(path, text, params)` sees one file; `check_repo(ctx, params)` sees the whole tracked set.
Rules read parameters only; repo-specific behaviour is configuration, never a branch in code.
"""
from __future__ import annotations

from . import claude_md, constants, duplicate, paths, rot, shape, size, specrefs, testnames

RULES = {rule.ID: rule for rule in (size, shape, testnames, paths, specrefs, rot, duplicate, constants, claude_md)}

# Each rule's NAME is an alias for its ID in config files (docs/adr/0004).
ALIASES = {rule.NAME: rule_id for rule_id, rule in RULES.items()}
if len(ALIASES) != len(RULES) or set(ALIASES) & set(RULES):
    raise RuntimeError("rule NAMEs must be unique and must not equal a rule ID")
