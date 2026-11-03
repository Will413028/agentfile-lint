# ADR 0003: The default preset runs only objective checks

Status: accepted. Supersedes the default values in decision 1 of ADR 0002 and its rejection of the
32 KiB limit; the `limits` model of ADR 0002 stands.

## Context

Up to 0.4.0 every rule ran with no config: R1 at `error`, the others at `warn`. Running 0.4.0 with no
config on the root of popular public repositories (the twelve most-starred with an AGENTS.md or
CLAUDE.md, picked by `gh search repos "stars:>5000"`) gave mostly noise. Sampled false-positive rates
(false / (true + false), up to 20 findings per rule): R3b 18/19, R4 16/19, R5 20/20, R6 13/17. Every
C1 finding was a repository that keeps real content in CLAUDE.md, a convention of this tool rather
than an error. Seven of the twelve repositories exited 1 on R1, four of them only on limits with no
source (12000/6000 bytes, 500 characters per line).

Constraints:

- External: Codex reads at most 32 KiB of project docs (`project_doc_max_bytes`, a hard limit;
  https://learn.chatgpt.com/docs/agent-configuration/agents-md). Claude Code asks for fewer than 200
  lines per CLAUDE.md, reads AGENTS.md when no CLAUDE.md exists, and truncates nothing
  (https://code.claude.com/docs/en/memory). A version number uploaded to PyPI cannot be reused.
  Existing users pin a SHA or a vendored copy, so a new default reaches them only when they upgrade.
- Inherited: "new rules enter at `warn`" (docs/versioning.md) still holds; it governs raising a rule,
  and this decision only lowers rules. R1 at `error` dates from 0.1.0; it still holds for the one
  limit that is a hard limit, not for guidance.

## Options considered

1. Baseline: default only checks whose findings are facts, put heuristics and conventions in a named
   opt-in group (ruff selects only `E4`, `E7`, `E9`, `F` by default; ESLint's `recommended` holds only
   likely errors; Clippy keeps `pedantic` off). Chosen, with the threshold below.
2. Turn a rule off when its sample false-positive rate exceeds 30%. Rejected: with 5 to 20 findings a
   sample rate cannot show a rate below 30%; five findings with no false positive still allow 43%
   (Wilson 95% upper bound).
3. Keep every rule at `warn` and tighten patterns. Rejected: meeting 30% would mean removing 92 to 100%
   of the false positives of R3b, R4 and R6 without losing their true findings.
4. R1 entirely at `warn`. Rejected: then no default ever fails CI, even for a file Codex cannot read
   in full.

## Decision

1. A rule is on by default only if it is objective, or if on a held-out sample of repositories (not
   used to tune it) 9 to 20 labelled findings give a Wilson 95% upper bound on its false-positive rate
   of at most 30% (in practice: at most one false positive in 20). Fewer than 9 findings: not on by
   default.
2. Default: R1, R2, R3a, R3c, and R5 for same-name ancestor pairs (`ancestor_pairs = "same-name"`,
   `sibling_level = "off"`). R3b, R4, R6 and C1 are `off`. `preset:strict` turns them on at `warn`
   and sets R5 to `any` pair and siblings to `warn`, the 0.4.0 behavior.
3. Every default `error` points to a hard limit in an agent's documentation. R1 default: AGENTS.md over
   32768 bytes is an error; AGENTS.md and CLAUDE.md over 200 lines are a warning. `limits` entries take
   `bytes_level` and `lines_level` so one entry can carry both; `max_line_chars` is optional.

R5 same-name pairs passed point 1: on a held-out sample of ten repositories, 0 of 13 findings were
false positives (upper bound 22.8%); a sample this small passes only with zero. Same-name ancestor
files are what one agent loads together (Codex reads AGENTS.md from the root down to the working
directory, Claude Code CLAUDE.md from the working directory up). Different names in one directory
are read by different agents, and siblings by none together.

## Rationale

The trade-off: with no config the tool now reports little (mostly R1, sometimes R5), so a first run
shows less of what the tool can do, in exchange for findings a stranger can trust. The value for teams
is in rules that need config anyway (R2 shapes, R3c spec references, expiring allowlist entries,
vendored copies); `preset:strict` is one line for anyone who wants the heuristics. Turning rules off
first is the cheap direction: turning one on later only adds warnings, while shipping it on and
turning it off later is noticed only by readers of the changelog.

## Consequences

- Repositories that relied on the 0.4.0 defaults add `extends = ["preset:strict"]` and, for the old R1
  limits, copy them from the CHANGELOG.
- `docs/rules.md` states each rule's measured false-positive rate and interval.
- The 13 R5 findings come from two repositories, and in the tuning sample the same class had 54 false
  positives in one repository (translated and example copies under `docs/<language>/` and `examples/`).
  Findings in one repository are not independent, so the interval is optimistic.

Revisit when:

- A heuristic rule passes point 1 on a new sample: move it into the default in a minor release.
- Users report R5 same-name findings on deliberate copies (translations, examples): add path
  exclusions or turn it off by default.
- A file under 32 KiB is still cut off because of the combined limit along the path: consider checking
  the sum, which ADR 0002 left out.
- Codex documents that it does not drop content past 32 KiB: lower that limit to `warn`.
