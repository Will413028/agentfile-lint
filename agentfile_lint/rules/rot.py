"""R4: text that rots. Dates and issue numbers are state, not rules; narrative words date a sentence.

Dates and issue references are reported at the rule's level. Narrative words are reported at
`narrative_level` (never above the rule's own level). File names that carry a date (a decision
record, a plan) are not dates: a match inside a token that contains `/` or a file extension is skipped.
"""
from __future__ import annotations

import re
from typing import Any

from ..errors import check_keys, expect_level, expect_regex_list, expect_str_items, require_keys
from ..finding import Finding
from ._text import prose_lines

ID = "R4"
NAME = "rot"
DESCRIPTION = "dates and issue numbers (rule level); narrative words (narrative_level)"

_KEYS = {"level", "narrative_level", "date_patterns", "issue_patterns", "ignore_token_patterns", "narrative_words"}


def validate(params: dict[str, Any]) -> dict[str, Any]:
    where = f"rules.{ID}"
    check_keys(params, _KEYS, where)
    require_keys(params, _KEYS - {"level"}, where)
    return {
        "level": params["level"],
        "narrative_level": expect_level(params["narrative_level"], f"{where}.narrative_level"),
        "date_patterns": expect_regex_list(params["date_patterns"], f"{where}.date_patterns"),
        "issue_patterns": expect_regex_list(params["issue_patterns"], f"{where}.issue_patterns"),
        "ignore_token_patterns": expect_regex_list(params["ignore_token_patterns"], f"{where}.ignore_token_patterns"),
        "narrative_words": expect_str_items(params["narrative_words"], f"{where}.narrative_words"),
    }


def _word(word: str) -> re.Pattern[str]:
    if word.isascii():
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(re.escape(word))


def _token(line: str, start: int, end: int) -> str:
    """The whitespace/backtick-delimited token around a match."""
    left = max(line.rfind(c, 0, start) for c in " \t`") + 1
    cuts = [i for i in (line.find(c, end) for c in " \t`") if i >= 0]
    return line[left:min(cuts) if cuts else len(line)]


def check(path: str, text: str, params: dict[str, Any]) -> list[Finding]:
    found: list[Finding] = []
    dates = [re.compile(p) for p in params["date_patterns"]]
    issues = [re.compile(p) for p in params["issue_patterns"]]
    ignore = [re.compile(p) for p in params["ignore_token_patterns"]]
    words = [(w, _word(w)) for w in params["narrative_words"]]
    narrative = params["narrative_level"]
    for number, line in prose_lines(text):
        for kind, patterns in (("date", dates), ("issue reference", issues)):
            for pattern in patterns:
                for m in pattern.finditer(line):
                    token = _token(line, m.start(), m.end())
                    if any(i.search(token) for i in ignore):
                        continue
                    found.append(Finding(path, number, ID, f"{kind} {m.group(0)!r} goes stale; state the rule, not the moment"))
        if narrative != "off":
            for word, pattern in words:
                if pattern.search(line):
                    found.append(Finding(path, number, ID, f"narrative word {word!r}; describe the current rule, not its history", level=narrative if narrative == "warn" else "error"))
    return list(dict.fromkeys(found))
