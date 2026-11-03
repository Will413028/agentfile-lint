# Rules

For each rule: why a finding is a problem, where its default comes from, whether it runs by default or
only with `preset:strict`, and how often it was wrong when measured. Every key is documented in
`agentfile_lint/presets/default.toml`; `agentfile-lint --list-rules` prints the effective levels.

Every rule in the table except `allowlist` has an id and an alias (the name after the level in
`--list-rules`); `allowlist` and `E0` have only their id. The alias works wherever the id does: `[rules.size]`
is `[rules.R1]`, an allowlist entry may say `rule = "size"`, and an override may say `rules = { size = "warn" }`. Each config file is resolved on its
own before merging, so a repo's `[rules.size]` overrides a preset's `[rules.R1]`; one file that names a
rule both ways fails (exit 2). Findings and error messages always print the id.

| Rule | Alias | Checks | Kind | Default | `preset:strict` |
|---|---|---|---|---|---|
| [R1](#r1-size) | `size` | size of a file and of the files on its path | objective | error (32 KiB on a path), warn (200 lines) | same |
| [R2](#r2-shape) | `shape` | required headings and file shape | objective, needs config | warn | warn |
| [R3a](#r3a-test-names) | `test-names` | a backticked test name is defined | objective | warn | warn |
| [R3b](#r3b-path-references) | `path-refs` | a backticked path exists | heuristic | off | warn |
| [R3c](#r3c-spec-references) | `spec-refs` | a `§N` reference matches a spec heading | objective, needs config | warn | warn |
| [R4](#r4-rot) | `rot` | dates, issue numbers, narrative words | heuristic | off | warn |
| [R5](#r5-duplicates) | `duplicates` | identical lines in files an agent loads together | objective match, heuristic intent | warn (same-name ancestor pairs) | warn (any pair, siblings) |
| [R6](#r6-copied-constants) | `constants` | values copied from code | heuristic | off | warn |
| [C1](#c1-claudemd) | `claude-md` | `CLAUDE.md` only imports `AGENTS.md` | convention | off | warn |
| [allowlist](#allowlist) | — | exceptions are current and still needed | objective | error | error |

## How the rates were measured

A rule runs by default only if its findings are facts, or if on a held-out sample of repositories (not
used to tune it) 9 to 20 labelled findings give a Wilson 95% upper bound on the false-positive rate of
at most 30% (docs/adr/0003). The rates below come from that measurement (2026-11-03):

- Sample: the most-starred public repositories with an `AGENTS.md` or `CLAUDE.md` at the root, in star
  order from `gh search repos "stars:>5000" --sort stars`. The first 12 are the tuning sample, the next
  10 the held-out sample. Each was cloned at a recorded commit and checked with no config.
- Labels: up to 20 findings per rule, drawn at random, each labelled true problem, false positive or
  undecidable by one reviewer with a second reviewer spot-checking. Rate = false / (true + false);
  undecidable findings are listed apart.
- Interval: Wilson score interval, 95%. Findings from one repository are not independent, so every
  interval here is optimistic. Repositories are not named (they did nothing wrong by not using this
  tool's conventions).
- Heuristic rules were labelled on the tuning sample with 0.4.0. Their patterns have not changed since;
  0.5.0 only stops counting a same-directory symlink as a second file, which removed findings that were
  all false positives.

## R1 size

Why: agents load these files whole, every session. Codex reads `AGENTS.md` from the repository root
down to the working directory and stops adding files once their combined size reaches
`project_doc_max_bytes`, 32 KiB by default; text past that is silently not read
([Codex: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)). Claude Code asks for
fewer than 200 lines per `CLAUDE.md`, because longer files use more context and reduce adherence, and
reads `AGENTS.md` when there is no `CLAUDE.md`
([Claude Code: memory](https://code.claude.com/docs/en/memory)).

Default: `AGENTS.md` files on one path that total over 32768 bytes are an error (`path_limits`, reported
on the file where the total first exceeds the limit); `AGENTS.md` and `CLAUDE.md` over 200 lines are a
warning. Both are limits an agent's documentation states; the first one drops text, the second is
guidance. Per-line character limits and other byte limits are yours to add (`limits`,
`max_line_chars`).

Measured: objective, so no false-positive rate. With no config, 22 public repositories gave 16 errors
in 6 repositories (all combined sizes over 32 KiB; 2 single files were over on their own) and 20
warnings (files over 200 lines). A per-file 32 KiB check would have found 3 files in 2 repositories.

## R2 shape

Why: when every module's file has the same sections in the same order, an agent (and a reviewer) knows
where to look, and a missing section is visible.

Default: on, but `shapes` is empty, so it checks nothing until a repository lists its shapes.

Measured: not measured; nothing to check with no config.

## R3a test names

Why: a test named as a guard ("keep `test_login_redirects` green") that no longer exists sends the agent
looking for it, and the guard the line promises is gone.

Default: on at `warn`, for Go (`func TestX(` in `*_test.go`) and Python (`def test_x(` in `test_*.py`,
`*_test.py`). A language with no tracked test file is skipped.

Measured: objective, so no false-positive rate. 0 findings on 22 public repositories.

## R3b path references

Why: a path that no longer exists points the agent at the wrong place.

Default: off. Telling a path in this repository from an example, a placeholder, a path in another
repository or a path relative to each package is a guess; `base_dirs`, `source_roots` and
`ignore_patterns` help once you know your layout.

Measured (tuning sample, 0.4.0): 18 of 19 false positives, 95% (Wilson 95%: 75.4% to 99.1%); 1
undecidable. False positives were external or placeholder paths, paths relative to each package, build
output and negated examples ("not `src/__tests__/`").

## R3c spec references

Why: `§3.2` in an instruction file stops pointing anywhere once the spec is renumbered.

Default: on, but `specs` is empty, so it checks nothing until a repository maps instruction files to
their spec document.

Measured: not measured; nothing to check with no config.

## R4 rot

Why: dates, issue numbers and words like "currently" or "recently" describe history. The file should
state the rule that holds now; history belongs in the changelog or the commit, where it cannot go stale
in front of an agent.

Default: off. Dates and issue numbers are also used as citations, and narrative words have ordinary
meanings ("used to produce").

Measured (tuning sample, 0.4.0): 16 of 19 false positives, 84% (Wilson 95%: 62.4% to 94.5%); 1
undecidable. Most false positives were issue numbers cited as the source of a rule ("(#1234)"); the true
problems described change history ("PR #1234 moved ...").

## R5 duplicates

Why: an agent that loads a file and its ancestor reads a duplicated line twice, and the two copies drift
apart (one gets edited, the other does not).

Default: on at `warn`, only for a file and a same-name file in an ancestor directory (`AGENTS.md` and
`sub/AGENTS.md`), the pair one agent loads together (`ancestor_pairs = "same-name"`). Lines must be at
least 40 characters and identical after collapsing whitespace and dropping list markers; headings are
skipped. `preset:strict` also compares different names and files in one directory (`ancestor_pairs =
"any"`) and sibling files (`sibling_level = "warn"`).

Measured, default pairs (held-out sample): 0 of 13 false positives (Wilson 95%: 0% to 22.8%), from two
repositories; one false positive would have failed the 30% bar. Known false-positive class: in the
tuning sample, all 54 same-name findings came from one repository and were deliberate copies
(translations under `docs/<language>/`, `examples/`). Such a repository turns R5 off for those paths with
`[[overrides]]` (`paths = ["docs/**", "examples/**"]`, `rules = { duplicates = "off" }`). An override
silences the findings on the files it matches: with `preset:strict`, the sibling comparison still reports
the original outside those paths, since its finding is on that file.

Measured, strict pairs (tuning sample, 0.4.0): 20 of 20 false positives. 11 of them were a file compared
with its own symlink, fixed in 0.5.0; the other 9 were translations, templates and examples, 9 of 9
(Wilson 95%: 70.1% to 100%).

## R6 copied constants

Why: a value copied from code (a limit, a timeout, a retry count) drifts silently when the code changes;
a pointer to the code does not.

Default: off. Findings are always warnings, at any level: they are candidates, not proof.

Measured (tuning sample, 0.4.0): 13 of 17 false positives, 76% (Wilson 95%: 52.7% to 90.4%); 0
undecidable. Most false positives were how to set an environment variable (`NAME=1`) and performance
targets.

## C1 CLAUDE.md

Why: with `CLAUDE.md` containing only `@AGENTS.md` (or being a symlink to it), Claude Code and every
other agent read the same text, kept in one place.

Default: off. It is this tool's convention, not an error: many repositories keep real content in
`CLAUDE.md` on purpose. `mode = "forbid"` requires that there is no `CLAUDE.md` at all.

Measured: not a false-positive rate. On the tuning sample 0.4.0 reported 30 findings, all differences
of convention: a `CLAUDE.md` with its own content, or a `CLAUDE.md` symlinked to `AGENTS.md`, which 0.4.0
did not recognize as the import. 0.5.0 with `preset:strict` reports 26 of them.

## allowlist

Why: a debt exception without an end date becomes permanent without anyone deciding so. Every allowlist
entry has a reason and an expiry date at most `max_days` (90) ahead; an expired entry, or one that no
longer suppresses anything, fails. A path that is meant to differ for good goes in `[[overrides]]`
instead, with a required reason; each glob of an override in the config file the run loads (not one
reached through `extends`) that matches no analyzed instruction file is a warning, so a stale override
shows up without failing CI unless `--warn-as-error` is given.

Default: on, from your config only; with no entries it reports nothing. Entries warn `warn_days` (14)
before they expire, so run CI on a weekly schedule.

Measured: objective, so no false-positive rate.

## Rule ids for other files

Planned, not implemented: rules for other file types get an id prefix per family, so ids stay unique
as checks are added: `S` for `SKILL.md`, `H` for hooks, `M` for MCP configuration. `R` and `C` stay with
instruction files, and `E` is reserved for input errors such as `E0`.
