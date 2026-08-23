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
  alone; without it, "significantly better" cannot be computed. The judging half has been measured (§15);
  the generation half has not.
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

### An entry may carry a minimal artifact

Groups A, B and B/C read `**Service:**`, `**Tier:**` and `**Connects:**` from subsystem documents. Every
corpus repository was evaluated from `archagent.toml` alone, so those families could not fire on any of
them — not rarely, *structurally*. Adding a service-shaped repository did not change it: five compose
services and seventeen state-changing routes still produced `A`, `B`, `B/C` and `B — subsystem co-change`
all inactive.

An entry may therefore ship a hand-written, metadata-only artifact under
`tests/corpus/artifacts/<name>/`, copied into the worktree before `evaluate` runs. On the same repository
that changed the inactive list from five families to one, and produced the first group B finding the
corpus has ever contained.

**The bias is real and is stated in each artifact's own README.** Declaring the architecture declares what
the layering signals compare against, so these findings are not evidence that archagent describes the
system correctly. That is tolerable here for one reason only: this corpus asks *"did the output change?"*
and never *"is the output right?"* An artifact written by us is a legitimate input to the first question
and would be worthless for the second.

### What "read and re-recorded deliberately" means

A baseline is ~1000 lines of JSON, so a raw diff is unreadable and would be rubber-stamped. Three
properties make the re-record a decision rather than a reflex.

**The failure prints a projection, not the JSON.** `summarise_diff` reduces the change to the four things a
reviewer must judge:

```
LOST     <sign>  <subject>      appeared before, does not now
NEW      <sign>  <subject>      appears now, did not before
CHANGED  <sign>  <subject>      severity / confidence / values / subjects moved
INACTIVE / TRUNCATED / HISTORY  the coverage report itself changed
```

`LOST` is why the projection exists. A check quietly *losing* findings renders as a clean run — the
silent-failure shape that recurs throughout this project (Appendix A) — and in a thousand-line diff it is
invisible.

**Accepting requires a separate, explicit act.** The failure message names the only way through:

```
ARCHAGENT_UPDATE_CORPUS=1 uv run pytest -m corpus -k <repo>
```

There is no auto-update on failure and no `--update-snapshots` convenience. You read the projection, decide
the diff is what you meant, and then say so with an environment variable. A snapshot test whose baselines
are refreshed whenever they are inconvenient measures nothing; the gate is only a gate because updating it
is deliberate.

**The acceptance lands in git.** Re-recording rewrites a committed file, so the decision is reviewable by
someone else rather than a private judgement that disappears once the test goes green.

The worked example: adding `permissive-origin` produced one `NEW` and zero `LOST` on litellm; the site was
checked (`from flask_cors import CORS` then `CORS(app)` — genuinely permissive), the finding judged
correct, the baseline re-recorded, and datasette and django confirmed unchanged. Had it read
`LOST change-prone-file …`, the correct response would have been the opposite: do not re-record, treat it
as a regression, find out what stopped firing.

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

**How much these scores move on their own.** Measured: judging the same artifact six times, holding
everything constant, the mean across criteria varies by a standard deviation of 0.10, while an individual
criterion can move two points — `diagrams` was scored 2 by one run and 4 by another on identical input.
**So quote the mean, with ±0.1, and treat a single criterion's score as a finding to read rather than a
number to compare.** §15 has the method and the full table.

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

Misreading is what is left over, and §14 is what covers it.

### As built (2026-08-16)

`tests/recurrence.py` and `scripts/recurrence.py`, with entries in `<eval-home>/recurrence/<target>.toml`.
Nineteen entries are on record — obstudio's nine and wardrowbe's ten — covering every defect confirmed in
rounds 2 and 3. `fastapi-template` contributes none: it was a scoring run, so it has a scorecard and no
review.

```
python scripts/recurrence.py <artifact-dir> --target wardrowbe   # exit 1 if any entry fails
python scripts/recurrence.py --list
```

Three things came out of building it that the design above did not anticipate.

**The second mechanism — checking which lines of code the artifact cites — was not built.** The table above
measures it at two real catches and two false passes. Both real catches are already covered by simply
requiring the artifact to contain the words `Allow-Origin`, `CheckOrigin` or `CORS` somewhere, which does
not depend on guessing how near a citation has to be to count, and does not care which line the artifact
happened to cite. A mechanism that passes half the cases it is given is not worth carrying when a simpler
one already catches everything it caught.

**Entries need to be tested themselves, because a badly written entry quietly passes everything.** Each
entry was written from a defect confirmed in a specific artifact, and that artifact is deliberately kept
unrepaired as evidence — so every entry must *fail* when run against it. A test asserts exactly that, and
it caught two broken entries the first time it ran:

- one searched for two phrases within forty characters of each other, and the sentence it was written from
  puts fifty-two characters between them;
- one asked that the artifact mention any of `ownership`, `tenant`, `user_id` or `scoped by`, and was
  satisfied by the string `user_id` appearing inside a URL in a table of routes.

Both reported a clean result on input already known to be wrong, which is the failure mode this whole
document is organised around. A keyword appearing somewhere is not evidence that a topic was addressed;
the replacement requires the keyword *and* a word about enforcement in the same paragraph.

**One entry is not about the target at all.** `kind = "guard"` marks an assertion about whether the
artifact's own text is intact, rather than a fact about the code. There is one so far: a paragraph that
was emptied out during an edit — the filenames in it were written through a shell that executed them
instead of quoting them — leaving a grammatical sentence with no content. A guard is exempt from the
positive-pair rule, because for a guard, an artifact that never writes the damaged paragraph is correct
and silence is the right outcome. The `kind` field exists so that exception has to be declared rather
than assumed.

## 14. Per-repository checklists

