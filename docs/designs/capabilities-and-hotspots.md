# Design: Two history-based architecture checks

Two new checks for archagent's `evaluate` command: **"scattered single-source-of-truth"** (one decision or
value that should have a single owner but has been re-implemented in several places) and **"change-prone
complex files"** (files that change very often and are also hard to read). Both read the project's **git
history**, which today feeds only one existing check.

Status: Draft — design phase (pre-implementation)
Date: 2026-07-25
Relates to: ROADMAP items *Capability fragmentation* and *Churn × complexity hotspots*; the `evaluate`
command (`src/archagent/evaluate.py`) and the git-history miner (`src/archagent/cochange.py`)

---

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
  In the declared-list file (below) this column is literally called **Authority**.

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

- **Runs on its own, no human required.** A full pass produces its findings — and, for the first check,
  *proposes* the entries it would add to the declared list — with no human input. People review or adjust
  the results *afterward*, if they want to. This matches the rest of `evaluate`: the code gathers facts, and
  an AI agent (or a person) judges them. There is never a step that *blocks* waiting for a human.
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
  for example, to decide whether a recurring word really names a shared decision or is just common English.
  This split mirrors current best practice for using language models to mine software repositories.

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
          │ files (per file: how    │      │  • find candidates from history        │
          │ often it changes × how  │      │  • check declared owners against the   │
          │ complex it is)          │      │    current code                        │
          └─────────────────────────┘      └────────────────────────────────────────┘

   Related, separate idea (NOT part of the declared-owner list): a "config value threaded
   inconsistently" check built on the scanner archagent already has for config keys (§6.4).
```

Both checks depend on Step 1. Check A is simple and ships first; Check B is the harder, novel piece.

---

## 4. Step 1 — Learn this project's commit wording

**Why.** Both checks need to know *which commits are bug fixes in this project*, and which words in commit
messages are meaningful versus generic. There is no universal rule: some projects write `fix(auth): …`, some
write `Fixed #123 -- …`, some write free-form prose, some write in another language. Hard-coding one style
fails on the others (an early experiment confirmed this — see §7). So the first step *learns* the project's
wording from evidence.

**What the code gathers (plain, reproducible):**
- **Commit guidelines from docs** — `CONTRIBUTING`, a commit-message config if present, pull-request
  templates, the README's commit section, and any agent-instruction files.
- **A sample of real commit subjects** — the most common leading words and patterns (e.g. `type(scope):`,
  an issue number like `#123`, a tracker id like `PROJ-456`, or a leading verb like "Fixed").
- **The project's own domain terms** — from the architecture docs and glossary, if any. Used later to tell a
  real shared-decision word apart from ordinary English.

**What the model then decides (judging the gathered facts):**
- Which commit style this project uses, and a small **bug-fix recognizer** for *this* repo — a few patterns
  that identify its bug-fix (or, more precisely, its *fix-labeled maintenance*) commits.
- A short list of the project's meaningful terms, and a list of generic words to ignore, beyond ordinary
  English stop-words.

**Output.** A small cached file, `.archagent/history-profile.json`, holding the bug-fix recognizer, the term
lists, and a note on how trustworthy the history is. Computed once, refreshed when the history window or the
docs change. Both checks read it.

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
change-count or bug-fix change-count is the better signal.

---

## 6. Check B — Scattered single-source-of-truth

### 6.1 The idea, and what's in scope

The thing being protected is a **single decision or piece of state that should have one owner**. This check
targets the "decision copied into several files" shape. The "config value threaded inconsistently" shape is
handled separately (§6.4), because the raw fact it needs is something archagent *already* extracts
deterministically, so a fuzzier approach would be more work and less reliable. Whether the two eventually
merge is decided by the experiment (§7).

The check has two halves that work independently:
- **Find candidates** from git history (needs a trustworthy history; runs only when the history is good
  enough).
- **Check declared owners** against the current code (runs every time, on whatever has been declared).

### 6.2 Finding candidates from history

