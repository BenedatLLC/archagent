# Held-out defect study — results

The analysis pre-registered in `docs/designs/evaluating-archagent.md` §7.1. **Every run stays on this
page**, including the ones that said nothing: a held-out study whose disappointing runs quietly disappear
is not held out. Sections below are newest first; where a later section corrects an earlier one, the
earlier text is left as written and the correction says so.

---

## Standing (current)

Does the churn × complexity signal identify files that go on to accumulate more defect fixes than
comparable files it did not flag?

| repo | language | flagged/controls | RR | 95% CI | verdict |
|---|---|---|---|---|---|
| kibana | TypeScript | 107 / 257 | 4.27 | [2.05, 11.71] | **passes** |
| nova | Python | 59 / 82 | 4.45 | [1.63, 16.14] | **passes** |
| homeassistant | Python | 141 / 375 | 2.05 | [1.55, 2.67] | **passes** |
| angular | TypeScript | 63 / 173 | 1.47 | [0.98, 2.18] | same effect, weaker; sample cannot resolve it |
| prettier, ansible, pandas, poetry, scrapy | — | — | 0.93–1.18 | all span 1 | underpowered, uninformative |
| flask, sympy | — | — | — | — | excluded at the flag step for power |

**Three of four adequately-powered repositories pass, across two languages and three architectures.** The
fourth is not a counter-example: angular's flagged files carry ~1.5× the defect fixes of their
churn-matched peers in the two deciles holding 52 of its 63 flagged files, and only a small third stratum
inverts. It is the weak end of a spectrum, not a contradiction — see the correction below, which revises
run 4's harsher reading of it.

Two qualifications on how to quote this:

- **Magnitudes are not comparable across repositories.** The rate ratio tracks how *concentrated* defect
  fixes are, partly mechanically: kibana and nova have 4–5% of files carrying any fix and RRs above 4;
  home-assistant has 37% and an RR of 2.05. Pass/fail is a within-repository comparison and stands; the
  numbers are not effect sizes for the check in general.
- **The pooled figure is exploratory** (RR 1.83 [1.51, 2.21] over nine repositories) and was never
  pre-registered.

What this does *not* establish: anything about small repositories, where every attempt was underpowered;
and anything about why angular's effect is weaker.

---

## Run 4 (2026-08-01) — the language explanation is out too

**Pre-registered in commit `8f6f726` before the run**, with all four outcomes and what each would license.

Run 3 killed the architectural explanation. What remained was that both passes were Python and the one
near-miss lacking specificity, angular, was the only TypeScript datapoint. kibana is TypeScript of a
different kind — a large application/platform, not a framework.

| repo | language | kind | flagged/controls | RR (defect fixes) | 95% CI | all commits | specific? |
|---|---|---|---|---|---|---|---|
| homeassistant | Python | plugin registry | 141 / 375 | 2.05 | [1.55, 2.67] | 1.28 | yes |
| nova | Python | coupled service | 59 / 82 | 4.45 | [1.63, 16.14] | 1.35 | yes |
| **kibana** | **TypeScript** | **platform** | **107 / 257** | **4.27** | **[2.05, 11.71]** | **0.99** | **yes** |
| angular | TypeScript | framework | 63 / 173 | 1.47 | [0.98, 2.18] | 1.39 | weak (see correction) |

**Answer: language is not the explanation either.** kibana passes, and with the cleanest specificity
signature in the study: its all-commits ratio is **0.99 [0.80, 1.23]** — stratification absorbed churn
essentially exactly — while its defect-fix ratio is 4.27. Flagged files receive no more commits than their
decile peers and more than four times the defect fixes.

It also clears the revised events bar with room to spare: 438 defect-fixing commits in the window, against
a bar of 100. The deletion sensitivity check holds (3.61 [1.78, 8.87] with deletions kept), on a window
where 8,645 files were deleted.

**Standing: three of four adequately-powered repositories pass, all three with the specificity signature,
across two languages and three architectures.** Angular is no longer the representative of a category.
Pooled across all nine repositories (exploratory): RR 1.83 [1.51, 2.21].

> **Corrected later.** This section went on to describe angular as showing "no specificity" and being
> "merely busier". The per-decile follow-up below shows that over-read a pooled interval whose lower bound
> was 0.978: angular carries ~1.5× in its two largest strata. The wording here is left as written; the
> corrected reading is in "Angular's flagged set is not unusual".

This is the pre-registered "passes, with specificity" outcome, whose recorded reading was: *the signal
generalises across languages; angular is the outlier; Check A's defect-prediction claim would stand
unqualified.*

**Scope limit:** kibana's manifest entry is `src` only — 21,180 TypeScript files, the platform core.
`x-pack` (63,178 files) is excluded. The result speaks to that subtree.

### The infrastructure this run cost, and what it exposed

Kibana failed four times before producing a number, and three of the four were failures that would have
produced a *plausible wrong answer* rather than an error:

