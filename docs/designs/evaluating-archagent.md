---
status: draft - open for review
date: 2026-07-28
---

# Design: How we evaluate archagent

archagent produces suggestions that a person or an agent then acts on. Nothing about that is self-checking:
a signal can be wrong, a prompt can lead a reader to the wrong verdict, and both can degrade without any
test failing. This design lays out how we measure whether the output is any good, and how we tell an
improvement from a regression.

The near-term goal is **confidence in the tool** and a repeatable way to gauge and improve the quality of
its results. A paper is a later consideration; the designs here are chosen so that the evidence they
produce would support one, but nothing is built for publication first.

## Terms used in this document

- **Signal / finding** — one deterministic result from `evaluate`, `drift`, or `check` (e.g. a
  change-prone file). A **check** is the code that produces a family of findings.
- **Precision** — of the findings reported, the share that a competent reviewer confirms. **Recall** — of
  the real problems present, the share reported. We can measure precision; recall is mostly out of reach,
  and this document says where we approximate it.
- **As-of evaluation** — running the tool against a repository as it stood at a chosen past commit, so
  that later history can be used as an outcome nobody could have seen at the time.
- **Held-out** — a repository (or a time window) deliberately excluded from any tuning, so that a
  measurement on it is not a measurement of our own threshold-fitting.
- **Rubric** — a fixed list of scored criteria, half of them machine-checkable and half judged, with an
  anchored scale so two runs are comparable.
- **Defect-fixing commit** — a commit that repairs a reported defect. Recognised two ways: by this
  project's learned commit wording (no external service), or by an issue reference that a public tracker
  confirms was labelled a bug (stronger, and used only inside our evaluation harness).

---

## 1. Why

Everything we currently know about result quality came from one pass in which a single reader labelled the
findings, tuned the thresholds against those labels, and then judged the prompt guidance against findings
they had already labelled. That loop has no independent signal in it. The reported figure — 71% of
duplicated-decision findings confirmed — should be read as "71% by one interested judge", not as a
measurement.

Three specific gaps follow from that:

1. **No outcome that is independent of our judgement.** We ask "does this look like a problem?" and never
   "did this turn out to be one?"
2. **No regression net on real code.** Golden fixtures pin behaviour on ~40 hand-written files. They
   caught nothing about whether the tool still works on Django.
3. **Nothing at all on the agent half.** The skills that turn findings into a report are the part a user
   actually reads, and they have never been evaluated.

---

## 2. What is being evaluated

Three layers, needing three different methods. Conflating them is why "is archagent good?" has been hard
to answer.

| Layer | What it is | How it's judged | Status |
|---|---|---|---|
| **L1 — signals** | the deterministic output of `evaluate` / `drift` / `check` | precision against review; prediction against later defects | partly measured, one biased pass |
| **L2 — skills** | the prompts that judge, cluster, and write up findings | blind comparison against a baseline prompt, scored on a rubric | not started |
| **L3 — artifact as context** | whether a maintained architecture artifact makes a coding agent better | task benchmark | not started; this is the research claim |

This design covers L1 and L2 in full and sketches L3 only far enough to keep from designing it out.

---

## 3. Ground rules

- **No loop where the same party labels, tunes, and grades.** Whoever (or whatever) produces a score must
  not have designed the thing being scored. Where that is unavoidable, the bias is recorded next to the
  number.
- **archagent never depends on an issue tracker.** Defect data is an input to *our evaluation harness*
  only. The shipped tool keeps working with nothing but a git repository.
- **Reproducible or it doesn't count.** Every evaluation names its repositories by URL and pins them to a
  tag or commit SHA, works in a temporary checkout, and never mutates a local working copy.
- **Tuning set and held-out set are separate, and stay separate.** Thresholds were fitted on Django,
  LiteLLM, opencode, OpenHands, and Datasette; those five can no longer produce an unbiased number for
  anything tuned on them.
