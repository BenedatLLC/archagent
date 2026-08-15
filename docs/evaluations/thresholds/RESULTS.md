# Leave-one-out threshold sensitivity — first run (2026-08-15)

Design §18. The question: *would we have chosen this value if one repository had not been in the room?*

Run with `python scripts/thresholds.py` over the pinned corpus (datasette 1.0a37, django 5.2.16,
litellm v1.95.0-dev.2; the openhands entry has no cached mirror and was skipped, reported rather than
silently dropped). The four `dupdecide` clustering thresholds were swept because they are pure code scans
and need no git history.

## What came back

| Threshold | Value | Verdict |
|---|---|---|
| `COHESION` | 0.6 | pinned by **django** — dropping it widens the agreed plateau from `0.6..0.6` to `0.1..0.6` |
| `TIGHTNESS` | 0.6 | **unconstrained** — no repository's output changes anywhere from 0.1 to 0.9 |
| `MIN_FILES_PER_VALUE` | 3 | pinned by **litellm** |
| `MIN_CLUSTER_VALUES` | 3 | pinned by **datasette** and **litellm** |

## The headline is the caveat

**Every one of these is marked THIN.** The corpus produces one or two group-F findings per repository, so
a "pinned by django" verdict rests on two findings. The check reports the count alongside every verdict for
exactly this reason: pinned-on-two and pinned-on-two-hundred are different claims and the arithmetic cannot
tell them apart.

So none of the four verdicts should change a threshold today. What the run establishes is that the
instrument works, is cheap to re-run, and is blocked on the same thing as everything else —
[#9](https://github.com/BenedatLLC/archagent/issues/9), a corpus assembled for checks that need only
source and history, now being asked questions it cannot answer.

## The one result worth acting on anyway

`TIGHTNESS = 0.6` is **unconstrained**: across the entire swept range, on all three repositories, the
finding count never moves. That is not three repositories agreeing on 0.6 — it is no evidence about 0.6 at
all, and the check prints the two differently on purpose.

Unconstrained is a weaker statement than it sounds, and specifically it does **not** mean the threshold is
useless: `TIGHTNESS` may well be doing necessary work on repositories the corpus does not contain. What it
means is that this value is currently unfalsifiable here, and nobody should cite corpus evidence for it.

## Reading the output

```
COHESION = 0.6
  agreed plateau (all repos): 0.6 .. 0.6
  without django         0.1 .. 0.6   (opportunity 2)   <- PINNED BY THIS REPO
```

- **agreed plateau** — the range of values that would produce identical output on every repository. A wide
  plateau means the exact value does not matter on this evidence.
- **without R** — the same, computed with R removed. A large widening means R was the only thing holding
  the value where it is.
- **opportunity** — R's finding count at the most permissive setting. A repository with zero cannot support
  or refute anything, and the check refuses to read its silence as agreement.

## The hotspot thresholds (added 2026-08-15)

`PCTILE_BAR` and `MIN_LOC` need mined churn, so the sweep mines each repository **once** and reuses it
across every value and every threshold — mining is the whole cost and does not depend on the value being
swept. Churn now comes from a real history: 388 files (datasette), 1,725 (django), 4,445 (litellm), each
bounded to the pinned revision's own commit date.

| Threshold | Value | Opportunity (ds / dj / ll) | Verdict |
|---|---|---|---|
| `MIN_LOC` | 30 | 10 / 41 / 95 | no repository pins it |
| `PCTILE_BAR` | 0.75 | 21 / 106 / 254 | **unranked** — see below |

**These are the first threshold verdicts that are not thin.** Where the `dupdecide` thresholds rest on one
or two findings per repository, these rest on tens to hundreds, so the arithmetic means something.

`MIN_LOC = 30` is clean: every repository's output responds, dropping any one of them leaves the value
just as constrained, and no repository sits on a cliff there.

`PCTILE_BAR = 0.75` returns **unranked**, a verdict added because of this result. Every repository's count
changes at *every* step of the sweep, so the plateau is a single point no matter which repository you drop
— "not pinned" is then guaranteed by the arithmetic rather than earned. The honest reading is that no
single repository holds 0.75 in place, **and nothing here prefers 0.75 to 0.70 or 0.80 either.** This check
asks who holds a value where it is; it never asks whether the value is right, and a report that read as
endorsement would be the more dangerous error.

What would rank `PCTILE_BAR` is precision data across the sweep — the labels the corpus does not have.
The held-out defect study (§7) is the nearest thing, and it was run at 0.75 only.

## A bug this sweep found in itself

The first run reported litellm with **zero** files of churn while datasette and django looked plausible.
`mine_cochange(until=...)` passes its argument straight to `git log --until=`, which expects a *date*, and
the sweep handed it a tag. Two repositories produced numbers from a malformed date and one produced
nothing; nothing errored.

Fixed by routing through `resolve_as_of`, which is what the CLI's `--as-of` already does. The sweep now
also refuses to continue when a repository yields no per-file churn at all — otherwise every hotspot
threshold reports zero findings at every value, and the report records a repository with *nothing to say*
rather than a broken measurement. That is the silent-failure shape from Appendix A, arriving in the tool
built to detect overfitting.

## Not yet covered

`MAX_REPORTED`, `MAX_DECISIONS` and `MAX_ORIGIN_SITES` are display caps rather than filters — they change
what is shown, not what is found, so a plateau sweep says nothing useful about them. `DOUD_THRESHOLD`
(0.30) is a genuine filter and is not swept: group B needs `**Tier:**` metadata that no corpus repository
declares, which is [#9](https://github.com/BenedatLLC/archagent/issues/9) again.
