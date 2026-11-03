# agentfile-lint

A linter for agent instruction files (`AGENTS.md`, `CLAUDE.md`) that a team runs the same way in every
repository: rules are data in one TOML file, exceptions expire, and the runner is plain Python with no
dependencies, so the git hook, CI and a vendored copy give the same answer.

```sh
uvx agentfile-lint        # in any git repository; no config needed
```

Status: version 0.4.0 is on PyPI; the output below is from `dev`, whose changes (including these
defaults) are listed in the CHANGELOG under Unreleased.

With no config it runs only checks whose findings are facts. From a demo repository:

```text
$ uvx agentfile-lint
services/api/AGENTS.md:0: R1: file and its ancestors (AGENTS.md) total 34618 bytes, limit 32768
AGENTS.md:0: R1: file is 211 lines, limit 200
AGENTS.md:9: R3a: test `test_login_redirects` is not defined in any searched test file
services/api/AGENTS.md:3: R5: line repeats AGENTS.md:8 ('Never edit generated files under `gen/`; change the schem...'); keep it in the ancestor only
$ echo $?
1
```

Codex stops reading `AGENTS.md` files on a path once they total 32 KiB (its default), so the first line is an error;
the others are warnings. `extends = ["preset:strict"]` in `.agentfile-lint.toml` adds the heuristic
rules, which guess and are wrong more often (rates in [`docs/rules.md`](docs/rules.md)). Same
repository:

```text
$ printf 'extends = ["preset:strict"]\n' > .agentfile-lint.toml
$ uvx agentfile-lint
services/api/AGENTS.md:0: R1: file and its ancestors (AGENTS.md) total 34618 bytes, limit 32768
AGENTS.md:0: R1: file is 211 lines, limit 200
AGENTS.md:9: R3a: test `test_login_redirects` is not defined in any searched test file
CLAUDE.md:0: C1: CLAUDE.md must contain only the line '@AGENTS.md'
services/api/AGENTS.md:3: R5: line repeats AGENTS.md:8 ('Never edit generated files under `gen/`; change the schem...'); keep it in the ancestor only
services/api/AGENTS.md:4: R3b: path `src/legacy/router.py` not found from this file's directory, its ancestors, the repo root or base_dirs
services/api/AGENTS.md:5: R4: narrative word 'currently'; describe the current rule, not its history
services/api/AGENTS.md:5: R6: possible copied constant '`MAX_RETRIES = 5`'; point to the code instead of repeating the value
```

| Rule | Default | `preset:strict` | What it checks |
|---|---|---|---|
| `R1` | error | error | size: `AGENTS.md` files on one path over 32 KiB in total (error), `AGENTS.md` or `CLAUDE.md` over 200 lines (warn); your own byte, line and line-length limits by glob |
| `R2` | warn | warn | file shape: required section headings in order, optional title, one-line purpose, bullet-only sections (needs config) |
| `R3a` | warn | warn | a test name in backticks is defined in a tracked test file |
| `R3b` | off | warn | a path in backticks exists (heuristic) |
| `R3c` | warn | warn | a `§N` reference matches a numbered heading in the mapped spec document (needs config) |
| `R4` | off | warn | dates, issue numbers and narrative words such as "currently" (heuristic) |
| `R5` | warn | warn | identical lines in a same-name file of an ancestor directory; strict: any file in an ancestor or the same directory, and sibling files |
| `R6` | off | warn | candidates for constants copied from code (heuristic, always a warning) |
| `C1` | off | warn | `CLAUDE.md` is only the line `@AGENTS.md` (`import-only`) or absent (`forbid`) |
| `allowlist` | error | error | time-boxed exceptions: expired or no-longer-needed entries fail, entries warn before they expire |

Every rule except `R1` ships at `warn` or `off`; raise a rule to `error` in your own config once it is
clean. Why each rule exists, where its default comes from and its measured false-positive rate:
[`docs/rules.md`](docs/rules.md).

### Other instruction files

The default checks `AGENTS.md` and `CLAUDE.md` only. To add others, list them in `[discover] globs`:

```toml
[discover]
globs = ["AGENTS.md", "**/AGENTS.md", "CLAUDE.md", "**/CLAUDE.md",
         "GEMINI.md", "**/GEMINI.md", ".github/copilot-instructions.md"]
```

- The list replaces the default list, so repeat the four `AGENTS.md` / `CLAUDE.md` globs.
- With `preset:strict`, R5 compares files of different names too, so a `GEMINI.md` that copies the
  `AGENTS.md` next to it is reported line by line. The default compares only same-name files.

### Compared with similar tools

From each tool's own documentation, checked 2026-11-03; nothing here was installed or run. "Not
documented" means the documentation does not say, not that the feature is missing.

| | agentfile-lint | [agnix](https://github.com/agent-sh/agnix) | [ctxlint](https://github.com/YawLabs/ctxlint) | [agentlinter](https://github.com/seojoonkim/agentlinter) |
|---|---|---|---|---|
| Runs on | Python 3.11+, standard library only | Rust binary (npm, brew, pip, cargo) | Node (`npx`), no runtime dependencies | Node 18+ (`npx`) |
| Files | `AGENTS.md`, `CLAUDE.md`; others by glob | `CLAUDE.md`, `AGENTS.md`, `SKILL.md`, hooks, MCP, Cursor, Copilot, more | context files of 16 tools, MCP config | `CLAUDE.md`, `AGENTS.md`, `SKILL.md`, Cursor, Copilot, more |
| Shared config | `extends` presets and files | `extend` base files | not documented | `extends` of the built-in preset |
| Exceptions | allowlist entries need a reason and an expiry date; expired or unneeded entries fail | disabled rules, per-file overrides, inline comments | ignored rules with an optional reason; unused ones reported | ignored paths |
| Vendored copy | reproducible directory with a hash check | not documented | not documented | not documented |
| References checked | test names, `§N` spec sections; paths with `preset:strict` | import paths, commands, referenced files | paths, commands (against `package.json`, `Makefile`) | file references, imports |
| Duplicates between files | identical lines in a file and its ancestors | not documented | duplicate content across files | duplicate content; across files not documented |
| Auto-fix | no | yes | broken paths | yes |
| Editor | no | LSP, IDE plugins | LSP | no |
| Output | `file:line: rule-id: message`, exit 0/1/2 | GitHub, JSON, SARIF | text, JSON, SARIF; exit 0/1/2 | GitHub; 0-100 score |

Choose agnix for breadth (many file types, IDE plugins, auto-fix). Choose agentfile-lint to run one
small, pinned set of rules across many repositories: exceptions expire, the checker can be vendored
and verified, and the output and exit codes are a tested contract. Next for this project, if it is useful to others: `SKILL.md`, hooks and
MCP config.

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

`R2` and `R3c` need configuration to check anything (section lists, spec mappings); the preset
documents every key. A rule at `error` can still emit some findings as warnings.
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
