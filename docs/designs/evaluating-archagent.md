---
status: active
date: 2026-07-28
updated: 2026-08-15
---

# Design: How we evaluate archagent

archagent produces suggestions that a person or an agent then acts on. Nothing about that is self-checking:
a signal can be wrong, a prompt can lead a reader to the wrong verdict, and both can degrade without any
test failing. This design lays out how we measure whether the output is any good, and how we tell an
improvement from a regression.

The near-term goal is **confidence in the tool** and a repeatable way to gauge and improve the quality of
its results. A paper is a later consideration; the designs here are chosen so that the evidence they
produce would support one, but nothing is built for publication first.

## If you are reading this for the first time

The document is in four parts, and you do not need all of them.

| Part | What it answers | Read it if |
|---|---|---|
| **I — Orientation** (§1–4) | what we are trying to establish and under what rules | always; it is short |
| **II — The instruments** (§5–11) | how evidence is produced, from cheapest to most judged | you are running an evaluation or building one |
| **III — The process** (§12–17) | how evidence becomes a decision about a proposed change | you are proposing a change to archagent |
| **IV — Discipline and limits** (§18–21) | what keeps this honest, and what it still cannot tell us | before quoting any number from it |

**The shortest useful summary.** archagent is judged at two levels: the deterministic *signals* it computes,
and the *artifact* its prompts generate. Signals are checked against outcomes nobody chose — whether a
flagged file later accumulated bug fixes. Artifacts are scored against a fixed rubric, half of it computed
by code and half judged by a reader. Because a judged score means nothing on its own, a small number of
expensive **calibration runs** have both a model and an independent human score the same artifact, and the
agreement between them is what makes the cheap, frequent **scoring runs** interpretable. Every confirmed
defect is banked as a mechanical assertion so it can never quietly return.

**One idea does most of the work**, and it is worth stating before the detail: *no party may label, tune and
grade the same thing.* Nearly every rule below is that principle applied somewhere — held-out repositories,
blinded reviewers, excluding the repository that prompted a change, recording who could see what.

## Terms used in this document

- **Signal / finding** — one deterministic result from `evaluate`, `drift`, or `check` (e.g. a
  change-prone file). A **check** is the code that produces a family of findings.
- **Artifact** — the `architecture/` directory archagent generates and maintains for a target repository:
  constitution, invariants table, subsystem documents, ADRs, diagrams.
- **Target** — the repository being evaluated, always named as a URL pinned to a commit or tag. A target
  is a repository *at a revision*, never a repository.
- **Precision** — of the findings reported, the share a competent reviewer confirms. **Recall** — of the
  real problems present, the share reported. We can measure precision; recall is mostly out of reach, and
  this document says where we approximate it.
- **As-of evaluation** — running the tool against a repository as it stood at a chosen past commit, so
  later history can be used as an outcome nobody could have seen at the time.
- **Held-out** — a repository (or time window) deliberately excluded from any tuning, so a measurement on
  it is not a measurement of our own threshold-fitting.
- **Fresh repository** — one archagent has never been run against and no reviewer has previously read. A
  depleting resource: each use consumes it permanently (§12).
- **Rubric** — a fixed list of scored criteria, half machine-checkable and half judged, with an anchored
  scale so two runs are comparable (§9).
- **Recurrence suite** — assertions derived from confirmed defects, phrased as facts about a pinned
  target, checked mechanically against any newly generated artifact (§13).
- **Checklist** — a per-target list of specific claims an artifact should get right, with the correct
  answer stated, scored `correct` / `wrong` / `absent` by a judge (§14).
- **Calibration run / scoring run** — the two kinds of evaluation run. A calibration run is scored twice,
  by a model judge and independently by a human; a scoring run is scored once, by a model judge (§12).
- **Arm** — one condition in a comparison. Two arms of a prompt change means generating the artifact twice
  for the same target, once under each version of the prompt, and comparing (§10, §15).
- **Noise floor** — how much a score moves between identical runs, from generation and judging variance
  alone. Until it is measured, "significantly better" cannot be computed (§15).
- **Objective vs subjective change** — an objective change is a defect fix whose correctness can be
  demonstrated without a judge; a subjective change is a prompt edit or a heuristic adjustment whose value
  is a matter of degree. They are accepted by different rules (§15).
- **Defect-fixing commit** — a commit repairing a reported defect. Recognised two ways: by the project's
  learned commit wording (no external service), or by an issue reference a public tracker confirms was
  labelled a bug (stronger, used only inside our evaluation harness).

---

# Part I — Orientation

What we are trying to establish, about which parts of the tool, and under what rules.

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
| **L1 — signals** | the deterministic output of `evaluate` / `drift` / `check` | precision against review; prediction against later defects | **measured** — 3 of 4 powered repositories predict later defects (§7); precision still from one biased pass |
| **L2 — skills** | the prompts that judge, cluster, and write up findings | blind comparison against a baseline prompt, scored on a rubric | machinery built, **no labels**; blocked on an independent reviewer |
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
  anything tuned on them. If an automatic proposer is ever introduced (§20) this becomes a three-way
  split, because selecting among proposals consumes a held-out set as surely as tuning does.
- **A check must be able to fail.** If an evaluation cannot produce a result that would retire a signal,
  it is not measuring anything. Negative results are the point.
