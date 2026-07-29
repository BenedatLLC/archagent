---
status: implemented (steps 1-4; step 5 deferred)
date: 2026-07-25
revised: 2026-07-26
implemented: 2026-07-26
---

# Design: Two history-based architecture checks

This design proposed two new checks for archagent's `evaluate` command: **"scattered single-source-of-truth"** (one decision or
value that should have a single owner but has been re-implemented in several places) and **"change-prone
complex files"** (files that change very often and are also hard to read). Both read the project's **git
history**, which today feeds only one existing check.

## Terms used in this document

- **`evaluate`** — archagent's existing command that reports architecture-health problems. It does not fail
  a build; it produces *suggestions* for a person or an AI agent to confirm and act on. It already sorts its
  findings into themed groups (data ownership, module boundaries, structure, lifecycle).
- **Commit / subject** — one recorded change in git history; its *subject* is the first line of its message.
- **Bug-fix commit** — a commit whose message says it fixes a bug. How you *recognize* one differs by
  project (some write `fix(...)`, some write `Fixed #123`, some write free-form prose) — see Step 1.
- **Churn** (of a file) — how often it changes: the number of commits that touched it in the window we look
  at.
- **Complexity** (of a file) — a rough measure of how tangled the code is; here, how deeply nested it is,
  together with its length.
- **Subsystem** — a named part of the system. archagent's architecture docs define these; when a project
  has none, we fall back to grouping files by their top-level directory.
- **Owner** — the one file or function that is *supposed* to make a given decision or hold a given value.
  (In the deferred declared-owner list of Appendix A this is called the **Authority**.)

---

## 1. Why

`evaluate`'s existing checks all reason about the system's *structure* — which module imports which, which
subsystem runs as which service, which layer sits above which. Two kinds of real problem never show up in
that structure, so those checks are blind to them. Both came from usage feedback:

1. **Scattered single-source-of-truth.** A decision or a piece of state that *should* have one owner is
   instead re-implemented across several files that then drift apart. Nothing is structurally wrong — the
   offending files may already import the intended owner for other reasons, and they can all live in the
   *same* subsystem. Two shapes were observed:
   - a **decision copied into several files** instead of each one calling the single resolver;
   - a **configuration value threaded by hand** and missed on some code paths, so those paths see a stale or
     default value.
2. **Change-prone complex files.** A single file that both changes very often (lots of commits, many of them
   bug fixes) *and* is complex — the classic sign of an abstraction that is straining to hold too many
   special cases.

Neither is visible in the dependency graph; both are visible in the **git history**. archagent already mines
history for one existing check (which files change *together*), so the raw capability is there — this design
adds the missing pieces.

---

## 2. Ground rules

- **Runs on its own, no human required.** A full pass produces its findings with no human input. People
  review or act on the results *afterward*, if they want to. This matches the rest of `evaluate`: the code
  gathers facts, and an AI agent (or a person) judges them. There is never a step that *blocks* waiting for a
  human.
- **Adapts to each project; nothing hard-coded.** Do not bake in `fix(...)` or any fixed set of words —
  commit wording differs by project. Learn each project's wording from its own docs and history (Step 1).
  archagent's miner has a built-in pattern for one common style; that becomes a *fallback*, not the source
  of truth.
- **Stays lightweight.** Build on the existing git miner. Do not add a heavyweight git-mining library or a
  Java-based tool (see §8). A small, optional per-language complexity library is a *possible later* add-on,
  not part of this design.
- **Produces suggestions, never automatic failures.** These checks never fail a build on their own. Each
  finding is ranked with a confidence level, and confidence is lowered when the git history is too thin or
  too messy to trust.
- **Prove each check is worth building before building it.** The first check especially has a real risk of
  producing mostly noise. So each check is validated by a cheap throwaway experiment on real repositories
  *before* any lasting file format or command is added (§7).
- **Code finds the facts; the model only judges them.** An AI model is never used to *gather* data (that
  would make results non-reproducible). It is used only to *judge* the facts the code has already gathered —
  for example, to decide whether a set of values duplicated across files is really one decision
  re-implemented, or an intended family of implementations. This split mirrors current best practice for
  using language models to mine software repositories.

