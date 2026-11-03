# agentfile-lint

A linter for agent instruction files (`AGENTS.md`, `CLAUDE.md`). Rules and limits live in one
TOML file; the runner is a thin Python program that uses only the standard library
(Python 3.11 or newer). A local git hook and CI call the same program with the same config.

Status: version 0.4.0; the unreleased changes on `dev` are listed in the CHANGELOG. The default preset
runs only objective checks; `extends = ["preset:strict"]` adds the heuristic rules and the `C1`
convention at `warn`. Every rule except `R1` ships at `warn` or `off`; raise a rule to `error` in your
own config once it is clean.

| Rule | Default | `preset:strict` | What it checks |
|---|---|---|---|
| `R1` | error | error | byte and line limits chosen by path glob (first match wins), each with its own level, and an optional character limit per line; optional marker blocks (for example text a tool injects) are not counted. Default: `AGENTS.md` over 32 KiB is an error (Codex reads no more), `AGENTS.md` and `CLAUDE.md` over 200 lines a warning (Claude Code guidance) |
| `R2` | warn | warn | file shape: required section headings in order, optional title, one-line purpose, bullet-only sections |
| `R3a` | warn | warn | a test name in backticks is defined in a tracked test file |
| `R3b` | off | warn | a path in backticks exists (resolved from the file, its ancestors, the root and configured bases; heuristic) |
| `R3c` | warn | warn | a `§N` reference matches a numbered heading in the mapped spec document |
| `R4` | off | warn | dates and issue numbers (rule level), narrative words such as "currently" (`narrative_level`) |
| `R5` | warn | warn | identical lines in a same-name file of an ancestor directory (rule level; strict: any file in an ancestor or the same directory, `ancestor_pairs`) or in sibling files (`sibling_level`: off; strict: warn) |
| `R6` | off | warn | candidates for constants copied from code (always a warning) |
| `C1` | off | warn | `CLAUDE.md` is only the line `@AGENTS.md` (`import-only`) or absent (`forbid`) |
| `allowlist` | error | error | time-boxed exceptions: expired or no-longer-needed entries fail, entries warn before they expire |

## Usage

```sh
python3 -m agentfile_lint            # from a git repository; analyzes tracked files only
agentfile-lint --list-rules          # rules and their effective levels
agentfile-lint --today 2026-01-31    # replace the current date (reproducible runs)
agentfile-lint --config path.toml    # explicit config instead of .agentfile-lint.toml
agentfile-lint --warn-as-error
```

Other commands:

```sh
agentfile-lint check-pins            # every reference to this tool pins the same full commit SHA
agentfile-lint config --format json  # the effective merged configuration, sorted keys
agentfile-lint vendor --to DIR       # a pinned, self-contained copy (see below)
```

Output is one line per finding: `file:line: rule-id: message`. Findings about a whole file use
line `0` (printed as `:0`). Errors go to stderr, warnings to stdout. Exit codes: `0` no errors,
`1` at least one error, `2` usage or configuration problem.

Files given on the command line are ignored; the full tracked set is always analyzed
(cross-file checks and allowlist checks need it). Untracked local instruction
files (`*.local.md`) are never analyzed.

## Configuration

`.agentfile-lint.toml` at the repository root extends the shipped preset. Unknown keys fail.

```toml
extends = ["preset:default"]        # default; other entries are paths relative to this file

[discover]
globs = ["AGENTS.md", "**/AGENTS.md"]

[rules.R1]
level = "error"                     # error | warn | off
max_line_chars = 500                # optional; omitted, line length is not checked
excluded_blocks = [{ begin = "<!-- BEGIN:x -->", end = "<!-- END:x -->" }]

# First matching glob wins; a file matching no entry has no size limit.
[[rules.R1.limits]]
glob = "AGENTS.md"
max_bytes = 12000
max_lines = 200                     # optional; either or both
lines_level = "warn"                # optional, also bytes_level; default: the rule level

[[rules.R1.limits]]
glob = "**/AGENTS.md"
max_bytes = 6000

[allowlist]
max_days = 90

[[allowlist.entries]]
rule = "R1"
path = "docs/AGENTS.md"
reason = "split planned in the tracker"
expires = 2026-12-31
```

## Install and wire up

pre-commit:

```yaml
- repo: https://github.com/Will413028/agentfile-lint
  rev: <tag or full commit SHA>
  hooks:
    - id: agentfile-lint
```

Run on every commit and push: rules R3a, R3b and R3c read test files, source and docs, and cross-file
rules read the whole tracked set, so do not filter the hook, lefthook entry or workflow by instruction
files (no `files:`, `glob:` or `paths:` filters). The pre-commit hook sets `always_run: true`.

lefthook (no path filter):

```yaml
pre-commit:
  commands:
    agentfile-lint:
      run: python3 -m agentfile_lint
```

GitHub Actions (pin to a full commit SHA; no `paths:` filter, plus a weekly run so allowlist expiry
warnings appear even when nobody commits):

```yaml
on:
  push:
  pull_request:
  schedule:
    - cron: "0 6 * * 1"   # weekly

# steps:
- uses: actions/checkout@<sha>
- uses: Will413028/agentfile-lint@<sha>
```

Rules above `R1` need configuration to be useful (section lists, base directories, spec mappings);
the preset documents every key. A rule at `error` can still emit some findings as warnings.
The review criteria for what no program can decide are in `rubric.md`, with a pull request snippet in
`docs/pr-template-snippet.md`; the release and upgrade process is in `docs/versioning.md`.

Development: `make check` runs the unit tests (needs Python 3.11+, override with `PYTHON=...`).
Design notes are in `docs/design.md`, decisions in `docs/adr/`.

## Vendored copy

For environments that cannot install from git, `agentfile-lint vendor --to <dir>` writes one
self-contained directory: the runner package with the default preset, an entry script
(`agentfile-lint.py`), `verify.py` and a `README.md` that records the upstream tag, the upstream
commit and a SHA-256 for every file. Options: `--ref-tag` / `--ref-commit` (default: the exact tag
and HEAD of the source checkout, else `untagged`), `--force` (replace a non-empty target).

- Run it from the repository root: `python3 <dir>/agentfile-lint.py` (Python >= 3.11, standard
  library only, no network). Its output and exit codes equal `python3 -m agentfile_lint`.
- The output is reproducible: same source and same two upstream values give a byte-identical tree
  (sorted order, fixed newlines, no timestamps, no machine paths or user names).
- `python3 <dir>/verify.py` recomputes the hashes and fails (exit 1, naming the file) on a
  modified, missing or unlisted file.

Known limitation: verification only detects accidental modification. A deliberate change can edit
the files and the manifest together, so it is not tamper-proof. The real gate is review of the
diff of the pull request that upgrades the vendored copy.

## License

MIT, see `LICENSE`.
