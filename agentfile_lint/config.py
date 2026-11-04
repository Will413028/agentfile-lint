"""Configuration: shipped preset + optional repo config with `extends`; unknown keys fail.

Merge rule: tables merge key by key (the child wins); every other value, lists included,
is replaced as a whole. The one exception is `[[overrides]]`: lists concatenate (parents first), since
replacing them would silently drop the overrides of the config a file extends.
"""
from __future__ import annotations

import datetime
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from . import allowlist, overrides as overrides_mod
from .errors import LEVELS, ConfigError, check_keys, expect_int, expect_str, expect_str_list, expect_table_list
from .finding import INPUT_RULE
from .rules import ALIASES, MODULES, RETIRED, RULES, SHARED

CONFIG_NAME = ".agentfile-lint.toml"
# Migration aid for the 0.4.0 rename; remove at 1.0.
LEGACY_CONFIG_NAME = ".instruction-lint.toml"
PRESET_PREFIX = "preset:"
DEFAULT_PRESET = "preset:default"
_TOP_KEYS = {"extends", "discover", "allowlist", "shared", "rules", "overrides", "check_pins"}
PIN_DEFAULTS = {
    "repo": "agentfile-lint",
    "files": [
        ".pre-commit-config.yaml", ".pre-commit-config.yml", "lefthook.yml", "lefthook.yaml",
        ".lefthook.yml", ".lefthook.yaml", ".github/workflows/*.yml", ".github/workflows/*.yaml",
    ],
}


def default_config_path(root: Path | None) -> Path | None:
    """The repo-root config file, or None. Fails when only the pre-0.4.0 file name exists."""
    if root is None:
        return None
    path = root / CONFIG_NAME
    if path.is_file():
        return path
    if (root / LEGACY_CONFIG_NAME).is_file():
        raise ConfigError(
            f"found {LEGACY_CONFIG_NAME}, which agentfile-lint no longer reads; "
            f"rename it to {CONFIG_NAME} (git mv {LEGACY_CONFIG_NAME} {CONFIG_NAME})"
        )
    return None


@dataclass
class Config:
    globs: list[str]
    allowlist: allowlist.Settings
    entries: list[allowlist.Entry]
    rules: dict[str, dict[str, Any]]  # rule id -> its merged, validated `[rules.<id>]` table, including "level"
    shared: dict[str, dict[str, Any]] = field(default_factory=dict)  # group -> its `[shared.<group>]` table
    params: dict[str, Any] = field(default_factory=dict)  # rule module name -> what its validate() returned
    check_pins: dict[str, Any] = field(default_factory=lambda: dict(PIN_DEFAULTS))  # repo, files
    overrides: list[overrides_mod.Override] = field(default_factory=list)