---

## 3. How the pieces fit together

```
                ┌────────────────────────────────────────────────┐
   git history  │  Step 1 — Learn this project's commit wording   │  docs (CONTRIBUTING,
   ───────────► │  (which commits are bug fixes; project's own    │ ◄── commit guidelines,
                │   domain terms)  — computed once, cached        │     README, glossary)
                └───────────────┬──────────────────┬──────────────┘
                                │                  │
          ┌─────────────────────▼──┐      ┌────────▼──────────────────────────────┐
          │ Check A                 │      │ Check B                                │
          │ Change-prone complex    │      │ Scattered single-source-of-truth       │
          │ files (per file: how    │      │  scan the code for a decision          │
          │ often it changes × how  │      │  duplicated across files, ranked by    │
          │ complex it is)          │      │  change history — reported as findings │
          └─────────────────────────┘      └────────────────────────────────────────┘

   Both checks report findings the agent judges — no file to declare or maintain.
   Related, separate check: a "config value threaded inconsistently" check built on the
   scanner archagent already has for config keys (§6.4). A deferred, optional durable
   overlay for Check B (a declared-owner list) is in Appendix A.
```

Both checks use Step 1 to recognize this project's bug-fix commits (Check A's fix-weighted variant, Check B's
ranking). Check A is simple and ships first; Check B is the harder, novel piece.

---

## 4. Step 1 — Learn this project's commit wording

**Why.** Both checks lean on *which commits are bug fixes in this project* — Check A can weight bug-fix
changes, and Check B ranks duplicated decisions by them. There is no universal rule for recognizing a bug-fix
commit: some projects write `fix(auth): …`, some write `Fixed #123 -- …`, some write free-form prose, some
write in another language. Hard-coding one style fails on the others (an early experiment confirmed this —
see §7). So the first step *learns* the project's wording from evidence.

**What the code gathers (plain, reproducible):**
- **Commit guidelines from docs** — `CONTRIBUTING`, a commit-message config if present, pull-request
  templates, the README's commit section, and any agent-instruction files.
- **A sample of real commit subjects** — the most common leading words and patterns (e.g. `type(scope):`,
  an issue number like `#123`, a tracker id like `PROJ-456`, or a leading verb like "Fixed").
- **The project's own domain terms** — from the architecture docs and glossary, if any. A light aid when the
  model later judges whether a duplicated value set names a real decision.

**What the model then decides (judging the gathered facts):**
- Which commit style this project uses, and a small **bug-fix recognizer** for *this* repo — a few patterns
  that identify its bug-fix (or, more precisely, its *fix-labeled maintenance*) commits.

**Output.** A small cached file, `.archagent/history-profile.json`, holding the bug-fix recognizer, any
domain terms, and a note on how trustworthy the history is. Computed once, refreshed when the history window
or the docs change. Both checks read it.

> This is the concrete home for the requirement "sample the git history and read the documentation to learn
> the project's terminology." It is: code gathers evidence → model classifies → cache the result. No human
> input required.

---

## 5. Check A — Change-prone complex files

**What it flags.** A single file that is *both* changed very often *and* complex — the pattern that usually
marks an abstraction absorbing too many special cases. (This idea, and the specific way of measuring it, come
from Adam Tornhill's work on finding risky code by combining how often a file changes with how complex it
is.)

**How it's measured, per file, over the history window:**
- **How often it changes** = the number of commits that touched the file. A second variant counts only the
  file's *bug-fix* commits, using Step 1's recognizer.
- **How complex it is** = an **indentation-based** measure: how deeply the lines are indented, on average,
  plus the file's length. Deep, consistent nesting is a good, *language-agnostic* proxy for complexity, and
  it needs no per-language parser — which suits archagent's mix of languages. (A more precise per-language
  measure is a possible later upgrade, not part of this design.)
- **Combined score** = (this file's change-frequency rank) × (this file's complexity rank), each expressed
  as a percentile in 0–1. A file has to score high on *both* to be flagged — this separates a real problem
  file from one that is merely large-but-stable or churned-but-trivial.

