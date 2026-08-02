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
score:
evidence:
why:
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
score:
evidence:
why:
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
score:
evidence:
why:
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
score:
evidence:
why:
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
score:
evidence:
why:
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
score:
evidence:
why:
```

---