- **A check must be able to fail.** If an evaluation cannot produce a result that would retire a signal,
  it is not measuring anything. Negative results are the point.
- **Cheap evidence first.** History and public issues before human judgement, because they scale and they
  don't flatter us.

---

## 4. How the pieces fit

```
                    ┌──────────────────────────────────────────────┐
   pinned repos ───►│  as-of checkout  (§5)                        │
   (URL + tag)      │  worktree at <rev> + history bounded --until  │
                    └───────┬───────────────────────┬──────────────┘
                            │                       │
              ┌─────────────▼──────────┐   ┌────────▼─────────────────────┐
              │ §6 corpus regression   │   │ §7 held-out defect study     │
              │ same repos, same rev,  │   │ signals at T vs defect-fixing│
              │ same findings? (CI-ish)│   │ commits in (T, now]          │
              └────────────────────────┘   └──────────────────────────────┘

              ┌────────────────────────────────────────────────────────────┐
              │ §8 end-to-end self-evaluation                              │
              │ describe @rev1 → evaluate → score  →  describe @rev2 →      │
              │ evaluate → score  →  did quality hold? were changes caught? │
              └──────────────────────────┬─────────────────────────────────┘
                                         │ §9 rubric (deterministic + judged)
              ┌──────────────────────────▼─────────────────────────────────┐
              │ §10 blind comparison — is it the *guidance* doing the work? │
              └──────────────────────────┬─────────────────────────────────┘
                                         │  §9 and §10 are judged by a model
              ┌──────────────────────────▼─────────────────────────────────┐
              │ §11 human spot-check — a small blind sample, stored durably,│
              │ giving the agreement rate that calibrates those judgements  │
              └────────────────────────────────────────────────────────────┘
```

---

## 5. Prerequisite — running as of a past commit

Every evaluation below needs the same capability. It has *three* paths into the repository, and each one
reads the present unless told otherwise — missing any of them produces a plausible, silently wrong answer.

**The history half.** `mine_cochange` already accepts `--since`; it needs `--until` (and `evaluate` needs
to pass it through). That bounds churn, fix-churn, and co-change to a window ending at T.

**The commit-wording profile.** `history._subjects` runs `git log --no-merges -n 4000` with no time bound,
so an as-of run would learn the bug-fix recogniser from commits made *after* T and then use it to label
commits from before. The effect on accuracy is small; the problem is that it is leakage, in a study whose
entire premise is that nothing after T touches the signal. It takes the same bound.

**The tree half.** The complexity measure and every branch-value scan read files *from disk*. Bounding the
history without checking out the code measures old history against new code — a silent, plausible-looking
wrong answer. The harness therefore materialises the tree with `git worktree add` (or a shared clone) at
the chosen revision, and runs the tool there.

`drift` has the same issue in `_last_commit_ts`, which matters because §9 scores "drift is near zero right
after describe" as a deterministic check.

Because the paths can disagree, the tool should **warn when `HEAD`'s commit date is newer than
`--until`**: that combination is almost always a mistake, and it is invisible in the output otherwise.

A convenience `--as-of <rev-or-date>` sets `--until` from the revision's date. It does not check anything
out — the caller is responsible for the tree, and the warning above is what catches them if they forget.

---

## 6. Pinned-corpus regression

**Question:** does the tool still produce the same findings on real repositories?

The golden fixtures (`tests/test_golden.py`) pin behaviour on hand-written files. They are fast and they
run in CI, but they cannot notice that a change broke Django. This adds the other half.

A script — `scripts/corpus.py` — reads a manifest of repositories:

```toml
[[repo]]
url = "https://github.com/django/django"
rev = "5.2"                       # tag or SHA, never a branch
paths = { python = ["django"] }
```

For each entry it clones, checks out `rev` into a temp worktree, runs
`archagent evaluate --json --until <rev-date>`, and compares a projection of the result — the same shape
the golden tests use — against a recorded expectation under `tests/corpus/<name>.json`.