- **Cheap evidence first.** History and public issues before human judgement, because they scale and they
  don't flatter us.

---

## 4. How the pieces fit

Two flows. The **instruments** (Part II) turn a repository into evidence. The **process** (Part III) turns
evidence into a decision about a proposed change.

```
  INSTRUMENTS (Part II) — producing evidence
  ─────────────────────────────────────────
                    ┌──────────────────────────────────────────────┐
   pinned repos ───►│  as-of checkout  (§5)                        │
   (URL + commit)   │  worktree at <rev> + history bounded --until  │
                    └───────┬───────────────────────┬──────────────┘
                            │                       │
              ┌─────────────▼──────────┐   ┌────────▼─────────────────────┐
              │ §6 corpus regression   │   │ §7 held-out defect study     │
              │ same repos, same rev,  │   │ signals at T vs defect-fixing│
              │ same findings? (CI-ish)│   │ commits in (T, now]          │
              └────────────────────────┘   └──────────────────────────────┘
                                     the two objective instruments; no judge

              ┌────────────────────────────────────────────────────────────┐
              │ §8 describe an artifact  →  §9 score it                     │
              │      9.1 deterministic (no model)                           │
              │      9.2 judged 1-5 against anchors (a model, or a human)   │
              └──────────────────────────┬─────────────────────────────────┘
                                         │
              ┌──────────────────────────▼─────────────────────────────────┐
              │ §11 human spot-check — an independent read of the same      │
              │ artifact, giving the agreement rate that makes §9.2 mean    │
              │ something.  §10 blind comparison isolates the *guidance*.   │
              └────────────────────────────────────────────────────────────┘

  PROCESS (Part III) — turning evidence into a decision
  ────────────────────────────────────────────────────
     §12 calibration run                        §12 scoring run
     fresh repo, judged twice                   any repo, judged once
     (human + model)                            (model)
            │                                          │
            │ leaves behind                            │ produces
            ▼                                          ▼
     §13 recurrence entries  ──────────►  §15 accepting a change
     §14 checklist entries                  objective  → test + ship
            │                               subjective → suites pass 100%
            │                                          + defect stops recurring
            │                                          + no decline elsewhere
            ▼                                          │
     §17 the ledger  ◄──────────────────────────────────┘
     one row per run; §16 update pairs link via predecessor_run_id
```

**The direction that matters:** calibration runs are expensive and rare, and most of their value is not
their scores but the recurrence and checklist entries they leave behind. Those entries are what make the
cheap, frequent scoring runs able to decide anything.

# Part II — The instruments

Each section below is one way of producing evidence, ordered from cheapest and most objective to most
expensive and most judged. Nothing here decides whether a change is accepted — that is Part III. These are
the measuring devices.

A newcomer wanting the short version: §6 catches regressions, §7 is the only evidence that a signal
predicts anything, §9 scores a generated artifact, and §11 is what makes a model's score mean something.

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

**As built** it is opt-in pytest rather than a standalone script (`tests/corpus.py` + `tests/test_corpus.py`,
marked `corpus` and excluded from the default suite by `addopts`), which reuses the golden tests' projection
and their record-then-review workflow instead of duplicating both. `tests/corpus_manifest.toml` lists the
repositories:

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

**Expectations are recorded per repository, not all at once.** A manifest entry with no recorded
expectation skips — and skips *before* any network work, so declaring a repository costs nothing until
someone records it. Each clone is hundreds of megabytes, and a harness that pulls five of them to then
skip three is one nobody runs.

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

**Minimum size.** A repository needs enough *scored files* — not merely enough history — for decile
stratification to have anything to compare. Run 1 found this the hard way: flask has thousands of commits
and 22 scored files, and every one of its strata fell below the five-control minimum. See
`docs/evaluations/defect-study/RESULTS.md`.

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

Output is a scorecard (JSON, plus a readable markdown summary) written under `<eval-home>/selfeval/<repo>/`,
comparable across runs so a change to a prompt can be shown to help or hurt.

**Persist a trace, not only the scorecard.** Alongside the scores, record what actually happened: which
findings the skill was given, which it confirmed or dismissed and on what stated grounds, what reached the
report, and where any of that disagreed with the label store. A score says something regressed; a trace
says where. This is also the input any future feedback loop would mine (§20), and it makes failures
diagnosable by hand long before that.

**The dependency to settle:** steps 2 and 5 need a coding agent, run non-interactively. That makes this
command different in kind from everything else archagent ships — it invokes an agent rather than being
invoked by one. Which agent, how it is pinned (model + version), and how much its variance swamps the
signal are open questions; at minimum every scorecard records the agent and model used, and a repeat run
on the same inputs establishes the noise floor before any two scores are compared.

---

## 9. The rubric

Two halves, deliberately. The deterministic half is cheap, reproducible, and cannot be talked into a good
score. The judged half covers what matters most and cannot be automated.

### 9.1 The deterministic half

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
- **Orientation:** the index carries a system map and prose before its catalog. Both are already mandated
  by the `describe` prompt, which is exactly why this check exists — a requirement nobody verifies stops
  happening quietly (Appendix A).
