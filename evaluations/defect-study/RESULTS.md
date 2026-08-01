# Held-out defect study — results

The analysis pre-registered in `docs/designs/evaluating-archagent.md` §7.1. **Every run stays on this
page**, including the ones that said nothing: a held-out study whose disappointing runs quietly disappear
is not held out.

---

## Run 2 (2026-08-01) — one powered repository passes, one does not

| repo | scored | flagged | controls | RR | 95% CI | powered? | predicts |
|---|---|---|---|---|---|---|---|
| **homeassistant** | 1749 | 143 | 375 | **2.05** | **[1.55, 2.67]** | **yes** | **yes** |
| **angular** | 794 | 63 | 173 | 1.47 | [0.98, 2.18] | **yes** | no (just) |
| ansible | 395 | 51 | 67 | 1.18 | [0.63, 2.13] | no | no |
| pandas | 230 | 27 | 41 | 1.15 | [0.59, 2.72] | no | no |
| scrapy (run 1) | 137 | 13 | 26 | 0.95 | [0.41, 2.30] | no | no |
| poetry (run 1) | 112 | 17→10 | 12 | 0.99 | [0.44, 2.40] | no | no |
| flask (run 1) | 22 | 1 | — | — | — | no | excluded at the flag step |
| prettier | — | — | — | — | — | — | history walk failed |

*Powered* means ≥60 flagged and ≥120 controls after stratification, the bar fixed in
`tests/heldout_manifest.toml` before run 2 from a simulation of this design's own estimator (10 v 12
detects a real 1.5× effect 23% of the time; 60 v 120 detects it 82%).

**Two repositories met the bar. One passes the pre-registered test, one does not, and the more
interesting difference is between their specificity checks.**

### The check that decides whether to believe either of them

The obvious objection is that stratification failed and we are looking at residual churn. Comparing the
primary outcome against *all* commits answers it directly — and the two powered repositories answer it
differently:

| repo | defect fixes (primary) | all commits (secondary) | specific to defects? |
|---|---|---|---|
| homeassistant | **2.05** [1.55, 2.67] | 1.28 [1.00, 1.62] | **yes** — fixes far outrun general activity |
| angular | 1.47 [0.98, 2.18] | 1.39 [1.11, 1.72] | **no** — the two move together |

Home-assistant is the result the design was hoping to be able to distinguish: after stratification its
flagged files receive only slightly more commits of *any* kind than their decile peers, but roughly twice
the defect fixes. Churn is absorbed and something else is left over.

Angular's flagged files receive about 1.4× everything — commits and fixes alike. That is the pattern you
would expect if the flagged set is simply a bit busier than its stratum and nothing more specific is
happening. Angular's primary result would have been reported as a near-miss on the interval alone; the
secondary comparison is what says it is a *different* near-miss from home-assistant's pass.

### What this licenses, and what it does not

The pre-registered rule is per repository. **One of two adequately-powered repositories passes it**, with a
clean specificity check; the other misses, without one. That is real evidence — the first about
archagent's output that does not depend on our own judgement — and it is suggestive rather than
established.

Three limits worth stating plainly:

1. **Two powered repositories, split.** The other four were too small to see a 2× effect reliably, so their
   nulls are uninformative rather than contradictory — but they are not corroboration either.
2. **Home-assistant may be structurally atypical.** `homeassistant/components/*` is thousands of largely
   independent integration modules. Whether churn and complexity behave there as they would in a codebase
   with heavy internal coupling is exactly what a third powered repository would settle, and angular's
   contrary specificity result makes that question sharper rather than softer.
3. **The pooled estimate is not independent evidence.** RR 1.75 [1.42, 2.15] across seven repositories is
   exploratory, and 141 of its 304 flagged files are home-assistant's. It is that result diluted, not a
   replication of it.

### Exploratory (not pre-registered, not a basis for any claim)

- Pooled across repositories, stratified on repo × churn decile: RR 1.75 [1.42, 2.15] (304 flagged, 694
  controls).
- Deletion sensitivity on home-assistant: RR 2.03 [1.57, 2.67] with deleted files kept as zero-defect,
  against 2.05 excluding them — the choice does not drive the result. 518 files were deleted during the
  window.

---

## Run 1 (2026-08-01) — null, and uninformative

| repo | scored | flagged | RR | 95% CI | predicts |
|---|---|---|---|---|---|
| poetry | 112 | 17 | 0.99 | [0.44, 2.40] | no |
| scrapy | 137 | 13 | 0.95 | [0.41, 2.30] | no |
| flask | 22 | 1 | — | — | excluded |

Both intervals contained 1 — and also a doubling and a halving. After stratification poetry compared **10
flagged files against 12 controls**, which the power simulation later showed detects a genuine 1.5× effect
23% of the time. The run carried no information in either direction.

The binding selection criterion turned out to be **scored files, not years of history**: flask is a mature
project with thousands of commits and 22 scored files in `src/flask`.

### Deviations, and their honesty status

- **Flask excluded for power**, at the flag step, before any outcome existed. A power judgement made blind.
- **Poetry and scrapy were not.** Their thinness was equally visible at that step and I acted only after
  seeing the outcomes. Had they come out strongly positive, the same sample sizes would have been just as
  inadequate and correspondingly easier not to notice.
- **Run 2 added repositories rather than replacing any.** §7.1 forbids swapping a held-out set after a run,
  because that is how a set stops being held out. The distinction relied on here is that the sample was too
  small to answer the question, which was visible before the answer was — and run 1 remains on this page.
- **Prettier never ran.** Its history walk failed and the harness refused to record an empty flagged set —
  the guard added after that same failure was silently recorded as litellm's corpus baseline. Angular hit
  the identical wall and was fixed rather than dropped: the clone warm-up only covered `head`'s trees,
  while the flag step walks 3000 commits back from a cutoff a year earlier, so the lazy fetches recurred
  and the walk timed out. Warming at the cutoff as well fixed it. Prettier is unfinished work, not an
  exclusion.

---

## Reproducing

```bash
python scripts/defect_study.py flag       # signals as of the cutoff; writes the flagged set
python scripts/defect_study.py outcome    # refuses unless the flagged set already exists
python scripts/defect_study.py pool       # the exploratory pooled estimate
python scripts/defect_study.py report
```

Windows are fixed relative to each repository's pinned `head`, not to today, so a rerun next month gives
the same numbers. The bootstrap seed is fixed for the same reason.
