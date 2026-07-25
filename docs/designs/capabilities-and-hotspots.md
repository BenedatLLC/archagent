# Design: Capability Fragmentation & Churn×Complexity Hotspots

**Status:** Draft — design phase (pre-implementation)
**Date:** 2026-07-25
**Owners:** archagent maintainers
**Relates to:** ROADMAP items *Capability fragmentation* and *Churn × complexity hotspots*; the `evaluate`
command (`src/archagent/evaluate.py`) and the co-change miner (`src/archagent/cochange.py`); design history
in `research/architecture-agent/feedback/capabilities-design-notes.md`.

---

## 1. Motivation

`evaluate`'s current signals (groups A–D) all reason about **structure declared or inferable as a graph** —
import edges, `Service`/`Tier`/`Connects` metadata, pairwise co-change. Usage feedback surfaced two classes
of real architectural problem that shape *cannot* see:

1. **Fragmented single source of truth.** A decision or piece of state that *should* have one owner is
   instead re-implemented across several files/paths that then drift out of sync. There is no missing edge
   (the offenders may already import the "authority" for other reasons) and no oversized subsystem — every
   offender can live in the *same* subsystem. Two observed shapes:
   - a **decision re-implemented** in N places instead of calling the one resolver;
   - a **config/state value propagated inconsistently** — passed by hand and not threaded through every path.
2. **Churn × complexity hotspots.** A single file with **both** heavy git churn (many commits, especially
   bug fixes) **and** high complexity — the classic sign of an abstraction absorbing too many edge cases.

Both are **historical / within-artifact** and need git-history mining, which today feeds only the pairwise
co-change signal. This design adds the mining substrate and both signals.

---

## 2. Principles & constraints

- **Autonomous by default.** A pass requires *no* human input. Deterministic mining + LLM judgment produce
  the findings and — for capabilities — *propose* the declarations. Humans review or fine-tune **after** a
  pass, optionally. This mirrors the rest of `evaluate` ("candidates the agent judges"): the *agent* (LLM)
  does the judgment, never a required human gate.
- **Project-adaptive, not keyword-hardcoded.** Do **not** bake in `fix(scope):` or any fixed bug/commit
  vocabulary — terminology is project-specific (conventional commits vs. tracker refs vs. free-form). Learn
  each project's conventions from its docs + history in **Phase 0**. The existing hardcoded `_CONVENTIONAL`
  regex in `cochange.py` becomes one *input/fallback* to a learned matcher, not the source of truth.
- **Lightweight substrate.** Extend `cochange.py`; no PyDriller / Code Maat / JVM dependency (see §10). A
  narrow, gated `lizard` add-on is a *possible later* upgrade only if the indentation complexity proxy
  proves too coarse.
- **Candidates, not verdicts; low-noise; gated.** Never gate CI by default. Scale confidence by the
  history-hygiene metrics already computed. Prove value by experiment (§9) before shipping the artifact
  member.
- **Deterministic extraction ⟂ LLM judgment.** The LLM is never in the extraction loop (reproducibility).
  It classifies / judges / proposes over deterministic candidates — the PRIMES and IRIS pattern
  (`papers.md` group G).

---

## 3. Architecture: one substrate, one learning phase, two signals (+ one spin-off)

```
                ┌────────────────────────────────────────────┐
   git history  │  Phase 0 — Project profile (shared)         │  docs (CONTRIBUTING,
   ───────────► │  learn commit conventions + bug-fix matcher │ ◄── commitlint, README,
                │  + domain terminology  (cached)             │     ADRs, glossary)
                └───────────────┬───────────────┬─────────────┘
                                │               │
                 ┌──────────────▼──┐     ┌──────▼───────────────────────┐
                 │ Signal F         │     │ Signal E — Capability         │
                 │ Churn×complexity │     │ fragmentation                 │
                 │ hotspots         │     │  • Discovery (history, gated) │
                 │ (per file)       │     │  • Enforcement (static)       │
                 └──────────────────┘     └───────────────────────────────┘

   Spin-off (scoped OUT of capabilities.md): Config-propagation — a separate, more-deterministic
   signal built on the existing configscan extractor (§8).
```

---

## 4. Phase 0 — Project profile (terminology & convention learning)

**Why.** Discovery and hotspots both need to know *which commits are bug fixes in this project* and *what
domain vocabulary is signal vs. English noise*. Hardcoding `fix:` fails on the many repos that use tracker
refs (`Fixes #123`, `PROJ-456:`), free-form subjects, or another language. So the first phase **learns** the
project's conventions.

