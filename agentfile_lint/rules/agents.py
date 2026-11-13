"""A1 to A5: Claude Code subagent files (`.claude/agents/**/*.md`).

A subagent file that Claude Code cannot read is not an error anywhere: the subagent is simply not in
the list Claude chooses from. Each id is one way that happens (measured with Claude Code 2.1.323,
docs/rules.md "A1 to A5 subagent files"):

- A1: the frontmatter does not parse, even after Claude Code's second attempt.
- A2: the file has no frontmatter.
- A3: `name` is missing, not a non-empty string, or one Claude Code refuses (it starts with `-`, has
  a `:`, or is longer than 256 characters; documented, not measured here).
- A4: `description` is missing or not a non-empty string.
- A5: another subagent file in the same `agents` directory has the same `name`; only one is loaded.

Runs on the agents file family (`[discover] agents_globs`). The frontmatter is read as Claude Code
reads it (`frontmatter.parse_as_claude_code`): a `description` with a colon in it is quoted on the second
attempt and is fine. Upper case and spaces in `name` are fine too.
"""
from __future__ import annotations

import posixpath
from typing import Any

from ..context import Context
from ..discover import matches
from ..errors import check_keys, expect_str_list, levels_only, require_keys
from ..finding import Finding
from ..frontmatter import is_string, parse_as_claude_code

FAMILY = "agents"

CHECKS = (
    ("A1", "agent-yaml", "a subagent file's frontmatter is valid YAML and a mapping"),
    ("A2", "agent-frontmatter", "a subagent file starts with YAML frontmatter"),
    ("A3", "agent-name", "a subagent file has a name"),
    ("A4", "agent-description", "a subagent file has a description"),
    ("A5", "agent-duplicate-name", "no two subagent files in one agents directory have the same name"),
)
WHOLE_FILE = ("A2",)   # the other ids are on frontmatter lines; A ids take no directive anyway

NOT_LOADED = "Claude Code does not load the subagent"
MAX_NAME = 256


def validate(shared: Any, tables: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    a2 = tables["A2"]
    check_keys(a2, {"level", "ignore"}, "rules.A2")
    require_keys(a2, ["ignore"], "rules.A2")
    ignore = expect_str_list(a2["ignore"], "rules.A2.ignore", allow_empty=True)
    effective = levels_only({rule_id: table for rule_id, table in tables.items() if rule_id != "A2"})
    effective["A2"] = {"ignore": ignore}
    return {"ignore": ignore}, effective


def agents_dir(path: str) -> str:
    """The `agents` directory a file belongs to: the one inside `.claude` when the path has one (Claude
    Code reads its subdirectories too), else the file's own directory."""
    parts = path.split("/")
    for i in range(len(parts) - 2):
        if parts[i] == ".claude" and parts[i + 1] == "agents":
            return "/".join(parts[:i + 2])
    return posixpath.dirname(path)


def check_repo(ctx: Context, params: dict[str, Any], levels: dict[str, str]) -> list[Finding]:
    found: list[Finding] = []
    names: dict[tuple[str, str], str] = {}   # (agents directory, name) -> the first file that has it
    for path, text in sorted(ctx.family_files.get(FAMILY, {}).items()):
        fm = parse_as_claude_code(text)
        if fm is None:
            if not matches(path, params["ignore"]):
                found.append(Finding(path, 0, "A2", f"no YAML frontmatter with `name` and `description`; {NOT_LOADED}"))
            continue
        if fm.error is not None:
            found.append(Finding(path, fm.line, "A1", f"{fm.error}; {NOT_LOADED}"))
            continue
        data = {} if fm.value is None else fm.value
        if not isinstance(data, dict):
            found.append(Finding(path, 1, "A1", f"frontmatter is a YAML {type(data).__name__}, not a mapping; {NOT_LOADED}"))
            continue
        usable = {}
        for key, rule in (("name", "A3"), ("description", "A4")):
            value = data.get(key)
            usable[key] = isinstance(value, str) and bool(value.strip()) and is_string(value, fm.plain.get(key, False))
            if not usable[key]:
                what = "missing" if key not in data else "not a non-empty string"
                found.append(Finding(path, fm.keys.get(key, 1), rule, f"`{key}` is {what}; {NOT_LOADED}"))
        name = data["name"].strip() if usable["name"] else ""
        refused = ("starts with `-`" if name.startswith("-") else "contains `:`" if ":" in name
                   else f"is {len(name)} characters, over {MAX_NAME}" if len(name) > MAX_NAME else None)
        if refused:
            usable["name"] = False
            found.append(Finding(path, fm.keys.get("name", 1), "A3", f"`name` {refused}; {NOT_LOADED}"))
        if all(usable.values()):
            key = (agents_dir(path), data["name"].strip())
            first = names.setdefault(key, path)
            if first != path:
                found.append(Finding(path, fm.keys.get("name", 1), "A5", f"name {key[1]!r} is also the name of {first}; "
                                     "Claude Code loads only one of them"))
    return found
