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
              └────────────────────────────────────────────────────────────┘
```

---

## 5. Prerequisite — running as of a past commit

Every evaluation below needs the same capability, and it has two halves that are easy to confuse.

**The history half.** `mine_cochange` already accepts `--since`; it needs `--until` (and `evaluate` needs
to pass it through). That bounds churn, fix-churn, and co-change to a window ending at T.

**The tree half.** The complexity measure and every branch-value scan read files *from disk*. Bounding the
history without checking out the code measures old history against new code — a silent, plausible-looking
wrong answer. The harness therefore materialises the tree with `git worktree add` (or a shared clone) at
the chosen revision, and runs the tool there.

Because the two halves can disagree, the tool should **warn when `HEAD`'s commit date is newer than
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

For each entry it clones (shallow where possible, cached between runs), checks out `rev` into a temp
worktree, runs `archagent evaluate --json --until <rev-date>`, and compares a projection of the result —
the same shape the golden tests use — against a recorded expectation under `tests/corpus/<name>.json`.

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

**Repositories.** A held-out set, disjoint from the tuning five, chosen for long history and public
issue trackers. This set is used for nothing else, ever.

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
comparison partly measures self-preference. Use a different model for judging where possible, and say
which was used.

---

## 11. Threats to validity

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

## 12. Build order

1. **`--until` / as-of plumbing** (§5) — the prerequisite for everything else, including the mismatch
   warning. Small.
2. **Pinned-corpus regression** (§6) — the highest ratio of protection to effort, and it makes every later
   change safer to make.
3. **Held-out defect study** (§7) — the credibility anchor, and the only item that can retire a signal.
   Start with the history-only proxy; add issue verification as a cross-check on two repositories.
4. **Self-evaluation tool + rubric v1** (§8, §9) — begin with the deterministic half only, which is
   useful on its own and needs no agent; add the judged half once the noise floor is known.
5. **Blind comparison** (§10).
6. **L3 task benchmark** — not designed here. Revisit once L1 and L2 have numbers.

---

## 13. Out of scope

- **Any runtime dependency on an issue tracker.** Defect data belongs to the harness, not the tool.
- **Modifying the local test-repository checkouts.** They are the measurement baseline; evaluations work in
  temporary clones and leave them untouched.
- **Human-subject studies.** Everything here is judged by code, by public history, or by a model.
- **Benchmarking against other tools.** Interesting later; it needs a shared task definition we don't have.
- **Optimising for a paper.** The evidence should be publishable if we want it to be, but no evaluation is
  chosen because it would look good in one.