A checklist is a fixed list of specific claims an artifact should get right about one target, **with the
correct answer written down**, scored `correct` / `wrong` / `absent` by a judge.

The distinction from the open rubric (§9) is the ground truth. Do not ask a judge *"is the concurrency
description correct?"* — that is a research task, and it re-runs the very error the checklist exists to
prevent. Ask:

> `Store` uses a `sync.RWMutex` plus three further mutexes — `subMu`, `invalidateMu`, `changeMu`
> (`store/store.go:313-332`). Does the artifact convey this?
> **correct / wrong / absent**

That turns a research task into a comparison. It is cheaper, because the judge never explores the
codebase; it repeats better, because the questions and their order are fixed; and it asks for one of three
answers rather than a number from one to five, which is a far easier judgement to make consistently.

The reading was done once, by a human, during a calibration run. **The checklist is where that work is
banked so it never has to be repeated.**

### The `accuracy` criterion selects against finding errors

Round 3 produced the sharpest result the rubric has given, and it is about the rubric.

The criterion says *"pick the five most load-carrying claims and check each against the code."* A human
reviewer did exactly that, found five for five correct, and scored `accuracy` 5. A blind judge walked the
artifact against the tree instead and found five contradicted claims — a schema inferred from a directory
listing, a table count taken from a file count, a startup behaviour recalled rather than read. All five
verified.

**Load-bearing claims are the ones the author checked while writing.** Asking a reviewer to sample them
selects for the claims most likely to be right. The errors were all in claims made in passing, and no
amount of care in sampling would have surfaced them.

So the criterion should ask for **coverage, not importance** — walk the documents against the tree — and
a checklist (below) is how that becomes repeatable rather than a matter of how thorough a given reviewer
felt.

### Coverage was at ceiling exactly where the problem was

Round 3's human reviewer scored `completeness` 3 because three subsystem documents were too thin to trace
a change through, and noted that five had no diagram where three needed one. `archagent status` reported
**100% coverage** on the same artifact.

That is not a scoring disagreement, it is two different questions. Coverage answers *is this file
described by something*; it says nothing about whether the description is usable, and an artifact can sit
at ceiling on the first while failing the second completely.

The fix is not a stronger prompt. A prompt rule for exactly this already existed and was written by the
same person who then violated it — twice, on `Status: active` and on glob-shaped prose. What was missing
was a measurement, so `status` now reports **prose words per file claimed**, diagram count, and the number
of type or table declarations each document covers, and flags two shapes:

- **thin** — under half the median density of the artifact's *own* documents. Relative on purpose: an
  absolute bar would punish a terse house style everywhere, while one document far below its siblings is a
  claim about this artifact.
- **no diagram** — five or more type or table declarations with nothing drawn. Not "every document needs a
  diagram": a CLI with no states was right that a lifecycle diagram would be decoration.

On the reviewed artifact it flags the two documents the reviewer named and one more they did not — a
108-file subsystem at 2.7 prose words per file. On archagent's own artifact it flags nothing as thin and
asks one question about a diagram, which is answered in that document rather than silenced with a picture.

### There is no sample review, deliberately

Two of the first three reviews were unreadable — fields read to end-of-line in one, a score in the heading
in the other — and the obvious fix is to ship a filled-in example. It is the wrong fix.

Format and content are separable, and only format needs an example. A completed sample carries three
biases, and the second is the one that matters:

- **Score anchoring** — a visible `3` drags a reviewer toward 3.
- **Finding anchoring** — showing a *kind* of criticism makes reviewers hunt that kind. Round 3 showed
  that method decides findings: sampling five load-bearing claims found nothing, walking the tree found
  five. A sample would quietly standardise whichever method it demonstrated.
- **Effort anchoring** — a short sample produces short reviews, a long one produces performative length.

Instead the parser accepts any reasonable markdown, and `selfeval check-brief` tells a reviewer whether
their file reads *before* they hand it back — which criteria parsed, which citations resolve — while
showing them no content at all. Format certainty with zero anchoring.

### Three cautions

**A checklist is an answer key.** Whoever authors a prompt change must not be reading it while doing so, or
the change is fitted to the test rather than to the problem. The same blinding rule as §15's exclusion of
the prompting repository.

**It is still a model reading prose.** More repeatable than open-ended scoring, not immune to error. Expect
what error remains to sit on the line between `wrong` and `absent` — an artifact that gestures at the right
topic without ever committing to a claim.

**The open rubric must survive alongside it.** A checklist can only re-test what is already known. If it
replaces the open-ended rubric, the next calibration round finds nothing new and the checklist stops
growing. The open rubric is what discovers; the checklist is what re-tests. Every new defect the open
rubric turns up becomes a checklist item for the round after.

### As built (2026-08-16)

`tests/checklist.py` and `scripts/checklist.py`, with the answers stored in
`<eval-home>/checklists/<target>.toml`. Started at fourteen items each for obstudio and wardrowbe; now
seventeen and sixteen, after the change described below.

```
python scripts/checklist.py render --target obstudio --artifact architecture --out worksheet.md
python scripts/checklist.py score worksheet.md --target obstudio
```

Four decisions the design above left open.

**Items are weighted by how much they matter, and both the weighted and unweighted scores are reported.**
Without weighting, a false claim about who can read a user's data counts the same as a wrong file count.
A `serious` item counts 3, `moderate` 2, `minor` 1. Both numbers are printed, because a gap between them
is itself worth seeing: an artifact that reaches a given score by getting the small things right is not the
same artifact as one that reaches it by getting the important things right.

**A `wrong` verdict requires the judge to quote the passage it is calling wrong.** This is how the
`wrong`-versus-`absent` problem named above is held in check. Without the rule, `wrong` becomes the verdict
for anything vague, and an artifact that merely fails to say something scores like one that says something
false. A `wrong` with no quote is thrown out — counted as neither right nor wrong, and reported as thrown
out rather than silently ignored.