| attempt | symptom | actual cause |
|---|---|---|
| flag ×2 | "history walk failed" | 89,382-file worktree checkout from a blobless clone consumed the budget |
| flag (ad-hoc) | *nearly recorded* | reused a worktree at `cf40a31d` against a window bounded to `2af339dd` — the tree/history mismatch the design warns about, in a shortcut around the harness |
| outcome ×1 | "a year with 0 commits, 0 fixes" | `outcome_log` returned `""` on git error — the same silent-failure class the miner had on litellm, in code written after fixing that one |
| outcome ×2 | exit 128 in 84s | **clone corruption**: commit-graph referencing objects absent from the object database |

The last is the root cause and it invalidated two earlier diagnoses: twice I concluded "too slow" and
raised a timeout, when git was erroring. A 75-second failure against a 3600-second budget said so plainly
and I read it only on the third look, after capturing stderr instead of inferring from the exit path.

Fixed: `outcome_log` now refuses rather than reporting an empty window; `ensure_clone` validates that a
cached clone can perform a `--name-status` walk (neither `HEAD` existing nor `rev-parse` resolving detects
this) and repairs a bad commit-graph by dropping it, which is lossless because the graph is a derived
cache. After the repair kibana's walk returned exit 0, 29.5 MB, 566 seconds.

**One unresolved oddity, recorded rather than dropped:** during diagnosis `rev-list -1 --before=2025-07-15`
returned `e128b393` once and `2af339dd` on every subsequent invocation — two commits twelve minutes apart.
It has been stable across many runs since and the recorded rev is `2af339dd`, but the first reading is
unexplained, and an unexplained non-reproducibility belongs in a study that rests on reproducibility.

---

## Follow-ups (2026-08-01): prettier, and why angular differs

### prettier — runs now, but underpowered

The clone validation added in run 4 repaired prettier's commit-graph and it completed:
RR 0.93 [0.39, 3.21], all-commits 1.07. It clears the *events* bar (134) but not the *file* bar
(22 flagged, 38 controls, against ≥60/≥120), and the revised bar requires both. So it is recorded, not
counted — the same standing as ansible and pandas.

### Testing the maintenance-mode hypothesis for angular

The proposal: angular's null reflects a project in maintenance rather than active development, so there is
less for a file-level signal to predict. Checkable, so it was checked.

| repo | fix % of commits | files with ≥1 fix | share of fixes in the top 10% of files | fixes per scored file |
|---|---|---|---|---|
| kibana | 3.1% | 5% | 100% | 0.06 |
| nova | 8.3% | 4% | 100% | 0.06 |
| ansible | 14.5% | 12% | 86% | 0.13 |
| pandas | 11.4% | 17% | 77% | 0.28 |
| prettier | 10.2% | 28% | 63% | 0.59 |
| **angular** | **15.5%** | **33%** | **60%** | **0.69** |
| homeassistant | 12.6% | 37% | 56% | 0.76 |

**Partially supported, but it does not explain the null.** Angular does have the highest fix share of any
repository here — 15.5% of its commits are defect fixes, which is what a maintenance-heavy phase looks
like. But it is not quiet: 4,055 commits in the outcome window is an active project.

And the consequence the hypothesis predicts does not appear. If angular's fixes were spread too thin for a
file-level signal to find, its distribution would look flat — but **home-assistant's is flatter still**
(37% of files fixed, 56% concentration) and home-assistant passes at 2.05. Two repositories with nearly
identical defect distributions, opposite results. Whatever distinguishes angular, it is not how widely its
fixes are spread.

### What the table does explain — and it tempers the headline numbers

Reading down it, **the size of the rate ratio tracks how concentrated defect fixes are**, which is partly
mechanical:

| | fixes concentrated | RR |
|---|---|---|
| kibana, nova | 4–5% of files carry them, top decile holds 100% | 4.27, 4.45 |
| ansible, pandas | 12–17% | 1.18, 1.15 |
| prettier, angular, homeassistant | 28–37% | 0.93, 1.47, 2.05 |

When only 5% of files receive any fix, correctly identifying them is high-leverage and the achievable
ratio is large. When a third of files receive one, the ceiling on any ratio is far lower. So **the
cross-repository spread in RR — 0.93 to 4.45 — is substantially about defect concentration, not about how
well the signal works.** Kibana's 4.27 and home-assistant's 2.05 are not straightforwardly comparable as
"how good the check is here".

This does not undercut the pass/fail conclusions, which are within-repository comparisons against matched
controls. It does mean the *magnitudes* should not be quoted as effect sizes for the check in general, and
home-assistant's 2.05 against a flat distribution is arguably the more impressive of the two passes.

### Angular's flagged set is not unusual — and "no signal" was the wrong description

Checked, and it rules the composition hypothesis out. Angular's flagged files are central framework code,
not test-adjacent or generated: `common/http/src/client.ts`, `compiler-cli/src/ngtsc/annotations/
component/src/handler.ts`, `router`, `language-service`. Nothing junk-like is being selected.