- Every command is invoked through the checkout being scored, not through `PATH`. A global install
  shadowing the venv once failed the `tools.clean` gate with a missing subcommand and reported it as a
  defect in the artifact.

### 9.2 The judged half

**Judged criteria** (scored 1–5 by a subagent against anchored descriptors, each score requiring a
`file:line` citation that **resolves** — the path must exist and the line must be inside it. A well-formed
citation is not a true one, and fabricated citations are the specific failure mode: an artifact review is
mostly unfalsifiable prose. A criterion whose citations all fail to resolve is discarded like an uncited
one; an ambiguous bare basename resolves if any candidate supports it, since vagueness is not fabrication):

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

**The label store is the durable asset.** `<eval-home>/labels/<repo>.jsonl`, one record per labelled
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

**Agreement is conditional, not a constant.** The rate is measured over a particular distribution of
output. Anything that moves that distribution — a prompt rewrite, a model change, an optimiser (§20) —
invalidates it, and it has to be re-sampled from the new output rather than carried forward.

**Cautions.** This is an evaluation mode and never a runtime gate — the ground rule that a full pass needs
no human still holds. And a label from the tool's own author is better than model-only but is not
independent; the store records who reviewed each item so that can be weighed later.

---

---

# Part III — The process

Part II lists instruments. This part is the procedure that uses them: what a run is, what gets recorded,
and the rules by which a proposed change to archagent is accepted or rejected.

The problem this part exists to solve: an evaluation produces a list of defects and a temptation to fix
each one. Some of those fixes are improvements and some are the tool memorising one repository. Without a
written rule, the difference is decided by whoever is holding the defect list, which is the same closed
loop §1 opens by criticising.

## 12. Two kinds of evaluation run

An **evaluation run** applies archagent at a known commit to a target repository at a known commit, and
scores the result. Everything in Part III is built from runs of two kinds.

| | Calibration run | Scoring run |
|---|---|---|
| **Target** | a **fresh** repository | known or fresh |
| **Scored by** | a model judge **and** an independent human, same rubric, neither seeing the other's scores | a model judge |
| **Produces** | agreement data; new recurrence entries; new checklist entries | a score, comparable to other scoring runs |
| **Cost** | hours of human attention, plus the judge | the judge only |
| **Frequency** | rarely — the supply of fresh repositories is finite | often; this is the routine measurement |

**Calibration runs are what make scoring runs mean anything.** A model judge's number is uninterpretable
on its own. Agreement with an independent human on the same artifact and the same rubric is what converts
it from an opinion into an estimate with a known error. Calibration also produces the durable assets: the
defects found become recurrence entries (§13), and the ground truth established while finding them becomes
checklist entries (§14). A calibration round is expensive and most of its value is in what it leaves
behind, not in its scores.

**Scoring runs are the routine instrument.** They are what Part III's acceptance rules consume. They need
no human, so they can be run across several targets for every proposed change.

### Fresh repositories are a consumable

Each calibration run permanently consumes one fresh repository: afterwards it is a known target, useful for
scoring and regression but no longer able to produce an independent read. Budget them.

**"Fresh" also has to be fresh to the judge.** A model has very likely seen Django in pretraining and can
describe it from memory rather than from the code in front of it — which is the same failure as a citation
that resolves without supporting its claim. For calibrating a *judge*, prefer repositories obscure enough
that memory is not an option. A small, recently published project is a better calibration target than a
famous one, despite being a worse regression target.

## 13. The recurrence suite

Every confirmed defect is a fact about a target at a revision. The recurrence suite turns those facts into
mechanical assertions, so that a defect found once can be checked for on every future artifact generated
for that target.

It lives in the evaluation data repository, not in archagent: it is data, it grows without bound, and
running it requires generating an artifact, which is expensive.

### Entries are phrased against the target, not the artifact

This is the rule that makes an entry survive. An assertion like *"the artifact must not mark SKILL-002 as
`active`"* breaks the first time a regenerated artifact numbers its invariants differently — and it does,
every time, because the numbering is invented afresh on each run.

Write the ground truth instead:

> **obstudio @ 88aebe8** — `skills/*/scripts/` contains ~2,616 lines of logic across four files
> (`validate_gap_closure.py` 712, `validate_reader_report.py` 599, `validate_configure_output.py` 1222,
> `scan_python_otel_topology.py` 83). Any claim that per-skill scripts are shims over
> `references/scripts/` is false.

That is checkable against any artifact, however it chooses to name things, and it stays true because the
target is pinned.

### Every negative assertion needs a positive pair

Most defects express naturally as *"the artifact must not claim X"*. Left alone, that drives artifacts
toward silence: an artifact passes "must not describe `Store` as a single mutex" by never mentioning
concurrency at all. That is the same degenerate direction `check_specificity` exists to punish (§9).

So each negative gets a positive pair wherever the topic is load-bearing:

- *must not* claim `Store` is a single `sync.Mutex`, **and**
- *must* say something about how `Store` serialises access.

Some defects are naturally positive already — *"the artifact must describe the origin policy"* — and those
are the better-shaped entries. Prefer "must address X correctly" over "must not say Y" when both are
available.

### What the suite catches, and what it cannot

