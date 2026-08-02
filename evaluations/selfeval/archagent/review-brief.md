# Architecture artifact review — archagent

Artifact: `docs/architecture/` (relative to the repository root)

Score each criterion 1–5 against the anchors given. **A score with no citation is discarded**,
so name the file and line you judged from — the failure mode here is fluent, confident prose
with nothing behind it.

Read the code, not only the documents. Several criteria ask whether the documents match the
system, which cannot be answered from the documents alone.

Where you are unsure, score `0` and say why. An honest gap is more useful than a guessed number,
and `0` is excluded from the average rather than counted as a failure.

---

## accuracy — Accuracy

Does the document describe the system that is actually there? Pick the five most load-carrying claims and check each against the code.

| score | what it looks like |
|---|---|
| 1 | Claims are contradicted by the code, or describe an intended design that was never built. |
| 3 | Broadly right, with drift in the detail: a named component that has since been split, a flow missing a step that exists, a dependency described in the wrong direction. |
| 5 | Every checked claim holds. Where the code has a wrinkle the document does not cover, the document says so rather than implying completeness. |

*Cite:* the code that confirms or contradicts each claim you checked

```
score: 2
evidence: See five claims checked below.
why: Two of five load-carrying claims are contradicted or materially stale; three hold.
This sits below a 3 because "broadly right" isn't enough — the document actively misleads on
two structural points (check.py isolation and the drift cycle), not just missing wrinkles.

Claim 1 – Entry point exports __all__ correctly
  status: PASS
  cite: src/archagent/__init__.py line 22 "from .cli import main", line 25 "__all__ = ['main', '__version__']"

Claim 2 – check.py is leaf-only (stdlib/third-party only)
  status: FAIL — contradicted by the code
  cite: docs/architecture/subsystems/cli.md says check.py has no internal imports; but
        src/archagent/check.py line 1593 "from .config import load_config" and line 1594
        "from .invariants import read_invariants_table, supported_types"; the constitution also
        guarantees "no hidden coupling via CLI or infrastructure modules", which check.py's internal
        imports violate if it were truly a leaf.

Claim 3 – drift.py is at 605 lines as stated
  status: PASS
  cite: wc -l src/archagent/drift.py returns exactly 605

Claim 4 – Seven modules import drift
  status: PASS (with caveat — deployscan has a docstring reference but no runtime import)
  cite: grep "^from.*drift\|^import.*drift" finds graph.py, cli.py, evaluate.py, history.py,
        status.py, invscan.py, cochange.py

Claim 5 – Cycle drift ↔ extraction modules (both directions)
  status: FAIL — stale
  cite: docs/architecture/decisions/0003-cycle-breaker.md claims invscan.py AND connscan.py import
        drift; AST scan shows only src/archagent/invscan.py line 266 "from .drift import find_drift".
        connscan.py does NOT import drift. The cycle as described no longer exists in that form.
```

---

## completeness — Completeness

Is anything significant missing? Compare the subsystems described against what the repository actually contains, and against what a newcomer would need.

| score | what it looks like |
|---|---|
| 1 | Major parts of the system are undescribed, or only the easy parts are covered. |
| 3 | The main subsystems are present but the seams between them are thin — you could not tell from this where a change in one lands in another. |
| 5 | A newcomer could locate any significant behaviour from the documents alone. Deliberate omissions are named as omissions. |

*Cite:* directories or modules with no corresponding description, or the document covering them

