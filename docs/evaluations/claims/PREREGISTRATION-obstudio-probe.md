# obstudio saturation probe — pre-registration

One question, one generation, one judge: **does a freshly generated obstudio artifact saturate the
17-item obstudio checklist the way a fresh wardrowbe artifact saturated its own?**

wardrowbe went 0.12 on the original artifact to 1.00 / 1.00 / 0.94 on three fresh generations, because
roughly two-thirds of its checklist items were written from the original's defects and current `describe`
does not repeat them. If that is systematic rather than a wardrowbe quirk, no existing checklist can serve
as the instrument for a two-arm comparison, and the step-3 question needs a checklist built from the code
rather than from an artifact's mistakes.

## Setup

obstudio at `88aebe8` — the revision the checklist was written against. A copy of the checkout with the
existing artifact removed before the copy, `archagent init` run to scaffold, and the same `describe`
instructions and constraints as the step-2 generation runs. One blind judge on the 17-item checklist.

## Thresholds, fixed in advance

- **≥ 0.9** — saturated. Confirms the effect is systematic. obstudio cannot be the step-3 target, and
  calibration round 4 with a code-derived checklist is the way forward.
- **0.5 – 0.8** — real headroom. obstudio works as a step-3 target now, and the two-arm experiment can run
  without spending a fresh repository.
- **< 0.5** — headroom, and also a signal that current `describe` is materially worse on a repository
  archagent cannot analyse, which is a finding in its own right.

## What this cannot answer

One generation. Step 2 measured generation variance at about one checklist item in sixteen on wardrowbe,
so a single run is a usable point estimate for a saturation question but not for anything finer.
