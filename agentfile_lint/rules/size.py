"""R1: size limits. Byte and line limits chosen by path glob (first match wins) and a character limit per line."""
from __future__ import annotations

import re
from typing import Any

from ..discover import glob_to_regex
from ..errors import ConfigError, check_keys, expect_int, expect_str, expect_table_list, require_keys
from ..finding import Finding

ID = "R1"
NAME = "size"
DESCRIPTION = "byte and line limits per path glob and character limit per line"

_MIGRATION = (
    "rules.R1.max_bytes (root/subproject/nested) was removed in 0.3.0; replace it with "
    "[[rules.R1.limits]] entries, each with a glob and max_bytes and/or max_lines (first match wins). "
    "See the 0.3.0 entry in CHANGELOG.md for a migration example"
)


def validate(params: dict[str, Any]) -> dict[str, Any]:
    where = f"rules.{ID}"
    if "max_bytes" in params:
        raise ConfigError(f"{where}: {_MIGRATION}")
    check_keys(params, {"level", "max_line_chars", "limits", "excluded_blocks"}, where)
    for key in ("max_line_chars", "limits", "excluded_blocks"):
        if key not in params:
            raise ConfigError(f"{where}: missing key {key}")
    expect_int(params["max_line_chars"], f"{where}.max_line_chars")
    for i, raw in enumerate(expect_table_list(params["limits"], f"{where}.limits")):
        at = f"{where}.limits[{i}]"
        check_keys(raw, {"glob", "max_bytes", "max_lines"}, at)
        require_keys(raw, ["glob"], at)
        expect_str(raw["glob"], f"{at}.glob")
        if "max_bytes" not in raw and "max_lines" not in raw:
            raise ConfigError(f"{at}: needs max_bytes, max_lines or both")
        for key in ("max_bytes", "max_lines"):
            if key in raw:
                expect_int(raw[key], f"{at}.{key}")
    blocks = params["excluded_blocks"]
    if not isinstance(blocks, list):
        raise ConfigError(f"{where}.excluded_blocks: expected a list of {{begin, end}} tables")
    for i, block in enumerate(blocks):
        check_keys(block, {"begin", "end"}, f"{where}.excluded_blocks[{i}]")
        for key in ("begin", "end"):
            if key not in block:
                raise ConfigError(f"{where}.excluded_blocks[{i}]: missing key {key}")
            expect_str(block[key], f"{where}.excluded_blocks[{i}].{key}")
    return params


def _block_patterns(params: dict[str, Any]) -> list[re.Pattern[str]]:
    # Same shape as a hand-written `BEGIN.*?END\n?` with DOTALL: the block and one trailing newline.
    return [
        re.compile(re.escape(b["begin"]) + ".*?" + re.escape(b["end"]) + "\n?", re.DOTALL)
        for b in params["excluded_blocks"]
    ]


def limit_for(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """The first `limits` entry whose glob matches; no match means no size limit."""
    for entry in params["limits"]:
        if glob_to_regex(entry["glob"]).match(path):
            return entry
    return {}


def check(path: str, text: str, params: dict[str, Any]) -> list[Finding]:
    body = text
    for pattern in _block_patterns(params):
        body = pattern.sub("", body)
    found: list[Finding] = []
    size = len(body.encode("utf-8"))  # bytes after block removal
    limit = limit_for(path, params)
    if "max_bytes" in limit and size > limit["max_bytes"]:
        found.append(Finding(path, 0, ID, f"file is {size} bytes, limit {limit['max_bytes']}"))
    lines = len(body.splitlines())
    if "max_lines" in limit and lines > limit["max_lines"]:
        found.append(Finding(path, 0, ID, f"file is {lines} lines, limit {limit['max_lines']}"))
    max_chars = params["max_line_chars"]
    # Line numbers count on the body after block removal; length is in characters.
    for number, line in enumerate(body.splitlines(), start=1):
        if len(line) > max_chars:
            found.append(Finding(path, number, ID, f"line is {len(line)} characters, limit {max_chars}"))
    return found
