# Step 3 — not run, and why (2026-08-16)

**Step 3 as pre-registered cannot be run on this target: the instrument is saturated and the baseline is
nearly clean.** Running it would have cost roughly 1.2M tokens of generation to produce a null result that
was arithmetically determined before the first agent started.

## Two instrument fixes first

Both defects step 2 exposed are fixed.

**Conditional checklist items.** An item phrased *"if the artifact states a count, is it right?"* is
answered correctly by an artifact that declines to state an incidental count, and the scorer counted that
`absent` as a miss. Items now carry `conditional = true`, and `absent` on one is a pass. Three items in the
wardrowbe checklist and one in obstudio's are marked.

**Ambiguous `require` lists in the recurrence suite.** `require` is conjunctive, which reads wrongly to
anyone writing one pattern per phrasing — and it produced a false alarm on an artifact that covered
ownership with its own ADR. `ambiguous_requires` now flags any entry whose `require` patterns share terms,
with a test over the real entries. The fix is one pattern with an `|`, and the guard says so.

## The fix changes the arm-A baseline, and that is what stops step 3

With conditional items scored correctly, the three step-2 artifacts — generated under the **current** ADL —
score:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| checklist | **1.00** | **1.00** | **0.94** |
| recurrence entries recurring | 0/10 | 0/10 | 0/10 |

The pre-registered gate for step 3 was *"items move from `wrong`/`absent` to `correct` on at least five
more items than move the other way."* **At most one item can move.** Two arms cannot be separated by five
items when one arm is already at sixteen out of sixteen.

This is not a result about the ADL change. It is the wardrowbe checklist reaching its ceiling: sixteen
items, written from an artifact generated months earlier, which current generations get essentially all of.

## So how much room is there at all? One defect in fifteen

Rather than assume, this was measured on an endpoint that is not saturated: **how many factual assertions
does a freshly generated artifact get wrong?** Fifteen predicate claims were written against run 1's
assertions and checked (`claims/arm-a-run1.md`).

**14 of 15 hold. One is false**, and it is precisely the class this design targets:

> `index.md:140` — *"The only place a third-party API is called: the OpenAI-compatible model endpoints and
> Open-Meteo."*

The code calls three hosts from `services/` and `workers/`: `open-meteo.com`, plus
`nominatim.openstreetmap.org` for geocoding and `exp.host` for push notifications. The enumeration omits
two, and *"the only place"* is an exhaustiveness claim — the exact shape `describe` rule 3 already warns
about and this design would force through a command.

The mechanism works. The question is whether a 1-in-15 defect rate justifies the ADL complexity, and that
is a judgement rather than a measurement.

## The power arithmetic, which is what actually settles it

If arm A produces false assertions at ~7% and arm B eliminates them entirely — the most favourable
assumption available — then with 15 claims per artifact and 3 artifacts per arm, the expected counts are
about 3 against 0. Fisher's exact on 3/45 versus 0/45 gives p ≈ 0.24.

**Detecting this at conventional significance needs roughly ten defects in arm A, so about 150 claims per
arm** — ten artifacts per arm, or a target with a much higher defect rate. Neither is what step 3 was
scoped to.

## What this does and does not say about the design

**It does not say the change is worthless.** It found a real exhaustiveness error in a fresh artifact in
about a minute, and step 1 showed the predicate form reaching 13 of 28 recorded defects. The mechanism is
sound and cheap.

**It does say the case has to be made on a different basis than "measurably better artifacts on
wardrowbe".** Two bases remain open, and both are honest:

1. **Drift, which has never been measured at all.** The claim that a claims file makes drift mechanical is
   untested, and §16's machinery has never run. A two-revision experiment — change the code, see what the
   claims file catches that `drift` alone does not — has real headroom, needs no new generation, and tests
   the half of the proposal that is not about accuracy.
2. **Targets where the baseline is not already clean.** wardrowbe is a small, conventional
   FastAPI/Next.js application that current generations describe accurately. obstudio, which archagent
   cannot analyse statically at all, scored 0.24 on its checklist. A repository the tool is *bad* at is
   where a mechanism for grounding claims should pay, and that is where the arms should be run.

## Recommendation

**Do not run step 3 on wardrowbe.** Two alternatives, in order of cost:

- **The drift experiment**, which is cheap and tests an untested claim.
- **Two arms on obstudio**, where the baseline leaves room to improve — and which also satisfies §18
  better, since obstudio is not the repository whose defects shaped the predicate design most heavily.

The design's status stays `proposed`. Steps 1 and 2 passed their gates; step 3 is blocked on an instrument
ceiling rather than on the design, and the write-up says which.
