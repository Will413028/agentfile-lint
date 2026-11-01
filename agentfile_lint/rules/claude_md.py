"""C1: CLAUDE.md files.

`import-only` (default): a tracked CLAUDE.md must contain exactly one non-blank line, the import
line (`@AGENTS.md`), and an AGENTS.md must sit next to it. `forbid`: no tracked CLAUDE.md at all.
Looks at every tracked file named CLAUDE.md, whatever `discover.globs` says. `*.local.md` is never touched.
"""
from __future__ import annotations

import posixpath
from typing import Any

from ..context import Context
from ..errors import ConfigError, check_keys, expect_str, require_keys
from ..finding import Finding

ID = "C1"
NAME = "claude-md"
DESCRIPTION = "CLAUDE.md is a one-line import of AGENTS.md (import-only) or absent (forbid)"

MODES = ("import-only", "forbid")


def validate(params: dict[str, Any]) -> dict[str, Any]:
    where = f"rules.{ID}"
    check_keys(params, {"level", "mode", "import_line"}, where)
    require_keys(params, ["mode", "import_line"], where)
    if params["mode"] not in MODES:
        raise ConfigError(f"{where}.mode: expected one of {', '.join(MODES)}")
    return {"level": params["level"], "mode": params["mode"], "import_line": expect_str(params["import_line"], f"{where}.import_line")}


def check_repo(ctx: Context, params: dict[str, Any]) -> list[Finding]:
    found: list[Finding] = []
    for path in ctx.tracked:
        if posixpath.basename(path) != "CLAUDE.md" or not (ctx.root / path).is_file():
            continue
        if params["mode"] == "forbid":
            found.append(Finding(path, 0, ID, "CLAUDE.md must not exist (mode forbid); keep the instructions in AGENTS.md"))
            continue
        text = ctx.read(path)
        lines = [] if text is None else [line.strip() for line in text.splitlines() if line.strip()]
        if lines != [params["import_line"]]:
            found.append(Finding(path, 0, ID, f"CLAUDE.md must contain only the line {params['import_line']!r}"))
        sibling = posixpath.join(posixpath.dirname(path), "AGENTS.md")
        if sibling not in ctx.tracked_set:
            found.append(Finding(path, 0, ID, f"imports {params['import_line']} but {sibling} is not tracked"))
    return found
