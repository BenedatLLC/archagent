# Computed claims — the evaluation record

Design: `docs/designs/computed-claims.md`, **status: deferred (2026-08-22)**. The mechanism works and is
measured; the case for its cost is not made. §9.1 of the design states what would reopen it.

Everything here is kept whatever the outcome. A deferred design with evidence is worth more than a silence
somebody re-derives in six months.

## What was run, in order

| # | run | pre-registered | result |
|---|---|---|---|
| 1 | Step 1, value-based claims | prediction ≥17 divergences | `RESULTS.md` — **8, gate not met**. A claims table only catches a defect when the artifact commits to a *number*, and most fabricated claims are not numbers. |
| 2 | Step 1, predicate redesign | `PREREGISTRATION-2.md` — 12 defects named individually, gate 10 of 12 | `RESULTS-2.md` — **12 of 12, plus one predicted not to be caught. Gate met.** |
| 3 | Step 2, generation variance | `STEP2-METHOD.md` | `RESULTS-step2.md` — three independent generations differ on **1 checklist item of 16**; the deterministic rubric cannot see the difference at all. |
| 4 | Step 3, two arms | gate: 5 net items | `RESULTS-step3.md` — **not run.** The baseline scores 1.00/1.00/0.94, so at most one item can move. |
| 5 | Drift experiment, wardrowbe | `PREREGISTRATION-drift.md` | `RESULTS-drift.md` — real history, 21 commits: **`drift` 3 of 8, claims 0 of 8.** The broad drift claim is not supported. |
| 6 | Drift experiment, obstudio | `PREREGISTRATION-obstudio-drift.md` | `RESULTS-obstudio-drift.md` — **`drift` byte-identical, claims caught it.** `drift` can check 0 of 16 Go closed collections. |
| 7 | obstudio saturation probe | `PREREGISTRATION-obstudio-probe.md` | `RESULTS-obstudio-probe.md` — 0.88 fresh against 0.24 original. Saturation is systematic. |

## The four results worth carrying out of this

**Predicate claims over closed sets are the load-bearing form.** Values were the first design and reached 8
of 28 recorded defects; predicates reach 13. The difference is that most fabricated claims are behaviours,
not numbers, and a `set` or an `absent` can refute a behaviour.

**The authoring error rate is the real cost.** 27% of commands measured something other than what the prose
meant, 20% after the redesign. In this retrospective those errors were loud, because the recorded value
came from the prose. In production they are silent, because the recorded value comes from the command.

**The safety rules are nearly free.** One command refused by static validation across the entire
evaluation. The facts that could not be expressed were beyond *any* command — import graphs, properties of
every code path, reasons, hedges — not beyond the allowlist.

**Two of three blind-spot cases were ordinary tool gaps.** paperless-ngx's config surface was closed by
teaching `configscan` to follow helper wrappers: 40 lines, no ADL change, and `drift` went from certifying
an incomplete list as complete to reporting 82 undocumented keys. Only the unparsed-language case survives,
and there the comparison is claims versus language support.

## Method notes that outlived the design

Recorded because they apply to any future evaluation here, not only to this one:

- **Pre-register the prediction, by name where possible.** Attempt 2's gate named its 12 defects
  individually rather than setting a count, so the result could not be reached by unrelated finds.
- **An instrument's own defects show up as clean results.** Two recurrence entries and a checklist scoring
  rule were found wrong only because a run reported something implausible.
- **Measure the headroom before running the experiment.** Step 3 was retired by fifteen claims and a Fisher
  exact test, not by six generations.
