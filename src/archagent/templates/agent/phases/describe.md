# archagent: describe — build or update the architecture artifact

Produce or update the `architecture/` artifact for THIS repo so it accurately describes the
system and protects it with checkable invariants. Work incrementally — do not document
everything at once.

## Principles
- **Trust but verify existing docs.** Read the README, `docs/`, ADRs, and module docstrings for
  the intended abstractions and the *why* — but treat every claim as a hypothesis and confirm it
  against the code before recording it. Note contradictions as drift.
- **The deterministic tools are your eyes, not your guess.** Use `ast-grep` and `rg` (ripgrep) to
  find real structure (imports, components, call sites, patterns). Do not infer topology from memory.
- **Go top-down at scale.** First map packages/modules and their dependencies, carve the system into
  subsystems, *then* write one doc per subsystem. Never write a single flat document.
- **Write for a junior engineer and an agent.** Purpose before mechanism; define jargon; self-contained
  sections; ground each claim in a real file path; cut what the code already says. Keep the constitution
  terse; put the narrative in subsystem docs.

## Steps
1. **Survey.** Read existing docs and the top-level layout. List candidate subsystems.
2. **Extract structure deterministically** (confirm or correct the doc-derived picture):
   - Python: imports/packages/entrypoints (e.g. `ast-grep -p 'import $$$' -l py`, `rg`).
   - JS/TS: modules, imports, React component boundaries.
3. **Per subsystem**, write `architecture/subsystems/<name>.md` across the six dimensions: process
   topology & components · key abstractions/patterns · state & tiering · lifecycles (Mermaid
   `stateDiagram` + caption) · key flows (Mermaid `sequenceDiagram` + caption) · invariants. Cite real
   files. Record provenance (doc vs code) and mark anything unverified.
4. **Fill `architecture/constitution.md`** (terse, always-loaded): conventions, the patterns the system
   relies on, how to work here.
5. **Capture invariants** in `architecture/invariants.md` (the table). Prefer checkable rules:
   - BOUNDARY (layering / forbidden deps) → `forbid <a> -> <b>`
   - STRUCTURAL (banned code shape) → `forbid-pattern <ast-grep pattern>`
   Choose Tier + Severity and link an ADR in `decisions/` for the *why*. Invariants you can't yet express
   as a rule: record them as prose in the subsystem doc and mark Tier `prose`.
6. **Validate.** Run `archagent gen`, then `archagent check`. Confirm each new invariant parses and flags
   what it should (try a quick local violation if unsure). Fix or refine.
7. **Index + log.** Update `architecture/index.md` and append a line to `architecture/log.md`.

First pass: the top-level map, 1–3 subsystems, and the highest-value invariants. Then iterate.