**Deterministic inputs (mined, reproducible):**
- **Convention docs:** `CONTRIBUTING*`, `.gitmessage`, commitlint config (`commitlint.config.*`,
  `.commitlintrc*`), PR/issue templates, `README` "commit" sections, `AGENTS.md`/`CLAUDE.md`.
- **Commit-subject sample:** frequency-rank leading tokens / prefixes across the history; detect structural
  patterns (`type(scope):`, `[A-Z]+-\d+`, `#\d+`, `Fixes|Closes #…`, leading imperative verbs).
- **Domain terminology:** terms from the architecture docs (subsystem docs, glossary, ADRs) — used later to
  separate real capability vocabulary from generic English.

**LLM judgment (classify, propose — over the deterministic sample):**
- Classify the project's **commit convention** and emit a **bug-fix commit matcher** for *this* repo: the
  set of patterns/keywords that identify bug-fix commits (e.g. `{prefixes: [fix, bugfix, hotfix], refs:
  ["Fixes #"], tracker: "PROJ-\\d+"}`). This is the PRIMES "classify a commit" task, run once per repo.
- Emit a **domain glossary** (project terms) + a **noise list** (project-specific generic words to strip in
  discovery, beyond the English stopwords).

**Output (cached artifact):** `.archagent/history-profile.json` — the learned bug-fix matcher, domain
glossary, noise list, and a confidence note (how conventional the history is, reusing the hygiene metrics).
Computed once, invalidated when the history window or docs change. Both signals read it.

> Phase 0 is the concrete home for the "sample the git history and use the documentation to understand the
> terminology" requirement. It is deterministic-mine → LLM-classify → cache; no human input required.

---

## 5. Signal F — Churn × complexity hotspots

**Metric (per source file `f`, over the co-change window):**
- **churn(f)** = number of commits touching `f` (CodeScene/Tornhill "change frequency"). A **fix-churn(f)**
  variant counts only commits the Phase-0 matcher marks as bug fixes.
- **complexity(f)** = **indentation complexity** (Tornhill): tab-normalized leading-whitespace depth summed
  / averaged over non-blank lines — a language-agnostic nesting proxy — with **LOC** as a size co-factor.
  Pure Python, no per-language parser; fits archagent's polyglot reach. (Optional future upgrade: a gated
  `lizard` cyclomatic-complexity path.)
- **hotspot_score(f)** = `pctile(churn) × pctile(complexity)` in `[0,1]`. A file must be **both** churny and
  complex to score — this separates a real hotspot from a big-but-stable file or a churny-but-trivial config.

**Gating & confidence.** Needs git; reuses the history-hygiene signal — thin or bulk-heavy history →
low confidence or skip. Flag files above a percentile bar on *both* axes (default: both ≥ 75th pct);
report as a ranked list.

**Output.** New **group F (maintainability)**, regime `history`, confidence scaled by hygiene. Subjects =
the file(s); detail = churn count, fix-churn, complexity; recommendation = *"changes often and is complex —
a refactor/split candidate; check whether it's absorbing too many edge cases."* Never gates CI.

**Reconciliation with god-component.** Different granularity + evidence: god-component is *subsystem*-level
fan-in/out + size-share (regime A, static); a hotspot is *file*-level churn×complexity (regime B, history).
Complementary, no dedup; a hotspot often sits inside a god-component but needn't.

**To calibrate (experiment):** window default, the percentile bar, and whether raw-churn or fix-churn is the
better axis.

---

## 6. Signal E — Capability fragmentation

### 6.1 Concept & scope

A **capability** = a single decision/state that the design says should have **one owner**. Signal E targets
the **decision-re-implemented** shape. The **config-propagation** shape is *scoped out* into a separate,
more-deterministic signal (§8) because the raw fact ("which files read config key X") is already extracted
deterministically by `configscan` — forcing it under a fuzzy vocabulary detector would be more work and less
reliable. Decision after the experiment (§9) may merge or keep them separate.

### 6.2 Discovery (regime history — autonomous, auto-gated)

Finds *candidate* capabilities from history, with no declarations.

1. Using the Phase-0 matcher, gather subjects of **bug-fix** commits per subsystem.
2. Tokenize each subject after stripping: the convention scope (`fix(auth):` → drop `auth`), ticket/PR refs,
   English stopwords, and the Phase-0 project noise list. Keep domain-glossary terms.
