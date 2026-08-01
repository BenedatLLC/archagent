# Held-out defect study — run 1 (2026-08-01)

The analysis pre-registered in `docs/designs/evaluating-archagent.md` §7.1, run for the first time.
**This record is permanent.** A held-out study whose disappointing runs quietly disappear is not held out,
so run 1 stays here whatever later runs say.

## Result

| repo | scored files | flagged | RR | 95% CI | strata used | predicts |
|---|---|---|---|---|---|---|
| poetry | 112 | 17 | 0.99 | [0.44, 2.40] | 7, 8 | no |
| scrapy | 137 | 13 | 0.95 | [0.41, 2.30] | 7, 8, 9 | no |
| flask | 22 | 1 | — | — | none usable | excluded, see below |
| prettier | — | — | — | — | — | not run, see below |

**No evidence either way — and that is a statement about the study, not about Check A.** Both intervals
comfortably contain 1, but they also contain a doubling and a halving. An interval that wide cannot
distinguish "no effect" from "a large effect we lacked the data to see". Nothing here licenses a claim in
either direction, and in particular it does **not** license dropping the complexity axis.

Secondary (exploratory, per §7.1 — not a basis for any claim): counting *all* commits rather than
defect-fixing ones gives RR 1.44 [0.85, 2.30] for poetry and 1.18 [0.86, 1.67] for scrapy. Consistent with
flagged files simply being busier, which is what the stratification is supposed to remove and what a larger
sample would settle.

## Why it is underpowered, and what that says about the design

After stratification, poetry compares **10 flagged files against 12 controls** and scrapy 13 against 26.
Two causes, both structural rather than accidental:

1. **Only the top deciles are usable.** Check A requires top-quartile churn, so no flagged file exists in
   deciles 0–6 and those strata drop out. This is correct — within the top deciles the flagged/unflagged
   split is driven by the *complexity* axis, which is exactly the question worth asking. But it means the
   analysis only ever uses the top ~30% of files.
2. **The repositories are too small.** 112 and 137 scored files leave ~11–14 files per decile, of which the
   controls in a usable stratum number a dozen at best.

The binding selection criterion is therefore **scored files, not years of history** — which the
pre-registration missed. Flask is a mature project with thousands of commits and 22 scored files in
`src/flask`; every one of its strata fell below the five-control minimum.

## Deviations from the pre-registration, and their honesty status

- **Flask excluded for power.** Caught at the *flag* step, before any outcome was computed: 22 scored
  files cannot support decile stratification. Determinable without seeing a single outcome, so this is a
  power criterion rather than a result-driven exclusion.
- **Poetry and scrapy were not.** Their thinness was equally visible at the flag step and I did not act on
  it until after seeing the outcomes. Recording that plainly: had these come out strongly positive, the
  same sample sizes would have been just as inadequate, and it would have been correspondingly tempting not
  to notice.
- **Prettier not run.** The history walk failed at the cutoff and the harness refused to record a flagged
  set rather than record an empty one — the guard added after the same failure was silently recorded as
  litellm's corpus baseline. Needs a longer walk budget or a warmed clone; it is not an exclusion.

## What run 2 needs

Larger held-out repositories, so that a usable stratum holds hundreds of files rather than a dozen.
**Run 1 is not deleted or replaced** — §7.1's rule against swapping a held-out set exists precisely for
the situation where the first numbers disappoint, and the distinction being drawn here is that the sample
was too small to answer the question, which was visible before the answer was.

Candidates with no prior contact and enough scored files: `ansible/ansible`, `home-assistant/core`,
`pandas-dev/pandas` (Python), `elastic/kibana` (TypeScript). Adding them makes run 2 an *additional* set
reported alongside run 1, not a substitute for it.

A power calculation should also be part of the manifest rather than discovered afterwards: given a target
effect size, how many files per stratum are needed?