**When it runs and how confident it is.** Needs git. It reuses the existing check for whether the history is
trustworthy (enough commits, not dominated by giant bulk commits, reasonably consistent messages); thin or
messy history lowers confidence or skips the check. It flags files above a high bar on *both* measures
(default: both in the top quartile) and reports them ranked.

**What a finding looks like.** A new *maintainability* group of findings. Each names the file, its
change-count, its bug-fix change-count, and its complexity, with the suggestion: *"changes often and is
complex — a candidate to refactor or split; check whether it's absorbing too many special cases."* It never
fails a build.

**How it differs from the existing "oversized subsystem" check.** That check flags a whole *subsystem* that
too many others depend on and that owns too much code, using the current dependency structure. This one
flags a single *file*, using its change history. They look at different things and complement each other; a
change-prone file often sits inside an oversized subsystem, but need not.

**Still to settle (via experiment):** the history window, the exact "top quartile" bar, and whether total
change-count or bug-fix change-count is the better signal. The held-out defect study in
`evaluating-archagent.md` §7 is designed to answer the last of these against an outcome that does not
depend on our own labelling — including whether the complexity axis earns its place over churn alone.

---

## 6. Check B — Scattered single-source-of-truth

### 6.1 The idea, and what's in scope

The thing being protected is a **single decision or piece of state that should have one owner**. This check
targets the "decision copied into several files" shape. The "config value threaded inconsistently" shape is
handled by a separate check (§6.4).

The check is a single autonomous flow: **scan the current code for a decision duplicated across files, rank
it by how often those files change, and report the survivors as candidates for review** (§6.2). It declares
nothing and stores nothing — like Check A, it re-computes from the code every run. A deferred, optional
extension would let a person record durable confirmations and dismissals in a declared-owner list; that is
out of the main flow and lives in **Appendix A**.

### 6.2 Finding candidates — duplicated decisions in the code

> *Revised after experiments (§7).* The original plan mined recurring words from bug-fix commit *messages*.
> On real repositories that mostly rediscovered each subsystem's subject matter (commits about forms mention
> "form") — low precision. The reliable signal is in the **code**: a decision that is already duplicated
> across files. Commit history is kept, but only to *rank* the results.

Surfaces *possible* single-owner decisions with nothing declared up front, by finding a decision that is
already duplicated across files and then using change history to rank which duplications actually hurt.

1. **In each file, find the domain values that are branched on** — string literals compared with `==`/`!=`,
   used in a `case`/`match`, or tested for membership. These are the concrete values a decision turns on
   (a set of statuses, kinds, provider names, and so on).
2. **Within a subsystem, group values that co-occur across files.** Keep values branched on in *several*
   files, and group together the values that keep appearing in the same files. Each group is a candidate
   decision — a *set of related values* (for example `{cancelled, completed, failed, running, succeeded}`).
3. **Keep only tight groups.** Some file must branch on *most* of the group's values — that file is the
   likely **owner** — while other files branch on only a subset (the re-implementations). This "one file has
   the whole set, others have pieces" shape is what separates a real duplicated decision from an incidental
   pile-up of common strings. Skip vendored, minified, and generated files, which otherwise dominate.
4. **Rank the candidates by the change history of the files involved** (reusing Check A's per-file
   change-counts): a duplicated decision whose files change often — especially in bug-fix commits — is far
   more likely to be a real, costly problem than one whose files barely change. This is the only place commit
   history is used, and only to *rank*, never to *find*.
5. **The model then judges** each candidate by reading the files: is this genuinely one decision
   re-implemented, or an intended family of implementations behind a shared interface (see the note below)?
   A confirmed one is **reported as a finding** — the decision (its value set), the owner from step 3, the
   re-implementing files, and the change history that ranked it. Nothing is written to a file.