**A checklist may not consist only of past defects, and a test enforces that.** The caution above warns
that the checklist stops growing if it replaces the open-ended rubric. The same thing happens one level
down if a checklist contains nothing but known mistakes: its score can then only go down, and it measures
what the recurrence suite (§13) already measures. So at least a quarter of each list has to come from
reading the code rather than from a past finding. Those items include the single most important fact about
each system — for obstudio, that stored telemetry is discarded when the process that produced it exits;
for wardrowbe, that image tagging runs through a background job queue. Neither has ever been the subject
of a defect.

**Items about counts are phrased conditionally** — *"if the artifact states a Go file count, is it 57?"*
An artifact that states no number is marked `absent`, not wrong. Asking for the count unconditionally would
reward an artifact for inventing one, and inventing a number is exactly how two of the defects on record
came about.

The scorer also refuses to report a clean-looking result it has not earned: a worksheet nobody answered
reports no score at all rather than a perfect one, and an item a judge skipped is listed as skipped rather
than quietly dropped.

### Results so far (2026-08-16)

Two rounds of judging have been run, on the same two artifacts, with four judges each time: two different
models (Opus and Sonnet) on each of the obstudio and wardrowbe artifacts. Every judge worked from the
artifact and the worksheet alone — not the source repository, not the other judges' answers, not any
earlier review. Full write-ups in `docs/evaluations/checklists/RESULTS.md` and `RESULTS-run2.md`.

| | round 1 | round 2 |
|---|---|---|
| items per target | 14 / 14 | 17 / 16 |
| **two judges gave the same verdict** | 26 of 28 (93%) | **31 of 33 (94%)** |
| a judge repeating an earlier verdict on an unchanged item | — | 35 of 36 (97%) |
| items describing a known defect that were scored `correct` | 0 of 20 | 0 of 22 |

**Two judges given the same worksheet reach the same verdict about 94% of the time.** That is the number
this whole section was built to produce. Compare it to the 1–5 rubric measured on one of these same
artifacts, where a single criterion was scored 2 by one run and 4 by another with nothing about the
artifact changed (§15). The practical consequence is that a checklist result can support a claim about one
specific item, where a rubric score cannot support a claim about one specific criterion.

**No item describing a known defect was ever scored `correct`.** Both artifacts are deliberately left
unrepaired, so every such item should come back `wrong` or `absent` — and every one did, from all four
judges, in both rounds. This is the check that the worksheet is legible and the verdicts mean what they
say: a judge that could not find the relevant passage would have produced `correct` out of charity, and a
judge not reading carefully would have produced `absent` out of laziness. Neither happened once.

**Round 1 found a defect in the items rather than in the judges, and fixing it is where the fifth rule
came from.** One of that round's two disagreements was the `wrong`/`absent` case predicted above. The other
was `correct` versus `absent`, on an item that asserted two facts — the retry limit is three, *and* the
queue library only reschedules a job that raises a particular exception — where the artifact stated the
first and not the second. One judge scored the half that was present, the other the half that was missing.
Both flagged the call as hard, independently, without seeing each other's work.

That is not a judge failing. An item asserting two facts has no correct answer on a three-way scale when
the artifact carries one of them, and the two defensible answers are a full verdict apart. Hence:

**An item asserts one fact** — not a fact plus its rationale, not two facts about one mechanism. This joins
the rules for writing items, which live with the checklists themselves in the evaluation data repository.

**Round 2 applied that rule and the `correct`-versus-`absent` disagreements disappeared.** Five items that
had bundled two facts together were split into ten. Both of the disagreements that remain are the
`wrong`-versus-`absent` case this section predicted, and both have the same shape: the artifact describes
the right topic using different words, one judge reading that as a contradiction and the other as silence.
Neither judge is wrong about that, and it appears to be as good as this instrument gets.

**Splitting the items moved verdicts in both directions, which is why the improvement is believable.** An
instrument that only ever scored higher after its own repair would be measuring the repair. Instead:

- obstudio's item about telemetry being discarded when the process that produced it goes away moved from
  *both judges say absent* to *both judges say correct*. The artifact does describe the discarding; what it
  does not describe is that the two network transports notice a departed producer by different means.
  Bundled into one item, the missing half was cancelling out the half that was there.
- wardrowbe's item about retry limits moved the other way. Split into the limit itself and the mechanism
  that enforces it, both halves came back `absent` from both judges — the artifact names the constant that
  holds the limit without giving its value, and says nothing about the mechanism. The earlier `correct` had
  been generosity toward a bundled item, and splitting it withdrew that.

**The scores themselves are not yet a measure of these two artifacts' quality, and should not be quoted as
one.** Eleven of the items per target were written *from these artifacts' own confirmed defects*, so a low
score is arithmetic rather than a finding. The numbers become meaningful the next time these targets are
described, when the same items face an artifact they were not derived from — which is the entire reason for
writing them down. The part that carries information today is the handful of items per target that came
from reading the code rather than from a past defect: obstudio 4 of 6, wardrowbe 2 of 5, both unanimous
across judges.

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
2. **The pinned-corpus regression (§6) is run, and any diff is read and re-recorded deliberately.**
   `pytest -m corpus` — it is deselected by default because it clones over the network, so it does *not*
   run in an ordinary `pytest` invocation. For a change to a pattern, a threshold, or any matching
   heuristic this is the control that shows the change did not quietly alter behaviour on repositories
   nobody was thinking about (§18). A green default run is not evidence of this.
3. **The recurrence suite shows the specific defect no longer recurs.** This is the evidence *for* the
   change.
4. **Scoring runs on N targets show no significant decline**, where the targets include at least one fresh
   repository and **exclude the repository whose evaluation prompted the change**. This is the guard
   against collateral damage.
