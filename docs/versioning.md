# Versioning, changelog and upgrades

## Versions

Semantic versions as git tags (`v0.2.0`). The tag points at a commit; consumers pin the full
40-hex commit SHA and note the version in a comment. Pre-1.0, a minor version may add rules and
change defaults; it may also remove or rename a config key (listed under "Changed (breaking)" in the
changelog). Always read the changelog before moving a pin.

| Change | Version part |
|---|---|
| Output format, exit codes, a removed or renamed rule id or config key | major |
| A rule promoted from `warn` to `error`, a changed default limit, a new rule, a new option | minor |
| A bug fix in a rule or command, documentation | patch |

## Changelog rules

`CHANGELOG.md` follows Keep a Changelog. Every user-visible change has an entry in the section of
the release that ships it (`Added`, `Changed`, `Fixed`, `Removed`).

- A new rule enters the default preset at `warn`. Whatever its specification calls the intended
  severity, the preset ships `warn`; a repository raises it with `level = "error"` after a clean run.
- Promoting a rule to `error` in the preset is a minor change and must be listed under a
  `### Graduated` heading, one bullet per rule starting with the rule id in backticks.
- `tests/test_versioning.py` fails when a rule in any shipped preset (`agentfile_lint/presets/*.toml`)
  is above `warn` and not listed under `Graduated` (`off` is allowed: lowering needs no entry), and when `pyproject.toml`, `__version__` and the newest
  changelog section disagree.
- Changing a default value changes every consumer that did not override it: say so under `Changed`.

## Branches and releasing

Work lands on `dev` (pushed directly; CI runs on every push). `main` holds released code only and
changes through a pull request from `dev` with all required checks green. Merge `dev` into `main`
with a merge commit, never squash or rebase: a squashed `main` no longer contains the `dev` commits,
and the next release pull request conflicts with itself.

1. On `dev`: move the `Unreleased` entries under `## [x.y.z] - YYYY-MM-DD`, update the version in
   `pyproject.toml` and `agentfile_lint/__init__.py`; `make check`; push and wait for CI.
2. Open a pull request `dev` -> `main` and merge it with a merge commit once checks are green.
3. Tag `vx.y.z` (annotated, signed) on the merge commit on `main` and note the full commit SHA for
   consumers.
4. Publish a GitHub release for the tag (notes from the changelog section). `publish.yml` then
   builds the sdist and wheel from the tag and uploads them to PyPI with Trusted Publishing (no stored
   token). PyPI holds the name and offers an install path; consumers still pin the full commit SHA.

## Upgrading a consumer

Pick one mechanism per consumer; `check-pins` keeps the references consistent.

- pre-commit: `pre-commit autoupdate --repo <url>` rewrites `rev:` to a tag; use
  `pre-commit autoupdate --freeze` to write the full commit SHA with the tag as a comment.
- renovate: its pre-commit manager updates `rev:` in `.pre-commit-config.yaml`; actions and `uvx`
  references need their own rules or a manual edit. Dependabot's coverage of pre-commit files was not
  verified for this document; check the current documentation before relying on it.
- `uvx --from git+<url>@<sha>` and `uses: owner/agentfile-lint@<sha>`: edit by hand (or with
  renovate's regex manager) in one commit, so every reference moves together.
- Vendored copy: run `agentfile-lint vendor --to <dir> --force` from the new tag's checkout; the
  diff of that change is the review. `verify.py` detects accidental edits only.

After any upgrade run `agentfile-lint check-pins` (every reference pins the same full SHA) and the
normal check; new `warn` output after an upgrade is expected and is the point of the warn-first policy.

## `check-pins`

`agentfile-lint check-pins [--repo STRING] [--files GLOB ...] [--require-refs]` scans tracked
files (default: `.pre-commit-config.yaml`, `lefthook.y*ml`, `.github/workflows/*.y*ml`) for
references to this tool and fails when a reference is not a full 40-hex SHA or when two
references pin different SHAs. Output is `file:line: check-pins: message` on stderr, exit 1.
`[check_pins]` in the config sets `repo` and `files`. It reads lines, not YAML: anchors,
multi-line values and `${{ }}` expressions are not understood (an expression is reported as a non-SHA).
It checks consistency among the references it finds; it cannot prove it found all of them.
