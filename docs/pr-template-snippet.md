# Pull request template snippet

Paste this into the repository's pull request template. It only matters when a pull request touches
an instruction file (`AGENTS.md` or `CLAUDE.md`); the author ticks the box and pastes the summary,
the reviewer reads it. Nothing here runs in CI.

```markdown
### Instruction files

- [ ] This pull request does not change `AGENTS.md` / `CLAUDE.md` files (skip the rest), or:
- [ ] `instruction-lint` passes locally and in CI
- [ ] Reviewed against the rubric (J1-J7) and the summary is pasted below

<!-- Summary of the review (findings, or "no findings"). Rubric:
     https://github.com/Will413028/instruction-lint/blob/<tag or sha>/rubric.md -->
```

Notes for adopters:

- Link a tag or full SHA, not a branch, so the rubric the author used is the rubric the reviewer sees.
- A repository that vendors the tool can copy `rubric.md` next to the vendored copy instead of linking it.
- The checkbox is a prompt for a human, not a gate. If a gate is wanted, use a rule in the config.
