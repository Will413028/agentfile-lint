"""R1: size limits. Byte and line limits chosen by path glob (first match wins) and an optional
character limit per line.

Each `limits` entry may give its byte and line limits their own level (`bytes_level`, `lines_level`);
an omitted level follows the rule level, and no entry level can raise a finding above the rule level.

`path_limits` limit the combined size of a file and the files matching the same glob in its ancestor
directories, the set an agent loads from the root down (Codex stops at 32 KiB in total). The finding is
on the file where the total first exceeds the limit, not on the files below it.
"""
from __future__ import annotations

import posixpath
import re
from typing import Any

from ..context import Context
from ..discover import glob_to_regex
from ..errors import ConfigError, check_keys, expect_int, expect_level, expect_str, expect_table_list, require_keys
from ..finding import Finding

ID = "R1"
NAME = "size"
DESCRIPTION = "byte and line limits per path glob, optional character limit per line"

_MIGRATION = (
    "rules.R1.max_bytes (root/subproject/nested) was removed in 0.3.0; replace it with "
    "[[rules.R1.limits]] entries, each with a glob and max_bytes and/or max_lines (first match wins). "
    "See the 0.3.0 entry in CHANGELOG.md for a migration example"
)


def validate(params: dict[str, Any]) -> dict[str, Any]:
    where = f"rules.{ID}"
    if "max_bytes" in params:
        raise ConfigError(f"{where}: {_MIGRATION}")
    check_keys(params, {"level", "max_line_chars", "limits", "path_limits", "excluded_blocks"}, where)
    for key in ("limits", "excluded_blocks"):
        if key not in params:
            raise ConfigError(f"{where}: missing key {key}")
    if "max_line_chars" in params:  # omitted: line length is not checked
        expect_int(params["max_line_chars"], f"{where}.max_line_chars")
    for i, raw in enumerate(expect_table_list(params["limits"], f"{where}.limits")):
        at = f"{where}.limits[{i}]"
        check_keys(raw, {"glob", "max_bytes", "max_lines", "bytes_level", "lines_level"}, at)
        require_keys(raw, ["glob"], at)
        expect_str(raw["glob"], f"{at}.glob")
        if "max_bytes" not in raw and "max_lines" not in raw:
            raise ConfigError(f"{at}: needs max_bytes, max_lines or both")
        for key in ("max_bytes", "max_lines"):
            if key in raw:
                expect_int(raw[key], f"{at}.{key}")
        for key in ("bytes_level", "lines_level"):
            if key in raw:
                expect_level(raw[key], f"{at}.{key}")
    for i, raw in enumerate(expect_table_list(params.get("path_limits", []), f"{where}.path_limits")):
        at = f"{where}.path_limits[{i}]"
        check_keys(raw, {"glob", "max_bytes", "level"}, at)
        require_keys(raw, ["glob", "max_bytes"], at)
        expect_str(raw["glob"], f"{at}.glob")
        expect_int(raw["max_bytes"], f"{at}.max_bytes")
        if "level" in raw:
            expect_level(raw["level"], f"{at}.level")
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


def _body(text: str, params: dict[str, Any]) -> str:
    for pattern in _block_patterns(params):
        text = pattern.sub("", text)
    return text


def _in_or_below(directory: str, path: str) -> bool:
    return directory == "" or posixpath.dirname(path) == directory or path.startswith(directory + "/")


def check_repo(ctx: Context, params: dict[str, Any]) -> list[Finding]:
    found: list[Finding] = []
    for entry in params.get("path_limits", []):
        level = entry.get("level", "error")  # "error" = follow the rule level (the engine caps it)
        if level == "off":
            continue
        pattern = glob_to_regex(entry["glob"])
        sizes = {p: len(_body(t, params).encode("utf-8")) for p, t in ctx.files.items() if pattern.match(p)}
        limit = entry["max_bytes"]
        for path in sorted(sizes):
            ancestors = sorted((a for a in sizes if a != path and _in_or_below(posixpath.dirname(a), path)
                                and posixpath.dirname(a) != posixpath.dirname(path)), key=lambda a: (a.count("/"), a))
            before = sum(sizes[a] for a in ancestors)
            total = before + sizes[path]
            if total <= limit or before > limit:  # within the limit, or the overflow starts above
                continue
            if ancestors:
                message = f"file and its ancestors ({', '.join(ancestors)}) total {total} bytes, limit {limit}"
            else:
                message = f"file is {total} bytes, limit {limit}"
            found.append(Finding(path, 0, ID, message, level=level))
    return found


def check(path: str, text: str, params: dict[str, Any]) -> list[Finding]:
    body = _body(text, params)
    found: list[Finding] = []
    size = len(body.encode("utf-8"))  # bytes after block removal
    limit = limit_for(path, params)
    bytes_level = limit.get("bytes_level", "error")  # "error" = follow the rule level (the engine caps it)
    if "max_bytes" in limit and bytes_level != "off" and size > limit["max_bytes"]:
        found.append(Finding(path, 0, ID, f"file is {size} bytes, limit {limit['max_bytes']}", level=bytes_level))
    lines = len(body.splitlines())
    lines_level = limit.get("lines_level", "error")
    if "max_lines" in limit and lines_level != "off" and lines > limit["max_lines"]:
        found.append(Finding(path, 0, ID, f"file is {lines} lines, limit {limit['max_lines']}", level=lines_level))
    max_chars = params.get("max_line_chars")
    if max_chars is None:
        return found
    # Line numbers count on the body after block removal; length is in characters.
    for number, line in enumerate(body.splitlines(), start=1):
        if len(line) > max_chars:
            found.append(Finding(path, number, ID, f"line is {len(line)} characters, limit {max_chars}"))
    return found
