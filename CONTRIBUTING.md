# Contributing

Thanks for helping. This is a small project maintained on a best-effort basis: expect a first reply to
an issue or pull request within a week.

## Reporting

- A bug or a crash: open a **Bug report**, with the command, the output and the exit code.
- A finding that is wrong: open a **False positive**, with the reported line and why it is fine. These
  reports are how the measured rates in `docs/rules.md` get better.
- A new check: open a **Rule proposal** before writing code, with real examples of what it would catch
  and what it must not.
- A vulnerability: do not open an issue; see `SECURITY.md`.

## Developing

```sh
make check                     # all unit tests; needs Python 3.11+
make check PYTHON=python3.12   # with another interpreter
python3 -m agentfile_lint      # lint this repository's own instruction files
```

- The runner uses only the Python standard library. Pull requests that add a runtime dependency are not
  accepted; new development or CI tools need a discussion in an issue first.
- Open pull requests against `dev`. `main` holds released code only (see `docs/versioning.md`).
- Every user-visible change has a `CHANGELOG.md` entry under `Unreleased`.

## Rules

- Rules are data: defaults and patterns live in `agentfile_lint/presets/*.toml`, not in code branches
  for one kind of repository. Unknown config keys fail, so a new key goes into the preset and its tests
  in the same change.
- A new rule enters at `warn`. It goes into the default preset only if it is objective or passes the
  false-positive bar in `docs/adr/0003-objective-checks-by-default.md`; otherwise it goes into
  `preset:strict`. Add its entry to `docs/rules.md`.
- The output format `file:line: rule-id: message` and the exit codes 0, 1 and 2 are a contract
  (`tests/test_contract.py`); changing them is a major version.
- Write the failing test first; tests build throwaway git repositories (`tests/helpers.py`).