Two mechanical checks are available. **Text assertions** match claims the artifact must not make. **Citation
assertions** ask whether the artifact engaged with a specific piece of evidence at all — the inverse of the
citation resolution already used on reviews (§9), and the stronger of the two, because it asks what the
author looked at rather than what they wrote.

Measured against the real obstudio artifact:

| ground truth the artifact should have engaged with | result |
|---|---|
| CORS header, `api/handler.go:283` | file cited at 40, 75, 76, 354 — nowhere near 283 |
| WebSocket `CheckOrigin`, `web/websocket.go:21` | file cited at 204, 233, 238, 260 — nowhere near 21 |
| `DELETE` route, `api/handler.go:93` | cited at 75, 76 — **passes** |
| `Store` mutexes, `store/store.go:313` | cited at 314 — **passes** |

The first two are a real defect caught with no judge. The last two are false passes, and not by accident:
one is an invariant citing `handler.go:75-92`, so a proximity window sees a citation seventeen lines away
and calls it engaged; the other cites `store.go:314` for a neighbouring fact while describing line 313
wrongly.

So the suite covers exactly one class:

- **Omission** — the artifact never looked at the evidence. Mechanical, cheap, run every time.
- **Misreading** — the artifact looked at the right place and drew the wrong conclusion. **Not mechanical,
  and no window size fixes it**: too tight raises false alarms on off-by-a-few citations, too loose passes
  a citation range that stops one line short of its own counterexample.

Misreading is the residual, and §14 is what covers it.

## 14. Per-repository checklists

A checklist is a fixed list of specific claims an artifact should get right about one target, **with the
correct answer written down**, scored `correct` / `wrong` / `absent` by a judge.

The distinction from the open rubric (§9) is the ground truth. Do not ask a judge *"is the concurrency
description correct?"* — that is a research task, and it re-runs the very error the checklist exists to
prevent. Ask:

> `Store` uses a `sync.RWMutex` plus three further mutexes — `subMu`, `invalidateMu`, `changeMu`
> (`store/store.go:313-332`). Does the artifact convey this?
> **correct / wrong / absent**

That converts research into comparison. It is cheaper (the judge does not explore the codebase), more
reproducible (fixed questions in a fixed order), and ternary rather than 1–5, so aggregation is simple and
the variance is far below a five-point judgement.

The reading was done once, by a human, during a calibration run. **The checklist is where that work is
banked so it never has to be repeated.**

### Three cautions

**A checklist is an answer key.** Whoever authors a prompt change must not be reading it while doing so, or
the change is fitted to the test rather than to the problem. The same blinding rule as §15's exclusion of
the prompting repository.

**It is still a model reading prose.** More reproducible than open scoring, not immune. Expect the residual
error in the boundary between `wrong` and `absent` — an artifact that gestures at the right topic without
committing to a claim.

**The open rubric must survive alongside it.** A checklist can only re-test known defects. If it replaces
the open rubric, the next calibration finds nothing new and the suite stops growing. The open rubric
explores, the checklist exploits, and every new defect the open rubric finds becomes a checklist entry for
the round after.

## 15. Accepting a change

Evaluation produces proposed changes. They are accepted by two different rules, and telling them apart is
the first decision.

**An objective change is a defect fix whose correctness can be demonstrated without a judge.** A glob
reported as a missing file; a wrapped declaration read only to its first line; `check` printing "All
invariants hold" having checked none. These are accepted on a passing test that would have failed before —
no comparison, no scoring runs. Write the regression test, fix, ship.

**A subjective change is a prompt edit or a heuristic adjustment whose value is a matter of degree.** Guidance
telling `describe` to ground abstractions at first mention; a new pattern in a matching heuristic. There is
no test that proves these correct, which is why they need the procedure below.

### The gate for a subjective change

1. **The unit suite and the recurrence suite pass 100%.** Non-negotiable and cheap.
2. **The recurrence suite shows the specific defect no longer recurs.** This is the evidence *for* the
   change.
3. **Scoring runs on N targets show no significant decline**, where the targets include at least one fresh
   repository and **exclude the repository whose evaluation prompted the change**. This is the guard
   against collateral damage.

### Why the burden of proof sits where it does

An earlier draft had this the other way around: the rubric proving improvement, the recurrence suite
guarding regression. That cannot work.

The rubric mean is a judge score over six criteria, carrying both generation variance and judging variance.
A plausible prompt effect is perhaps +0.3 on a five-point scale. With three to five targets and unmeasured
variance, a paired test has almost no power — the gate would reject good changes and teach nothing by
rejecting them.

The recurrence suite is binary, per-defect, and needs no judge. It tests exactly what the change was for.

**So the sensitive instrument proves the effect, and the insensitive one guards against damage.** "No
significant decline" is a far weaker claim than "significant improvement" and is achievable at N we can
afford.

### Excluding the prompting repository is the anti-overfitting control

The repository that surfaced a defect is the one a fix is most likely to be fitted to. Measuring the fix
there measures memorisation. This single rule does more than any other to keep prompt guidance general;
§18 is the wider discussion.

### The noise floor is a prerequisite, not a refinement

Rules 2 and 3 both contain "significant", and neither can be computed without knowing how much a score
moves between *identical* runs. That number does not exist yet. It is obtained by generating the artifact
for one target several times with everything held constant and measuring the spread of the scores.