Surfaces *possible* single-owner decisions, with nothing declared up front.

1. Using Step 1's recognizer, collect the subjects of each subsystem's bug-fix commits.
2. Break each subject into words, after removing: the commit-style prefix (`fix(auth):` → drop `auth`), issue
   and pull-request numbers, ordinary English stop-words, and Step 1's project-specific generic words. Keep
   the project's domain terms.
3. Count how often each word recurs across that subsystem's bug-fix commits. Flag a word as a candidate when
   it clears **both** a minimum count and a minimum *share* of the subsystem's bug-fix commits — and only for
   subsystems with enough bug-fix commits to be meaningful. *(All three thresholds are placeholders to be
   set by experiment — §7.)* The intuition: a decision with no single owner gets patched one call-site at a
   time, so the same word keeps recurring across otherwise-unrelated fix commits over months.
4. Emit each candidate as `{subsystem, word/phrase, count, share, the commit hashes and subjects that back
   it up}`.
5. **The model then judges** whether the recurring word really names a shared decision (versus an accident
   of common English), by reading the cited commits and the code. For a confirmed one, it works out the
   **owner** (§6.3) and *proposes* an entry for the declared list (marked "proposed," not yet confirmed).
6. Candidates that match something already declared are skipped, so the check doesn't re-surface known ones.

**When it runs.** Only when Step 1 / the history-trust check clears a bar (enough consistent bug-fix
history). Otherwise it reports itself as "not run, because the history isn't clean enough" — visibly, never
silently (`evaluate` already reports which checks were inactive and why). While the check is still
experimental it may be opt-in only; the target is to turn it on automatically when the history is good.

### 6.3 Checking declared owners against the current code

Runs every time, over whatever owners have been declared (including the ones the model proposed above).

- Read the declared list (§6.5), stripping Markdown formatting (like backticks) from **every** column.
- Each declared entry carries a **detector** — how to spot a file that is re-making the decision. Detectors
  are written with a leading keyword so more kinds can be added later without changing the file format:
  - **the simple detector (built first): "key words."** Flag any source file — other than the owner itself,
    and other than files the entry marks as exempt — that contains several of the decision's key words.
  - **the better detector (built next): "uses the words but never calls the owner."** Flag files that use
    the decision's key words yet never import or call the owner. This removes the biggest source of false
    alarms — files that merely *display* a value the owner already decided.
  - later: a regular-expression detector, and possibly a config-threading detector (or keep that in §6.4).
- **Working out the owner automatically.** The owner is *inferred*, not required from a human: prefer an
  explicit claim in the code or docs ("the single source of truth", "the only place", "canonical"),
  otherwise the definition most-called by the files that use the decision's words. The model decides; a
  person can correct it later.

### 6.4 Related idea: a config value threaded inconsistently (kept separate)

The "config value that's right in one place and stale in another" shape is *not* handled by the key-words
detector. archagent already has a scanner (used by its drift check) that lists, for each file, which
configuration or environment keys it reads — a plain, reliable fact. A config-threading check is then:
*"key X is read in files A, B, and C; is one owner passing it through, or does each read it independently and
risk a stale default?"* Because the raw fact is already extracted deterministically, this belongs on its own
as a higher-precision check rather than as a fuzzy key-words detector. Whether it stands alone (expected) or
merges into Check B is decided after the experiment.

### 6.5 The declared-owner list — a new file in the architecture docs

A new file alongside the existing invariants list, read with the same table parser. **It is only added once
the experiment (§7) shows the check is worth it.** Columns:

