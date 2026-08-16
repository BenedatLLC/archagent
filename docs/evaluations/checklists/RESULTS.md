# Checklists — first run (2026-08-16)

Four blind judges: Opus and Sonnet, on each of the obstudio and wardrowbe artifacts. Each read only the
artifact and its worksheet — not the source repository, not the other judges, not `DEFECTS.md` or any prior
review. 14 items per target, all 28 answered by all four judges, none discarded.

This run measures two different things, and only one of them is about the artifacts.

## 1. Judge agreement — the number §14 was missing

| target | agreement | disagreements |
|---|---|---|
| obstudio | **14/14** | none |
| wardrowbe | 12/14 | `tagging-retries` (correct vs absent), `item-status` (wrong vs absent) |
| **combined** | **26/28 = 0.93** | 2 |

**This is the result the instrument was built for.** The 1–5 rubric's noise floor, measured on this same
wardrowbe artifact a day earlier, had `diagrams` moving from 2 to 4 across two Sonnet runs — the full width
of the usable scale — and only two of six criteria unanimous across six judgings. Here two *different
models* agree on 26 of 28 ternary verdicts against a stated answer.

The design argued that comparison varies less than research. It does, and by enough to matter: a checklist
score can carry a per-item claim, which a per-criterion rubric score cannot.

## 2. Construct validity — 0 of 20 known defects scored `correct`

Both artifacts are left unfixed as evidence, so every defect-derived item *should* come back `wrong` or
`absent`. All twenty did, from both judges, on both targets. No false `correct` anywhere.

That is the check that the worksheet is readable and the verdicts mean what they say. A judge that could
not find the relevant passage would have produced `correct` by charity or `absent` by laziness, and neither
happened at any rate above zero.

## 3. What the scores do *not* say

| target | judge | accuracy | weighted |
|---|---|---|---|
| obstudio | opus | 0.14 | 0.14 |
| obstudio | sonnet | 0.14 | 0.14 |
| wardrowbe | opus | 0.21 | 0.21 |
| wardrowbe | sonnet | 0.14 | 0.14 |

**These are not quality scores for these artifacts, and must not be quoted as such.** Ten of the fourteen
items per target were written *from these artifacts' own confirmed defects*. A list built that way can only
produce a low number; it says how thoroughly the defects were catalogued, not how good the documents are.

The score becomes a measurement at the *next* generation of these targets, where the same items face an
artifact the list was not built from. That is the entire point of banking them.

The informative subset today is the four items per target that came from reading the code rather than from
a finding — the only ones facing these artifacts blind:

| target | judge | fresh items correct |
|---|---|---|
| obstudio | both | 2/4 |
| wardrowbe | opus | 3/4 |
| wardrowbe | sonnet | 2/4 |

At n=4 that is an anecdote, not a rate. What it is not is zero: both artifacts convey some load-bearing
facts nobody has ever flagged, which is worth knowing given that every other item on the list is a failure.

## 4. The residual is not only where §14 predicted

The design named the `wrong`/`absent` boundary as the instrument's weak point — an artifact that gestures
at a topic without committing. One of the two disagreements is exactly that (`item-status-has-four-values`:
Opus called the tagging-lifecycle diagram's `queued`/`done`/`abandoned` vocabulary a contradiction of the
enum, Sonnet called it a different subject and therefore silence).

**The other disagreement is a boundary the design did not anticipate: `correct` vs `absent` on a
partially-conveyed fact.** `tagging-retries-are-bounded-and-explicit` states two things — that the limit is
three, and that arq only reschedules on `Retry`, so returning normally voids the limit. The artifact
carries the first and not the second. Opus scored the half it had; Sonnet scored the half it lacked. Both
judges flagged the call as hard, independently, without seeing each other's work.

That is a defect in the item, not in either judge. **An item should assert one fact.** A compound item has
no correct ternary answer when an artifact splits it, and the two available answers differ by a full
verdict. Three other items on the two lists bundle a fact with its rationale the same way and should be
split before the next run.

Two of the four judges' three flagged "hard calls" were on compound items. The third —
`retention-is-scoped-to-the-producing-process` — is the same shape: the artifact conveys the per-connection
eviction and over-generalises the two-mechanism half, and Opus's note says explicitly that a stricter
reading would have called it `wrong` rather than `absent`.

## 5. What each artifact was found to convey

Unanimous `absent` on the three items that are pure omissions rather than errors:

- obstudio — `cors-is-wide-open` and `websocket-accepts-any-origin`. Both judges found nothing to quote.
  This is the round-2 finding reproduced mechanically: the strongest defect either reviewer found was a
  thing the artifact does not mention, and a checklist finds it every time without a reviewer.
- wardrowbe — `ownership-is-enforced-at-every-call-site`. Four human and model reviewers named this as the
  artifact's largest gap; both judges here return `absent` with no quote available.

Unanimous `wrong` on the two false-security-posture claims in wardrowbe — `misconfiguration-refuses-to-start`
and `image-access-has-three-independent-paths` — both `serious`, both reported by the scorer under *serious
claims contradicted*.

## Limits

- One run per judge per artifact. Agreement between two models is not the same as agreement across runs of
  one, which the rubric's floor showed can differ.
- Both artifacts are the ones the checklists were written from. Everything in §3 above follows from that.
- Two of the four judges were Sonnet and two Opus; the noise-floor run found Sonnet the noisier judge on a
  1–5 scale. On this instrument the two models differ on 2 of 28 items, so if that property carries over it
  is small enough not to show at this n.
- The `correct`/`absent` boundary found in §4 is one observation. It is being acted on because the fix —
  one fact per item — costs nothing and has no downside, not because one observation establishes a rate.
