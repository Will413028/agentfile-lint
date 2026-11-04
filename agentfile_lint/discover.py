"""File discovery: tracked instruction files only, always the full set (never just argv)."""
from __future__ import annotations

import functools
import os
import posixpath
import re
import subprocess
from pathlib import Path

LOCAL_SUFFIX = ".local.md"  # untracked local instruction files are never analyzed


class DiscoverError(Exception):
    pass


@functools.lru_cache(maxsize=None)
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


def aliases(root: Path, paths: list[str]) -> dict[str, str]:
    """Paths that are the same file as another path in the same directory: alias -> kept path.

    `CLAUDE.md -> AGENTS.md` gives one file two names in one directory, each loaded by a different
    agent, so it is analyzed once. Identity is device and inode, so case-insensitive file systems agree
    and a symlink loop is skipped. The kept path is the first non-symlink, else the first in sort order.
    The same file in another directory is a separate load location and is analyzed on its own.
    """
    groups: dict[tuple[str, int, int], list[str]] = {}
    for path in paths:
        try:
            st = os.stat(root / path)
        except OSError:
            continue
        groups.setdefault((posixpath.dirname(path), st.st_dev, st.st_ino), []).append(path)
    out: dict[str, str] = {}
    for members in groups.values():
        kept = next((p for p in members if not (root / p).is_symlink()), members[0])
        out.update({p: kept for p in members if p != kept})
    return out