**Until it is measured, this gate cannot be operated as written**, and any significance claimed would be
decoration. Measuring it is the first item in the build order (Appendix D).

## 16. Evaluating the update path

Describing a system once is the easy half. The maintenance claim — that archagent keeps an artifact true as
the code moves — is the one that matters to a user, and it has never been measured.

The design is a paired run: generate the artifact for a target at commit **N**, score it, advance the
target to commit **N+x**, run the update, score again.

### Gate on update-specific measures, not the overall score

The obvious gate — "the score must not decline" — conflates two different things. An artifact can score
lower at N+x because the update failed, or because the system genuinely became larger and harder to
describe in the intervening commits. Only the first is archagent's fault.

Three sharper measures already exist:

- **`check_update_captured`** — of the files that changed between N and N+x, the share sitting in a
  subsystem whose document was also updated. Directly measures whether the update noticed the change.
- **Post-update drift** — running `drift` after the update should report close to nothing. A fresh
  disagreement is an update that did not land.
- **`update_quality`** — the judged criterion that only appears on a second run. Its 3-anchor names the
  failure worth hunting: *"new material was added but old material was not removed, so the document now
  describes two systems at once."* An artifact that only ever grows looks complete and describes a system
  that no longer exists.

Gate on those; report the overall score as context.

### Status

**Built and never run.** `check_update_captured` exists and is tested, but `do_score` only calls it when
passed a set of changed files and nothing passes one — the `score` subcommand has no flag for it.
`update_quality` renders only with `--second-run`. Both are waiting on the two-revision loop (§8), which
still refuses to execute. Wiring the changed-file set from a `git diff` between the two revisions is a
small piece of work and unblocks the rest.

## 17. The evaluation ledger

One table, one row per evaluation run, so that results accumulate into a record rather than a pile of
files. CSV, in the evaluation data repository, alongside the runs it indexes.

### What a row must carry

The scores are the least interesting part. What makes two rows comparable are the inputs:

| Column | Why it is there |
|---|---|
| `run_id` | primary key |
| `date` | |
| `archagent_commit` | the tool version under evaluation |
| `target_url`, `target_commit` | a target is a repository *at a revision* |
| `target_fresh` | whether this target had ever been used before |
| `run_kind` | `calibration` or `scoring` (§12) |
| `generating_agent`, `generating_model` | **likely the largest single source of variance** |
| `judge_model` | a judge is not interchangeable with another judge |
| `rubric_version` | criteria and briefs change; two means from different briefs are not comparable |
| `replicate_id` | which repeat of an identical configuration this is — this is where the noise floor lives |
| `blinding` | what the reviewer could see: the other scores, the defect list, the artifact's author |
| `deterministic_score`, `judged_mean`, `judged_scored`, `judged_answered` | §9; the last two because a mean over a fraction of a review is not a score of the artifact |
| `recurrence_pass`, `recurrence_total` | §13 |
| `checklist_correct`, `checklist_wrong`, `checklist_absent` | §14 |
| `predecessor_run_id` | set on the second run of an update pair (§16) |
| `notes` | free text, including any deviation from the pre-registered procedure |

Two of these are corrections of an earlier design rather than obvious additions. Without
`generating_model`, `judge_model` and `rubric_version`, two rows cannot be compared at all — the first two
calibration rounds already used different briefs, so their means were never comparable and nothing recorded
that. And without `replicate_id` there is nowhere to put the runs that establish the noise floor, which is
the measurement everything in §15 depends on.

### Updates are a relation, not extra columns

An update evaluation is two runs plus a link between them. Modelling it as a second set of columns on one
row leaves most of the table empty and cannot express a chain longer than two. `predecessor_run_id` on an
ordinary row handles both, and keeps every run the same shape.

---

# Part IV — Discipline and limits

What keeps the process honest, what it still cannot tell us, and what is deliberately not built yet.

## 18. Avoiding overfitting to the repository in front of you

Every evaluation round ends with a list of defects and a temptation: fix each one. Some of those fixes
generalise and some encode one repository's shape into the tool, and the two are hard to tell apart while
you are making them. This section is the discipline, written after round 2 because that round produced
ten changes and the question "how many of these are about obstudio?" turned out to have a measurable
answer.

### The test: can you state the rule without naming the repo?

A fix that generalises describes a *class* of mistake. Round 2's changes, classified:

| change | states a rule about | general? |
|---|---|---|
| `_resolve_ref` handles wildcards | a glob is not a missing file | yes |
| `_resolve_ref` checks the filesystem | a file in an unparsed language still exists | yes |
| `**Config:**` reads past line one | a wrapped declaration is one declaration | yes |
| citation regex longest-first | `ts\|tsx` truncates `.tsx` | yes — a plain bug |
| citations outside the repo skipped | a path outside the tree is not a claim about the tree | yes |
| `check` lists unchecked prose rows | "nothing was checked" ≠ "everything passed" | yes |
| `describe`'s five claim rules | how a checkable claim goes wrong | yes |
| per-reviewer `judged.json` | two records that exist to be compared must not share a path | yes |
| origin **reflection** detection | reflection is more permissive than `*` | yes |
| **`permissive-origin` signal** | a trust boundary the documents skip | mechanism yes, evidence thin |

