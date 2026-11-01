"""File discovery: tracked instruction files only, always the full set (never just argv)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

LOCAL_SUFFIX = ".local.md"  # untracked local instruction files are never analyzed


class DiscoverError(Exception):
    pass


def glob_to_regex(glob: str, capture: bool = False) -> re.Pattern[str]:
    """`**/` matches zero or more directories, `*` and `?` never cross `/`.

    With `capture`, each `*` run of a path segment becomes a group (used by `{1}` in templates).
    """
    out: list[str] = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("([^/]*)" if capture else "[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, globs: list[str]) -> bool:
    if path.endswith(LOCAL_SUFFIX):
        return False
    return any(glob_to_regex(g).match(path) for g in globs)


def repo_root(cwd: Path) -> Path:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise DiscoverError("not inside a git repository (or git is not installed)") from exc
    return Path(out)


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True, capture_output=True, text=True,
    ).stdout
    return sorted(p for p in out.split("\0") if p)


def instruction_files(root: Path, globs: list[str]) -> list[str]:
    """Tracked files matching `globs` that still exist in the working tree (staged deletions skipped)."""
    return [p for p in tracked_files(root) if matches(p, globs) and (root / p).is_file()]
