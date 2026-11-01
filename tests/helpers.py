"""Shared test helpers: temporary git repos and subprocess runners."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LEGACY = FIXTURES / "legacy-oracle" / "check-agents-md.py"
HAWKR_LIMITS = FIXTURES / "hawkr-limits.toml"


def make_repo(files: dict[str, str | bytes], track: bool = True) -> Path:
    """Create a temp git repo. Files are written byte-exact; `track` runs `git add -A`."""
    root = Path(tempfile.mkdtemp(prefix="il-test-"))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    if track:
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def run_new(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(REPO))
    return subprocess.run(
        [sys.executable, "-m", "agentfile_lint", *args],
        cwd=root, env=env, capture_output=True, text=True,
    )


def run_legacy(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LEGACY)], cwd=root, capture_output=True, text=True,
    )