**Not a shallow clone.** `--depth` truncates history, and churn, fix-churn and co-change are computed from
the full log — a shallow clone would quietly produce different numbers rather than an error. Use a blobless
partial clone (`git clone --filter=blob:none`), which keeps every commit and fetches file contents on
demand, and cache the clone between runs. Expectations are regenerated the same way as the unit goldens,
by an explicit environment variable, so accepting a change is always a deliberate act.

Differences from the unit goldens, all deliberate: it needs network and is therefore opt-in
(`pytest -m corpus` or a make target, not the default suite); the expectations are large, so the script
prints a summarised diff (findings added/removed by sign and subject) rather than a raw JSON dump; and a
change here is *expected* whenever a check improves, so the workflow is review-the-diff-then-accept, same
as the goldens.

**Repository selection.** The five already used for tuning go in this set, because regression testing does
not need independence — it needs realism and stability. The held-out set of §7 must not be used here, or
it stops being held out.

---

## 7. Held-out defect study — do the signals predict anything?

**Question:** in the parts of a system archagent flags, are more defects reported afterwards?

This is the measurement that does not depend on our judgement, and the one that can retire a signal.

**Design.** Choose a cutoff T (initially 12 months before the pinned head). Compute signals using only
history ≤ T against the tree at T (§5). Then measure, in the window (T, now], the **defect-fixing commits
touching each file**.

**Two ways to recognise a defect fix**, deliberately layered so the study runs without any API:

- *History-only* — the project's own learned commit wording (`history.py`). No external service, available
  for every repository, and already validated across five commit styles.
- *Issue-verified* — the commit references an issue that a public tracker confirms carries a bug label.
  Stronger, needs a GitHub token, and is run on a subset as a **cross-check on the history-only proxy**.
  If the two disagree badly on a repository, that repository's history-only numbers are not trusted.

The issue-verified path exists to keep us honest about the proxy, not to become a dependency. Nothing in
the shipped tool learns about issues.

**The control is the whole experiment.** Churn predicts churn: flagged files are high-churn by
construction, so "flagged files change more later" is true by definition and says nothing. Every
comparison is therefore against **churn-matched controls** — unflagged files in the same churn decile at
T, matched also on size. The claim under test is narrow and falsifiable:

> Among files with comparable change history at T, do the ones archagent flagged accumulate more
> defect-fixing commits afterwards than the ones it didn't?

Two ablations make the answer useful rather than merely positive: complexity-only ranking versus the
churn × complexity product (does the second axis earn its place?), and total churn versus fix-weighted
churn (§5 of the hotspots design left this open).

**For Check B**, the outcome differs: for each flagged duplicated decision, do its re-implementing files
subsequently change **together** in defect-fixing commits more than a matched set of file groups? That is
the cost the finding claims — a change to one forcing a change to the others — expressed as something the
history can confirm or deny.

### 7.1 Pre-registered analysis

Fixed **before** any outcome is computed, because every one of these choices moves the answer, and picking
them after seeing results is the same failure as tuning thresholds on the repositories you then measure.
Deviations get recorded in the results with a reason.

**Order of operations.** Signals are computed and the flagged set is **written to disk and committed**
before any outcome data is fetched. The harness refuses to compute outcomes if the flagged set does not
already exist. This is mechanical, not a matter of discipline.

**1. Renames.** Follow them. A file flagged at T that was later moved would otherwise have its subsequent
fixes attributed to nothing — deflating the signal precisely for the churny files the checks flag, which
biases *against* us in a way that looks like a null result. The miner reads `git log --name-status -M` and
canonicalises every later path back to its name at T. Files whose rename chain is ambiguous are dropped and
counted.

**2. Files that disappear.** A flagged file deleted during the window is **excluded from the primary
analysis and reported as a count**. Deletion is ambiguous — it may be the refactor the finding asked for,
or an unrelated reorganisation — and either inclusion rule embeds an assumption. The count is published so
the reader can see how much was dropped, and a sensitivity analysis treating deletions as zero-defect is
reported alongside. If the two disagree, neither is claimed.