Two further checks then found where the difference actually lies.

**Churn predicts defects about equally everywhere**, so churn-matching does not remove more in angular
than elsewhere. Mean defects per file by churn decile, decile 9 against decile 5:

| repo | d9/d5 | RR |
|---|---|---|
| kibana | 6.8 | 4.27 |
| nova | ∞ (d5 = 0) | 4.45 |
| homeassistant | 4.5 | 2.05 |
| angular | 4.3 | 1.47 |
| prettier | 4.0 | 0.93 |

**The per-decile breakdown is the informative one, and it revises the earlier reading:**

| decile | angular | homeassistant | kibana |
|---|---|---|---|
| 7 | **0.87** (11 flagged) | 3.01 (10) | 8.08 (24) |
| 8 | 1.53 (20) | 1.61 (57) | 3.28 (40) |
| 9 | 1.58 (32) | 2.19 (74) | 4.31 (43) |

Angular is **not** flat. In its two largest strata the flagged files carry ~1.5× the defect fixes of their
churn-matched peers — the same order as home-assistant's decile 8 (1.61). What pulls its pooled estimate
under the line is decile 7 inverting (0.87, on only 11 flagged files) plus uniformly smaller effects.

**Correcting what I wrote in run 4.** I described angular as showing "no specificity" and being "the
pattern of a flagged set that is merely busier". That over-read a pooled interval whose lower bound was
0.978. The per-decile view shows a real but modest effect in the strata that carry most of the files, with
one small stratum going the other way. The accurate statement is **a weaker signal the sample cannot
resolve**, not the absence of one — and its interval barely excluding a pass is what that looks like.

The specificity comparison still separates the repositories, but by less than the headline suggested:
defect ratio over all-commits ratio is 1.06 for angular, 1.60 for home-assistant, 4.3 for kibana. Angular
is the weak end of a spectrum, not a different phenomenon.

---

## Run 3 (2026-08-01) — the architecture explanation is out; the split is by language

**The pre-registration for this run is in the commit history (`5d890cc`), written before the run.** It
asked one question: run 2's pass (home-assistant) is a plugin registry in Python and its near-miss
(angular) is a coupled framework in TypeScript, so architecture and language are confounded. Does the
specificity pattern replicate in a **coupled Python** codebase?

| repo | architecture | language | flagged/controls | RR (defect fixes) | 95% CI | all commits | specific? |
|---|---|---|---|---|---|---|---|
| homeassistant | plugin registry | Python | 141 / 375 | 2.05 | [1.55, 2.67] | 1.28 | **yes** |
| **nova** | **coupled service** | **Python** | **59 / 82** | **4.45** | **[1.63, 16.14]** | **1.35** | **yes** |
| angular | coupled framework | TypeScript | 63 / 173 | 1.47 | [0.98, 2.18] | 1.39 | no |

**Answer: architecture is not the explanation.** Nova is a deeply coupled service — scheduler, compute
manager and API sharing state through a common object layer, nothing like a plugin registry — and it
passes, with the same specificity signature: a defect-fix ratio far above its all-commits ratio. The
plugin-structure hypothesis from run 2 is dead.

What remains is that both passes are Python and the one near-miss is TypeScript. That is now the open
question, and it is a different one from the one we started run 3 with.

### Two cautions that matter more than the point estimate

**Nova's interval is enormous** — [1.63, 16.14]. Its window contained only **28 defect-fixing commits**.
The sign of the effect is clear; the size is essentially unestimable.

**The power bar was expressed in the wrong unit.** It counts *files* (≥60 flagged, ≥120 controls), but for
a count outcome the binding constraint is *events*. Nova cleared the file bar within one file (59) and
still produced a near-useless interval because the event count was tiny. Run 4's bar should be stated in
defect-fixing events, not files. Achieved power at each repository's realised sample, for a 1.5× effect:

| repo | sample | achieved power |
|---|---|---|
| homeassistant | 141 v 375 | 100% |
| angular | 63 v 173 | 98% |
| nova | 59 v 82 | 57% |
| ansible | 50 v 67 | 59% |
| pandas | 27 v 41 | 50% |

**sympy was excluded at the flag step**, before any outcome: 23 flagged files against a bar of 60. A blind
exclusion on a criterion fixed in advance — the same handling flask received in run 1 — and it is recorded
in the manifest rather than deleted.

### Standing after three runs

Two of three adequately-powered repositories pass the pre-registered test, both with the specificity
signature that distinguishes a real signal from residual churn. The third misses narrowly and lacks that
signature. Pooled across all eight repositories (exploratory, not pre-registered): RR 1.77 [1.45, 2.16].

That is enough to say the churn × complexity signal predicts later defect activity **in the Python
repositories tested**, beyond what churn alone explains. It is not enough to say so of TypeScript, where
the single powered datapoint points the other way.

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
