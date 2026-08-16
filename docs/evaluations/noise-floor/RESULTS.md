# Judge noise floor — first measurement (2026-08-16)

Design §15 makes three acceptance rules turn on the word "significant", and none could be evaluated
without this number. It also decides how to read the two calibration rounds already collected.

**Method.** Six independent judgings of the *same* artifact — wardrowbe at `wardrowbe-v1.7.0`. Artifact,
code, brief and prompt byte-identical across every run; only the model varies, and only between groups.
Four Opus (one of them the original round-3 judge), two Sonnet. Each ran blind, in parallel, writing to
its own file, told not to read the others.

## Results

| criterion | opus-r0 | opus-r1 | opus-r2 | opus-r3 | sonnet-r1 | sonnet-r2 |
|---|---|---|---|---|---|---|
| accuracy | 3 | 3 | 3 | 3 | 3 | 3 |
| completeness | 3 | 3 | 4 | 3 | 4 | 4 |
| prose | 4 | 4 | 4 | 4 | 4 | 3 |
| diagrams | 3 | 3 | 3 | 3 | **2** | **4** |
| invariant_strength | 3 | 4 | 3 | 3 | 4 | 3 |
| invariant_criticality | 3 | 3 | 3 | 3 | 3 | 3 |
| **mean** | 3.17 | 3.33 | 3.33 | 3.17 | 3.33 | 3.33 |

## The mean is stable; the criteria are not

**Six runs, means from 3.17 to 3.33 — sd 0.10.** That is a tight floor, and it is the number §15 needs.

**Individual criteria are a different story.** `diagrams` ranged 2 to 4 across two Sonnet runs on identical
input — the full width of the usable scale. `completeness` and `invariant_strength` each moved a point.
Only `accuracy` and `invariant_criticality` were unanimous across all six.

That combination is the result worth carrying, and it points in two directions at once:

- **Aggregate scores can gate things.** A mean that reproduces to ±0.1 is a usable instrument.
- **Per-criterion scores cannot.** A single criterion moving two points on identical input means any rule
  of the form "criterion X must not decline" is measuring the die, not the artifact.

It also retroactively qualifies the calibration statistics. Round 3's headline was *exact agreement 1/6*,
computed criterion by criterion — against a floor where criteria move by 1–2 points between identical
runs, that number was always going to be small, and it says less about human-vs-judge disagreement than it
appeared to. **Within-one-point agreement (5/6) was the meaningful figure all along**, and the mean gap is
the number to track.

## The human-judge gap survives

Human 4.17, judges 3.28 — a gap of **0.89, which is 9× the floor**. Whatever that gap is, it is not run
variance. Two rounds have now shown the same direction (round 2's gap was −0.33), and this measurement
says the effect is real rather than noise.

What it does *not* say is what causes it. Round 3's own finding remains the best explanation available:
the human sampled five load-bearing claims and found them all sound, while the judges walked the artifact
and found claims made in passing to be wrong. That is a difference of method, and the `accuracy` criterion
selects for it.

## Opus and Sonnet agree on the number and differ in how they get there

Opus mean-of-means 3.25, Sonnet 3.33 — no meaningful difference at n=4 and n=2.

But **Sonnet is the noisier judge per criterion** (`diagrams` sd 1.41 against Opus's 0.00; `prose` 0.71
against 0.00), and it was the only run to find that `backend-domain.md` claims schemas for seven of eight
models where five exist — a defect the human and all four Opus runs passed over.

Higher variance and a unique find are the same property seen twice. On this evidence a cheaper model is
usable for the *aggregate*, and a panel of mixed models finds more than replicates of one.

## What this cost, and what it implies for round 4

Six judgings, ~470k subagent tokens, ~15 minutes wall clock in parallel. That is cheap next to a
calibration round, which additionally consumes a fresh repository and a human's afternoon.

Practical consequences:

1. **Report the mean, and report it with ±0.1.** Per-criterion scores belong in the write-up as *findings*,
   not as measurements.
2. **§15's "no significant decline" gate should read on the mean.** A per-criterion gate is unusable at
   this floor.
3. **Prefer a mixed panel to replicates.** Two models found strictly more than four runs of one.
4. **Re-measure on a different artifact.** This is one artifact whose scores cluster at 3–4; the floor may
   be wider for an artifact scoring in the middle of each criterion, and narrower at the ends.

## Limits

- One artifact. The floor is not established as a constant.
- Generation variance is **not** measured. This says how much a *judging* moves; whether describing the
  same repository twice produces artifacts of different quality is the other half and costs a describe
  pass per replicate.
- `opus-r0` is the original round-3 judge, run days earlier under the same prompt but not the same
  session. Treated as a replicate; it sits at the bottom of the range, which is the conservative direction.
- Two Sonnet runs is enough to observe higher variance and not enough to estimate it.

## Defects the replicates found that the round-3 reviewers did not

Recorded in `../selfeval/wardrowbe/DEFECTS.md` (#16–19). Briefly: a paragraph in `frontend-tests.md`
corrupted by shell command-substitution during an edit; "65 backend Python files" against 125; "schemas
for seven of eight models" against five; and image access described as signed-URL-*instead-of*-session
when the code has three paths including family membership.

Six independent readings of one artifact found four defects that two careful readings missed. That is an
argument for panels, and it is also a reminder that the artifact was reviewed twice and called accurate.
