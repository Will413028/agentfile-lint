"""R5: identical lines across instruction files.

A line (whitespace-collapsed, list marker removed) of at least `min_chars` characters that appears
in two files is duplicated text. If one file is in an ancestor directory of the other (or in the same
directory), the descendant repeats what is already loaded: reported at the rule's level, on the
descendant's line. Between siblings it is reported at `sibling_level`. Exact matches only; the
whole tracked instruction-file set is always compared, never just the files named on the command line.
"""
from __future__ import annotations

import posixpath
import re
from typing import Any

from ..context import Context
from ..errors import check_keys, expect_bool, expect_int, expect_level, expect_regex_list, require_keys
from ..finding import Finding
from ._text import prose_lines

ID = "R5"
NAME = "duplicates"
DESCRIPTION = "identical lines in ancestor/descendant files (rule level) or sibling files (sibling_level)"

_KEYS = {"level", "sibling_level", "min_chars", "ignore_headings", "ignore_patterns"}
_MARKER = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
_TABLE_RULE = re.compile(r"^\|?[\s:|-]+\|?$")


def validate(params: dict[str, Any]) -> dict[str, Any]:
    where = f"rules.{ID}"
    check_keys(params, _KEYS, where)
    require_keys(params, _KEYS - {"level"}, where)
    return {
        "level": params["level"],
        "sibling_level": expect_level(params["sibling_level"], f"{where}.sibling_level"),
        "min_chars": expect_int(params["min_chars"], f"{where}.min_chars"),
        "ignore_headings": expect_bool(params["ignore_headings"], f"{where}.ignore_headings"),
        "ignore_patterns": expect_regex_list(params["ignore_patterns"], f"{where}.ignore_patterns"),
    }


def _normalize(line: str) -> str:
    return re.sub(r"\s+", " ", _MARKER.sub("", line.strip()))


def _is_ancestor(a: str, b: str) -> bool:
    """File `a` sits in an ancestor directory of `b`, or in the same directory (and sorts first)."""
    da, db = posixpath.dirname(a), posixpath.dirname(b)
    if da == db:
        return a < b
    return da == "" or db.startswith(da + "/")


def check_repo(ctx: Context, params: dict[str, Any]) -> list[Finding]:
    ignore = [re.compile(p) for p in params["ignore_patterns"]]
    groups: dict[str, dict[str, int]] = {}  # normalized line -> {path: first line number}
    for path, text in ctx.files.items():
        for number, raw in prose_lines(text):
            if params["ignore_headings"] and raw.lstrip().startswith("#"):
                continue
            line = _normalize(raw)
            if len(line) < params["min_chars"] or _TABLE_RULE.match(line) or any(i.search(line) for i in ignore):
                continue
            groups.setdefault(line, {}).setdefault(path, number)
    found: list[Finding] = []
    sibling = params["sibling_level"]
    for line, where in groups.items():
        if len(where) < 2:
            continue
        shown = line if len(line) <= 60 else line[:57] + "..."
        for path, number in where.items():
            ancestors = sorted((o for o in where if o != path and _is_ancestor(o, path)), key=lambda o: (-len(posixpath.dirname(o)), o))
            if ancestors:
                found.append(Finding(path, number, ID, f"line repeats {ancestors[0]}:{where[ancestors[0]]} ({shown!r}); keep it in the ancestor only"))
                continue
            others = [o for o in where if o != path and not _is_ancestor(path, o)]
            if others and sibling != "off":
                names = ", ".join(f"{o}:{where[o]}" for o in sorted(others)[:3])
                more = f" and {len(others) - 3} more" if len(others) > 3 else ""
                found.append(Finding(path, number, ID, f"line also appears in sibling file(s) {names}{more} ({shown!r})", level="error" if sibling == "error" else "warn"))
    return found