5. **The evidence class is recorded** — `bug-with-test`, `independent-instances`, `mechanism` or
   `single-instance` (§18). A `single-instance` change ships with that limitation stated in the signal's
   own output rather than silently.

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

The rules above turn on the word "significant", and nothing can be called significant without knowing how
much a score moves between runs where *nothing changed*. Half of that number has now been measured.

**Method.** The wardrowbe artifact was judged six separate times against the 1–5 rubric of §9.2. The
artifact, the code, the review brief and the prompt were identical every time, down to the byte; the only
thing that varied was which model did the judging — four runs on Opus, two on Sonnet. Each ran
independently and wrote to its own file without seeing the others. Full write-up: `docs/evaluations/noise-floor/RESULTS.md`.

| criterion | opus ×4 | sonnet ×2 |
|---|---|---|
| accuracy | 3, 3, 3, 3 | 3, 3 |
| completeness | 3, 3, 4, 3 | 4, 4 |
| prose | 4, 4, 4, 4 | 4, 3 |
| diagrams | 3, 3, 3, 3 | **2, 4** |
| invariant strength | 3, 4, 3, 3 | 4, 3 |
| invariant criticality | 3, 3, 3, 3 | 3, 3 |
| **mean of the six** | 3.17, 3.33, 3.33, 3.17 | 3.33, 3.33 |

**The average across criteria is stable; the individual criteria are not.** Six runs produced means from
3.17 to 3.33 — a standard deviation of **0.10**. But `diagrams` was scored 2 by one run and 4 by another,
on identical input: the full usable width of the scale. `completeness` and `invariant strength` each moved
a point. Only two of the six criteria were unanimous across all six runs.

Three consequences, and they are the reason this measurement had to come before the gate:

1. **An overall score can gate a decision; a single criterion cannot.** A rule of the form "criterion X
   must not decline" would be responding to chance rather than to the artifact. The gate above therefore
   reads on the mean across criteria, and any mean quoted from this rubric carries ±0.1.
2. **One earlier calibration statistic was measuring the noise, not the artifact.** Round 3 reported
   *exact agreement between the human reviewer and the model judge: 1 of 6 criteria*. Against a floor where
   criteria move one to two points between identical runs, that number was always going to be small.
   Agreement within one point — 5 of 6 — was the meaningful figure the whole time.
3. **The human-versus-judge gap survives.** Human mean 4.17, judges 3.28: a gap of 0.89, which is nine
   times the floor. Whatever explains it, run-to-run variation does not.

A secondary finding, and the reason the judging panels elsewhere in this document use two models rather
than running one model twice: Sonnet varied more from run to run, *and* was the only one of the six runs to
catch a real error — the artifact claims schemas exist for seven of eight data models where only five do.
Those are two views of the same property. A model that answers less predictably also reaches conclusions
the steadier model does not, and here two models between them found more than four runs of one.

**What is still unmeasured.** This is judging variance — how much the *scoring* of a fixed artifact moves.
Generation variance — whether describing the same repository twice produces artifacts of genuinely
different quality — is the other half, and it costs a full describe pass per repeat. Until that is
measured, the floor stated here is a lower bound on the total.

The equivalent measurement for the checklist instrument of §14 is much tighter: two judges agree on 94% of
items, and a judge repeating itself agrees with its earlier answer on 97%.

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
| `archagent_commit` | the archagent that **generated** the artifact |
| `reviewing_tool` | the archagent the **review** ran against, when it differs — round 4 used two builds six weeks apart and recorded one |
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

Three of these are corrections of an earlier design rather than obvious additions. Without
`generating_model`, `judge_model` and `rubric_version`, two rows cannot be compared at all — the first two
calibration rounds already used different briefs, so their means were never comparable and nothing recorded
that. And without `replicate_id` there is nowhere to put the runs that establish the noise floor, which is
the measurement everything in §15 depends on.

The third is `reviewing_tool`, added after round 4. The ledger pinned the *target* revision religiously —
`validate()` refuses a row without a `target_commit` — and did not pin the tool. That round's artifact was
generated by the working tree and reviewed against a build six weeks older, missing four of the commands
`describe` tells agents to run; the reviewer correctly reported a command as unavailable and reasonably
concluded the artifact had drifted. **The problem was never that the two builds differed. It was that
nothing said so.** The review brief now names the build to use, `describe` records it in `log.md`, and a
row where the two differ prints the skew rather than hiding it. It is deliberately *not* a comparability
key: two rows reviewed against different builds are still comparable, because the scores are the
artifact's.

### Updates are a relation, not extra columns

An update evaluation is two runs plus a link between them. Modelling it as a second set of columns on one
row leaves most of the table empty and cannot express a chain longer than two. `predecessor_run_id` on an
ordinary row handles both, and keeps every run the same shape.

### As built (2026-08-16)

`tests/ledger.py` and `scripts/ledger.py`, writing `<eval-home>/ledger.csv`. Nineteen rows, backfilled from
every run on record: three calibration rounds (six rows, since two of them were scored twice), one scoring
run, the six noise-floor judgings, and the eight checklist judgings.

```
python scripts/ledger.py list [--target wardrowbe] [--kind checklist]
python scripts/ledger.py trend judged_mean --kind noise-floor --judge opus
python scripts/ledger.py add --run-id ... --target-commit ...
```

**The command that earns the file is `trend`, and what it mostly does is refuse.** Asked for a series of
judged means across the calibration rounds it prints the rows and then:

> NOT A TREND. These rows differ on `rubric_version`, so they are not measuring the same thing, and a
> series across them would be a property of the table rather than of the artifacts.
> `rubric_version: brief-v1, brief-v2, brief-v3`