Nine of ten are bug fixes or prompt rules whose statement never mentions obstudio. That is not a
coincidence — it is what a review of a *documentation artifact* mostly produces, because the failures are
in how claims are made rather than in what the system does.

### Where overfitting actually lives: pattern lists

Bug fixes generalise by construction. **Pattern lists do not**, and they are where every heuristic in this
tool will rot. Concretely: `originscan`'s test-directory skip list guesses `test`, `tests`, `__tests__`,
`testdata`, `fixtures`, `examples` — and litellm keeps its example servers in `cookbook/`, which the list
does not contain, so a permissive CORS in an example fired as a finding.

The wrong response is to add `cookbook` to the list. That is the overfitting move: it fixes litellm and
teaches nothing, and the next repository will use `recipes/` or `demos/`. Two better responses:

- **Let the judging step absorb it.** "Candidates, not verdicts" is an anti-overfitting mechanism, not
  only a humility one. A reader dismissing "this is in `cookbook/`, an examples directory" is the system
  working. The scanner does not need to know every repository's conventions if something downstream does.
- **Prefer a structural fact to a name.** Whatever can be tied to a declaration (`**Covers:**`, a build
  target, a package boundary) instead of a directory name survives contact with the next repository.

### Do not report a validation the corpus cannot support

The sharper lesson from round 2. Running `permissive-origin` over all fourteen corpus repositories gives
**one hit in fourteen**, which reads like strong evidence of a low false-positive rate. It is not:

> Files mentioning any CORS or HTTP-server construct — angular 0, ansible 0, datasette 0, django 0,
> flask 0, homeassistant 0, nova 0, pandas 0, poetry 0, prettier 0, scrapy 0, sympy 0, kibana 4,
> litellm 431.

**Twelve of fourteen had no opportunity to fire.** The corpus is libraries, frameworks and CLIs, assembled
to exercise the checks that existed at the time — co-change, hotspots, duplicated decisions — all of which
need only source and history. A signal about *service exposure* cannot be evaluated by a corpus with
almost no services in it, and "0 false positives across 14 repositories" would have been true and
misleading.

So: **before quoting a corpus result for a new check, ask how many of those repositories could have
produced a finding at all.** Report the denominator, not the numerator. The honest statement for this
signal is "validated on one repository, incidentally correct on a second, and the corpus cannot yet
evaluate it".

### The rules

1. **Fix the class, not the instance.** If the rule cannot be stated without naming the repository, it is
   not a rule yet.
2. **Prefer a tool fix to a pattern addition.** A bug fix generalises; a pattern list accumulates one
   repository's vocabulary.
3. **A new signal needs a mechanism argument, not just an instance.** CORS is a web-platform behaviour,
   not an obstudio behaviour — that is why the signal is defensible on thin evidence. A signal justified
   only by "it found something here" is not.
4. **Never tune a threshold on the repository that motivated the check.** `permissive-origin` has no
   numeric threshold, deliberately; the two it would have needed (how many sites, how close to a route)
   would both have been fitted to one example.
5. **Check whether the corpus can evaluate the change, and say so when it cannot.**
6. **The corpus has to grow with the signal set.** It was selected for the checks of the time and is now
   unrepresentative for a whole class of them.

---

## 19. Threats to validity

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
- **Goodhart.** Once the rubric exists, prompts will be tuned to it — by hand well before any optimiser
  exists. Keep some criteria out of the prompts, re-read the rubric when scores rise without the output
  visibly improving, and read every deterministic criterion adversarially before it gates anything
  (§20.3 shows two from §9 that are trivially gameable).
- **Held-out decay through selection.** Choosing among candidate changes on the held-out set spends it,
  even though nothing was "tuned" on it. §20.1 answers this with a three-way split and a consultation
  budget; until then, the held-out set is looked at rarely and each look is recorded.

---

## 20. Closing the loop — feeding results back into prompts and tools

**Status: deferred.** Nothing here gets built until the evaluation itself is proven — the preconditions
below are not a formality, they are what separates a feedback loop from an amplifier of our own mistakes.
Recorded now so the earlier sections are built in a shape that admits it later.

The inspiration is *Self-Harnesses: Harnesses That Improve Themselves* (arXiv 2606.09498): mine failure
patterns from execution traces, propose minimal edits tied to those failures, and accept an edit only if
regression tests still pass. The regression gate is the piece we already have — golden fixtures plus the
pinned corpus (§6), which between them catch the failure that matters most, a check quietly *losing* a
finding rather than producing a wrong one.

**The difference that drives the design.** Self-Harness accepts edits against task pass rates, a metric
that does not care what any model thinks. Our nearest equivalent for the skill layer is a rubric scored by
a model. An optimiser pointed at a model-judged score will find judge quirks at least as readily as
quality, so the acceptance gate cannot be the rubric as a whole.

### 20.1 Preconditions

1. **Noise floor measured** (§8) — no delta can be called an improvement until repeat runs on identical
   inputs establish the spread.
2. **Calibration established** (§11) — an agreement rate between judge and person.
3. **A three-way repository split** — train to propose against, dev to select among proposals, test
   consulted rarely against a stated budget. Two sets are not enough: proposal *selection* consumes a
   held-out set as surely as tuning does.