**3. Matching.** Stratify by churn decile at T, computed over all scored files in the repository. Within
each decile, compare the defect-fix rate of flagged files against unflagged ones, then pool across deciles.
Stratification rather than nearest-neighbour matching: it has no sampling variance, no arbitrary control
count, and it makes the comparison legible decile by decile. Deciles containing no flagged file, or fewer
than five unflagged ones, are excluded and counted.

**4. The statistic.** Primary outcome is the **stratified rate ratio** of defect-fixing commits per file,
flagged versus unflagged, with a **95% bootstrap interval resampling files within strata** (2000 draws).
Bootstrap rather than a parametric interval because per-file defect counts are overdispersed and we would
rather not defend a distributional assumption.

**5. Normalisation.** Primary outcome is the raw count of defect-fixing commits touching the file in
(T, now], because the comparison is already stratified on churn and the strata make size roughly
comparable. Per-KLOC is reported as a secondary and is not the basis of any claim.

**Primary versus secondary.** Exactly one primary test per check, stated in advance:

- *Check A* — flagged (churn × complexity, top quartile on both) versus unflagged, stratified as above.
- *Check B* — for each flagged duplicated decision, do its files change **together** in a defect-fixing
  commit more often than a matched set of same-size file groups drawn from the same subsystem?

Everything else — complexity-only versus the product, fix-weighted versus total churn, per-KLOC, the
deletion sensitivity check — is **secondary and exploratory**. Secondary results may motivate a future
pre-registered test; they are never reported as findings on their own.

**What the result licenses.** If the primary interval's lower bound exceeds 1, the check predicts later
defect activity beyond what churn alone explains. If it includes 1, we do **not** claim predictive value —
and specifically, the complexity axis of Check A would then need justifying on other grounds (readability,
reviewer agreement) or dropping. Predicting defects is not the only reason a signal might be worth having,
but it is the reason we have been implying, so a null result changes what we may say.

**Defect-fix recognition, exactly.** History-only is the learned recogniser bounded to (T, now]. The
issue-verified cross-check, run on two repositories, links a commit to an issue by an explicit reference in
the message (`#123`, `PROJ-456`), then asks the tracker whether that issue carries a bug-type label; the
label vocabulary differs per project, so the mapping is recorded per repository in the manifest rather than
guessed. Where the two recognisers disagree by more than 20% of commits on a repository, that repository's
history-only numbers are reported but not pooled.

**Repositories.** A held-out set of 3–4, disjoint from every repository used for tuning or regression —
which rules out Django, LiteLLM, opencode, OpenHands, Datasette, vue-core and my-research-assistant, all of
which have already been read while building or calibrating the checks. Selection criteria, fixed now:
several years of history, a public issue tracker with bug labels, a mix of commit conventions, at least one
non-Python project, and no prior contact with archagent. The specific repositories and their pinned
revisions are chosen once, recorded in the manifest, and **not changed after a run has been made** — the
usual way a held-out set decays is by being quietly swapped when the numbers disappoint.

---

## 8. End-to-end self-evaluation

**Question:** run the whole loop on a real repository — does it produce a good artifact, and does it stay
good when the code moves on?

This is the piece that exercises L1 and L2 together, and the only one that tests **update**, which is
where an artifact-maintenance tool most plausibly fails.

A command — `scripts/selfeval.py <repo-url> --from <rev1> --to <rev2>` — runs:

1. **Pull** the repository into a temporary directory and check out `rev1`.
2. **Initialise** archagent (`init`, non-interactive) and run **describe** as of `rev1` to produce the
   initial architecture artifact.
3. **Evaluate** as of `rev1`.
4. **Score** the artifact and the evaluation against the rubric (§9).
5. **Advance** to `rev2` and re-run **describe** in update mode, then re-evaluate.
6. **Score again, and diff the scores.** Did quality hold? Were the changes between `rev1` and `rev2`
   reflected in the artifact — new subsystems, removed ones, changed dependencies — or did stale content
   survive?