Those three means are 3.0, then 4.00, then 4.17 — a clean rising line, and the most tempting number in the
whole record. They were produced under three different review briefs, and until now nothing anywhere
recorded that. A ledger that would happily average them is worse than no ledger, because the number it
produces looks like a result.

**Two failure modes are kept separate, and collapsing them would make the tool useless.**

- *The rows differ* on a comparability key — fatal. Refuse, name the key, name the values, and tell the
  caller to narrow the selection. `--judge` and `--rubric` filters exist so the refusal is an instruction
  rather than a dead end.
- *A key was never recorded* — a caveat. Print the series with the gap named: "a difference between them
  cannot be ruled out; this is shown because it is the only history there is, not because it is sound."

That distinction is not theoretical. **Not one of the nineteen backfilled rows records which model
generated the artifact**, because no run ever captured it — and this is the column §17 called the largest
single source of variance. Under a strict rule the entire history would be excluded and the ledger would
be empty on the day it was built. Under a lenient one it would read as sound. It is shown, and it says
what is missing.

**What the backfill exposed by trying to fill the columns in.** Three rounds of expensive work produced
records that cannot answer basic questions: which model wrote each artifact, and in two cases which model
judged it. Those facts existed at the time and were not written down, and they are not recoverable now.
That is the argument for the ledger stated better than the design section above states it — the cost of
not having one is not extra effort later, it is information that is simply gone.

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

### Make it mechanical: "must not misfire elsewhere", not "must fire elsewhere"

The rules above are judgement. Two of them can be enforced by code, and one tempting rule should not be.

**The tempting one: require a change to fire on a second repository.** It sounds like the obvious control
and it is the wrong shape. A well-targeted signal *should* be quiet — `permissive-origin` fires on one of
fourteen corpus repositories and that is correct behaviour, not weak evidence. A "must fire elsewhere" gate
pressures every pattern toward breadth, which trades precision for a coverage statistic. It also confuses
firing with being right: a pattern that fires on five repositories with five false positives is worse than
one that fires once, correctly.

**The dual is the real control, and it already exists.** §6's pinned-corpus regression asserts that the
complete findings set for each pinned repository is unchanged. Any pattern or threshold change that starts
firing — or stops firing — anywhere other than the repository that motivated it breaks a baseline and
produces a diff that has to be read and re-recorded deliberately. That is exactly "this change did not
quietly alter behaviour on repositories I was not thinking about", and it needs no new machinery.

It works. Adding `permissive-origin` produced:

```
litellm @ v1.95.0-dev.2 changed:
  NEW      permissive-origin   cookbook/codellama-server/main.py
```

**And it was bypassed.** The corpus tests are marked `corpus` and deselected by default because they clone
over the network, so the ordinary `pytest` run stays green while the gate never executes. The signal was
built, tested, documented and committed without it ever running. Nothing was wrong with the control; it
simply was not in the procedure. §15 now lists it explicitly, and the same applies to anyone reading this:
**a green default test run is not evidence that a matching change is contained.**

The finding above is genuine (that example server does open its origin), so the baseline was re-recorded.
The point is that re-recording is a deliberate act with a visible diff, which is what makes it a control.

### Two further mechanical controls

**Leave-one-out for numeric thresholds.** Thresholds are where overfitting bites hardest, and here a
mechanical check genuinely works. **Implemented**: `tests/thresholds.py` + `scripts/thresholds.py`.

It does not re-fit, because there is no fitting objective and inventing one would be worse than the
judgement it replaced. It answers the narrower, answerable question: *would we have chosen this value if
one repository had not been in the room?* A filter threshold produces a step function, so any value inside
a step is equivalent — a **plateau**. Compute the plateau with every repository included, then again with
each one dropped. A large widening means that repository was the only thing holding the value where it is.

Three verdicts, and the last two matter as much as the first:

- **pinned by R** — dropping R would have let you choose very differently.
- **unconstrained** — nothing responds to the threshold anywhere in the swept range. That is *not*
  agreement, and the check prints them differently: a value nobody's output distinguishes is unfalsifiable
  on this evidence, not endorsed by it.
- **thin** — the verdict rests on too few findings to mean much. "Pinned by django" on two findings and on
  two hundred are different claims, and the arithmetic cannot tell them apart, so the report must.

A fourth verdict, **unranked**, exists because of the hotspot sweep: when every repository's count changes
at every step, the plateau is a single point however many repositories you drop, so "not pinned" is
guaranteed by the arithmetic rather than earned. `PCTILE_BAR = 0.75` reads that way — no repository holds
it in place, and equally nothing prefers it to 0.70 or 0.80. **This check asks who holds a value where it
is, never whether the value is right**, and a report that read as endorsement would be the worse error.

First run: `docs/evaluations/thresholds/RESULTS.md`. The four `dupdecide` thresholds came back pinned or
unconstrained and **all marked thin**, resting on one or two findings per repository — no threshold should
move on that. The two hotspot thresholds rest on tens to hundreds of findings and are the first
non-thin verdicts: `MIN_LOC = 30` is clean, `PCTILE_BAR = 0.75` is unranked.

The sweep also found a bug in itself worth recording, because it is the shape this project keeps hitting:
`until` is handed straight to `git log --until=`, which wants a date, and the sweep passed a tag. Two
repositories produced plausible churn from a malformed date and one produced none, with no error. It now
resolves the revision to its commit date and refuses to continue when a repository yields no churn at all
— otherwise every value reports zero findings and the report records a repository with nothing to say
rather than a broken measurement.

**A computed opportunity denominator.** Before any corpus number is quoted for a check, the count of
repositories that *could* have produced a finding must be reported alongside it — the measurement in the
previous subsection, produced by a script rather than by hand. "One hit in fourteen" and "one hit in the
two that contain an HTTP server" are different claims, and only the second is evidence.

