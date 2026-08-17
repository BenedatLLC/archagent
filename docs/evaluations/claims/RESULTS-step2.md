# Step 2 — generation variance (2026-08-16)

Method fixed in advance: `STEP2-METHOD.md`. Three independent generations of the wardrowbe artifact at
`wardrowbe-v1.7.0`, same model, same prompt, same revision, each in its own copy of the checkout with the
existing artifact removed before the copy was made.

**Generation variance is small on the instruments that can see it, and invisible to the one that cannot.
Step 3 can proceed.**

## The numbers

| | run 1 | run 2 | run 3 | sd | range |
|---|---|---|---|---|---|
| deterministic score | 0.889 | 0.888 | 0.888 | **0.001** | 0.001 |
| checklist accuracy | 0.88 | 0.88 | 0.81 | **0.040** | 0.070 |
| checklist weighted | 0.94 | 0.94 | 0.88 | 0.035 | 0.060 |
| recurrence entries recurring | 0/10 | 0/10 | 0/10 | 0 | 0 |

For scale: the judged 1–5 rubric's noise floor is **sd 0.10 on the mean with the artifact held fixed**, and
the checklist's own between-judge disagreement is **1 item in 16**.

**Generation variance is not larger than judging variance.** On the checklist, three independently
generated artifacts differ on exactly **one item of sixteen** — the same magnitude as two judges reading
one artifact. That is the answer step 3 needed.

## The one item that differed, and why it may not be generation variance at all

Every run agrees on 15 of 16 items. The exception is `auth-modes-are-oidc-dev-unknown`, `correct` for runs
1 and 2 and `absent` for run 3.

**Both of the judges who scored it `correct` flagged it as a borderline call, unprompted**, and both said a
stricter reading would be `absent`: the artifacts name `oidc` and `dev` and model the third case as a
warned "no auth method configured" state without ever printing the literal `unknown`. So the single
difference in the whole measurement sits precisely on the `wrong`/`absent` boundary the checklist design
names as its residual, and it is at least as likely to be judge variance as artifact variance.

The honest statement is therefore that **generation variance is bounded above by 1 item in 16, and may be
smaller** — this measurement cannot separate the last item from the judge.

## The deterministic rubric cannot see generation variance

0.889 / 0.888 / 0.888 — three decimal places of agreement between artifacts that are *plainly* different:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| subsystems | 18 | 17 | 14 |
| words | 27,019 | 26,501 | 21,689 |
| invariant rows | 56 | 48 | 28 |
| ADRs | 17 | 10 | 9 |

Run 1 splits the frontend four ways (`web-edge`, `web-routes`, `web-data-layer`, `web-components`); run 3
uses two (`web-ui`, `web-client-lib`). Run 3 promotes `weather` to its own subsystem; the others fold it
into integrations. Only about five subsystem names appear in all three. One artifact carries twice the
invariant rows of another.

**This is a finding about the instrument, not a reassuring result.** The deterministic rubric measures
conformance — do the globs resolve, is every file claimed, is there an entry narrative — and all three
conform. It was never designed to rank two conforming artifacts, and this confirms it cannot. **It must not
be used as the score in a two-arm comparison.** The checklist can carry that; the deterministic half is a
gate, not a measure.

## The regenerated artifacts are much better than the original

| | original artifact | runs 1–3 |
|---|---|---|
| checklist accuracy | 0.12 | 0.81–0.88 |
| recurrence entries recurring | 10 of 10 | 0 of 10 |

Read with care in one direction and not the other. **The recurrence and checklist items were derived from
the original's own defects**, so the original failing everything is arithmetic. What is *not* arithmetic is
the other side: those items are facts about the target, and three artifacts generated months later by a
different route get 13–14 of 16 right on questions written from another artifact's mistakes. None of the
defects came back.

Six items moved from `wrong` on the original to `correct` on all three runs, including four `serious` ones:
image access having three independent paths, misconfiguration refusing to start, `ItemStatus` having four
values, and stale jobs being failed rather than requeued. The two ownership items — the gap four reviewers
named as the original's largest — are `correct` in all three.

## Two defects this measurement exposed in the instruments

**A recurrence entry that cried wolf.** The first pass reported run 1 as failing the ownership entry. Run 1
covers ownership thoroughly, with its own ADR. The entry had *two* `require` patterns, one for each word
order, which reads as "either will do" and means the opposite — every `require` must match, so an artifact
stating the fact in one order fails. Now one pattern with an alternation. It still fires on the original
artifact, so the self-check holds. **Second entry defect on record, both in the crying-wolf direction.**

**The checklist scores conditional items as misses.** Two items are `absent` in all three runs:
`five-model-modules-have-matching-schemas` and `backend-source-scope`. Both are phrased conditionally — *if
the artifact states a count, is it right?* — so `absent` is the **correct** answer for an artifact that
sensibly declines to state an incidental count. The scorer counts it as not-correct anyway, which
understates all three runs. Excluding the two conditional items the runs are 14/14, 14/14, 13/14.

That interacts directly with the predicate-claims design, which argues incidental counts should not be
written at all. An artifact following that advice is currently penalised by the checklist for taking it.
The fix is a `conditional` flag on an item, with `absent` scored as a pass.

## What this does not establish

- One target, one model, three runs. It bounds generation variance for this repository under this prompt
  at this revision.
- The checklist and recurrence entries were written from an earlier artifact of the same target, so they
  are enriched for that artifact's failure modes rather than neutral. The *spread* across the three runs is
  unaffected by that; the *level* is not comparable to a fresh target.
- One judge per artifact. The three-way comparison mixes generation variance with one judging each, which
  is why the single differing item cannot be attributed.

## Consequence for step 3

Proceed, with the arm sizes already planned, and with three constraints this measurement earns:

1. **Score the arms on the checklist, item by item, not on the deterministic rubric.** The deterministic
   score is blind to differences this large and would report any two arms as identical.
2. **A difference of one checklist item is inside the noise.** A two-arm comparison needs the ~5-item
   margin the pre-registration already specified, and that margin is now justified rather than guessed.
3. **Fix the conditional-item scoring first**, or the arm that follows the new advice about incidental
   counts is penalised for it.
