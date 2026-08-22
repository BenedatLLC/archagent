# Calibration round 4 — paperless-ngx

Target: paperless-ngx at `v3.0.5` (`8fb73b270`), 727 source files under the configured paths — Django apps
under `src/`, an Angular frontend under `src-ui/src`. Roughly three times the size of round 3's target.
First fresh repository since round 3, and the first round run under a changed protocol.

**There is no calibration number. The human review was not independent, and the fault is in how the round
was set up.** What the round did produce is a different measurement this project has never had, a valid
artifact score from a new kind of instrument, and nine filed issues.

## What went wrong, and it was procedural

One review brief was generated. The blind model judge was handed that exact path and filled it in. The
human reviewer was then told "the brief is at `review-brief-2026-08-17.md`" — the same file, now containing
a complete set of scores and reasoning.

The returned review is that document edited: the same six `why` blocks, the same structure, corrections
threaded through the judge's text, one score changed (`diagrams` 5→4) and a new *Overall observations*
section appended. `diff` between the two files is a list of amendments, not two independent readings.

**§14 of the design predicts this exactly.** Its "There is no sample review, deliberately" section says a
completed sample carries score anchoring, finding anchoring and effort anchoring — and names finding
anchoring as the one that matters, because "method decides findings". The round handed a reviewer a
completed sample and then measured agreement with it.

Two consequences, both permanent:

- **Round 4 has no human-versus-judge number**, and cannot acquire one. The reviewer has now read the
  judge's reasoning; a second attempt on this artifact would measure recall, not agreement.
- **paperless-ngx is consumed as a calibration target.** §12 calls fresh repositories a depleting
  resource. This one was spent on a round that cannot produce the number it was run for.

The fix is trivial and should have been in place: **generate two briefs to two paths, and never give a
reviewer a path a judge has touched.** `selfeval.py judged` already writes per-reviewer JSON files to avoid
exactly this collision on the output side; the input side has no equivalent guard.

## What the round did measure: the judge's precision

The edit pass is not a calibration, but it is a **verification of the model judge**, which nothing in this
project has previously attempted. The human checked the judge's claims against the code and amended eight:

| the judge wrote | the code says |
|---|---|
| `settings/__init__.py:719` | `:720` |
| `index.md:216` | `:217` |
| the Config line "lists 98" | lists **94** |
| "~185 distinct keys" | 185, and the command needed `--no-filename … \| sort -u` to produce it |
| "roughly half are absent" | **ninety-one** |
| `settings/__init__.py:727` | `:728` |
| "all sixteen management commands" | fifteen modules, plus a shared `CryptMixin` |
| "HOLDS" on the ownership claim | holds *for the ownership boundary* — not default-denied is not the same as unauthenticated |

**The substance was right and the precision was not.** All five load-bearing claims the judge chose to
check were correctly adjudicated, including the one genuine failure (the config-completeness claim). Six of
the eight corrections are citations off by one line or counts off by a few.

That is the resolves-but-imprecise pattern — the thing this project has tracked in artifacts since round 2
— appearing in the instrument rather than in the thing being measured. The practical consequence:
**a judge's line numbers and counts should be treated as approximate unless someone re-derives them**, and
a judged finding is a pointer to look at, not a fact to record.

The eighth correction is the most interesting, because it is not imprecision. The judge wrote "HOLDS" where
the human wrote "HOLDS for the ownership boundary" and added a sentence distinguishing *no default-deny*
from *no authentication*. Both readings are defensible; the human's is more careful about what a reader
would take away. That is a difference in standard, not in fact, and it is the kind of thing a calibration
number exists to quantify — which is what this round cannot do.

## The artifact scored well on every instrument

| instrument | score |
|---|---|
| deterministic rubric | **1.00** — first clean score in the project; 727/727 covered, 69/69 globs resolve, zero drift |
| blind model judge (1–5) | **4.33** |
| human (not independent, see above) | 4.17 |
| code-derived checklist | **0.92** — 23 correct, 0 wrong, 2 absent |