3. Count token frequency across the subsystem's fix commits. Flag a token as a candidate iff it clears
   **both** an absolute count and a **share-of-fix-commits** bar, and the subsystem has enough fix commits
   to be meaningful. *(All three thresholds are placeholders to be calibrated by experiment — §9.)*
4. Emit candidate `{subsystem, token/phrase, count, share, cited commit hashes + subjects}`.
5. **LLM judgment (autonomous):** decide whether the recurring token is a real capability (a decision that
   keeps breaking) vs. an accident of English, by reading the cited commits + the code. For a confirmed
   candidate, **infer the authority** (§6.3) and **propose a `capabilities.md` row** (status `proposed`).
6. **Dedup** against already-declared capabilities so discovery doesn't re-surface known ones.

**Gating (decision: auto-gated on history hygiene — validate first).** Discovery runs only when the
Phase-0/hygiene profile clears a bar (enough conventional/bug-fix signal + fix volume); otherwise it reports
as **inactive** (via the coverage reporting already built), never silently. During the experimental phase we
may run it opt-in only; the *target* is auto-gated.

### 6.3 Enforcement (regime static — every run)

Checks *declared* capabilities (including LLM-proposed ones) on every `evaluate`.

- Parse `capabilities.md` (§7), **backtick-stripping every column** (the field-lesson bug) with a per-column
  unit test.
- **Detector** dispatched by a leading **kind keyword** so the grammar grows without a schema change:
  - **v1 `vocabulary: TOK…, [min N]`** — flag any source file **not** in `authority` and **not** in
    `exclude` that contains ≥ N tokens.
  - **next `not-calls: <authority-symbol>`** — flag files that *use* the vocabulary but never import/call the
    authority. This kills the biggest false-positive class (files that read an already-decided value) and is
    the principled fix for "displays vs. decides."
  - later: `regex:`, and possibly a config-propagation kind (or keep that in §8).
- **Authority inference (autonomous).** The authority is *mined*, not hand-declared: prefer an explicit
  claim in code/docs ("single source of truth", "canonical", "the only place"), else the definition site
  most-called by the vocabulary's consumers. The LLM judges; a human may correct later.

### 6.4 Autonomy & the optional human loop

- A pass runs end-to-end with no human input: Phase 0 → discovery → LLM proposes `capabilities.md` rows
  (`proposed`) → enforcement checks them → findings in group E.
- Humans *optionally* fine-tune afterward: promote `proposed` → `active`, adjust vocabulary/authority, add
  `exclude` globs. Nothing blocks on them.
- Confidence is always low/med; group-E findings **never** gate `--exit-code` by default.

---

## 7. `capabilities.md` — the new artifact member

A new member of the architecture artifact (parallel to `invariants.md`), parsed with the existing
`_parse_first_table` helper. **It must earn its keep (§9) before it ships.**

