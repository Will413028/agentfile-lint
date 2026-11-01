"""Shared text helpers for rules: skip fenced code and HTML comments, find inline code spans."""
from __future__ import annotations

import re
from typing import Iterator

_FENCE = re.compile(r"\s*(`{3,}|~{3,})")
_COMMENT = re.compile(r"<!--.*?-->")
SPAN = re.compile(r"`([^`\n]+)`")


def prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """(1-based line number, line) for lines outside fenced code blocks; HTML comments are cut out."""
    fence: str | None = None
    in_comment = False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw
        if in_comment:
            end = line.find("-->")
            if end < 0:
                continue
            line = line[end + 3:]
            in_comment = False
        if fence is not None:
            closing = raw.strip()
            if closing and set(closing) == {fence[0]} and len(closing) >= len(fence):
                fence = None
            continue
        m = _FENCE.match(line)
        if m:
            fence = m.group(1)
            continue
        line = _COMMENT.sub("", line)
        start = line.find("<!--")
        if start >= 0:
            line = line[:start]
            in_comment = True
        yield number, line


def code_spans(line: str) -> Iterator[str]:
    for m in SPAN.finditer(line):
        yield m.group(1)
