# Design

## Problem

Agent instruction files are loaded whole whenever an agent works in their directory, so they
need budgets, and they rot: duplicated text, stale references, one-off exceptions that never
expire. A review checklist does not hold. A deterministic check that runs in the same way
locally and in CI does.

## Goals

- One rule file (TOML) plus a thin Python runner; no third-party dependencies at run time.
- The local hook and CI run the same program, the same rules, the same version.
- Three levels per rule: `error` (blocks), `warn` (prints), `off`.
- Exceptions are time-boxed: every allowlist entry has a reason and an expiry date, and the
  list can only shrink.
- Reproducible: same input and same injected date give the same output. No network, no telemetry.

## Non-goals

- No LLM in the gate (non-deterministic, paid, and the checked text is untrusted input).
- Not a Markdown style linter; it knows instruction-file semantics (tiers, budgets), not prose style.
- Untracked local instruction files (`*.local.md`) are out of scope; CI cannot see them.
- No distribution channel the runner depends on. It ships as a git repository (pre-commit hook,
  composite action), a PyPI package (`uvx agentfile-lint`) and a pinned vendored copy for restricted
  environments (see Vendored copy); consumers pin a version or a full commit SHA.

## Model

```
preset (shipped) <- repo config (.agentfile-lint.toml, `extends`) -> effective config
effective config + git ls-files (full set) -> rules -> findings -> allowlist -> output + exit code
```

- Rules are data: a rule module reads parameters, and repo-specific behaviour is never a
  branch in code. Differences between repositories are config values.
- Merge: tables merge key by key (the child wins); every other value, lists included, is replaced.
- Unknown keys, unknown rule ids and malformed allowlist entries fail the configuration (exit 2).
  A typo must not silently disable a check.

## File discovery

Files are `git ls-files` entries matching `discover.globs` (default `AGENTS.md`, `**/AGENTS.md`,
`CLAUDE.md`, `**/CLAUDE.md`), never a file ending in `.local.md`, skipping files deleted in the
working tree. Two discovered paths in the same directory that are the same file (for example
`CLAUDE.md -> AGENTS.md`) are one file under two names, each loaded by a different agent: only the
non-symlink path is analyzed (the first in sort order when all are symlinks), so no rule reports the
same text twice. The same file in another
directory is a separate load location and is analyzed on its own; when it sits in an ancestor or
descendant directory, an agent working there loads both, and R5 reports the repeated lines. A
symlink to a file outside the discovered set is analyzed as its own file; a dangling one is skipped.
File names given on the command line are not used to narrow the analysis: cross-file rules and the
allowlist "no longer needed" check need the whole set, and a partial view would make them pass locally
and fail in CI. Hooks therefore use `pass_filenames: false`.

Trigger scope: R3a, R3b and R3c depend on test files, source and docs, not only on instruction files,
so a hook or workflow must not filter by instruction-file paths. The pre-commit hook sets
`always_run: true` and has no `files:`; lefthook and CI examples carry no path filters. Run on every
commit and push; cross-file rules read the whole tracked set. Add a weekly `schedule` in CI so allowlist
expiry warnings appear without commits.

## Rule R1: size

- Limits come from `limits`, an ordered list of `{glob, max_bytes, max_lines, bytes_level, lines_level}`
  entries (either or both limits; each level is optional and defaults to the rule level, which caps it). The first entry whose glob matches the path applies; a file that matches no entry has no size
  limit, so the default preset ends with entries that cover every discovered file. Globs use the matcher
  of R2 shapes and R3c specs: `*` and `?` never cross `/`, `**/` matches zero or more directories.
  Depth tiers are written as globs: `AGENTS.md`, `*/AGENTS.md`, `**/AGENTS.md`.
- `path_limits`: `{glob, max_bytes, level}` entries for the combined size of a file and the files
  matching the same glob in its strict ancestor directories; every entry applies (unlike `limits`).
  Sizes are the bytes on disk, as the agent reads them: `excluded_blocks` and CRLF are not discounted.
  The finding is on the file where the total first exceeds the limit; files below it are not reported
  again, and a single file over the limit is reported the same way. The glob is meant to match one file
  per directory (`**/AGENTS.md`); Codex also loads `AGENTS.override.md` or fallback names instead of
  AGENTS.md, which the default does not model (revisit when an issue reports such a repository).
