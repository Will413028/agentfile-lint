# ADR 0006: User-requested configuration, output and suppression features for 0.8.0

Status: accepted. Amends decision 3 of ADR 0004 (overrides only lower a level). Implemented in 0.8.0;
each section is written by the change that implements it.

## Context

Up to 0.7.0 several features users of similar linters expect were deferred until someone asked: adding
globs without repeating the defaults, leaving known copies out of duplicate checks, raising a level on a
path, undoing an inherited override, per-line suppression, SARIF output and scanning outside git. 0.8.0
adds them before the tool is announced, so the first public version has the configuration surface that
later versions keep.

## Overrides can raise a level, and an inherited override can be undone

ADR 0004 lets an override only lower a level, so a shared config reached through `extends` can never make
a path stricter by accident. It also leaves no way to turn a rule on for one path, and since overrides
concatenate under `extends`, no way to remove an inherited override that does not fit a repository.

Options:

- A: keep lowering as the default; an entry with `raise = true` only raises (from `off` too). When
  entries that lower and entries that raise both match a file, lowering wins. `[[overrides]] unset =
  [globs]` removes globs from inherited entries.
- B: an override sets any level and the last entry wins (ESLint `overrides`). ruff's `per-file-ignores`
  can only turn rules off.

Decision: A. An override that makes a path stricter is written as such, so the guarantee of ADR 0004
holds for every entry without `raise`. Lowering wins over raising because a lowering entry is the more
specific statement about a path that is meant to differ, and the result does not depend on entry order.
`unset` names a glob, not an entry index, so it survives reordering in the file it undoes, and a glob
that is in no inherited entry fails the configuration instead of doing nothing.

Consequences:

- A raised rule runs even when its level is `off`; its findings outside the raised paths are dropped.
- Inherited override globs are now checked for staleness too (a warning on the file that wrote them):
  with `unset` available, a repository can act on the warning.
- `discover.extend_globs` and `[shared.duplicates] exclude` are added in the same release: the first
  concatenates along `extends` like overrides do, the second removes files from the R5a and R5b input,
  which an override (which only changes levels on the files it matches) cannot do.
