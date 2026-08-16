# Checklists — run 2, after splitting compound items (2026-08-16)

Run 1 (`RESULTS.md`) found two judge disagreements. One was the `wrong`/`absent` boundary §14 predicted.
The other was `correct` vs `absent` on an item asserting *two* facts where the artifact carried one — a
defect in the item, not the judge. Five compound items were split (obstudio 14→17, wardrowbe 14→16),
incidental clauses were trimmed, and the same four judges re-ran with one added instruction: *judge only
the fact stated in this item; do not withhold `correct` because a related fact is missing elsewhere*.

## The split worked

| | run 1 | run 2 |
|---|---|---|
| agreement, obstudio | 14/14 | 16/17 |
| agreement, wardrowbe | 12/14 | 15/16 |
| **combined** | **26/28 = 0.93** | **31/33 = 0.94** |
| disagreements off the wrong/absent boundary | 1 | **0** |

The `correct`/`absent` class is gone. Both remaining disagreements are the boundary the design named as
the residual, and both are the same shape: an artifact renders the right topic under the wrong vocabulary,
one judge calls that a contradiction and the other calls it silence.

- obstudio `ui-and-skills-are-embedded-separately` — Opus quotes the artifact placing the UI embed in
  `cmd/obstudio/embed.go` and calls it `wrong`; Sonnet reads the second embed as never addressed.
- wardrowbe `item-status-has-four-values` — the only place the artifact renders these states is a lifecycle
  diagram using `queued`/`done`/`abandoned`. Opus: the artifact's own prose calls that diagram the item's
  tagging progression, so it contradicts the enum. Sonnet: the diagram never claims to *be* the enum.

Neither judge is wrong. This is the irreducible part, and it is one item in sixteen.

## Splitting changed two verdicts in opposite directions, both correctly

**obstudio `retention-is-scoped-to-the-producing-process` moved from unanimous `absent` to unanimous
`correct`** — a `serious` item. The artifact does say records carry an `ownerConnID` so telemetry can be
evicted per connection and a restarted service clears its own data. What it does not say is that gRPC and
HTTP detect a departed producer differently. The combined item made the half it lacked erase the half it
had; the split scores each. `retention-differs-by-transport` is unanimously `absent`, which is the true
finding.

**wardrowbe `tagging-retries` moved the other way.** Run 1: Opus `correct`, Sonnet `absent`. Split into the
bound (3) and the mechanism (arq only reschedules on `Retry`), both halves come back unanimously `absent` —
the artifact names `TAGGING_MAX_TRIES` without its value and says nothing about the mechanism. Opus's
`correct` was generosity toward a compound item, and splitting withdrew it.

An instrument that only ever moved scores up after a fix would be measuring the fix. This one moved a
`serious` item up and a `moderate` item down in the same change.

## Construct validity holds: 0 of 22 known defects scored `correct`

Eleven defect-derived items per target now, both judges, both artifacts. Not one `correct`. Same as run 1,
on a larger list, with no drift.

## Run-to-run stability: 35/36 on unchanged items

Comparing each judge against *itself* across the two runs, restricted to the eighteen items whose ground
truth text was not edited:

| target | judge | stable |
|---|---|---|
| obstudio | opus | 8/8 |
| obstudio | sonnet | 7/8 |
| wardrowbe | opus | 10/10 |
| wardrowbe | sonnet | 10/10 |

One flip, and it is the same item and the same model as one of the two between-judge disagreements:
Sonnet's `ui-and-skills-are-embedded-separately` went `wrong` → `absent`. So a single item on a single
boundary accounts for both this run's obstudio disagreement and the only instability observed.

**0.97 within-judge, 0.94 between-judge.** For comparison, the 1–5 rubric measured on one of these same
artifacts had `diagrams` spanning 2 to 4 across two runs of one model. The two instruments are not close.

## Scores

| target | judge | correct | wrong | absent | accuracy | weighted |
|---|---|---|---|---|---|---|
| obstudio | opus | 4 | 9 | 4 | 0.24 | 0.26 |
| obstudio | sonnet | 4 | 8 | 5 | 0.24 | 0.26 |
| wardrowbe | opus | 2 | 9 | 5 | 0.12 | 0.12 |
| wardrowbe | sonnet | 2 | 8 | 6 | 0.12 | 0.12 |

**Still not quality scores for these artifacts** — eleven of the items per target were written from these
artifacts' own defects. The informative subset is the items that came from reading the code: obstudio 4/6
both judges, wardrowbe 2/5 both judges. Unanimous on both counts, which run 1 was not.

## Limits

- The added instruction (rule 7) and the item splits changed together, so the improvement cannot be
  attributed between them. The direction of the two moved verdicts argues for the splits doing the work,
  since rule 7 alone would only push toward `correct`, and one item moved away from it.
- Stability is measured across two runs, days apart in neither wall-clock nor model version. It says the
  verdicts are reproducible, not that they are stable over a model upgrade.
- Both artifacts remain the ones the checklists were written from.