4. **Regression nets blocking**, not advisory (§6).
5. **Traces persisted** (§8) — a scorecard is a number; weakness mining needs a record of what happened.

### 20.2 Shape, if built

- **Eligible surfaces: prompts and configuration.** Thresholds stay on the slow loop, because their
  objective metric is the defect study and its outcome window is months; letting a fast loop tune them
  re-creates exactly the fit-then-measure failure §7.1 exists to prevent. Changes to check *code* are
  proposed, never applied automatically.
- **Two loops at different speeds.** Fast: prompt edits, gated on the deterministic half of §9 plus the
  ground-truthed dismissals from the label store. Slow: threshold changes, gated on §7. The fast loop's
  results are re-checked by the slow one periodically.
- **Acceptance is gated on objective criteria only.** Judged rubric scores may *inform proposals* — they
  are good at pointing at what is weak — but they never decide acceptance.
- **Calibration is re-sampled every round.** Agreement between judge and person is conditional on the
  output distribution it was measured over. An optimiser moves that distribution, so a rate carried
  forward from before the change may no longer describe anything. Without this the loop can settle in a
  region where the judge is confidently wrong and nothing says so.
- **Containment.** The evaluation assets — fixtures, goldens, corpus expectations, the label store — are
  **read-only to the optimiser**. An agent able to edit both the prompt and the test will improve the
  score. Accepted edits land as a branch with provenance (which run, which failure it answers, before and
  after on each gate), never straight onto the main line — the same stance archagent takes toward its own
  findings.
- **Stopping rule.** No acceptance when the delta sits inside the noise floor.

### 20.3 The deterministic criteria need an adversarial reading first

Being machine-checkable does not make a criterion safe to optimise against. Two from §9 that are already
gameable:

- **Coverage** — the share of files claimed by some subsystem's `**Covers:**` — is maximised by writing
  `**Covers:** src/**` in one document. Perfect score, no architecture described.
- **Drift near zero after describe** is maximised by writing documents vague enough that nothing can
  contradict them.

Both are fine as *diagnostics* and dangerous as *targets*. Before any criterion becomes an acceptance
gate, it gets read adversarially — what is the laziest change that maximises this? — and either paired
with a counter-criterion or left out of the gate.

---

## 21. Out of scope

- **Any runtime dependency on an issue tracker.** Defect data belongs to the harness, not the tool.
- **Modifying the local test-repository checkouts.** They are the measurement baseline; evaluations work in
  temporary clones and leave them untouched.
- **Human-subject studies.** Everything here is judged by code, by public history, or by a model.
- **Benchmarking against other tools.** Interesting later; it needs a shared task definition we don't have.
- **Optimising for a paper.** The evidence should be publishable if we want it to be, but no evaluation is
  chosen because it would look good in one.

---

---

# Appendices

Operational detail: current status, what we build versus adopt, where the outputs live, and what order to
build in. None of it is needed to understand the method.

## Appendix A — Where this stands

*Current as of 2026-08-15. This is the only part of the document that goes stale by design.*

### What has evidence

**L1, the deterministic signals — partial.** The held-out defect study (§7) ran four times, each
pre-registered, and three of four adequately-powered repositories show that files flagged as
change-prone-and-complex go on to accumulate significantly more defect-fixing commits than churn-matched
controls, across two languages and three architectures. Record with every deviation:
`docs/evaluations/defect-study/RESULTS.md`. Two limits on quoting it: magnitudes are **not comparable
across repositories**, because the rate ratio partly tracks how concentrated defect fixes are; and every
attempt on a *small* repository was underpowered, so nothing here speaks to those.

**Group F has precision data**, from 19 independently labelled findings — 89% for
`scattered-source-of-truth`, 60% strict / 90% lenient for `enum-value-escape`, intervals roughly ±25
points. One reviewer, and 17 of the 19 findings from one repository.

**Everything else has none.** Of roughly 19 signals, three have evidence. Groups A, B, C and D — about 16
signals — have **zero labelled findings**, and this is structural rather than an oversight: those signals
read `**Service:**`, `**Tier:**` and `**Connects:**` from subsystem documents, and no corpus repository has
an artifact at all. They cannot fire on the corpus however many repositories are added to it. Splitting
that problem is an open item: synthetic injection into the fixture repos would give recall cheaply,
precision still needs real repositories carrying real artifacts.

**L2, the artifact quality — one agreement number.** Calibration round 2 (obstudio) produced the first:
exact agreement 2/6, within one point 6/6, human mean 4.00 against a model judge's 3.67. On n=6 over one
artifact the within-one figure is the only one worth reading. Both scorings were evidenced — no fabricated
citations, unlike round 1 — but the judge found six defects the human did not, including the strongest of
the round. Full write-up: `docs/evaluations/selfeval/obstudio/CALIBRATION.md`.

### What is built and not yet running

| Piece | State |
|---|---|
| deterministic rubric (§9.1) | works today; no agent, no model |
| judged rubric (§9.2) | works; one agreement number, still uncalibrated for practical purposes |
| spot-check worksheet + label store (§11) | works; holds 19 labels |
| blind comparison (§10) | objective half works; generating the arms needs other sessions |
| recurrence suite (§13) | **designed, not built** — nine confirmed obstudio defects are the seed |
| per-repository checklists (§14) | **designed, not built** |
| the ledger (§17) | **designed, not built** |
| update evaluation (§16) | machinery built, never run; blocked on the two-revision loop |
| noise floor (§15) | **not measured** — this blocks the acceptance gate as written |

