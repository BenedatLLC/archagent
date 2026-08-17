# Drift experiment — pre-registration

**Committed before the code is advanced and before either instrument is run against the new revision.**

## The claim under test

`computed-claims.md` asserts that a claims file *"makes much of the drift computation mechanical"*. That
has never been measured. `archagent drift` exists and works; the question is whether a claims file catches
staleness that `drift` alone does not.

## Why this design has nothing to rig

**The change is real.** wardrowbe's own history continues past the pinned revision: 21 commits, 95 files,
4,589 insertions between `wardrowbe-v1.7.0` (`eda843f`) and `wardrowbe-v1.8.0` (`f2c676b`), written by the
project's developers with no knowledge of archagent. This is the as-of evaluation §5 of
`evaluating-archagent.md` describes: later history used as an outcome nobody could have seen at the time.

**The artifact and the claims file are both fixed and both predate the question.** The artifact is
generation run 1 from step 2, produced against v1.7.0. The claims file (`claims/arm-a-run1.md`, 15 claims)
was written against v1.7.0 **for a different purpose entirely** — the arm-A defect-density power check —
before the v1.8.0 diff had been looked at. Neither can have been shaped by what v1.8.0 happens to change.

Nothing is authored between now and the measurement.

## Procedure

1. **Baseline at v1.7.0.** Record what `drift` reports and what `claims check` reports, unchanged. Both
   already have non-zero output; the measurement is the *delta*, not the absolute.
2. **Advance the code to v1.8.0**, leaving `architecture/` and the claims file exactly as they are.
3. **Run both instruments again.** Record what each newly reports.
4. **Establish ground truth independently.** Read the v1.7.0→v1.8.0 diff and enumerate every change that
   makes a statement in the artifact wrong or incomplete. This is done from the diff, and the list is
   written down before comparing it to either instrument's output.
5. **Score.** Of the ground-truth staleness items: how many does `drift` catch, how many does the claims
   file catch, and what does each catch that the other misses.

## What counts as a catch

A finding **catches** a ground-truth item if it points at that item specifically enough that a reader would
know what to revise. "Undocumented module `backend/app/services/upload_manager.py`" catches a new service;
a general increase in a count does not catch anything.

A finding that fires on something the diff did not change is a **false positive**, and both instruments'
false positives are counted the same way.

## Predictions, recorded now

1. **`drift` catches structural staleness — new and moved files, new modules, changed declared edges — and
   the claims file mostly does not.** A claims file says nothing about a file that did not exist when it
   was written.
2. **The claims file catches value staleness — counts and enumerations that moved — and `drift` mostly does
   not.** `drift` compares globs and declarations against the tree; it does not know that the artifact said
   "104 routes".
3. **The two overlap little.** If they overlap heavily, the claims file is redundant and this design is
   not worth its complexity.
4. **The claims file's recall is limited by its size.** Fifteen claims cover a fraction of a 27,000-word
   artifact, so the measured recall is "what a 15-claim file catches", not what a complete one could. This
   is stated now so it cannot be presented later as a property of the mechanism.

**The result that would argue against the design**: `drift` catches most of the ground-truth items on its
own, or the claims file's catches are all things `drift` also reports.

**The result that would argue for it**: a class of staleness that only the claims file reports, in changes
nobody selected for that purpose.

## What this cannot answer

One revision pair on one repository. It says whether the mechanism catches anything `drift` misses on this
change; it does not estimate a rate, and a 21-commit release is not a typical single commit.