**A false alarm to expect: intended families of implementations.** Adapters, database backends, or plugins
that all implement one interface legitimately branch on the same values in parallel — the scan will surface
them, and the reviewer (person or model) dismisses them. That is fine: these are *suggestions* to confirm,
not automatic failures. (In testing, this correctly surfaced Django's per-database-backend operations and a
project's per-provider request transformers — real duplication, but by design.)

**When it runs.** The code scan works on *any* repo, whatever the commit-message quality — the duplication is
in the code, not the messages. Commit history is used only to *rank*, so on a repo with thin or messy history
the candidates are still found, just ranked less confidently and marked as such. This is a real improvement
over the message-mining plan, which needed clean history even to get started.

### 6.3 What a finding looks like, and running on its own

A full pass runs end to end with no human input: find duplicated decisions in the code (§6.2) → rank them by
change history → the model judges each → report the survivors. Each finding is a new *single-source-of-truth*
group finding that names the decision (its value set), the likely owner, the re-implementing files, and the
change history that ranked it, with the suggestion: *"this decision looks re-implemented across N files —
check whether they should call the owner instead, or whether it's an intended family of implementations."*
Findings are low-to-medium confidence and never fail a build.

There is **no file to declare or maintain**: the scan re-derives the candidates, their values, and their
owner every run, exactly like Check A. A person may act on a finding (refactor it, or record it as
reviewed/dismissed the way any `evaluate` finding is accepted today), but nothing waits on them. An optional
*durable overlay* — a declared-owner list that persists confirmations and dismissals so intended families
stop re-appearing — is deferred; see **Appendix A**.

### 6.4 Related idea: a config value threaded inconsistently (separate check)

The "config value that's right in one place and stale in another" shape is *not* handled by the duplication
scan. archagent already has a scanner (used by its drift check) that lists, for each file, which
configuration or environment keys it reads — a plain, reliable fact. A config-threading check is then:
*"key X is read in files A, B, and C; is one owner passing it through, or does each read it independently and
risk a stale default?"* Because the raw fact is already extracted deterministically, this belongs on its own
as a separate, higher-precision check — not part of the main Check B flow. Its fate is decided after the
experiment.

---

## 7. Proving each check is worth building — experiment results

No new file format, command, or documentation-format change is added until cheap throwaway experiments show
the checks produce real signal on real repositories. These were run on six open-source repos (Django,
LiteLLM, Datasette, and others) spanning three commit styles. Full log:
`research/architecture-agent/feedback/probe-results.md`. Outcomes:

- **Experiment 1 — commit-wording learning: PASS, and shown necessary.** The hard-coded pattern found *zero*
  of Django's ~16,000 fix commits (Django uses `Fixed #NNN`, not `fix:`) and missed ~40% of LiteLLM's even
  though LiteLLM declares Conventional Commits. Learning the project's own wording is required, not optional.
- **Experiment 2 — candidate quality from commit messages: WEAK → led to the pivot.** Mining recurring
  bug-fix *words* mostly rediscovered each subsystem's subject (`form` in forms, `router` in the router).
  Low precision. This is why §6.2 now finds duplicated decisions in the *code* instead.
- **Experiment 2b — duplicated decisions in the code: STRONG PASS.** The §6.2 scan surfaced real,
  coherent duplicated-decision clusters that message-mining missed — e.g. a provider list re-branched across
  five high-change LiteLLM core files (one file holding 20 of 21 values, the clear owner), and a status set
  across many files. Two deterministic filters control false alarms: excluding vendored/generated files, and
  keeping only *tight* groups (some file owns most of the value set). Change history ranked the real clusters
  far above incidental ones — confirming history-as-ranker.
- **Experiment 3 — false alarms (Check B):** the classes to design against were identified by 2b —
  vendored/generated files, loose "grab-bag" groups, and intended families of implementations (handled by
  the filters in §6.2 and by reviewer judgment). The "uses-the-words-but-never-calls-the-owner" detector
  remains the next precision improvement.
- **Experiment 4 — change-prone files (Check A): PASS.** The change × complexity ranking surfaced exactly
  the files a maintainer would name (Django's ORM query/compiler/base and ModelAdmin; LiteLLM's router,
  logging, and streaming). Defensible top lists, essentially no noise. Notably, several files flagged here
  also appeared as duplicated-decision clusters in 2b — the two checks corroborate.

**Repositories wanted** (larger than earlier test repos; ~3–4 covering these):
1. Large and long-lived (thousands of commits, hundreds of files).
2. **A mix of commit styles across the set** — at least one using `fix(scope):`, one using issue/tracker
   references (`Fixed #123`), and one free-form. This is what proves the learning step (Step 1) rather than
   a hard-coded rule.
3. Commit guidelines present (a `CONTRIBUTING` file, a commit-message config, a pull-request template).
4. A clear division into parts (or existing architecture docs), so files can be grouped into subsystems.
5. Domains prone to this problem (status/state machines, permissions, config-heavy systems).
6. At least one project mixing two languages (e.g. Python and TypeScript).
7. Open-source, so candidates can be confirmed by reading the code.

**Bar to clear — met.** On multiple repos the code-first Check-B candidates were mostly real after judging,
the recognizer agreed with hand labels across all three commit styles, and Check A's top files were
defensible. The bar is cleared for building, with the candidate-finding method changed as above. Remaining
calibration (thresholds, the tightness bar, the ranking) is noted inline and left to implementation.

---

## 8. Git-mining approach (decided) and the alternatives

- **Extend the existing miner (`cochange.py`)** — chosen. Change-count comes from the commit-and-file stream
  it already parses; complexity is computed by reading current files. Everything the checks need comes from
  reading `git log` output and reading files.
- **A dedicated Python git-mining library (PyDriller)** — not used. For these specific measures it gives no
  better results (its complexity feature is per-language; the indentation measure is language-agnostic and a
  better fit), is not faster (it builds rich objects per commit; streaming `git log` is quicker on large
  histories), and saves nothing downstream. Its only effect would be adding a dependency. Reconsider only if
  we later need line-level change counts or true per-language complexity — and then via a small optional
  complexity library, not this.
- **A Java-based miner (Code Maat)** — not used. It is largely unmaintained and needs a Java runtime. Use its
  published formulas as a reference only.

---

## 9. Build order

0. **Experiments (§7)** — the gate. **Done** — checks confirmed worth building; Check B's candidate-finding
   changed to the code-first method above.
1. **Miner additions** — **done**. `cochange.py` now yields per-file change-count and bug-fix change-count
   from the same single pass; `hotspots.py` holds the indentation-complexity function; `history.py` holds
   Step 1's commit-wording profile, cached at `.archagent/history-profile.json` and surfaced by the new
   `archagent history-profile` command (`--evidence` dumps the raw facts for an agent to judge).
2. **Check A (change-prone files)** — **done**. `hotspots.py` → the group-E `change-prone-file` finding.
3. **Check B (scattered single-source-of-truth)** — **done**. `dupdecide.py` → the group-F
   `scattered-source-of-truth` finding: branch-value sets, vendored/generated excluded, tightness-filtered,
   owner inferred, ranked by the churn of the files involved. No new file format.
4. **Command/skill updates** — **done**. New `E` and `F` groups in the `evaluate` output and JSON
   (`--group A|B|C|D|E|F`), the learned profile reported under `history.profile`, and the `evaluate` skill
   guidance extended with both signals and how to judge them (including the intended-family false alarm).
5. **Later, if warranted:** the separate config-threading check (§6.4) — still open — and the deferred
   declared-owner overlay (Appendix A), still deferred as a *file format*. Its **"never calls the owner"
   detector shipped without it**: where the project already declares an owner as an **enum**, no
   `capabilities.md` entry is needed to know the authority or the key words, so `find_enum_escapes`
   flags files that re-decide the enum by comparing against its raw member strings
   (`state.value == "summarized"` instead of `WorkflowState.SUMMARIZED`). This catches a shape the
   clustering scan structurally cannot: the enum's values are *assigned* in the definer and only
   *compared* elsewhere, so they never reach the "branched on in ≥3 files" bar. Precision comes from two
   measured guards — a file must escape ≥3 of the enum's members, or ≥2 that are ≥50% of it (LiteLLM has
   a `Role` enum containing "system", and dozens of files compare an API payload's role to `"system"`
   knowing nothing of it); and the near-conclusive `.value ==` unwrap only counts in Python, since in
   TypeScript `.value` is an ordinary property (Vue compares a Babel node's `key.value` to `'set'`,
   unrelated to its `TriggerOpTypes.SET`). Measured after both guards: 0 findings on Django, 0 on
   Datasette, 0 on vue-core, 17 on LiteLLM, and the 1 real one on my-research-assistant that prompted it.

