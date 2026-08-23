# End-to-end user test, round 1 — httpx, archagent 1.0.0rc1

**Status: kit built 2026-08-23, awaiting testers.** No results yet. This document records the design
*before* any worksheet comes back, so the rationale cannot be rewritten to fit the numbers.

## The question this round asks

Every earlier round handed a reviewer a finished artifact and asked whether it was any good. All five
therefore assume the tool was already installed, configured and run correctly — by me. This round asks
the question none of them can: **can someone else get a result at all, from the published documentation
alone?**

So the kit ships a repository with no `archagent.toml`, no `architecture/`, and no pre-run output. Where
the tester gets stuck *is* the measurement, and the log in Part 1 of the worksheet matters more than any
of the four scores.

## Target: httpx at `b5addb64f`

Pinned so two testers see the same repository. Selected against three criteria:

- **No prior contact.** `tests/corpus_manifest.toml` and `tests/heldout_manifest.toml` between them
  disqualify litellm, django, opencode, OpenHands, datasette, flask, poetry, scrapy, pandas, ansible,
  homeassistant, nova, kibana, prettier and angular. litellm was the first proposal and is the worst
  available choice: it is the repository `dupdecide`'s clustering was tuned against, where
  `CoChange.mining_failed` was discovered, and whose findings supply two `test_blindcomp.py` fixtures.
- **Finishable in an evening.** 23 source files, 1,523 commits, a 3.9 MiB pack. litellm is 132 MiB and
  its history walk is the one that forced the git timeout to 900s.
- **The layout that breaks things.** httpx's package sits at the repository root, the shape that produced
  three silent-failure bugs in round 5. A test that never exercises it would not be testing much.

A test enforcing the first criterion is in `tests/test_usertest.py`, so the rule cannot be quietly
relaxed later.

## What the rubric measures, and what it cannot

Four dimensions, 1–5: **ease of use**, **correctness**, **completeness**, **impact**.

Only the first is a measurement this design can actually support. Correctness and completeness ratings
from someone who has not verified claims one at a time are *impressions* — and round 5 established that
6 of 19 findings which read as entirely plausible described nothing real. So the worksheet asks how many
claims the tester actually checked, and the answer travels with the score.

**These numbers may not be pooled with `spotcheck` precision, ever.** Same boundary as round 5's impact
ratings: that harness withholds severity and asks a blind question, this one shows the tester everything
because it is testing the whole experience.

## What the kit is built to catch

- **The silent-failure path.** A wrong `source_paths` makes every check examine nothing and report that
  all is well. A tester who hits it would rate correctness on an artifact covering none of the code, so
  question (b) asks directly whether they saw an implausible coverage number and whether the tool told
  them or they noticed themselves.
- **Whether `init`'s printed settings work as a safety net.** They exist for exactly this failure and
  have never been tried by anyone but their author.
- **Dismissal rate**, as a check on round 5's finding that 58% of sampled findings were noise.

## Already found, before shipping

Rehearsing the kit caught a defect on the first screen a new user sees. `init` guessed
`root_package = httpx` correctly, flagged `source_paths`, and suggested **`tests/`** — because the hint
picked the directory with the most `.py` files and a test suite is larger than the package it tests.
Following it would have produced the exact silent failure the warning one line above describes. Fixed
before release: the hint now names the directory that *contains* the package.

That is one defect found by rehearsing an onboarding path that five calibration rounds never touched,
which is the argument for this round existing.

## Provenance

- Kit: `scripts/usertest.py kit`, built at `/tmp/archagent-usertest-2026-08-23`
- Under test: archagent `1.0.0rc1`, tag `v1.0.0rc1`, published to PyPI 2026-08-23
- Rubric: `usertest-v1`
