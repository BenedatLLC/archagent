# obstudio saturation probe — results (2026-08-17)

Pre-registered in `PREREGISTRATION-obstudio-probe.md`. One fresh generation at `88aebe8`, one blind judge,
17-item checklist.

**Result: 0.88 — 15 correct, 0 wrong, 2 absent.**

## The pre-registered thresholds did not cover this

I set ≥ 0.9 for "saturated" and 0.5–0.8 for "real headroom", and **left 0.8–0.9 undefined**. The result
landed in the gap. That is a defect in the pre-registration, and stating it is better than retro-fitting a
bin around the number.

**The decision does not turn on the score, and that resolves it.** The operative quantity for step 3 is how
many items *can move*, against a gate that needs five. Two items are `absent` and none are `wrong`, so **at
most two can move, and five are required.** obstudio cannot support the two-arm comparison, for the same
reason wardrowbe could not.

## Saturation is systematic, not a wardrowbe quirk

That was the question the probe existed to answer, and it is answered.

| target | original artifact | fresh generation |
|---|---|---|
| wardrowbe | 0.12 | 1.00 / 1.00 / 0.94 |
| obstudio | 0.24 | **0.88** |

Both checklists are roughly two-thirds defect-derived — items written from what one artifact got wrong.
Both jump by 0.6–0.9 when a fresh artifact faces them, because current `describe` does not repeat those
particular mistakes. **A defect-derived checklist cannot serve as the instrument for a two-arm comparison**,
whatever repository it is built for. The fix is the construction, not the target: a checklist built from
reading the code is not selected for what current `describe` happens to get right, so it does not collapse
this way.

## What the fresh artifact got right that the original did not

Worth recording, because it is a result about archagent rather than about this design.

- **Both security items.** `cors-is-wide-open` and `websocket-accepts-any-origin` — the strongest findings
  of calibration round 2, which the original artifact missed entirely and which neither the human reviewer
  nor the author found. The fresh artifact carries both.
- **The whole resolves-but-wrong class.** `rest-can-clear-the-store`, `four-state-changing-http-routes`,
  `wiring-happens-outside-cmd`, `store-serialises-with-four-locks`, `ui-and-skills-are-embedded-separately`
  — every one of the round-2 factual defects, correct.
- **Zero `wrong` verdicts.** The original had eight.

**Confounded, and the write-up should not pretend otherwise.** The originals were generated months earlier
under earlier prompts, and several `describe` rules have been added since — the five claim rules from round
2, the diagram, contract-enumeration and ownership rules from round 3. This is consistent with those rules
working, and it is equally consistent with a stronger model or a longer run. One generation cannot separate
them.

## The two items still missing

- **`per-skill-scripts-hold-real-logic`** (`serious`) — the artifact says "One implementation, three shims …
  There is no duplicated logic", scoped to `observe_report.py` and never claiming those are the only
  per-skill scripts. The four substantive validators (2,616 lines) are simply undescribed. The judge placed
  this on the `absent`/`wrong` boundary explicitly.
- **`validation-is-cancelled-only-by-reset`** (`moderate`) — not addressed.

Both are omissions, which remains the class no mechanical instrument reaches.

One item is worth flagging as a judgement rather than a pass: the artifact reports **35** non-test Go files
under `observer/` where the key says 57 including tests, with the command shown and the figure used
consistently in three places. The judge scored it `correct` on scope-consistency. That is defensible and it
is also exactly the kind of call a stricter reader would make differently — and it is the count item, which
is now `conditional`.

## Consequence

**Step 3 cannot be run on either existing target.** Both instruments are saturated, and the reason is how
they were built.

The way forward is the one the alternative branch already pointed at: **calibration round 4 on a fresh
repository, with a checklist built primarily from reading the code rather than from an artifact's
defects.** That gives an uncontaminated instrument, a non-saturating one, the generalisation test §18 asks
for, and progress on what Appendix A names as the standing binding constraint — 2 calibration rounds of a
target six.

The probe cost one generation and one judge and saved a six-generation experiment that would have produced
a null result for a reason unrelated to the design under test.