**Calibration as shipped** (the values §5 and §6 left to implementation): top-quartile bar on both hotspot
axes (`PCTILE_BAR = 0.75`) with tied files sharing an average rank; `MIN_LOC = 30`; a value must be branched
on in ≥3 files, a cluster needs ≥3 values, the owner must hold ≥60% of the set, and ≥2 other files must hold
≥2 values each; a duplicated decision is only reported once its files average ≥2 commits in the window. Both
total and fix-labeled churn are reported; total churn drives the ranking, since the learned recognizer's
reliability varies by repo (it is reported alongside, with its cautions, so a reader can weigh it).

---

## 10. Out of scope

- **No required human step** — the tool reports findings; people act only if they want to (§6.3).
- **No new declared file in the first version** — Check B reports findings like Check A; the declared-owner
  list is deferred (Appendix A).
- **No hard-coded commit wording** — learned per project (§4).
- **Never fails a build on its own** — these are suggestions, not pass/fail gates.
- **No heavyweight git-mining dependency** (§8).
- **Not full clone-detection or data-flow analysis** — the first version finds duplicated *value sets*; the
  key-word and "never calls the owner" detectors (Appendix A) and true data-flow tracing are later, separate
  steps.
- **No author/team analysis** — a possible future idea (it would need commit-author data), not part of this
  design.