def to_jsonable(cfg: "Config") -> dict[str, Any]:
    """The effective configuration as plain JSON data (dates as ISO strings)."""
    return {
        "discover": {"globs": cfg.globs},
        "allowlist": {
            "max_days": cfg.allowlist.max_days,
            "max_entries": cfg.allowlist.max_entries,
            "warn_days": cfg.allowlist.warn_days,
            "entries": [
                {"rule": e.rule, "path": e.path, "reason": e.reason, "expires": e.expires.isoformat()}
                for e in cfg.entries
            ],
        },
        "shared": cfg.shared,
        "rules": cfg.rules,
        "overrides": [{"paths": list(o.paths), "rules": dict(o.rules), "reason": o.reason} for o in cfg.overrides],
        "check_pins": cfg.check_pins,
    }


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _read(source: str, text: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{source}: invalid TOML: {exc}") from exc


def _load_raw(ref: str, base_dir: Path | None, seen: tuple[str, ...]) -> dict[str, Any]:
    if ref.startswith(PRESET_PREFIX):
        name = ref[len(PRESET_PREFIX):]
        key = ref
        try:
            text = (resources.files("agentfile_lint") / "presets" / f"{name}.toml").read_text(encoding="utf-8")
        except (FileNotFoundError, OSError) as exc:
            raise ConfigError(f"unknown preset {name!r}") from exc
        data = _read(ref, text)
    else:
        path = Path(ref)
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        key = str(path.resolve())
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read config {path}: {exc.strerror}") from exc
        data = _read(str(path), text)
        base_dir = path.parent
    if key in seen:
        raise ConfigError(f"extends cycle at {ref}")
    extends = data.get("extends", [DEFAULT_PRESET] if ref != DEFAULT_PRESET else [])
    if isinstance(extends, str):
        extends = [extends]
    if not isinstance(extends, list) or not all(isinstance(e, str) for e in extends):
        raise ConfigError(f"{ref}: extends must be a list of strings")
    merged: dict[str, Any] = {}
    inherited: list[tuple[Any, str | None, int]] = []
    for parent in extends:
        parent_raw = _load_raw(parent, base_dir, seen + (key,))
        inherited += parent_raw.pop("overrides")
        merged = _merge(merged, parent_raw)
    own = _resolve_aliases({k: v for k, v in data.items() if k != "extends"}, ref)
    own_overrides = expect_table_list(own.pop("overrides", []), f"{ref}: overrides")
    # Only the file this run loads directly is checked for stale globs.
    direct = not seen and not ref.startswith(PRESET_PREFIX)
    merged = _merge(merged, own)
    merged["overrides"] = inherited + [(entry, ref, i, direct) for i, entry in enumerate(own_overrides)]
    return merged


def _resolve_aliases(data: dict[str, Any], source: str) -> dict[str, Any]:
    """Replace rule aliases with rule ids in one config file, before it merges with its parents.

    Resolving per file keeps a repo's `[rules.file-lines]` overriding a preset's `[rules.R1b]`; one file
    naming the same rule both ways is ambiguous and fails.
    """
    rules = data.get("rules")
    if isinstance(rules, dict):
        resolved: dict[str, Any] = {}
        written: dict[str, str] = {}  # rule id -> the key the file used
        for key, value in rules.items():
            _retired(key, f"{source}: rules.{key}")
            rule_id = ALIASES.get(key, key)
            if rule_id in resolved:
                raise ConfigError(f"{source}: rules.{written[rule_id]} and rules.{key} name the same rule; use one")
            resolved[rule_id] = value
            written[rule_id] = key
        data = {**data, "rules": resolved}
    al = data.get("allowlist")
    if isinstance(al, dict) and isinstance(al.get("entries"), list):
        for i, e in enumerate(al["entries"]):
            if isinstance(e, dict) and isinstance(e.get("rule"), str):
                _retired(e["rule"], f"{source}: allowlist.entries[{i}].rule")
        entries = [
            {**e, "rule": ALIASES[e["rule"]]} if isinstance(e, dict) and isinstance(e.get("rule"), str) and e["rule"] in ALIASES else e
            for e in al["entries"]
        ]
        data = {**data, "allowlist": {**al, "entries": entries}}
    ov = data.get("overrides")
    if isinstance(ov, list):
        resolved_ov = []
        for i, entry in enumerate(ov):
            if isinstance(entry, dict) and isinstance(entry.get("rules"), dict):
                levels: dict[str, Any] = {}
                written = {}
                for key, value in entry["rules"].items():
                    _retired(key, f"{source}: overrides[{i}].rules.{key}")
                    rule_id = ALIASES.get(key, key)
                    if rule_id in levels:
                        raise ConfigError(
                            f"{source}: overrides[{i}].rules.{written[rule_id]} and .{key} name the same rule; use one"
                        )
                    levels[rule_id] = value
                    written[rule_id] = key
                entry = {**entry, "rules": levels}
            resolved_ov.append(entry)
        data = {**data, "overrides": resolved_ov}
    return data


def _retired(key: str, where: str) -> None:
    if key in RETIRED:
        raise ConfigError(f"{where}: {RETIRED[key]}")


def load(config_path: Path | None, today: datetime.date) -> Config:
    """Load the preset plus `config_path` (when given). Raises ConfigError on any problem."""
    if config_path is None:
        raw = _load_raw(DEFAULT_PRESET, None, ())
    else:
        raw = _load_raw(str(config_path), None, ())
    return _validate(raw, today)


def _validate(raw: dict[str, Any], today: datetime.date) -> Config:
    check_keys(raw, _TOP_KEYS, "config")
    discover = raw.get("discover", {})
    check_keys(discover, {"globs"}, "discover")
    globs = expect_str_list(discover.get("globs"), "discover.globs")

    al = raw.get("allowlist", {})
    check_keys(al, {"max_days", "max_entries", "warn_days", "entries"}, "allowlist")
    settings = allowlist.Settings(
        max_days=expect_int(al.get("max_days"), "allowlist.max_days", 0),
        max_entries=expect_int(al.get("max_entries"), "allowlist.max_entries", 0),
        warn_days=expect_int(al.get("warn_days"), "allowlist.warn_days", 0),
    )

    shared_raw = raw.get("shared", {})
    check_keys(shared_raw, set(SHARED), "shared")
    for group, keys in SHARED.items():
        if group not in shared_raw:
            raise ConfigError(f"shared.{group}: missing")
        check_keys(shared_raw[group], keys, f"shared.{group}")
    rules_raw = raw.get("rules", {})
    check_keys(rules_raw, set(RULES) | set(ALIASES), "rules")  # aliases are resolved by now; listed as a hint
    rules: dict[str, dict[str, Any]] = {}
    params: dict[str, Any] = {}
    for module in MODULES:
        ids = [rule_id for rule_id, _, _ in module.CHECKS]
        for rule_id in ids:
            if rule_id not in rules_raw:
                raise ConfigError(f"rules.{rule_id}: missing")
            if not isinstance(rules_raw[rule_id], dict):
                raise ConfigError(f"rules.{rule_id}: expected a table")
            if rules_raw[rule_id].get("level") not in LEVELS:
                raise ConfigError(f"rules.{rule_id}.level: expected one of {', '.join(LEVELS)}")
        group = module.SHARED[0] if hasattr(module, "SHARED") else None
        tables = {rule_id: rules_raw[rule_id] for rule_id in ids}
        params[module.__name__] = module.validate(shared_raw.get(group), tables)
        for rule_id in ids:
            # `config --format json` shows effective values (defaults filled in). A one-id module's
            # params are its effective table; the tables of a module with several ids have no defaulted
            # keys (all required, or optional without a default), so as merged they are effective.
            rules[rule_id] = params[module.__name__] if len(ids) == 1 else tables[rule_id]

    # E0 has no `[rules]` table (it cannot be turned off), but an allowlist entry may name it.
    entries = allowlist.parse(al.get("entries", []), settings, set(RULES) | {INPUT_RULE}, today)
    pins = raw.get("check_pins", {})
    check_keys(pins, set(PIN_DEFAULTS), "check_pins")
    pins = {
        "repo": expect_str(pins.get("repo", PIN_DEFAULTS["repo"]), "check_pins.repo"),
        "files": expect_str_list(pins.get("files", PIN_DEFAULTS["files"]), "check_pins.files"),
    }
    overrides = overrides_mod.parse(raw.get("overrides", []), set(RULES))
    shared = {group: shared_raw[group] for group in SHARED}
    return Config(
        globs=globs, allowlist=settings, entries=entries, rules=rules, shared=shared, params=params,
        check_pins=pins, overrides=overrides,
    )