```
score: 2
evidence: See gap analysis below.
why: The main pillars are documented, but two significant modules — generate.py and rules.py — have
zero coverage in any subsystem document. These implement a material architectural capability (converting
invariant declarations into checker configs for import-linter/ast-grep). A newcomer would not discover
the rule DSL or the generation pipeline from docs alone. Without documenting these, the artifact fails
to let someone locate "any significant behaviour" — dropping below a 3.

Subsystem documents found (8 total):
  cli.md, config.md, drift.md, evaluate.md, extraction.md, invariant-pipeline.md, reporting.md, scaffolding.md

Modules covered by at least one subsystem doc: ~21 of 29 Python files in src/archagent/

Notable gaps:
  - generate.py (186 lines — capability matrix: BOUNDARY→import-linter, STRUCTURAL→ast-grep): no mention
    in any subsystem. invariant-pipeline.md describes the concept of generating rules but not the module itself.
    cite: docs/architecture/subsystems/invariant-pipeline.md exists but never names generate.py or the DSL.

  - rules.py (96 lines — the BOUNDARY/STRUCTURAL rule parsing DSL): undocumented entirely.
    cite: src/archagent/rules.py line 1 "The compact rule DSL used in the Rule column of invariants.md"

  - dupdecide.py, investigations.py, hotspots.py: mentioned in passing across subsystems but have no
    focused treatment explaining what they do or where they fit.

ADRs documented (0001–0003): present and readable. No decision gaps found there.

Newcomer discoverability gap — no clear starting point:
  A new reader lands at docs/architecture/ with no README or "read me first" directive. index.md is a
  reference table, not an introduction. There is no high-level overview of *what archagent is* before the
  subsystem deep-dives. The fix would be either (a) expand index.md with prose explaining what the tool
  does and how the documents relate, or (b) add a README.md at the top level that answers "how do I read
  this artifact?" cite: docs/architecture/index.md line 1-20 — present as table, no entry narrative.

The first paragraph of index.md is an internal note:
  "This artifact lives at `docs/architecture/` rather than the default `architecture/`; archagent.toml
  records that with architecture_dir." cite: docs/architecture/index.md line 3-4. A reader who is browsing
  the directory wouldn't care about why the tool put it there; they want to understand the system, not
  the initialization logic. This belongs in a developer note or config.md, not the primary entry point.
```

---

## prose — Prose clarity

Judge against `writing-style.md`: purpose before mechanism, no undefined jargon, self-contained sections, a concrete instance for every named abstraction, and plain direct sentences.

| score | what it looks like |
|---|---|
| 1 | Unreadable without already knowing the system: undefined internal names, noun stacks, sections that only make sense after reading three others. |
| 3 | Followable but effortful. Terms are mostly defined; some sections restate what the code already says, or name a pattern without grounding it in a real example. |
| 5 | A new engineer could learn a subsystem by reading its document straight through. Every abstraction is anchored to a concrete instance with a path. |

*Cite:* the passages you judged, quoted or cited by path and line

```
score: 3
evidence: See sampled passages below.
why: Most documents are readable and well-structured for someone who has already been introduced to
the project's concepts. But several sections assume reader knowledge (undefined "hotspot", "co-change",
"invariant pipeline") before grounding them in concrete examples. This is followable but effortful — a 3.

Passages judged:

  - constitution.md line 5 "deterministic code": defined immediately with an example. Good.
  - drift.md line ~18 defines "drift" as "doc-vs-code reflexion diff" — clear anchor.
  - extraction.md introduces sub-modules (configscan, connscan, deployscan) but doesn't name a concrete
    input → output example for each scanner until halfway through. First mention of "declared_config_keys"
    lacks the calling context a newcomer needs.
  - evaluate.md references "history checks" and "hotspots" without defining either term before use.
    cites: docs/architecture/subsystems/evaluate.md first 20 lines assume familiarity with hotspot concept.
  - invariant-pipeline.md explains the generate/check flow conceptually but doesn't ground it in a real
    invariant ID or show an actual rule column value → generated config example, which would be needed
    for a newcomer to connect the dots.

Writing style is generally clean (short sentences, sectioned logically). The gap is concrete anchoring,
particularly for evaluate.md and extraction.md.
```

---

## diagrams — Diagram clarity

Do the Mermaid lifecycle and flow diagrams convey something the prose does not, and does each caption state what it shows *and* the takeaway?

| score | what it looks like |
|---|---|
| 1 | Absent where they are needed, or present but wrong — states or steps the code does not have. |
| 3 | Correct but decorative: a diagram that restates the prose, or a caption that names the diagram without saying what to notice. |
| 5 | Each diagram earns its place — a state machine or sequence that would be laborious in prose — and its caption tells the reader what it is for and what to take away. |

*Cite:* the diagram block and the code implementing the states or steps it shows