### Record which kind of evidence a change has

Every accepted change records one of four, and the classification is auditable in review:

| Evidence | Meaning | Example |
|---|---|---|
| `bug-with-test` | a regression test fails before and passes after | a glob reported as a missing file |
| `independent-instances` | the same failure observed in ≥2 unrelated repositories | — |
| `mechanism` | justified by how the platform works, not by an instance count | CORS is a web-platform behaviour, not one repository's |
| `single-instance` | one occurrence, no mechanism argument | **a recorded limitation**, which must constrain the signal's confidence and be revisited |

`single-instance` is not a rejection. It is a requirement to say so in the signal's own output, so that a
reader is not given a `high`-confidence finding backed by one example.

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

## 22. Evaluating `evaluate`, in every describe round

Everything numbered above measures the **artifact** — what `describe` wrote. `evaluate` output has been
measured three times, covering three signals of roughly twenty: the held-out defect study (§7.1) for
`change-prone-file`, the first spot-check round (§11) for `scattered-source-of-truth` and
`enum-value-escape`, and the threshold sensitivity run (§18) over four group-F constants. Groups A, B, C
and D have no evidence outside our own judgement at all, and the two newest signals — the group-D
exposure pair — have the least of any.

The regression baselines under `tests/corpus/` and `tests/golden/` are not evidence about quality. They
fail when archagent's behaviour *changes* and stay green on a signal that is confidently wrong.

So from 2026-08-22 every describe evaluation also captures and checks `evaluate`.

### 22.1 Capture, because it is not recoverable later

`evaluate` output cannot be reconstructed after the fact. The group B, E and F signals are computed from
the git log as it stood; `--until` bounds the window but assumes the tree matches it, and `evaluate`
itself warns when it does not. Every round so far has discarded its findings.

`selfeval.py score` therefore captures by default (`--no-findings` to skip, `--repeat` to capture twice).
The capture stores the coverage report and the cautions beside the findings, because a findings list read
without them says "eight problems" where the run meant "eight problems, four families never ran, and the
history mining failed".

This is worth doing in rounds that never score the findings. It turns "get precision labels on group B
someday" from an expedition into a filter over data already on disk, pinned to a revision, sitting next
to the artifact the same run produced.

### 22.2 Four checks that need no judge

None of these is a quality score. Each is a defect that holds regardless of anyone's opinion:

| Check | What it catches |
|---|---|
| `unresolved-subject` | a finding naming a file that is not in the tree at that revision |
| `nondeterminism` | two captures of one revision disagreeing — labels cannot attach to findings the next run does not produce |
| `inactive-conflict` | a sign reported among the findings while its family is listed as inactive |
| *silences* | families that produced nothing **for lack of metadata** — not a defect, recorded because unrecorded silence reaches a later reader as health |

Only path-shaped subjects are checked against the filesystem. Most subjects are subsystem or service
names, and reporting one as a missing file is the false positive `drift` needed two rounds to stop
producing.

### 22.3 Three judged criteria — about the report, not the findings

`finding_actionability`, `finding_restraint` and `finding_coverage_honesty`. They ask whether a reader
could act on the report, whether it claims more than it established, and whether it is clear about what
never ran.

**None of them asks whether a finding is true, and that boundary is the design.** §11 withholds severity,
confidence and the recommendation from a spot-check reviewer precisely so that the labels measure reality
rather than agreement with our own prior. This brief shows every finding with its severity attached, so a
correctness judgement collected here would be that prior coming back as a precision figure. Precision
stays in the blinded spot-check. A test asserts no evaluate criterion asks the blinded question, rather
than leaving it to a comment somebody edits later.

### 22.4 Two version keys, two means, one brief

The evaluate criteria are a **separate section with its own version** (`eval-v1`), not new entries in the
artifact brief. Folding them in would bump `rubric_version`, and §17's ledger would then correctly refuse
to place any future round in a series with rounds 1 through 5 — right behaviour, and it would buy the
evaluate series by restarting the artifact one.

`JudgedReview.mean` therefore stays artifact-only and `evaluate_mean` is computed beside it. Both rubric
versions are now emitted by the brief itself; they were hand-typed into the ledger until now, and a
version key entered by hand can disagree with the brief it names without anything noticing.

### 22.5 Comparability depends on the metric

This is the substantive change to §17, and getting it wrong in either direction is a real error.

**For artifact scores**, `generating_model` dominates and `archagent_commit` is recorded but deliberately
does not gate: an artifact is the model's output, and the tool that scored it afterwards did not change
what the model wrote. Round 4 used two builds six weeks apart and its scores were still the artifact's.

**For findings scores, that inverts.** The findings *are* the tool's output, so the archagent build gates
a comparison exactly as the generating model gates an artifact comparison — a changed threshold or a new
signal makes two finding sets incomparable with identical models on both sides. Meanwhile the artifact's
rubric version is irrelevant to them, and gating on it would refuse sound comparisons.

So `compare(rows, metric)` reads `METRIC_KEYS`, which has **no default**. A metric nobody has classified
is refused by name rather than compared under a guess: falling back to the artifact keys for an unknown
metric is precisely how three means across three different briefs came to look like a rising line.

A new `precision` run kind records a spot-check round, which is not a calibration — calibration scores an
artifact — and forcing the two under one name would put different measurements in one series.

### 22.6 `--repeat` on calibration and precision rounds

Determinism has never once been checked. `selfeval.py score --kind calibration` (and `--kind precision`)
therefore captures twice by default; `--no-repeat` opts out and `--repeat` forces it on any kind. A
calibration round costs hours of a reviewer's time, so a second `evaluate` run is noise against it.

The verdict is written onto the capture (`deterministic: yes | no | ""`), not just printed. Three states,
and the empty one means *never checked* — an empty field must not read as a pass.