Output is a scorecard (JSON, plus a readable markdown summary) written under `evaluations/<repo>-<date>/`,
comparable across runs so a change to a prompt can be shown to help or hurt.

**The dependency to settle:** steps 2 and 5 need a coding agent, run non-interactively. That makes this
command different in kind from everything else archagent ships — it invokes an agent rather than being
invoked by one. Which agent, how it is pinned (model + version), and how much its variance swamps the
signal are open questions; at minimum every scorecard records the agent and model used, and a repeat run
on the same inputs establishes the noise floor before any two scores are compared.

---

## 9. The rubric

Two halves, deliberately. The deterministic half is cheap, reproducible, and cannot be talked into a good
score. The judged half covers what matters most and cannot be automated.

**Deterministic checks** (pass/fail or a count, computed by code):

- The artifact conforms to the ADL (`lint-docs` clean; required documents present; every `**Covers:**`
  glob resolves to at least one file).
- Coverage: the share of source files claimed by some subsystem's `**Covers:**`.
- Every command completed without error, and no traceback appears in any output.
- **Self-consistency:** `drift` run immediately after `describe` reports close to nothing. A fresh artifact
  that already disagrees with the code is a describe bug.
- Invariants parse, generate checker configs, and `check` passes them **non-vacuously** (the existing
  vacuity gate).
- `evaluate` coverage: how many signal families were inactive for missing metadata, and whether any list
  was truncated.
- For the update run: what fraction of files changed between `rev1` and `rev2` fall inside a subsystem
  whose document was also updated.

**Judged criteria** (scored 1–5 by a subagent against anchored descriptors, each score requiring a cited
`file:line` as evidence):

- *Accuracy* — does the document describe the system that is actually there? Spot-check claims against code.
- *Completeness* — are the major subsystems present, and is anything significant missing?
- *Usefulness of invariants* — would these catch a real violation someone might plausibly commit, or are
  they restatements of what the code already enforces?
- *Prose quality* — does it follow `writing-style.md`: purpose before mechanism, no undefined jargon,
  claims grounded in code?
- *Evaluation report quality* — are findings judged rather than echoed, clustered to roots, prioritised;
  are dismissals reasoned?
- *Update quality* (second run only) — are the changes reflected, and is stale content gone?

**Calibration.** These scores are only worth tracking once we know how far the judge agrees with a
person; §11 is how that is established, and the agreement interval belongs next to any score quoted from
this rubric.

**Anti-gaming.** Scores without a citation are discarded. The judging subagent is a separate invocation
that sees the artifact and the code but not the previous scores, so it cannot anchor on them. Where we
have ground truth — the labelled intended-family cases from the corpus pass — it is scored automatically
rather than judged, and the judge is not told which findings those are.

---

## 10. Blind comparison for the skill layer

**Question:** is the guidance doing the work, or would any competent reader with the same findings reach
the same report?

Same repository, same `evaluate --json` output, three arms:

- **A** — the archagent `evaluate` skill as shipped.
- **B** — a generic prompt: "here are some architecture findings, write a report."
- **C** — the findings with no guidance at all beyond the tool's own recommendation text.

Reports are stripped of anything identifying the arm (the guidance already tells writers to keep group
letters and sign names out of prose, which helps), shuffled, and scored by a judge that is not told which
is which, using the §9 report criteria.

The measurement that matters most has ground truth: the corpus pass labelled three findings as intended
families that a good report must **dismiss with a reason**. Whether an arm dismisses them correctly is
checkable, not a matter of taste.

**A caution to record with any result:** if the judge and the author are the same model family, the
comparison partly measures self-preference. Use a different model for judging where possible, say which
was used, and calibrate it against human labels (§11) before treating a difference between arms as real.

---

## 11. Human spot-check and calibration

**Question:** do the automated judgements of §9 and §10 mean anything?

