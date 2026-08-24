# End-to-end user test, round 1 — httpx, archagent 1.0.0rc1

**Status: one worksheet returned 2026-08-23.** The design section below was written before it came back
and is unchanged; the results follow it.

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


---

# Results

**One tester, `docs_path = fallback`.** Read the caveat below before the scores.

| dimension | score |
|---|---|
| ease of use | **2** |
| correctness | **1** |
| completeness | **2** |
| impact | **2** |

Claims actually verified by the tester: **6**. Estimated dismissal rate: **~80%+**. Four distinct
blockers logged. Time from start to readable output: **4 minutes**; total **5 minutes**.

**These are not averaged and there is no `mean()` in the ledger to do it.** `ease_of_use` is a direct
observation of the thing this design measures; `correctness` is a 6-claim spot check. A combined 1.75
would say less than the four numbers do.

## The caveat that governs the whole round

The tester **could not fetch the version-pinned GitHub tree** and fell back to `archagent --help` plus
the installed skill files.

So round 1 did not measure the question it was built to ask. It measured something harder — *can someone
get a result from the CLI's own help and the installed prompts?* — and several of the friction points
follow directly from that. `--agents auto` not detecting Codex reads as a bug in the log, but the README
documents it explicitly (*"no — opt in with `--agents codex`"*); the tester could not read the README.

This is recorded as a comparability key, not a footnote. `docs_path` is one of
`("rubric_version", "archagent_version", "docs_path")`, so a future `published` round is **refused as a
series** against this one rather than quietly compared.

## What the tester got right — verified against the source

Three findings, all reproduced and confirmed before being recorded.

**Endpoint findings fire inside docstrings** ([#33](https://github.com/BenedatLLC/archagent/issues/33)).
Eight of eleven, all `MED`. `httpx/_urls.py:185` is `httpx.URL("https://[::ffff:192.168.0.1]")` inside a
`"""` block demonstrating URL normalization; `asgi.py:71` is inside a markdown code fence *inside* a
docstring. `_endpoint_in` skips lines that *start* with a comment marker and has no notion of being
inside a string. This is #31 part 1 not going far enough: the reserved-range and test-path fixes both
worked — the two surviving test findings are correctly `LOW` — but a documentation example is the same
category of thing and was never considered.

**`investigate` prints the wrong questionnaire**
([#34](https://github.com/BenedatLLC/archagent/issues/34)). A `change-prone-file` brief reports churn and
complexity correctly and then asks the reader to find duplicated enum declarations and compare them
member by member. Header, evidence and triage reason are all sign-specific; only the question list falls
through to a default, and nothing catches that.

**`status` overstates coverage** ([#35](https://github.com/BenedatLLC/archagent/issues/35)). 100% in a
full-width green bar, with its own depth table marking the same subsystem `thin` at 3.6 words per file.
This is the round 5 defect recurring one level up — that round fixed the *artifact* that quoted the
number, not the tool that presents it, so the next artifact would have made the same claim.

## What the tester got wrong

**`archagent --version` is implemented.** The worksheet says twice that it is missing. It works, and
prints `1.0.0rc1` from the tester's own shim.

The reconstruction is in their own log: the install line reads `uv tool install --force
archagent==1.0.0rc1`, and `--force` implies an earlier install. A plain `uv tool install archagent`
resolves to **0.3.0**, which predates `--version` (#7). So the *experience* was real and is a genuine
consequence of the pre-release trap — they hit 0.3.0 first — but the claim about 1.0.0rc1 is false.

Worth stating plainly because it is the one place this round would have entered a wrong fact into the
record, and the guard against it was reproducing every checkable claim rather than trusting a careful
reviewer.

## What this round actually establishes

**The `init` safety net works, and is the tool's best-rated feature.** It was named as *the single most
useful thing* the tool reported: it caught `source_paths = ["src"]` on a root-package layout, said no
Python files were there, suggested `./`, and explained the vacuous-pass failure. The tester set `["."]`
and moved on. That path is 24 hours old — the suggestion said `tests/` until the pre-release rehearsal —
and it is now the only part of the tool a first-time user rated highly.

**~80% dismissal, against round 5's 58%.** Different target, different rater, n=1, so not a trend. But
both rounds point the same way, and #31 was supposed to move this. It did not move it enough, and
[#33](https://github.com/BenedatLLC/archagent/issues/33) is why: the recommendations got better while the
*population* still contains findings that should never have been raised.

**"Would you use it?"** — *"Only after significantly better finding precision and prioritization. I would
keep the init source-path check; I would not use the current evaluator as an action list without
substantial manual review."*

## Fixed, 2026-08-23

All three, measured on the same checkout: **httpx goes from 46 findings to 17**, with **zero**
production-code endpoint false positives left.

| issue | fix | effect on httpx |
|---|---|---|
| #33 | docstring line ranges from an `ast` walk; findings collapse per file; RFC 2606 subdomains | endpoint family 34 → 5, all `low`, none in production code |
| #34 | brief questions and ratings are per sign, with **no default** | `change-prone-file` asks about churn, not enums |
| #35 | table says "files claimed by a glob"; `Described` moved directly under it; green withheld when depth disagrees | 100% no longer reads as health |

Two of the three grew a second finding while being fixed, which is the pattern this round shares with
round 5. #33's docstring filter revealed that httpx's URL suite names addresses on 23 lines of one file —
as 23 findings that is a census of a single fact — so findings now collapse per file. And #34's real
defect was not the wrong questionnaire but that **nothing could notice**: header, evidence and triage
reason were all sign-specific and only the questions fell through. The test now reads the triaged signs
out of `evaluate.py` rather than restating them, so a new one cannot inherit someone else's questions.

`_BRIEF_QUESTIONS` has no default, on the same reasoning as `METRIC_KEYS` in the ledger: printing another
sign's questions is worse than printing none, because they read as authoritative and send the reader
looking for something that is not there.

## What to change before round 2

1. ~~Fix #33, #34, #35~~ — **done**, see above.
2. ~~Make the instructions self-contained~~ — **done.** The kit now bundles the whole doc set at the tag
   (61 files, `git archive`, structure preserved so relative links resolve on disk). The whole set, not a
   selection: choosing the three pages a tester "needs" would replace *which page do I need?* with a
   curated answer. `docs_path` gained a **`bundled`** value distinct from `published`, because rendering,
   cross-link navigation and in-page search are part of whether documentation is usable and a kit reader
   has none of them — collapsing them would let a bundled round stand as evidence about the GitHub
   experience, which is what most users will actually have.
3. Recruit a tester with **no prior exposure**. This one authored the tool, which is recorded in the
   ledger and is the strongest limit on what round 1 shows — the scores are harsh, but a stranger has
   friction an author cannot feel.

## Provenance

- Worksheet: `usertest/httpx/worksheet-httpx-b5addb6.md` in the data repo
- The report they read: `usertest/httpx/evaluate-report-b5addb6.txt`; their config alongside it
- Ledger: `usertest/usertest.csv`, run `2026-08-23-httpx-usertest` — **a separate ledger**, see
  `tests/usertest_ledger.py` for why it is not joinable with `ledger.csv`
