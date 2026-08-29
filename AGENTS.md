# Working on archagent

Conventions for an agent (or a person) making changes to **this** repository. This is not the file
archagent installs into your project — that is `architecture/AGENTS.md`, which archagent owns and
`archagent upgrade` overwrites. Nothing here is shipped to users.

Read `docs/architecture/README.md` first; it is this repository's own artifact and the worked example the
README points at.

## The gates

Four, all of which must pass before a change lands. CI runs the same set.

```bash
uv run pytest -q
uv run archagent check              # this repo's invariants, enforced by this repo's tool
uv run archagent drift --exit-code
uv run archagent lint-docs --exit-code
```

`drift` is a **gate here**, stricter than what the README asks of users, because this artifact is offered
as the worked example and one that has drifted teaches the wrong thing. The practical consequence: a code
change lands in the same commit as its documentation update, not the next one.

## Recording a defect found on a fresh target

**If you find a defect while running archagent against a repository it has not seen before, file an issue
and label it — even if you fix it in the same hour.**

```
found-by:<encounter-id>          e.g. found-by:usertest-2, found-by:calibration-5
```

The issue body says which encounter found it and reproduces the defect against the target at its pinned
revision. Fixing it immediately is fine and usually right; the issue exists so the count is derivable and
each entry is auditable to evidence, not to schedule work.

This is not bookkeeping. `scripts/defects.py` generates the fresh-target defect ledger from these labels,
and that ledger is the only instrument that can answer whether the tool is converging. It is generated
rather than typed because the hand-kept version already failed: of the first twelve defects, three existed
only in commit messages, and those three were the ones found by the author rather than a reviewer — the
category most likely to go unrecorded. See `docs/designs/evaluating-archagent.md` §17.3.

## Issues, designs and commits

A change of any size is traceable in three directions, and the chain is only useful if every link is
written at the time:

- **An issue states the problem and the plan.** Implementation steps live here, not in the design
  document — the design holds the reasoning and outlives any particular plan.
- **If a design document covers it, the issue links to it** and carries a label naming the design
  (`design:extraction-confidence`), so the set of issues implementing one design is a query rather than a
  memory.
- **The commit message explains the change; the issue is closed naming the commit.** `Fixed in <sha>`,
  with what was measured. A closing comment that says only "done" throws away the part a future reader
  needs — several issues in this repository were closed with the before/after numbers, and those are the
  ones still worth reading.

The same applies to defects found on a fresh target (above), where the discipline is stricter: file the
issue even when the fix lands in the same hour, because the label is what makes the count derivable.

## What the evaluation record will not tolerate

These are enforced by tests and by refusals in code, and they exist because each was once violated:

- **No metric without declared comparability.** `tests/ledger.py:keys_for()` raises on an unclassified
  metric rather than guessing. Three calibration means from three different briefs once looked like a
  rising line.
- **No averaging across incommensurable dimensions.** The user-test ledger has no `mean()` and a test
  asserts it never grows one. Impact ratings are reported as a distribution.
- **The three ledgers are never joined.** `usertest_ledger.refuse_join()` raises when called.
- **A blank is data.** "Could not judge" must stay distinct from a low score.
- **Reproduce a claim before recording it.** Every claim in a returned worksheet is checked against the
  code first. Round 2 recorded one that was wrong; without the check it would have entered the record.

## Things that have gone wrong more than once

- **A filename in backticks is read as a citation of a file in this repository.** Naming another repo's
  path that way creates a dangling reference. `lint-docs` has caught this three times, including inside
  the paragraph explaining the problem. Name foreign paths in prose.
- **Use absolute paths and `--project`.** Relying on the shell's working directory has produced
  stale-binary runs and accidental virtualenv builds inside a target repository.
- **Anything a human produced is write-once.** A kit rebuild once destroyed a completed review worksheet.
  `spotcheck.py` and `usertest.py` now refuse to overwrite a filled-in sheet; keep it that way.
- **Verify before asserting, especially when confident.** Three claims in a generated artifact were
  fabricated and caught only by running the searches the prompt itself demanded.

## Evaluation data

Lives in the private `archagent-evaluations` repository, cloned beside this one. The test suite does not
read it — all tests pass with it absent. Write-ups live here; numbers live there.
