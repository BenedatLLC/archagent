# Rough notes — the evaluation process discussion (2026-08-13/15)

Working notes behind the §18–§21 rewrite of `evaluating-archagent.md`. Kept because the reasoning is
denser than what belongs in the design doc, and because several conclusions rest on measurements that are
cheaper to record than to re-run. Not maintained; the design doc is the current statement.

## Where the discussion started

Two questions: what should happen next, and how do we avoid tuning archagent to whichever repository we
last looked at.

State at the time, measured rather than recalled:

- **Evidence existed for 3 of ~19 signals.** `change-prone-file` (held-out defect study, 3 of 4 powered
  repos), and group F's two signs (19 labels, one reviewer, 17 of them litellm). Groups A, B, C, D — about
  16 signals — had **zero labelled findings**.
- That is structural, not an oversight. A–D read `**Service:**`, `**Tier:**`, `**Connects:**` from
  subsystem documents, and **no corpus repository has an artifact at all** — they are evaluated from
  `paths` config alone. Those signals cannot fire on the corpus no matter how many repos are added.
- **Nothing could measure improvement.** Every prompt change of the preceding week (diagram captions, the
  five claim rules, orientation, grounding abstractions) came from one reviewer finding one instance, and
  none had been shown to change artifact quality. The deterministic rubric sat at 1.0 on archagent and
  moved 0.037 across a week of substantive work, so it could not referee.

## The proposed framework, and what changed in review

The proposal: three validation levels; calibration runs on fresh repos judged by both an agent and a
human; scoring runs on known or fresh repos judged by an agent; a recurrence suite in the data repo;
objective fixes always accepted, subjective ones gated on before/after; updates evaluated as commit N →
N+x; a master table of runs.

Changes argued for and adopted:

**Swap which instrument proves what.** The original had the rubric proving improvement and the recurrence
suite guarding regression. The rubric mean carries generation variance plus judging variance, neither
measured; a plausible prompt effect is ~+0.3; with N=3–5 repos a paired test has almost no power. The
recurrence suite is binary and per-defect, tests the change directly, and needs no judge. So the
recurrence suite proves the effect and the rubric guards against collateral damage ("no significant
decline"), which is a far weaker and achievable claim. Corollary: the noise floor stops being optional,
because "statistically significant" cannot be computed without σ.

**Recurrence entries must be phrased against the target's ground truth, not the artifact's naming.** An
entry asserting "the artifact must not mark SKILL-002 active" breaks as soon as a regenerated artifact
numbers its invariants differently — and it does, every time. "Any claim that obstudio's per-skill scripts
contain no logic is false; `validate_gap_closure.py` is 712 lines" survives regeneration because it is a
fact about `88aebe8`.

**Negative assertions reward silence.** Eight of the nine obstudio defects express naturally as "the
artifact must not claim X" — and an artifact passes all eight by never mentioning mutexes, file counts or
composition roots. That drives artifacts toward exactly the vagueness `check_specificity` exists to
punish. Every negative needs a positive pair where the topic is load-bearing.

**Fresh repositories are a depleting resource, and "fresh" is ambiguous.** Each calibration burns one
permanently. And a judge model has likely seen Django in pretraining, so it can score from memory — the
same failure as a citation that resolves without supporting its claim. Obscure repositories are better for
*judge* calibration specifically; obstudio at 12 stars was a better choice than it looked.

**The ledger needs the variance sources, not just the scores.** Generating agent + model version, judge
model version, rubric/brief version, replicate id, blinding state. Round 1 and round 2 used different
briefs, so those two means were already incomparable. Updates modelled as `predecessor_run_id` rather than
sparse columns — an update is two runs plus a relation, and chains can exceed two.

**The update gate should not be the overall mean.** "No decline" conflates *the update process failed*
with *the system got harder to describe between N and N+x*. `check_update_captured`, post-update drift and
the `update_quality` criterion are sharper and already exist.

## The measurement that settled the positive/negative question

Question: are positive assertions mechanically checkable? Answer: partly, and the split is clean if you
assert *which evidence the artifact should have engaged with* rather than what prose it should contain.

Run against the real obstudio artifact, matching citations by basename:

| ground truth | result |
|---|---|
| CORS header `handler.go:283` | file cited at 40, 75, 76, 354 — nowhere near 283 |
| WS `CheckOrigin` `websocket.go:21` | file cited at 204, 233, 238, 260 — nowhere near 21 |
| `DELETE` route `handler.go:93` | cited at 75, 76 — **false pass** |
| `Store` mutexes `store.go:313` | cited at 314 — **false pass** |

The first two are defect 8, caught with no judge. The last two are false passes and not by accident:
defect 3 is the invariant citing `handler.go:75-92`, so a proximity window sees a citation 17 lines away
and calls it engaged; defect 7 cites `store.go:314` for ring buffers while describing the mutex at `:313`
wrongly.

So:

- **Omission** — never looked at the evidence → mechanical, cheap, every run.
- **Misreading** — looked at the right place and concluded wrong → not mechanical. No window size fixes
  it: too tight gives false alarms on off-by-a-few citations, too loose passes a range that stops one line
  short of its own counterexample.

That second class is the "citation resolves but does not support the claim" failure, now observed three
times (HTTP-001; the human's `manager.go:68` diagram verification; defect 7).

## The per-repository checklist

Covers exactly the residual — the misreading class. The refinement that matters: **put the ground truth in
the checklist.** Not "is the concurrency description correct?" (a research task that re-runs the same
error) but:

> `Store` uses a `sync.RWMutex` plus `subMu`, `invalidateMu`, `changeMu` (`store.go:313-332`). Does the
> artifact convey this? **correct / wrong / absent**

Research becomes comparison. The reading was done once, by a human, during calibration; the checklist is
where that work is banked so it never has to be redone. Cheaper (no code exploration), more reproducible
(fixed questions, fixed order), ternary rather than 1–5.

Three cautions: the checklist is an answer key and must be blinded from whoever authors a prompt change;
it is still a model reading prose, with the residual error expected in "wrong vs absent"; and the open
6-criterion rubric must survive, because a checklist can only re-test known defects — open rubric explores,
checklist exploits, and every new defect found becomes next round's checklist entry.

## Open items not resolved in the discussion

- The noise floor is still unmeasured. Everything gated on "statistically significant" is blocked on it.
- Groups A–D still have no evidence and no instrument that can produce any. Split proposed but not built:
  synthetic injection into `fixture_repos.py` for recall, artifact-bearing real repos for precision.
- Who runs the re-describe arms. Not the person holding the defect list.
