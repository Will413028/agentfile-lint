# ADR 0002: Size limits and triggers

Status: accepted. The default values in decision 1 and the rejection of the 32 KiB limit are
superseded by ADR 0003 (only limits with an external source in the default).

## Context

Version 0.2 shipped rule R1 (size) with a table of byte limits per directory depth, copied from the
first adopting repository's own convention. Two things showed that this model was borrowed rather
than justified:

- The only numeric guidance from a tool vendor is about lines: Claude Code recommends fewer than 200
  lines per CLAUDE.md file (https://code.claude.com/docs/en/memory). A bytes-only depth table cannot
  express it.
- Adopting repositories need different limits for files at the same depth (for example two files at
  the repository root), which depth tiers cannot say.

Separately, the first hook examples ran only when an instruction file changed. Rules R3a to R3c
compare instruction files against test names, source paths and spec documents, so they can be broken
by a commit that touches none of the instruction files.

## Decision

1. `limits` is an ordered list of `{glob, max_bytes, max_lines}` entries; either limit may be
   omitted. The first matching entry applies. Depth tiers are just three globs (`AGENTS.md`,
   `*/AGENTS.md`, `**/AGENTS.md`). The default preset gives root files 12000 bytes and 200 lines, and
   all other instruction files 6000 bytes and 200 lines.
2. The old byte-tier table is rejected with a message pointing to the changelog migration note.
3. Hooks and CI run on every commit and push, with no path filters. The pre-commit hook uses
   `always_run: true` and `pass_filenames: false`; CI adds a weekly scheduled run so allowlist expiry
   warnings appear without commits. Cross-file rules read the whole tracked set.
4. An oversized file is fixed by moving specifications out of it (the instruction file keeps
   invariants and pointers), not by raising the limit or by a long-lived allowlist entry.

## Alternatives considered

- Keep depth tiers and bytes only: rejected, no line limit and no per-file limits.
- A "sum along the path" rule to stay under another vendor's combined limit (32 KiB): not adopted.
  With the defaults, a root file plus one nested file is at most 18000 bytes, and that vendor's tool
  is not the primary target. Revisit if instruction files nest three or more levels deep, or if a
  vendor changes its loading or limit rules.
- Path filters on hooks and CI for speed: rejected, a change to a test or a source file can break R3
  while no instruction file changed, and the failure would surface only on a scheduled run. Measured
  full runs take from about 0.2 to 1.0 seconds per commit on the adopting repositories.
- Run cross-file rules only on the files passed by the hook: rejected, see ADR 0001.

## Consequences

- Config gets an ordering rule (first match wins); a file that matches no entry has no limit, so the
  preset ends with catch-all entries.
- Every commit pays the full-scan cost. If a repository's scan grows well past one second, add caching
  or reconsider path filters for that repository.
- Limits that were tuned for the old tiers must be restated as globs when upgrading to 0.3.0.
