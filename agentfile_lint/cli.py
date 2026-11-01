"""Command line entry point.

Output: one line per finding, `file:line: rule-id: message`. Whole-file findings use line 0 and
the `:0` is always printed, so the format has exactly one shape. Errors go to stderr, warnings to
stdout. Exit codes: 0 no errors (warnings allowed), 1 at least one error, 2 usage or config problem.
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 11):  # checked before importing anything that needs tomllib
    sys.stderr.write(f"agentfile-lint needs Python >= 3.11, found {sys.version.split()[0]}\n")
    raise SystemExit(2)

import argparse
import datetime
import json
import os
from pathlib import Path

from . import __version__
from . import config as config_mod
from . import discover, engine
from .errors import ConfigError
from .rules import RULES


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentfile-lint", description="Lint agent instruction files.")
    p.add_argument("files", nargs="*", help="only decides whether to run; the full tracked set is always analyzed")
    p.add_argument("--config", help=f"config file (default: {config_mod.CONFIG_NAME} at the repo root, if present)")
    p.add_argument("--today", help="YYYY-MM-DD, replaces the current date (reproducible runs)")
    p.add_argument("--version", action="version", version=f"agentfile-lint {__version__}")
    p.add_argument("--list-rules", action="store_true", help="print the rules and their effective levels, then exit")
    p.add_argument("--warn-as-error", action="store_true", help="treat warnings as errors")
    return p


def _relevant(files: list[str], root: Path, cwd: Path, globs: list[str]) -> bool:
    """argv names only decide whether to run at all (full-set semantics)."""
    for name in files:
        try:
            rel = Path(os.path.abspath(cwd / name)).relative_to(root).as_posix()
        except ValueError:
            continue
        if rel == config_mod.CONFIG_NAME or discover.matches(rel, globs):
            return True
    return False


def _config_main(argv: list[str]) -> int:
    """`agentfile-lint config --format json`: the effective (merged, validated) configuration."""
    p = argparse.ArgumentParser(prog="agentfile-lint config", description="Print the effective configuration.")
    p.add_argument("--format", choices=["json"], default="json", help="output format (only json)")
    p.add_argument("--config", help=f"config file (default: {config_mod.CONFIG_NAME} at the repo root, if present)")
    p.add_argument("--today", help="YYYY-MM-DD, used to validate allowlist expiry dates")
    args = p.parse_args(argv)
    try:
        today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    except ValueError:
        sys.stderr.write("agentfile-lint: --today must be YYYY-MM-DD\n")
        return 2
    try:
        cfg_path = Path(args.config) if args.config else None
        if cfg_path is None:
            try:
                root = discover.repo_root(Path.cwd())
            except discover.DiscoverError:
                root = None
            cfg_path = config_mod.default_config_path(root)
        cfg = config_mod.load(cfg_path, today)
    except ConfigError as exc:
        sys.stderr.write(f"agentfile-lint: {exc}\n")
        return 2
    sys.stdout.write(json.dumps(config_mod.to_jsonable(cfg), sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "vendor":  # subcommand; any other first word keeps the check CLI
        try:
            from . import vendor
        except ImportError:
            sys.stderr.write("agentfile-lint: vendor is only available from a source checkout\n")
            return 2
        return vendor.main(argv[1:])
    if argv and argv[0] == "check-pins":
        from . import check_pins
        return check_pins.main(argv[1:])
    if argv and argv[0] == "config":
        return _config_main(argv[1:])
    args = _parser().parse_args(argv)
    try:
        today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    except ValueError:
        sys.stderr.write("agentfile-lint: --today must be YYYY-MM-DD\n")
        return 2
    cwd = Path.cwd()
    try:
        try:
            root = discover.repo_root(cwd)
        except discover.DiscoverError:
            if not args.list_rules:
                raise
            root = None
        cfg_path = Path(args.config) if args.config else None
        if cfg_path is None:
            cfg_path = config_mod.default_config_path(root)
        cfg = config_mod.load(cfg_path, today)
    except (ConfigError, discover.DiscoverError) as exc:
        sys.stderr.write(f"agentfile-lint: {exc}\n")
        return 2

    if args.list_rules:
        for rule_id, module in RULES.items():
            print(f"{rule_id}  {cfg.rules[rule_id]['level']:<5}  {module.NAME}: {module.DESCRIPTION}")
        print("allowlist  error  expired or no-longer-needed allowlist entries; warns before expiry (always on)")
        return 0

    if args.files and not _relevant(args.files, root, cwd, cfg.globs):
        return 0

    findings = engine.analyze(root, cfg, today, args.warn_as_error)
    for f in findings:
        print(f.format(), file=sys.stderr if f.level == "error" else sys.stdout)
    sys.stdout.flush()
    return 1 if any(f.level == "error" for f in findings) else 0
