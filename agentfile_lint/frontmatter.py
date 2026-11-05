"""YAML frontmatter of a Markdown file: the only module that uses the vendored PyYAML (`_yaml`).

A frontmatter block starts on the first line with `---` and ends at the next line that is exactly
`---`. It is parsed with PyYAML's `SafeLoader`, which builds plain data only (no Python objects).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import _yaml
from ._yaml.reader import ReaderError

DELIMITER = "---"


@dataclass(frozen=True)
class Frontmatter:
    value: object = None        # the parsed YAML value when `error` is None (a dict for a mapping)
    error: str | None = None    # why the block could not be parsed, or None
    line: int = 1               # 1-based file line of the error (the opening `---` when unknown)
    column: int = 1             # 1-based column of the error
    end: int = 0                # 1-based line of the closing `---`; 0 when unterminated


def split(text: str) -> tuple[str, int] | None:
    """(YAML text, 1-based line of the closing `---`), or None when the file has no frontmatter.

    `text` has LF newlines; a leading UTF-8 BOM is ignored. An opening `---` without a closing one
    returns ("", 0)."""
    text = text.removeprefix("\ufeff")
    if text != DELIMITER and not text.startswith(DELIMITER + "\n"):
        return None
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i] == DELIMITER:
            return "\n".join(lines[1:i]) + ("\n" if i > 1 else ""), i + 1
    return "", 0


def _position(body: str, offset: int) -> tuple[int, int]:
    """1-based file (line, column) of a character offset into the YAML text (which starts on line 2)."""
    before = body[:offset]
    return before.count("\n") + 2, offset - (before.rfind("\n") + 1) + 1


def parse(text: str) -> Frontmatter | None:
    """Parse the frontmatter of `text` (LF newlines); None when the file has none."""
    found = split(text)
    if found is None:
        return None
    body, end = found
    if end == 0:
        return Frontmatter(error="frontmatter has no closing '---' line")
    try:
        value = _yaml.load(body, Loader=_yaml.SafeLoader)
    except _yaml.MarkedYAMLError as exc:
        # Report the mark together with the text that describes it.
        if exc.problem_mark is not None:
            mark, reason = exc.problem_mark, exc.problem or exc.context
        else:
            mark, reason = exc.context_mark, exc.context or exc.problem
        reason = f"invalid YAML: {reason or 'cannot parse'}"
        if mark is None:
            return Frontmatter(error=reason, end=end)
        # The YAML text starts on file line 2, after the opening `---`.
        return Frontmatter(error=reason, line=mark.line + 2, column=mark.column + 1, end=end)
    except ReaderError as exc:  # a character YAML does not allow; no mark, an offset instead
        line, column = _position(body, exc.position)
        return Frontmatter(error=f"invalid YAML: unacceptable character #x{exc.character:04x}",
                           line=line, column=column, end=end)
    except _yaml.YAMLError as exc:
        return Frontmatter(error="invalid YAML: " + str(exc).split("\n")[0], end=end)
    except RecursionError:  # nesting deeper than the interpreter's recursion limit
        return Frontmatter(error="invalid YAML: nested too deeply", end=end)
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        # SafeLoader's scalar constructors raise these on values that pass the grammar but not the
        # conversion: `2026-02-30`, `!!int abc`, `!!timestamp foo`, integers over Python's digit limit.
        return Frontmatter(error="invalid YAML: cannot convert a value: " + str(exc).split("\n")[0], end=end)
    return Frontmatter(value=value, end=end)
