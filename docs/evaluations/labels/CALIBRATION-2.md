# Calibration round 2 (2026-08-22) — groups B and C, labelled for the first time

14 findings from `archagent` at `fe2222b` and `fastapi-template` at `0.9.0`, labelled by a reviewer
working from a kit containing both repositories at those revisions with their architecture documents,
and with the tool's severity, confidence and recommendation withheld until ingest.

Groups B and C had never been labelled. Before this round, three of roughly twenty signals had any
evidence outside our own judgement: `change-prone-file` from the held-out defect study, and the two
group-F signals from round 1.

## Precision by signal

| signal | n | confirm | partial | dismiss | strict | 95% CI | lenient | 95% CI |
|---|---|---|---|---|---|---|---|---|
| `cycle-subsystem` | 2 | 2 | 0 | 0 | **100%** | [0.34, 1.00] | 100% | [0.34, 1.00] |
| `layer-inversion` | 4 | 2 | 0 | 2 | **50%** | [0.15, 0.85] | 50% | [0.15, 0.85] |
| `unstable-interface` | 4 | 2 | 0 | 2 | **50%** | [0.15, 0.85] | 50% | [0.15, 0.85] |
| `god-component` | 1 | 0 | 1 | 0 | 0% | [0.00, 0.79] | 100% | [0.21, 1.00] |
| `layer-skip` | 3 | 0 | 0 | 3 | **0%** | [0.00, 0.56] | 0% | [0.00, 0.56] |

Overall 6 of 14 strict, 7 of 14 counting the partial. Every interval here is wide enough to be nearly
uninformative on its own; the reasons are where the round's value is.

## The headline is not a precision figure

**Not one of the fourteen measurements was disputed.** Every dismissal affirms what the tool measured
and rejects what it concluded:

> "The measurement is real, but `cli` is deliberately the composition root…"
> "The numeric tier gap reports a skip, but there is no missing intermediate abstraction…"
> "The upward edge is real but reflects the tier assignment, not a production layering defect."

Round 1 was not like this: there, findings were dismissed because the escape came from a different enum,
or because the strings were RFC-frozen constants — the *measurement* was wrong or misattributed 4 times
in 19. Here the extraction is accurate 14 times out of 14, and the judgement layer is carrying every
error.

That is a useful place for the errors to be. It says the static analysis under groups B and C does not
need work, and that the triage, scoping and severity around it does.

## `layer-skip` — 0 of 3, and the three reasons agree

The clearest result of the round, and stronger than `n=3` and `[0.00, 0.56]` suggest, because the three
dismissals are not three independent judgements. They are one mechanism seen three times:

| finding | why dismissed |
|---|---|
| `cli` → `invariant-pipeline` | `cli` is the composition root; a direct orchestration dependency is its stated job |
| `backend-http` → `backend-domain` | no missing intermediate abstraction exists in a small FastAPI app |
| `frontend-app` → `frontend-client` | the generated client *is* the explicit contract; an intermediate layer would not improve it |

`layer-skip` measures distance between declared tiers and infers a missing layer from it. In all three
cases the layer it infers was never intended to exist. A composition root reaching past a tier is
ordinary architecture, and an entry point that adapts commands to subsystems is *supposed* to touch
several of them.

Stated without naming a repository (§18's test): **a skip originating in an entry-point or adapter tier
is not a defect, because reaching across the system is what that tier is for.** That generalises, so
acting on it is not overfitting to these two repositories.

## `layer-inversion` — 2 of 4, and the two failures share a cause

Both confirmations are genuine production inversions: `extraction` (infra) importing `drift` (domain)
via `invscan.py`, and `core/db.py` importing `crud`. Both dismissals are `backend-ops` and
`backend-tests` — operational and test code:

> "Tests must import the domain code and HTTP surface they exercise."
> "Alembic/start-up operations legitimately import model metadata and seed through the domain creation
> path."

Test and migration packages are not layers in the sense the rule assumes. The edge is real; treating
those subsystems as ordinary tiers is the error.

**A caveat on independence.** The worksheet guidance I wrote for this round said that "a test subsystem
depending on the code it tests is what tests are for, and may say more about how the tiers were assigned
than about the code." The reviewer's `backend-tests` dismissal restates that. It should be read as less
independent than the other twelve — I put the idea in front of them. The `backend-ops` dismissal was not
prompted and stands on its own.

## `unstable-interface` — 2 of 4, and possibly confounded

Both confirmations are archagent (`drift`, `extraction`); both dismissals are fastapi-template
(`backend-core`, `backend-domain`). The dismissal reason is consistent and is a real weakness:

> "The domain contains the shared schema and persistence operations, so co-change with core, HTTP and
> migrations is expected when a model changes."

The signal cannot currently distinguish *an interface that is churning* from *a module everything
depends on, changing along with the features that use it*. But the split falls exactly along the
repository boundary, so this may be a property of the two codebases rather than of the signal. Two
repositories cannot separate those. **No action; needs a third repository.**

## `cycle-subsystem` — 2 of 2, both already accepted

Both were confirmed, and both are recorded as accepted costs — archagent's `drift ↔ extraction` in ADR
0003, and fastapi-template's superuser-seeding cycle. The reviewer scored them `confirm` with a note,
following the brief's instruction that a real-but-accepted finding is still a true finding.

That instruction was added the same day, in response to a question about how to handle exactly this. It
worked, and it is worth keeping: had these been dismissed, the round would have taught us that correct
findings are wrong.

## What was decided

See `docs/designs/evaluating-archagent.md` §22.9. In short: scope `layer-skip` and `layer-inversion`,
leave `unstable-interface` alone pending a third repository, and leave the extractors entirely alone.

## Provenance

- Worksheet: `spotcheck/worksheet-2026-08-22.md` in the evaluation data repo, 14 items, group filter `B,C`
- Labels: `labels/archagent.jsonl`, `labels/fastapi-template.jsonl`
- Findings captured by archagent `fe2222b`; both captures verified deterministic across two runs
- Reviewer: jeff, 2026-08-22. Severity, confidence and recommendation withheld until ingest.

**One process failure worth recording.** The first completed copy of this worksheet was destroyed by
`spotcheck.py kit`, which rebuilt over the review directory without checking whether the sheet had been
filled in. The review had to be redone. `selfeval.py` has refused to clobber a completed brief since
round 3 for this exact reason and the new command shipped without the equivalent guard; it now has one,
with a test.