First result: archagent and fastapi-template both come back `yes`.

### 22.7 The group B/C spot-check, and the source problem it exposed

Groups B and C had never been labelled. Scoping a round to them (`spotcheck.py generate --groups B,C`)
turned out to need two changes rather than a filter.

**The pinned corpus cannot supply the evidence.** `tests/corpus/*.json` are regression baselines: they
store only the fields that must not change, so `detail` and `recommendation` are stripped. Group E and F
findings survive that — their evidence is a file or a value set — but a group B finding read from a
baseline is two subsystem names and nothing else. Asking a reviewer about that is not a spot-check; it
asks them to reconstruct the finding and then grade their own reconstruction, and the number that comes
back would describe that exercise.

`evidence_is_usable` therefore refuses any item carrying nothing beyond its subjects, and `generate`
prints what it skipped instead of quietly shrinking the denominator. The test is whether a measurement
survived, not how long it is: a first version required six words and rejected `god-component`'s
`70/122 files (57%)`, which is the entire finding.

**And the corpus repositories cannot produce these findings at all.** Groups B and C need `**Tier:**` and
`**Connects:**` metadata, which only a repository with an archagent artifact has. datasette, django and
litellm have none. That is the real reason four groups have never been labelled, and it is
[#9](https://github.com/BenedatLLC/archagent/issues/9) again in a new place: a corpus assembled for
checks that need only source and history, asked a question it cannot answer.

So `collect` now reads the `evaluate` captures of §22.1 as well as the baselines, preferring the capture
where a finding appears in both. This is the first payoff from capturing: the B/C round exists because
the data does.

**Round 2 is 14 items across 2 repositories** (archagent at `fe2222b`, fastapi-template at `0.9.0`),
covering `layer-inversion`, `layer-skip`, `unstable-interface`, `cycle-subsystem` and `god-component`.
Two repositories is thin, and `generate` warns when a round draws on fewer than two. Whatever precision
comes back is quoted with its interval and its sources, the way round 1's was.

### 22.10 Round 3 — pre-registered, because only half its outcomes are decisive

Six items, all wardrowbe at `wardrowbe-v1.7.0`: three `unstable-interface` and three `layer-inversion`.
Handed over 2026-08-23. **How it will be read is written down here before the results exist**, for the
same reason §7.1 pre-registers the defect study — the confound below is easy to rationalise away once
there is a number attached to it.

**The confound.** Round 2 split `unstable-interface` 2 confirm (archagent) / 2 dismiss
(fastapi-template), exactly along the repository boundary. wardrowbe is architecturally the same shape as
fastapi-template: Python `app` package under `backend/`, TypeScript frontend, `backend-*` / `frontend-*`
subsystems, a shared `backend-domain` and a `backend-tests`. archagent — where both confirmations came
from — is the odd one out, a CLI with no web layer.

So the round is asymmetric:

- **Confirmed → decisive.** It breaks the fastapi-template pattern inside a repository of the same shape,
  which means those dismissals were about that codebase rather than about the signal.
- **Dismissed → still confounded.** "The signal is weak" and "web backends with a shared domain module
  co-change for ordinary reasons" both predict it, and two repositories of one shape cannot separate
  them. A dismissed result may **not** be written up as having resolved the question. It raises the
  dismissal count and leaves the cause open.

**The genuinely independent third repository is obstudio, and it is blocked by
[#25](https://github.com/BenedatLLC/archagent/issues/25).** Go, ten subsystems, an observability tool
rather than a web application — and its structural signals produce nothing because `model.edges` is built
only from the parsed import graph, so its seventeen declared `**Connects:**` edges are ignored. Unblocking
it means deciding whether a finding may rest on a declaration `drift` has not verified, and probably
carrying a lower `confidence` when it does.

paperless-ngx is the other candidate and has no stored artifact — only reviews — so it needs a full
`describe` run first.

**Also changed for this round:** the `layer-inversion` guidance no longer says that a test subsystem
depending on the code it tests is what tests are for. Round 2's `backend-tests` dismissal restated that
sentence almost exactly, so the label measured the guidance. Four more test-package inversions are in
front of a reviewer and the question is whether they arrive there unprompted.

### 22.8 What this still does not do

It does not measure whether a finding is true. Three signals of twenty have that evidence and this
changes none of it. What it changes is that the data to produce it now accumulates by default instead of
being thrown away, and that a round which never asks the question says so out loud.

---

### 22.9 What calibration round 2 decided

Round 2 labelled groups B and C for the first time: 14 findings, 2 repositories, reviewer blind to
severity, confidence and recommendation. Full results in `docs/evaluations/labels/CALIBRATION-2.md`.

**The result that matters is not a precision figure. Not one of the fourteen measurements was
disputed.** Every dismissal affirmed what the tool measured and rejected what it concluded — "the
measurement is real, but", "the upward edge is real but reflects the tier assignment", "the numeric tier
gap reports a skip, but there is no missing intermediate abstraction". Round 1 was different: there the
measurement itself was wrong or misattributed 4 times in 19.

So the static analysis under B and C does not need work, and the judgement around it does. That is a
useful place for the errors to be, and it narrows what is worth changing.

**Acted on — `layer-skip`, 0 of 3.** All three dismissals were one mechanism: the layer the finding says
to route through does not exist. Neither repository declared any subsystem at tier rank 3, so every
rank-4 → rank-2 edge counted as skipping a tier that was not in the system, and the recommendation named
nothing. `_tier_violations` now reports a skip only when some subsystem occupies a rank strictly between
the two ends.

The rule passes §18's test — *an intermediate layer that is not declared cannot be routed through* names
no repository — and it only ever removes findings, each of which was incoherent as written. It cleared
two of the three dismissed items. One remains and is named below.

**Not acted on — `layer-inversion`, 2 of 4.** Both failures were test and migration packages, where the
edge is real and the *tier assignment* is what the reviewer disputed. That is a question about how
`describe` assigns tiers to non-production code, not about this check, so narrowing the check would be
acting on a different finding than the one measured. One of the two dismissals also restated guidance
the worksheet itself supplied, making it less independent than the rest.

**Not acted on — `unstable-interface`, 2 of 4.** Both confirmations are archagent and both dismissals are
fastapi-template, so the split falls exactly along the repository boundary and two repositories cannot
separate a signal weakness from a property of one codebase. The dismissal reason is coherent and worth
testing later: the signal cannot distinguish an interface that is churning from a module everything
depends on, changing along with the features that use it.

**Not acted on — `cycle-subsystem` (2 of 2) and `god-component` (1 partial).** Too few to act on in
either direction.

#### What the narrowing does not fix

`frontend-app` (ui) → `frontend-client` (infra) was dismissed and still fires. It skips rank 2, which
*is* populated — by `backend-domain`, which a frontend module obviously cannot route through. The tier
ranks are global while this repository has two independent stacks, and nothing in the model says so.
Fixing it means knowing that a skip's intermediate layer must be reachable from the same stack, which
needs either a stack/service scoping on tiers or a much better inference than "some subsystem has that
rank". Recorded, not attempted.

Also worth stating: the sample held 3 of the repositories' layer-skip findings, not all of them. The
four that survive the narrowing were not labelled, so nothing here estimates their precision.

## Appendix A — Where this stands

*Current as of 2026-08-16. This is the only part of the document that goes stale by design.*

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

**L2, the artifact quality — two usable calibration rounds, and a fourth that failed procedurally.**
Round 4 (paperless-ngx, `docs/evaluations/selfeval/paperless-ngx/CALIBRATION.md`) produced no calibration
number: one review brief was generated, the blind judge filled it in, and the human reviewer was then given
that same file. The returned review is an edit pass over the judge's, so it measures recall rather than
agreement — the anchoring §14 predicts when it argues against shipping a sample review. The fresh
repository is spent and the count of usable rounds is still two. The fix is one line of procedure:
**generate two briefs to two paths, and never give a reviewer a path a judge has touched.**

**L2, the artifact quality — two calibration rounds and a variance measurement.** Round 2 (obstudio) gave
the first agreement number against a human reviewer: exact agreement on 2 of 6 criteria, within one point
on 6 of 6, human mean 4.00 against a model judge's 3.67. Round 3 (wardrowbe) repeated it at 1 of 6 exact
and 5 of 6 within one point, human 4.17 against 3.28.

Judging the wardrowbe artifact six times with nothing changed then established how much of that is noise
(§15): the mean across criteria varies by only 0.10, but a single criterion can move two points. That
retroactively explains the low exact-agreement figures — against a floor that wide, exact agreement was
never going to be high, and the within-one-point number was the meaningful one all along. The human-judge
gap of 0.89 is nine times the floor, so it is real.

The checklist instrument built for exactly this problem (§14) reaches 94% agreement between two judges and
97% when a judge repeats itself. Write-ups: `docs/evaluations/selfeval/obstudio/CALIBRATION.md`,
`.../wardrowbe/`, `docs/evaluations/noise-floor/RESULTS.md`, `docs/evaluations/checklists/`.

### What is built and not yet running

| Piece | State |
|---|---|
| deterministic rubric (§9.1) | works today; no agent, no model |
| judged rubric (§9.2) | works; two agreement numbers, and its variance is now measured |
| spot-check worksheet + label store (§11) | works; holds 19 labels |
| blind comparison (§10) | objective half works; generating the arms needs other sessions |
| recurrence suite (§13) | **built and run** — 19 entries across two targets |
| per-repository checklists (§14) | **built and run twice** — 33 items across two targets, four judges each |
| the ledger (§17) | **built** — 19 rows, backfilled from every run on record |
| update evaluation (§16) | machinery built, never run; blocked on the two-revision loop |
| noise floor (§15) | judging half **measured**; generation half not |

### The binding constraint

It has moved three times. It was the empty label store, then the missing noise floor, then the missing
ledger. **It is now simply the number of calibration rounds.**

Everything the loop needs mechanically is now in place: the judging half of the noise floor is measured, so
the acceptance gate in §15 can be operated on an overall score; the recurrence suite and the checklists
turn past rounds into assets rather than memories; and the ledger records what makes two runs comparable.

What is left is evidence. Two calibration rounds on genuinely fresh repositories is thin for any claim
about how the tool performs in general. The target is around six, and each one permanently consumes a
repository nobody has read before — so this constraint cannot be relieved by building anything.

One thing the ledger made visible on its first day: **no run on record captured which model generated the
artifact**, the column §17 identifies as the largest single source of variance. That information existed
each time and is not recoverable. Rounds four through six can record it; rounds one through three cannot.

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
| 5 | Human spot-check and calibration (§11) | machinery done; 19 labels, 3 calibration rounds |
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
5. **Human spot-check and calibration** (§11) — machinery shipped; 19 labels collected and three
   calibration rounds done. This was the binding constraint on the whole L2 half for a long time, and it
   could not be resolved by the person who built the checks. What limits L2 now is the *number* of
   calibration rounds: two on fresh repositories is thin, and each one consumes a repository nobody has
   read before (Appendix A).
6. **Blind comparison** (§10) — the objective half is shipped: identical hashed inputs, blinding and
   shuffling, and scoring against the ground-truth verdicts from the corpus pass. Generation is *not*
   automated, because one model writing all three arms and then grading them measures self-preference.
   The judged half still needs item 5.
7. **L3 task benchmark** — not designed here. Revisit once L1 and L2 have numbers.

---