| Column | Meaning |
|---|---|
| ID | a stable identifier, e.g. `CAP-ORDER-STATE` |
| Name | a human name for the decision |
| Authority | the file (or file + symbol) that is the one legitimate owner |
| Detector | how to spot a re-implementation; the simple form is `key-words: A, B, C [min 2]` |
| Exclude | files exempt from the check (tests; the owner's own inputs) |
| Severity | `warn` by default (these are suggestions) |
| Why | the reason, plus where it came from (proposed by the tool, or written by a person; the cited commits) |
| Status | `proposed` (tool-proposed) \| `active` (a person confirmed it) \| `deprecated` |

Example:

| ID | Name | Authority | Detector | Exclude | Severity | Why | Status |
|----|------|-----------|----------|---------|----------|-----|--------|
| CAP-ORDER-STATE | Order state | `src/orders/state.py::resolve` | key-words: pending, paid, shipped, refunded [min 2] | `tests/**` | warn | one resolver is the source of truth (see state.py docstring); recurred in 9 fix commits | proposed |

### 6.6 Running on its own, with an optional human step

A full pass runs end to end with no human input: Step 1 → find candidates → the model proposes entries
(marked "proposed") → check those entries against the code → report the findings. Afterward, a person may
*optionally* promote a "proposed" entry to "active," adjust its key words or owner, or add exemptions —
nothing waits on them. Findings here are always low-to-medium confidence and never fail a build on their own.

---

## 7. Proving each check is worth building (experiments come first)

No new file format, no new command, and no documentation-format change is added until cheap throwaway
experiments show the checks produce real signal on real repositories. Each experiment is a small script over
the existing miner plus a search — no new file format needed.

- **Experiment 1 — commit-wording learning.** On each repo, gather the commit guidelines and a sample of
  subjects, have the model produce the bug-fix recognizer, and compare it against a hand-labeled sample.
  *Decides:* does learning beat the hard-coded pattern, and on which commit styles. **(Already run — it does;
  results in `research/architecture-agent/feedback/probe-results.md`.)**
- **Experiment 2 — candidate quality (Check B).** Mine the recurring bug-fix words per subsystem and read
  the top candidates by hand. *Decides:* are the recurring words real shared decisions or common-English
  noise? Sets the three thresholds and the generic-word list.
- **Experiment 3 — false-alarm rate (Check B).** Pick one owner and its key words by hand, run the simple
  key-words detector, and count the false alarms (tests, files that only display a value, the owner's own
  inputs). *Decides:* is the simple detector usable, or is the "uses-the-words-but-never-calls-the-owner"
  detector needed from the start.
- **Experiment 4 — change-prone files (Check A).** Compute the change × complexity ranking and read the top
  files. *Decides:* does the ranking surface genuinely problematic files; sets the bar and the change measure.

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

**Bar to clear:** on at least two repos, the Check-B candidates are mostly real after judging, the recognizer
agrees with hand labels on the non-`fix(scope):` repos, and Check A's top handful of files are defensible. If
it falls short, narrow the scope (e.g. ship Check A only) or change the detector before adding the declared
list.

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

0. **Experiments (§7)** — the gate. Set the thresholds; confirm each check is worth building.
1. **Miner additions** — per-file change-count and bug-fix change-count; the indentation-complexity function;
   Step 1's cached commit-wording profile.
2. **Check A (change-prone files)** — small, needs no new file format; ships first.
3. **Check B, the "check declared owners" half** — the declared-owner list file, the key-words detector, and
   the matching documentation-format section.
4. **Check B, the "find candidates" half** — history mining, automatic owner inference, and tool-proposed
   entries.
5. **The better detector** ("uses the words but never calls the owner") and the separate config-threading
   check (§6.4), guided by what the experiments show.
6. **Command/skill updates** — teach the `evaluate` guidance to explain the two new kinds of finding and to
   drive the optional human review.

---

## 10. Out of scope

- **No required human step** — the tool proposes; people adjust only if they want to (§6.6).
- **No hard-coded commit wording** — learned per project (§4).
- **Never fails a build on its own** — these are suggestions, not pass/fail gates.
- **No heavyweight git-mining dependency** (§8).
- **Not full clone-detection or data-flow analysis** in the first version — key-word overlap first, the
  "never calls the owner" detector next; true data-flow tracing is a later, separate step.
- **No author/team analysis** — a possible future idea (it would need commit-author data), not part of this
  design.