Nothing so far establishes that. A model scoring a rubric produces a number whether or not the number
tracks reality, and the corpus pass showed how easily a single interested labeller drifts. The fix is not
more human labelling — nobody is going to review 78 hotspot findings — but *enough* human labelling to
measure how far the automated judge agrees with a person. That agreement rate is what turns every
automated score into an estimate with an error bar instead of an assertion.

**What gets reviewed.** Two kinds of item, because they answer different questions:

- **Findings** — confirm / dismiss / unsure, plus a one-line reason. Gives per-signal precision from a
  judge who did not build the signal.
- **Rubric scores** — agree / too high / too low, plus a reason. Shows whether the judging subagent drifts
  systematically in one direction, which a single overall agreement number would hide.

**Mechanics.** `scripts/spotcheck.py generate` writes a worksheet; `… ingest` parses it back. Three
details decide whether the labels are worth collecting:

- **Blind the tool's own claim.** The worksheet shows evidence only — the files, the value set, a short
  code excerpt, the churn — and withholds severity, confidence, and the recommendation until after the
  verdict is recorded. Shown up front, they anchor the reviewer and the exercise measures agreement with
  our own prior instead of with reality.
- **A worksheet, not a prompt loop.** Markdown, one block per item, with a fixed answer line the parser
  reads leniently. Thirty items is a week of spare moments, not one sitting, and a file can be reviewed
  in an editor, committed, and diffed.
- **Stratified sampling, capped.** Across signals, confidence tiers, and repositories, so a cheap
  high-confidence class can't dominate the estimate. Where the tool *rejected* something and we can
  reconstruct it (the cohesion and stop-value cases), include a few — precision alone never notices a
  check that has quietly stopped finding anything.

**The label store is the durable asset.** `evaluations/labels/<repo>.jsonl`, one record per labelled
finding, keyed by a **revision-independent identity** (sign + owner path + a hash of the value set) so a
label survives re-runs and tool changes. Each record keeps the verdict, the reason, who reviewed it, the
date, and the tool's claim *at the time of labelling*. Re-running asks only about items with no label. If
a finding's evidence has materially changed, its label is marked stale rather than silently reused.

Two properties follow from storing them this way. Labels are expensive, and this stops us spending them
twice on the same finding. And **once written, a label is not quietly rewritten** — changing a verdict
requires a note saying why, or the labels drift toward whatever the tool currently claims and the whole
exercise becomes circular.

**What it reports.** Human-vs-judge agreement on the overlapping items with a confidence interval;
per-signal precision from human labels, with intervals; and the direction of any systematic rubric drift.
Small samples give wide intervals, so the scorecard prints the interval — a point estimate off thirty
labels invites false precision.

**A convergence worth noting.** This store is exactly the "reviewed — intended, dismissed" record that
Appendix A of `hotspots-and-single-source-of-truth.md` wanted a declared-owner file for: the three
intended families that correctly re-surface on every corpus run get labelled once and stay labelled. If
this works, the separate `capabilities.md` format is probably unnecessary.

**Cautions.** This is an evaluation mode and never a runtime gate — the ground rule that a full pass needs
no human still holds. And a label from the tool's own author is better than model-only but is not
independent; the store records who reviewed each item so that can be weighed later.

---

## 12. Tooling — what we build and what we adopt

The judged half of §9 needs the usual scaffolding around an LLM judge: prompt construction, score
extraction against a schema, retries, thresholds, caching (judge calls are the slow, expensive part), and
some way to combine machine-checkable gates with judged criteria in one score.

**DeepEval is the candidate on the table** for that, as a dev/test dependency only. Two things fit well.
Its `DAG` metric — a graph-based judge builder with deterministic branching and model calls at the leaves —
is close to the shape §9 already has, where a failed ADL conformance check should short-circuit the whole
score rather than be averaged with a prose rating. And it is pytest-shaped, which matches the suite we
already run.