- Default preset: only limits an agent's documentation states. AGENTS.md files on one path that total
  over 32768 bytes are an error: Codex reads AGENTS.md from the root down to the working directory and
  stops adding files at 32 KiB in total (`project_doc_max_bytes`,
  https://learn.chatgpt.com/docs/agent-configuration/agents-md). `**/AGENTS.md` and `**/CLAUDE.md` over
  200 lines are a warning: Claude Code asks for fewer than 200 lines per CLAUDE.md file and reads
  AGENTS.md when there is no CLAUDE.md (https://code.claude.com/docs/en/memory), but truncates nothing.
  Every default error must point to such a hard limit (docs/adr/0003).
- The old `max_bytes` tier table is rejected with a message that points to the migration note in the
  changelog.
- Per-line limit in characters (`max_line_chars`), optional; omitted (the default), it is not checked.
  A merged config cannot remove a key, so once a parent config sets it, a child can only raise it.
- `excluded_blocks`: marker pairs; the text from a begin marker through the end marker (and one
  trailing newline) is removed before measuring.
- Exact semantics: files are read as UTF-8 in text mode (CRLF becomes LF); bytes and lines are counted on
  the body after block removal; line length is in characters; a limit is exceeded when
  `measured > limit` (equal passes); line numbers count on the body after block removal.
  These match the checker this rule replaces; a contract test compares both on boundary fixtures.

## Rules R2 to R6 and C1

The default preset runs only objective checks: R2, R3a, R3c and R5 (same-name ancestor pairs) at
`warn`; R3b, R4 and R6 guess and C1 checks a convention, so they are `off` and `preset:strict` turns
them on at `warn`, with R5 on any pair (docs/adr/0003). New rules enter at `warn` (see Versioning);
the severity named below is what a repository gets with `level = "error"`. Each rule reads its parameters from the config, and the
preset documents every key. Cross-file rules (`check_repo`) always see the full tracked set.
Fenced code blocks and HTML comments are ignored by every text rule.

- R2 shape: per glob (first match wins), `sections` must be the file's headings of `heading_level`,
  `exact` (no others, in order) or `ordered` (extras allowed). Optional `title` (starts with a level-1
  heading), `purpose` (a one-line paragraph after it), `bullets_only` (sections that hold only list
  items) and `must_match` (regexes that must match the file). Empty `shapes` means inactive.
- R3a test names: a backticked token that fully matches a `test_defs[].name` regex must be defined in a
  tracked file matching `files`, found with the `definition` template (`{name}` is the placeholder).
  A language with no matching tracked file is skipped. Presets: Go `func TestX(`, Python `def test_x(`.
- R3b path references (heuristic, `warn` by design): a backticked path-like token is tried against the
  file's directory and every ancestor, the repo root, the `base_dirs` (entries may contain `*`), each
  also under `source_roots` and with `resolve_extensions`. Existence means a tracked file or the
  directory of one. Skipped: spaces and `<>*{}$=|()[]?`, URLs, `@`/`~`/`-`/`/` prefixes, matches of
  `ignore_patterns`, lines with an `ignore_negated_words` word, and bare file names unless
  `check_bare_names`. On twelve popular public repositories with no config, 18 of the 19 sampled
  findings that could be judged were false positives (external or placeholder paths, paths relative to each
  package), so it is `off` by default and `warn` in `preset:strict`.
- R3c spec references: `specs` maps instruction files to a spec document (`{1}` is what the glob's first
  `*` matched); each `ref_pattern` match must match a numbered heading (`heading_pattern`; a heading
  2.1 also makes section 2 valid). Skipped: references qualified by an ASCII word other than
  `plain_words` (`other-doc §3`) and text matched by `ignore_before`. Empty `specs` means inactive.
- R4 rot: dates (ISO) and issue references at the rule level; `narrative_words` at `narrative_level`.
  A match inside a token that has a path separator, a file extension or a date-prefixed slug is a name,
  not a date.
- R5 duplicates: lines of at least `min_chars` characters, compared after collapsing whitespace and
  removing a list marker; headings and table rules are skipped. Same line in a file and in an ancestor
  file is reported on the descendant at the rule level. `ancestor_pairs = "same-name"` (default) counts
  only a file with the same name in a strict ancestor directory, the pair one agent loads together
  (Codex reads AGENTS.md from the root down to the working directory, Claude Code CLAUDE.md from the
  working directory up); `any` (strict) also counts different names and two files in one directory.
  Every other pair is a sibling pair, reported at `sibling_level` (default `off`, strict `warn`). Exact matches only. Always the full set (a partial view
  would pass locally and fail in CI).
- R6 constants: candidate patterns for values copied from code; findings are always warnings.
- C1 CLAUDE.md: any tracked file named `CLAUDE.md`, whatever `discover.globs` says. `import-only`:
  exactly one non-blank line, `import_line`, and an AGENTS.md next to it; a symlink to that AGENTS.md
  counts as the import. `forbid`: must not exist (a symlink included).

A finding carries its own level and the rule level caps it: a rule at `warn` never produces an error,
and a rule at `error` can still report some findings (R4 narrative words, R5 siblings, R6) as warnings.

## Allowlist

Each entry: `rule`, `path`, `reason`, `expires`.

- A live entry suppresses that rule's findings in that file.
- Expired (`expires` before today): error, and the finding is not suppressed. An entry that
  expires today is still live.
- No longer needed (the file does not violate the rule, or is not an analyzed file): error.
- Within `warn_days` (default 14) of expiry: warning "expires in N days".
- `max_days` (default 90): an `expires` later than today plus `max_days` fails the configuration.
- `max_entries` (default 10): more entries fail the configuration.
- Renewal means editing the config and writing a new reason; there are no inline suppressions.

Because expiry depends on the date, a repository with no commits can turn red. Run CI on a
weekly schedule so warnings appear before that happens.

## Output and exit codes

`file:line: rule-id: message`, one finding per line, sorted by file, line, rule. Line `0` means
the whole file and is printed as `:0` so the format has one shape. Errors go to stderr,
warnings to stdout. Exit `0`: no errors; `1`: at least one error; `2`: usage or configuration
problem. `--warn-as-error` promotes warnings. The format and exit codes are part of the
contract; which version part a change to them needs is in `docs/versioning.md`.

## Subcommands

- `agentfile-lint check-pins` (experimental: outside the compatibility contract, mainly for someone
  who maintains many repositories; docs/adr/0004): every reference to this tool (pre-commit `rev:`,
  `uvx --from git+...@<sha>`, `uses: owner/agentfile-lint@<sha>`) must be a full 40-hex SHA and all
  must be equal; output `file:line: check-pins: message`, exit 1. Line scanning, no YAML parser;
  limits are listed in `docs/versioning.md` and the module docstring.
- `agentfile-lint config --format json`: the effective merged configuration (preset, extends,
  repo config, defaults filled in) as JSON with sorted keys, so another program (a test in a language
  without a TOML parser) can read the same values the linter uses. Exit 2 on an invalid config.
- `agentfile-lint vendor`: see Vendored copy. It and the copy's `verify.py` are part of the contract.

## Judgment checks

What a program cannot decide (contradictions, stale claims, ambiguity, whether a line earns its place)
is not in the linter and not in CI: `rubric.md` lists the criteria for a human or an agent reviewer,
and `docs/pr-template-snippet.md` is the pull request prompt that asks for the result.

## Verification strategy

- Unit tests per component (config, discovery, allowlist, CLI).
- Contract test: a frozen snapshot of the legacy checker runs next to the new tool on
  generated git repositories with boundary cases (limit, limit +/- 1 per tier, 500/501
  character lines, multibyte text, marker blocks). Both outputs are normalised to
  `(path, line, kind, measured, limit)` sets and compared together with exit codes. A mismatch
  means one of the two tools is wrong; the normalisation is not adjusted to hide it.
- Rule tests: every rule has passing and violating fixtures in `tests/test_rules.py`, checked by
  mutation (neutralizing the rule must fail its tests); `tests/test_check_pins.py` covers `check-pins`
  and the JSON config; `tests/test_versioning.py` fails when a rule above `warn` is not listed as
  graduated in the changelog.
- The temporary checkout leg also runs every rule at its specified level on the pinned checkout,
  writes the report, and pins the set of error-level hits that were judged by hand.
- Timing test: a full scan of 46 synthetic files finishes in under a second.
- Date-injection test: the same `--today` gives byte-identical output.
- CI matrix: Python 3.11 to 3.13 on Linux and macOS; the repository checks its own instruction
  files through the composite action.

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

## Versioning

Semantic versions as git tags. New rules enter as `warn`; promoting a rule to `error` is a minor
change with a changelog entry under `Graduated`; renaming or removing a rule id is a major change
from 1.0, and before 1.0 a minor one listed under `Changed (breaking)`.
Consumers pin a full commit SHA with the version in a comment. The process (changelog rules, release,
how consumers upgrade) is in `docs/versioning.md`.