| Column | Meaning |
|---|---|
| ID | stable id, e.g. `CAP-STATUS` |
| Name | human name of the capability |
| Authority | file/glob (or `path::symbol`) that is the one legitimate owner |
| Detector | `<kind>: …` — v1 `vocabulary: A, B, C [min 2]` |
| Exclude | glob(s) exempt from the scan (tests, the authority's own inputs) |
| Severity | `warn` default (candidates) |
| Why | rationale + provenance (discovered vs. hand-written; cited commits) |
| Status | `proposed` (LLM-proposed) \| `active` (human-confirmed) \| `deprecated` |

Example:

```markdown
| ID | Name | Authority | Detector | Exclude | Severity | Why | Status |
|----|------|-----------|----------|---------|----------|-----|--------|
| CAP-ORDER-STATE | Order state | `src/orders/state.py::resolve` | vocabulary: pending, paid, shipped, refunded [min 2] | `tests/**` | warn | one resolver is the source of truth (see state.py docstring); recurred in 9 fix commits | proposed |
```

Parsing rules: declarations are table rows only; every column is backtick/fence-stripped; an empty/`(none)`
value is not a declaration.

---

## 8. Config-propagation — a separate, more-deterministic signal (spin-off)

The config shape is *not* a capability detector. `configscan.read_config_keys()` already extracts, per file,
which config/env keys are read — a deterministic fact. A config-propagation signal is then: *"key X is read
in files A, B, C; is there one owner threading it, or does each read it independently (risking a stale
default)?"* This is closer to a `drift`/`evaluate` deterministic check than a fuzzy vocabulary scan, so it
belongs on its own, likely with higher precision and less machinery. **Decision deferred to after the
experiment**, which will show whether it's clean enough to stand alone (expected) or better merged.

---

## 9. Experiment plan — the earn-its-keep gate (before any artifact/SPEC work)

No `capabilities.md`, SPEC section, or member ships until these probes show the signals are real. Each probe
is a throwaway script over `cochange.py` output + a grep — no new artifact.

**Probe A — Phase 0 terminology learning.** On each experiment repo, mine convention docs + subject sample,
have the LLM emit the bug-fix matcher, and check it against a hand-labeled sample of commits. *Decides:* does
learning beat the hardcoded `_CONVENTIONAL`, and on which convention styles.

**Probe B — Discovery precision.** Run the fix-commit vocabulary mining per subsystem; eyeball the top
candidate tokens. *Decides:* are recurring words real capabilities or English noise? Calibrates the three
thresholds and the noise list.

**Probe C — Enforcement precision.** Hand-pick one authority + vocabulary; run the plain `vocabulary` scan;
count the FP classes (tests, displays-not-decides, authority's own inputs). *Decides:* is vocabulary-only
usable, or do we need `not-calls` on day one?

**Probe D — Hotspots sanity.** Compute churn×complexity ranking; read the top files. *Decides:* does the
ranking surface genuinely problematic files; percentile bar; raw- vs. fix-churn axis.

**Repository properties wanted** (larger than prior test repos; ~3–4 covering these):
1. Large & long-lived (thousands of commits, hundreds of files).
2. **Convention diversity across the set** — at least one conventional-commits, one tracker/issue-ref, one
   free-form (this is what validates Phase 0 vs. hardcoding).
3. Convention documentation present (`CONTRIBUTING`, commitlint, PR template, `.gitmessage`).
4. Clear modular/subsystem structure (or existing arch docs) so files map to subsystems.
5. Domains prone to single-source-of-truth drift (status/state machines, auth/permissions, config-heavy).
6. At least one polyglot (Python + JS/TS).
7. Public/open-source, so candidates can be confirmed by reading the code.

**Success criteria (rough):** Probe B/C candidates are majority-real after LLM judgment on ≥2 repos; Phase 0
matcher agrees with hand labels on the non-conventional repos; hotspots' top-10 are defensible. Fall short →
narrow scope (e.g. hotspots-only) or redesign the detector before building the member.

---

## 10. Tooling decision (resolved) & rejected alternatives

- **Extend `cochange.py`** — chosen. Churn = per-file commit counts (we already stream `--name-only` +
  subjects); complexity = static indentation proxy on current files. Everything the signals need comes from
  git-log postprocessing + reading current files.
- **PyDriller — rejected for now.** No better *results* for our metrics (its Lizard integration is
  per-language; the indentation proxy is the validated, language-agnostic choice), not *faster* (it builds
  rich per-commit objects; raw `git log` streaming wins on large histories), no *token* savings (LLM
  judgment is downstream of mining either way). Only cost: a GitPython dependency. Revisit only if we need
  diff-level line churn or true cyclomatic complexity — and then likely via a narrow `lizard` add-on, not
  PyDriller.
- **Code Maat — rejected.** Unmaintained + JVM dependency. Use Tornhill's *formulas* as reference only.

---

## 11. Build order & rollout

0. **Experiments (§9)** — gate. Calibrate thresholds; confirm the member earns its keep.
1. **`cochange.py` substrate** — per-file churn/fix-churn; the indentation complexity function; Phase-0
   profile (matcher + glossary + cache).
2. **Signal F — hotspots** (group F). Small, no new artifact; ships first.
3. **Signal E — enforcement** (group E static): `capabilities.md` + `vocabulary` detector; SPEC section +
   `_TEMPLATE`.
4. **Signal E — discovery** (group E history, auto-gated) + autonomous authority inference + `proposed` rows.
5. **`not-calls` detector** + **config-propagation** spin-off (§8), per experiment findings.
6. **Skill updates**: `/archagent-evaluate` reads the new findings; explains group-E/F candidates; drives
   the optional human fine-tune.

---

## 12. Non-goals

- **No required human declaration.** The system proposes; humans optionally fine-tune (§6.4).
- **No hardcoded commit vocabulary.** Learned per project (§4).
- **No CI gating by default** for group E/F (candidates, not verdicts).
- **No heavy git-mining dependency** (§10).
- **Not semantic clone detection / call-graph dataflow** in v1 — vocabulary co-occurrence first, `not-calls`
  next; true dataflow is a later, separate escalation.
- **Not Conway's-Law / author mining** — a parked stretch idea (needs `git log --format=%ae`), out of scope
  here.