Two things fit badly. Its metric catalogue (answer relevancy, faithfulness, contextual recall) assumes a
query → answer → context triple, which an architecture artifact judged against a codebase is not; we would
use `G-Eval` and `DAG` and none of the rest, and its `LLMTestCase` shape would mean stuffing a document set
into `actual_output`. Shoehorning tends to drag what gets measured toward what the framework represents
easily, and criteria like "would this invariant catch a violation someone might plausibly commit" resist
that shape. Separately, the annotation and persistence features are the hosted product, whereas the label
store of §11 is deliberately a local, versioned, diffable file — the most distinctive part of this design
is the part such a framework least supports without its platform.

**Decision: not yet, and not ruled out.** Build order items 1–3 have no model in the loop, so nothing there
would use it. At item 4, build one rubric criterion **twice** — hand-rolled and with `DAG` — and compare
effort and output. That is a day's work and settles the question with evidence.

Two rules that hold either way:

- **No evaluation dependency enters the shipped package.** Everything here lives in the dev/test group;
  `archagent` keeps running with nothing but a git repository.
- **The judge sits behind a thin interface, and the scorecard schema is ours.** Whatever produces a score,
  the stored shape does not change, so the trial is cheap to reverse and results stay comparable across a
  tooling switch.

**A caution about the stack.** There is a lot of model judgement piled up here — a model-judged framework
scoring a model-written report about a tool whose findings a model acts on. §11 is the only thing anchoring
that to a human, and no framework supplies it. Adopting one should not create the impression that the
calibration problem has been handled.

---

## 13. Threats to validity

Written down because they are easy to forget once numbers exist.

- **Tuning on the evaluation set.** Cohesion, tightness, and the escape guards were all fitted on the five
  corpus repositories. Any number from those repositories overstates quality. Only §7's held-out set can
  correct this.
- **Churn autocorrelation** (§7) — addressed by matched controls; without them the study is worthless.
- **Repository selection.** Five popular, well-maintained, mostly Python projects are not the population
  archagent runs on. Small and messy repositories are where the history signals are weakest and are
  under-represented.
- **Proxy drift.** "Defect-fixing commit" is a proxy for "defect". The learned recogniser captures
  fix-labelled maintenance, which on Django was roughly half features and docs.
- **Self-preference in judging** (§10).
- **Goodhart.** Once the rubric exists, prompts will be tuned to it. Keep some criteria out of the prompts,
  and re-read the rubric when scores rise without the output visibly improving.

---

## 14. Build order

1. **`--until` / as-of plumbing** (§5) — the prerequisite for everything else, including the mismatch
   warning. Small.
2. **Pinned-corpus regression** (§6) — the highest ratio of protection to effort, and it makes every later
   change safer to make.
3. **Held-out defect study** (§7) — the credibility anchor, and the only item that can retire a signal.
   Start with the history-only proxy; add issue verification as a cross-check on two repositories.
4. **Self-evaluation tool + rubric v1** (§8, §9) — begin with the deterministic half only, which is
   useful on its own and needs no agent; add the judged half once the noise floor is known. This is the
   point at which to run the DeepEval trial of §12, not before.
5. **Human spot-check and calibration** (§11) — build it alongside the judged half of the rubric, not
   after. Until an agreement rate exists, a rubric score is a number with unknown meaning.
6. **Blind comparison** (§10).
7. **L3 task benchmark** — not designed here. Revisit once L1 and L2 have numbers.

---

## 15. Out of scope

- **Any runtime dependency on an issue tracker.** Defect data belongs to the harness, not the tool.
- **Modifying the local test-repository checkouts.** They are the measurement baseline; evaluations work in
  temporary clones and leave them untouched.
- **Human-subject studies.** Everything here is judged by code, by public history, or by a model.
- **Benchmarking against other tools.** Interesting later; it needs a shared task definition we don't have.
- **Optimising for a paper.** The evidence should be publishable if we want it to be, but no evaluation is
  chosen because it would look good in one.
