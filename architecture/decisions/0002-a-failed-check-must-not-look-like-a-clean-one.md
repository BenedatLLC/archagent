# 0002 — A failed check must never look like a clean one

## Status
Accepted

## Context
Five separate defects in this repository shared one shape: a failure that rendered as a plausible clean
result rather than an error.

- `git log` exceeded a 30-second timeout; `_git` returned `None`; `mine_cochange` returned all-zero
  counts. Every history signal went quiet and the repository read as clean. That run was recorded as a
  regression baseline before anyone noticed.
- The defect study's outcome walk returned `""` on a git error, which was read as *a year in which
  nothing was fixed* — producing `predicts=False` for any repository whose walk failed.
- A corrupt partial clone produced the same silence.
- History bounded by `--until` against a tree that was not checked out measures old history against new
  code, and nothing in the output looks wrong.
- A cached commit-wording profile learned from *after* a cutoff, used to label commits before it.

None produced a stack trace. Each was caught by two numbers that could not both be true.

## Decision
A check that cannot answer must say so, distinctly from answering "nothing found".

- `CoChange.mining_failed` is set when the walk fails; `evaluate` surfaces it as a caution and an
  inactive family.
- The defect study's outcome walk raises rather than returning an empty string.
- `ensure_clone` validates that a clone can perform a `--name-status` walk — neither `HEAD` existing nor
  `rev-parse` resolving detects the corruption.
- `evaluate` warns when `HEAD` is newer than `--until`.
- A `Check` score of `None` means "not applicable", never `0`.

## Consequences
Guards have caught more defects here than the test suite has. Budget for them accordingly.

## Rejected alternatives
Raising on every failure. Rejected: a repository with genuinely no history is a normal case, and the tool
must degrade to fewer signals rather than refusing to run.
