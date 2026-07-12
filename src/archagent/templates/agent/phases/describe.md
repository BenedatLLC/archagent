# archagent: describe — build or update the architecture artifact

Produce or update the `architecture/` artifact for THIS repo so it accurately describes the
system and protects it with checkable invariants. Work incrementally — do not document
everything at once.

**One-time setup.** If the repo's top-level agent instructions (`CLAUDE.md`, or a root `AGENTS.md`)
don't yet reference `architecture/AGENTS.md`, offer to add a short **additive** pointer to it — ask
the user first, and never overwrite their existing content.

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
   files. Record provenance (doc vs code) and mark anything unverified. Fill the doc's metadata lines —
   `**Covers:**`, `**Depends-on:**`, and where they apply `**Service:**` (deployment service) and `**Tier:**`
   (layer, e.g. `ui` / `domain` / `infra`) — so `drift` and `evaluate` have the inputs they need.
4. **Fill `architecture/constitution.md`** (terse, always-loaded): conventions, the patterns the system
   relies on, how to work here.
4b. **Fill `architecture/deployment.md`**: the deployment view (services/runtimes/infra, from
   `docker-compose.yml` / k8s / `Procfile`) and the **Configuration** — list the env keys the system reads
   under `**Config:**` (or maintain a `.env.example`). Consider a config-access boundary invariant.
5. **Capture invariants** in `architecture/invariants.md` (the table). Prefer checkable rules:
   - BOUNDARY (layering / forbidden deps) → `forbid <a> -> <b>`
   - STRUCTURAL (banned code shape) → `forbid-pattern <ast-grep pattern>`
   Choose Tier + Severity and link an ADR in `decisions/` for the *why*. Invariants you can't yet express
   as a rule: record them as prose in the subsystem doc and mark Tier `prose`.
6. **Validate.** Run `archagent gen`, then `archagent check`. Confirm each new invariant parses and flags
   what it should (try a quick local violation if unsure). Fix or refine.
7. **Evaluate health.** Run `archagent evaluate` (the `evaluate` skill judges the candidates). For each
   confirmed *system-level* smell, decide with the team: change the design, or accept it and record why.
   Turn accepted fixes into an ADR under `decisions/` and — where enforceable — a `check` invariant so it
   can't regress. This is how `evaluate` feeds back into the artifact and the enforcement tier.
8. **Index + log.** Update `architecture/index.md` and append a line to `architecture/log.md`.

First pass: the top-level map, 1–3 subsystems, and the highest-value invariants. Then iterate.

## Updating an existing artifact (re-running describe)

If `architecture/` already has content, you are **updating**, not starting over. Run this at
design-review time (does a proposed design fit the architecture?) and periodically as the code changes:
- **Start from the diff.** Run `archagent drift` (`--json` for a machine-readable work-list) and resolve
  each item instead of re-reading everything:
  - **dangling reference** — the doc names code that's gone: fix the reference, or delete the stale claim.
  - **possibly stale** — the subsystem's covered code changed after the doc: re-verify that section
    against the current code and update what moved.
  - **undocumented module** — code owned by no subsystem's `Covers`: document it under the right subsystem
    (extend a `**Covers:**` glob), or leave it if it's intentionally out of scope.
  - **undeclared dependency** — a subsystem imports another it doesn't declare: add it to `Depends-on`
    (if the coupling is intended) or remove the import (if it isn't).
  - **stale dependency / undocumented entry point / undocumented route** — a `Depends-on` with no
    matching import, a `[project.scripts]`/`package.json bin` command absent from the docs, or a web route
    not in the OpenAPI spec/docs: fix the declaration, or document the entry point / route.
  - **undocumented / dangling config** — an env key read in code but not in the manifest (add it to
    `architecture/deployment.md`'s `**Config:**` or `.env.example`), or a declared key never read (remove it).
  - **undocumented / dangling service** — a service in IaC (docker-compose/Procfile/k8s) not in the
    deployment view's `**Services:**` (add it), or a declared service no longer deployed (remove it).
  - **missing / extra deployment edge** — the code depends across services (via subsystem `**Service:**`
    mappings) that `docker-compose depends_on` doesn't wire (add the `depends_on` — likely a runtime bug),
    or a `depends_on` with no matching code dependency (remove it or record why).
- **Verify, don't rewrite.** Re-check each existing claim and invariant against the *current* code. Leave
  what still holds; only change what moved.
- **Declare coverage, dependencies, tier & service.** Give each `subsystems/<name>.md` a `**Covers:** <glob>`
  and `**Depends-on:** <subsystems>` line (so `drift` checks staleness + topology), plus `**Tier:**` and
  `**Service:**` where they apply (so `evaluate` can check layering and per-service data ownership).
- **Flag drift.** Where a doc or invariant disagrees with the code, surface it and decide: fix the code,
  or update the doc/invariant (with an ADR if it's a real decision) — don't silently overwrite intent.
- **Refresh what changed.** Update the affected `subsystems/<name>.md` and reconcile the invariants table
  (add rules for new boundaries; retire rules for removed ones).
- **Evaluate the architecture's health.** Beyond doc-vs-code drift, run `archagent evaluate` for
  *system-level smells* (god components, cycles, shotgun surgery, shared persistence, leaky layering).
  These are not record fixes — each confirmed one is a design decision: change the structure, or accept it
  with an ADR. Graduate the fixes you want to hold into `check` invariants (`/archagent-evaluate` does the
  judging, clustering, and prioritizing).
- **For a new design:** describe the proposed design first, check it against the existing architecture and
  invariants, and **run `archagent evaluate` to catch smells the change would introduce** — before it's
  built. Only update the artifact to match once it's built.
- **Record it:** append a line to `architecture/log.md` and add/adjust ADRs in `architecture/decisions/`.