---

## Appendix A — Deferred: a declared-owner list (`capabilities.md`)

**Status: deferred, potential future work.** Not part of the main design above.

**Why deferred.** In the original design this file was the source of truth that enforcement read: because
candidate-finding was weak, a person or model had to *declare* each capability, and enforcement re-checked
the declarations. After the Check B pivot (§6.2), the code-first scan re-derives the candidates, their value
sets, and their owners on every run, autonomously — so "enforce the declared entries" largely collapses into
"run the scan again." The file's role shrinks from a source of truth to an optional *durable-curation
overlay*.

**What it would still add** (things the scan cannot do on its own):
- **Durable dismissals** — the scan re-surfaces intended families (database backends, provider adapters) on
  every run; a place to record "reviewed — intended, dismissed" stops the repeated triage.
- **Durable confirmations + tightening** — a human-confirmed, narrowed entry (the right key words, the right
  exclusions, the stricter "never calls the owner" detector) is higher-precision than the raw scan, and
  should persist.
- **Proactive declarations** — a decision you want to *keep* single-owner but that isn't duplicated yet; the
  scan can't propose these, because there is nothing duplicated to find.

**When to build it.** Only if real use shows the overlay needs a structured format. In the interim, record
accept/dismiss the way `evaluate` findings are already handled (an ADR, or a lightweight suppressions note).

**Sketch, if built.** A file alongside the invariants list, read with the same table parser (strip Markdown
formatting from **every** column). Enforcement would check each declared entry against the current code via a
**detector**, written with a leading keyword so kinds can be added without changing the format:
- **key words** — flag any source file (other than the owner or an excluded file) that contains several of
  the decision's key words.
- **never calls the owner** — flag files that use the key words yet never import or call the owner; removes
  the biggest false-alarm class (files that merely *display* an already-decided value).

| Column | Meaning |
|---|---|
| ID | a stable identifier, e.g. `CAP-ORDER-STATE` |
| Name | a human name for the decision |
| Authority | the file (or file + symbol) that is the one legitimate owner |
| Detector | how to spot a re-implementation; the simple form is `key-words: A, B, C [min 2]` |
| Exclude | files exempt from the check (tests; the owner's own inputs) |
| Severity | `warn` by default (these are suggestions) |
| Why | the reason, plus where it came from (the cited duplication / commits) |
| Status | `proposed` \| `active` \| `deprecated` |

Example:

| ID | Name | Authority | Detector | Exclude | Severity | Why | Status |
|----|------|-----------|----------|---------|----------|-----|--------|
| CAP-ORDER-STATE | Order state | `src/orders/state.py::resolve` | key-words: pending, paid, shipped, refunded [min 2] | `tests/**` | warn | one resolver is the source of truth; the same values are branched on in 4 other files | active |
