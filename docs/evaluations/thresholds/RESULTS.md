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

## Not yet covered

`PCTILE_BAR` and `MIN_LOC` (hotspots) need mined churn, so sweeping them costs a history walk per value per
repository. They are the thresholds with the most evidence behind them already (§7), and they are the
obvious next target once the sweep can be cached across values.