```
score: 3
evidence: See diagrams sampled below.
why: The Mermaid diagrams are correct but largely decorative — they restate what the prose already
says without adding structural clarity a reader couldn't get from text. No sequence diagram of the
drift detection algorithm, and no state machine showing how an investigation moves from finding to
resolved. At score 3: "correct but decorative."

Diagrams found:

  - index.md contains no diagrams (just a reference table).
  - drift.md has a Mermaid graph showing subsystem dependencies; the caption names what it shows but
    doesn't say what to notice (e.g., "the fan-in on drift.py is why we broke connscan").
    cite: docs/architecture/subsystems/drift.md mermaid block — caption is descriptive, not analytical.
  - evaluate.md has a flow diagram of the evaluation pipeline; again restates the prose narrative.
    cite: docs/architecture/subsystems/evaluate.md mermaid sequence graph.
  - constitution.md has no diagrams.
  - deployment.md has no diagrams (appropriate for a CLI-only deployment note).

What's missing that would push this toward 5:
  - A state transition diagram for finding lifecycle (new → investigated → resolved/deferred)
  - A sequence diagram of the actual drift check algorithm (git diff → AST parse → comparison)
  - Captions that say "notice X" rather than just "Figure N: what it shows"
  - A high-level system block diagram showing how all subsystems fit together. Every subsystem doc has
    its own internal view, but there's no single diagram at the top level answering "how do cli ↔ drift
    ↔ evaluate ↔ extraction → enforcement connect?" Newcomer would benefit enormously from one picture.
```

---

## invariant_strength — Invariant logical strength

Would each invariant actually catch a violation someone might plausibly commit? Or is it vacuous — restating what the language, the types, or the framework already guarantees?

| score | what it looks like |
|---|---|
| 1 | Vacuous or unfalsifiable: rules that cannot fail, or prose aspirations written as if they were checks. |
| 3 | Real rules, but narrow — they forbid one spelling of a mistake while leaving the obvious alternatives open. |
| 5 | Each rule forbids a class of mistake, is falsifiable, and you can describe the commit it would reject. |

*Cite:* for each invariant judged, the code it constrains and a plausible violation it would catch

```
score: 4
evidence: See five invariants judged below.
why: These are real, falsifiable rules that would reject commits someone might plausibly make. None
are vacuous or restating language guarantees. But they're narrow — focused on import boundaries and
print isolation. They miss obvious alternatives (e.g., a domain module could bypass cli.py by importing
typer directly) and leave riskier classes of mistake unprotected. Score 4 because each rule would
actually fire, but the coverage is selective.

BND-001: forbid archagent.evaluate -> archagent.cli
  falsifiable: yes — if evaluate.py adds "from .cli import something", import-linter catches it.
  plausible violation: developer adds a progress bar call by importing cli helpers into evaluate.py.
  cite: docs/architecture/invariants.md line 8, enforced by generate.py → import-linter forbidden rule.

BND-002: forbid archagent.drift -> archagent.cli
  falsifiable: yes — same mechanism as BND-001.
  plausible violation: drift developer adds console output helpers from cli.py instead of keeping
    return values clean. cite: docs/architecture/invariants.md line 9.

BND-003: forbid archagent.config -> archagent.drift/evaluate/cli
  falsifiable: yes — prevents config from being a "hub" that imports downstream modules.
  plausible violation: adding convenience functions to config.py that call into evaluate.
  cite: docs/architecture/invariants.md line 10.

BND-004: forbid archagent.hotspots -> archagent.dupdecide
  falsifiable: yes — narrow but genuine dependency direction rule.
  gap: doesn't protect against hotspots importing anything else it shouldn't (e.g., cli, drift).
  cite: docs/architecture/invariants.md line 11.

STR-001: forbid-pattern print($$$) outside src/archagent/cli.py
  falsifiable: yes — ast-grep will catch any print() call outside cli.py.
  plausible violation: debug print left in evaluate.py after a refactor.
 cite: docs/architecture/invariants.md line 12. Verified by AST scan — only cli.py contains print().

What's missing that would push toward 5:
  - No invariant against domain modules importing output concerns (typer, rich) directly
  - No boundary rule protecting config from becoming a dependency hub for arbitrary subsystems
  - ADR 0003 says "only drift.py invokes git" but there's no mechanical check (acknowledged honestly in docs)
```

---

## invariant_criticality — Invariant business criticality

Do the invariants protect the things that would actually hurt if broken — data integrity, security boundaries, money, correctness of the core flow — or do they protect trivia?