### The binding constraint

It has moved. It used to be the empty label store; that is no longer true. **It is now the noise floor.**
Three of the acceptance rules in §15 contain the word "significant", and none of them can be evaluated
until we know how far a score moves between identical runs. Nothing downstream — accepting a subjective
change, gating an update, comparing two releases — can be operated as written until that number exists.

### A pattern worth recording, because it recurred seven times

Every serious defect found while building this was a **silent failure** — a condition that rendered as a
plausible clean result rather than an error: a timed-out history walk read as a repository with no commits;
an outcome walk read as a year with no defects; a corrupt clone read as an empty history; a bounded history
run against an unbounded tree; a cached profile learned from after the cutoff; a review parser that
discarded five of six scores and reported the sixth as the artifact's score; and `check` printing "All
invariants hold" having checked none of eight. None produced a stack trace. Each was caught by a
consistency check — one number beside another that could not both be true — rather than by code failing.
Budget for the guards accordingly; they have caught more than the tests have.

### Two things deliberately not automated

`selfeval run` refuses rather than invoking an agent, because comparing two scorecards is meaningless until
a repeat run establishes how much of a difference is agent variance. `blindcomp` refuses to generate its
own arms, because one session writing its own guidance's output and then grading it measures
self-preference. In both cases a working-looking implementation was available and would have produced
numbers worth less than nothing.

## Appendix B — Tooling: what we build and what we adopt

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

## Appendix C — Where the data and the write-ups live

Evaluation **data** moved to a separate private repository,
[BenedatLLC/archagent-evaluations](https://github.com/BenedatLLC/archagent-evaluations); the **write-ups**
stayed in `docs/evaluations/`. The split is by kind, not by size: a number without its reasoning is
unreadable, and a write-up separated from its evidence is untrustworthy, so each document states its
conclusions here and cites the data repo by path.

The reason is trajectory rather than present size. At the move the data was 1.0 MB across 55 files, which
is nothing; but every defect-study run adds a per-repo flagged-file dump (kibana's is 143 KB) and every
calibration round adds a whole generated artifact (obstudio's is 20 documents). A tool repository that
accumulates its own measurement history without bound becomes hard to clone and harder to read.

Two properties make this safe rather than merely tidy:

- **The test suite does not read it.** All 451 tests pass with the data repository absent. Only the
  regression fixtures under `tests/corpus/` and `tests/golden/` (44 KB, 5 files) are load-bearing, and
  those are inputs to tests rather than outputs of runs.
- **Scripts resolve their output root** through `scripts/evalhome.py`: `$ARCHAGENT_EVAL_HOME`, else a
  sibling `../archagent-evaluations/` checkout, else a gitignored `./evaluations/`. A fresh clone with no
  data repository still runs, and its output cannot land in git by accident.

It is private because it analyses third-party repositories and frames findings as defects — including a
security-relevant claim about litellm. Publishing that is a decision to take deliberately, not a
side effect of where a file sits.

---

## Appendix D — Build order

| # | item | state |
|---|---|---|
| 1 | `--until` / as-of plumbing (§5) | **done** |
| 2 | Pinned-corpus regression (§6) | **done** — 3 of 5 repositories recorded |
| 3 | Held-out defect study (§7) | **done, 4 runs** — 3 of 4 powered repositories pass |
| 4 | Self-evaluation + rubric (§8, §9) | **deterministic half done**; judged half gated on 5; `run` blocked on the agent seam |
| 5 | Human spot-check and calibration (§11) | **machinery done, no labels collected** |
| 6 | Blind comparison (§10) | **objective half done**; generation left to separate sessions; judged half needs 5 |
| 7 | L3 task benchmark | not designed |

1. **`--until` / as-of plumbing** (§5) — shipped. Three paths into the repository needed bounding, not the
   two this document originally described; the third (the commit-wording profile) was leakage.
2. **Pinned-corpus regression** (§6) — shipped as opt-in pytest. It found a silent failure in the miner on
   its first real run, which had already been recorded as a baseline before anyone looked.
3. **Held-out defect study** (§7) — shipped, four runs, each pre-registered before running. The one item
   here that could retire a signal did not: see below.
4. **Self-evaluation tool + rubric v1** (§8, §9) — the deterministic half is shipped and useful on its
   own. The judged half is gated on item 5, and `selfeval.py run` refuses rather than half-implementing
   the agent seam. The DeepEval trial of §12 belongs here and has not been run.
5. **Human spot-check and calibration** (§11) — machinery shipped, **zero labels**. This is the binding
   constraint on the whole L2 half, and it cannot be resolved by the person who built the checks.
6. **Blind comparison** (§10) — the objective half is shipped: identical hashed inputs, blinding and
   shuffling, and scoring against the ground-truth verdicts from the corpus pass. Generation is *not*
   automated, because one model writing all three arms and then grading them measures self-preference.
   The judged half still needs item 5.
7. **L3 task benchmark** — not designed here. Revisit once L1 and L2 have numbers.

---