The two judged means differ on one criterion of six, which is uninformative given the contamination.

Judge means across rounds, all on `brief-v3`: obstudio 3.67, wardrowbe 3.17, paperless-ngx 4.33. Against a
measured floor of ±0.10 that is a wide spread, and it is confounded by target difficulty. **It is not
evidence that archagent improved**, and should not be quoted as such.

## The protocol change worked, and did not fix what it was aimed at

Round 4 was the first to build its checklist **from the code, by an agent blind to the artifact, before the
artifact existed**. Rounds 2 and 3 built theirs from the defects a reviewer found, which made both
saturate: wardrowbe went 0.12 → 1.00 on fresh generations, obstudio 0.24 → 0.88.

**The construction change delivered validity.** 0.92 is an actual estimate of how much of the system the
artifact conveys correctly. The earlier numbers were not estimates of anything — they measured whether one
artifact repeated another artifact's mistakes.

**It did not deliver headroom.** Two items can move against a two-arm gate needing five. Across three
targets and both construction methods, fresh artifacts now score 0.88, 0.92, 0.94–1.00.

The diagnosis has to change accordingly, and it contradicts what was written after the obstudio probe:
saturation is not mainly an artefact of how checklists are built. **`describe` is accurate enough that a
per-item accuracy instrument cannot discriminate between variants of it.** Construction was a real problem
and not the main one.

**Where headroom remains is completeness.** Zero `wrong` verdicts across all 25 checklist items. Both
misses are silences. Four of the judge's six scores are 4, and two of those are coverage-shaped. The
generating agent declared five under-covered areas itself. Any future two-arm comparison should be scored
on coverage depth, not on factual accuracy.

## Findings, and where they went

Nine issues, [#13–#21](https://github.com/BenedatLLC/archagent/issues). The two that came from running the
round rather than from reading the artifact:

- **[#13](https://github.com/BenedatLLC/archagent/issues/13) — an evaluation can use two different
  archagents and record only one.** The generation ran against the working tree; the human review ran
  against a copy from 18 July with four of the commands `describe` tells agents to run missing. The
  reviewer correctly reported a command as unavailable and reasonably concluded the artifact's note had
  drifted. It had not. **This was initially misdiagnosed here as the released version being behind the
  working tree; it was the reverse** — `v0.3.0` contains all four commands and the command surface at HEAD
  is identical to it. The installed copy was simply old.
- **[#14](https://github.com/BenedatLLC/archagent/issues/14) — make the release trigger mechanical.**
  Evaluations should not require a public release; a release is warranted when the documented usage surface
  changes. Measured: zero commands added since `v0.3.0`.

Seven more from the review itself: the `**Config:**` line as inventory rather than explanation (#15);
`Verification` and `Graduation path` fields for prose invariants (#16); separating assignment coverage from
explanatory coverage (#17); provenance for generated counts (#18); a disposition for discovered risks
(#19); making the invariant table canonical (#20); a runtime context diagram alongside the generated map
(#21).

Two archagent defects the round surfaced were fixed during it rather than filed: `configscan` now follows
one hop through a project's own helper functions (98 keys → 176 on this target, and `drift` now reports 82
undocumented ones where it previously certified an incomplete list as complete), and `lint-docs` reports an
invariant ID cited with no matching row.

## Limits

- No calibration number, for the reason above.
- One judge, one artifact, one target. The judge-precision result is eight corrections on one review.
- The checklist and the artifact were produced concurrently by two agents of the same model. They could not
  read each other, but they are not independent in the way two different models would be.
- The artifact is partial by declaration — five areas covered at less depth, which is a completeness
  question the instruments here handle poorly, since the checklist asks about facts rather than depth.

## What round 5 needs

1. **Two briefs, two paths.** The one-line fix for the failure above.
2. **A completeness instrument.** Every accuracy instrument is now saturated. Without something that
   measures depth, the two-arm comparison in `computed-claims.md` §8 stays blocked whatever target is used.
3. **A fresh repository.** Round 4 spent one and returned no calibration number, so the count of usable
   rounds is still two of a target six.