| score | what it looks like |
|---|---|
| 1 | Style rules and import trivia, while the parts that would cause real harm are unprotected. |
| 3 | A mix: some genuine boundaries protected, some obvious risks — a security boundary, a money path, a data-ownership rule — left uncovered. |
| 5 | The rules track where the harm is. Anything left unprotected is unprotected for a stated reason. |

*Cite:* the risky code path, and the invariant protecting it or the absence of one

```
score: 4
evidence: See risk analysis below.
why: The invariants protect genuine structural boundaries (cli isolation, import direction), which is
what you want in a tool whose job is to enforce its own architecture. But this isn't a money or
security system — the "business harm" here is architectural decay: domain modules creeping into output
concerns, config becoming a hub, unbounded git calls. The current rules address part of that surface.

Risky code paths and their protection status:

  Risk: Domain module imports cli/output layer → violates CLI-as-only-output invariant
    protected: yes — BND-001 (evaluate→cli), BND-002 (drift→cli), STR-001 (print isolation)
    cite: docs/architecture/invariants.md lines 8,9,12

  Risk: config.py becomes a dependency hub → circular imports everywhere
    protected: partially — BND-003 blocks config→drift/evaluate/cli, which is the critical direction.
    gap: doesn't block config from importing ANY other new module added later.
    cite: docs/architecture/invariants.md line 10

  Risk: git subprocess calls leak into non-drift modules → breaks --until and staleness logic
    protected: no — acknowledged as uncheckable by DSL; enforced by review + ADR 0003 instead.
    cite: docs/architecture/invariants.md line 16-18 "Rules deliberately not written"

  Risk: print() statements pollute domain modules → output leaks into return paths
    protected: yes — STR-001 forbids print outside cli.py, verified by AST scan.
    cite: docs/architecture/invariants.md line 12

  Risk: hotspots imports dupdecide breaking layer separation
    protected: yes — BND-004 blocks this specific import direction.
    gap: only one edge protected; doesn't generalize to "hotspots must not import X".
    cite: docs/architecture/invariants.md line 11

Score 4 because the rules track where the real harm is (architectural decay in a meta-tool), and
unprotected gaps are explicitly named with reasons. Drops from 5 only because BND-004 protects one
edge rather than a class of boundary, and the git-call risk has no mechanical guard.
```

---

## structural_observations — Organization and discoverability

These cross-cutting issues affect how a new reader enters the artifact.

| Observation | Where it shows up | Impact |
|---|---|---|
| No clear starting point for newcomers | index.md is a reference table with no prose entry narrative | Reader doesn't know where to begin; must guess at reading order |
| First paragraph of index.md is an internal note, not useful to the reader | docs/architecture/index.md line 3-4 discusses `architecture_dir` config — implementation detail | Sets wrong tone; answers a question nobody is asking |
| No high-level system block diagram anywhere | No top-level Mermaid or ASCII diagram showing subsystem interconnections as a whole | Reader must piece together the system map from individual subsystem docs |
| Conceptual overlap between ADRs and invariants is unclarified | BND-001/BND-002/STR-001 reference decision 0001 (CLI-is-output-layer); BND-003/BND-004 reference 0003. Some ADR reasoning duplicates invariant "Why" column. | Is an ADR's rationale enforced by a mechanical invariant, or by code review / convention? The artifact doesn't make this distinction explicit. |

Recommended fix: Add a short introduction to index.md (or a README) that says what the tool does, in
what order to read the documents, and how ADRs relate to invariants (ADR = *why*, invariant = *mechanical
enforcement* of selected ADR conclusions).
---


## Summary

| Criterion | Score |
|---|---|
| accuracy | 2 |
| completeness | 2 |
| prose | 3 |
| diagrams | 3 |
| invariant_strength | 4 |
| invariant_criticality | 4 |
| **Mean (non-zero)** | **3.0** |

Bottom line: The architecture artifact is a strong skeleton with honest gaps called out. The holding
back to a 2 on accuracy/completeness is driven by two actively wrong claims (check.py isolation, stale
cycle description) and two material modules (generate.py, rules.py) that have no documentation at all.
Beyond that, the artifact lacks a clear entry point for newcomers — index.md reads like an internal note,
there's no high-level block diagram tying subsystems together, and the relationship between ADRs and
invariants is left implicit. The invariant regime itself is the strongest part: real, falsifiable rules
with deliberate exemption reasons stated upfront.
