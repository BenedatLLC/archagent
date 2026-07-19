# archagent: describe — build or update the architecture artifact

Produce or update the `architecture/` artifact for THIS repo so it accurately describes the
system and protects it with checkable invariants. Work incrementally — do not document
everything at once.

**One-time setup.** If the repo's top-level agent instructions (`CLAUDE.md`, or a root `AGENTS.md`)
don't yet reference `architecture/AGENTS.md`, offer to add a short **additive** pointer to it — ask
the user first, and never overwrite their existing content.

## Principles
- **Use the index files to find the docs.** Start from `README.md` and the agent-instruction files
  (`AGENTS.md`, `CLAUDE.md`, root and nested) — they usually point to where the real documentation lives
  (a `designs/` / `rfcs/` / `spec/` directory, a docs site, ADRs). Enumerate those locations before reading;
  don't rely on what you happen to know.
- **Trust but verify existing docs — and flag divergence.** Read the README, design/spec docs, ADRs, and
  module docstrings for the intended abstractions and the *why*, treating each as a **hypothesis** to
  confirm against the code. Record contradictions as drift — and where the *documented intended architecture*
  (its layering, boundaries, topology) has **significantly diverged** from what the code actually does, call
  that out prominently: it's either a real defect or a stale design, and it's the highest-value thing to
  surface.
- **The deterministic tools are your eyes, not your guess.** Use `ast-grep` and `rg` (ripgrep) to
  find real structure (imports, components, call sites, patterns). Do not infer topology from memory.
- **Go top-down at scale.** First map packages/modules and their dependencies, carve the system into
  subsystems, *then* write one doc per subsystem. Never write a single flat document.
- **Write for a junior engineer and an agent.** Purpose before mechanism; define jargon; self-contained
  sections; ground each claim in a real file path; cut what the code already says. Keep the constitution
  terse; put the narrative in subsystem docs.

## Steps
1. **Survey — locate and read the intent sources.** From the index files (README, `AGENTS.md`, `CLAUDE.md`),
   find where documentation lives, then **enumerate any design/spec directories** (`designs/`, `design/`,
   `rfcs/`, `adr/`, `adrs/`, `spec/`, `specs/`) and list their files — don't skip them. Read the docs
   relevant to each subsystem as *intended-architecture hypotheses*. Note the repo's **documentation
   conventions** (where design docs live, how they're named/organized) to record in the constitution.
   List candidate subsystems.
2. **Extract structure deterministically** (confirm or correct the doc-derived picture):
   - Python: imports/packages/entrypoints (e.g. `ast-grep -p 'import $$$' -l py`, `rg`).
   - JS/TS: modules, imports, React component boundaries.
3. **Per subsystem**, write `architecture/subsystems/<name>.md` across the six dimensions: process
   topology & components · key abstractions/patterns · state & tiering · lifecycles (Mermaid
   `stateDiagram` + caption) · key flows (Mermaid `sequenceDiagram` + caption) · invariants. Cite real
   files. Record provenance (doc vs code) and mark anything unverified. Fill the doc's metadata lines —
   `**Covers:**`, `**Connects:**` (subsystems this one connects to, each typed by connector kind — `import`
   / `sync-call` / `async-event` / `shared-data` / `pipe`), and where they apply `**Service:**` (deployment
   service) and `**Tier:**` (layer, e.g. `ui` / `domain` / `infra`) — so `drift` and `evaluate` have the
   inputs they need. Getting the connector *kind* right matters: it's how `evaluate` tells a distributed
   monolith (a synchronous service cycle) from a benign event-coupled one.
4. **Fill `architecture/constitution.md`** (terse, always-loaded): conventions, the patterns the system
   relies on, how to work here. Include the repo's **documentation conventions** — where design/spec docs
   live (e.g. `designs/`), how they're named and organized, and how to keep them in sync — so future
   `describe`/`drift` runs (and other agents) know where the intent is written down.
4b. **Fill `architecture/deployment.md`**: the deployment view (services/runtimes/infra, from
   `docker-compose.yml` / k8s / `Procfile`) and the **Configuration** — list the env keys the system reads
   under `**Config:**` (or maintain a `.env.example`). Consider a config-access boundary invariant. If the
   system is a single process with no IaC, **omit `**Services:**`** and describe the runtime in prose (see
   Metadata field rules below).
5. **Capture invariants** in `architecture/invariants.md` (the table). Prefer checkable rules:
   - BOUNDARY (layering / forbidden deps) → `forbid <a> -> <b>`
   - STRUCTURAL (banned code shape) → `forbid-pattern <ast-grep pattern>`
   Choose Tier + Severity and link an ADR in `decisions/` for the *why*. **Every invariant is a row in the
   table** — including ones you can only describe in prose today and ones the code would fail right now.
   Give those **Tier `prose`**: they stay documented and greppable in one place but are never generated or
   run (`gen`/`check` skip `prose` rows), so put the eventual `forbid`/`forbid-pattern` in the Rule column
   (or a short description) and graduate it later. **Don't write invariants as loose prose bullets outside
   the table.** Note: **any row with a real rule and Tier `structural`/`pbt` is enforced** regardless of
   `Status` (except `deprecated`) — `Status: proposed` does *not* stop enforcement; only Tier `prose` does.
5b. **Mine invariants already stated in the docs and code.** A big part of the value here is enforcing the
   rules the team *already wrote down* but never checked. Don't rely on noticing them by luck — actively
   enumerate:
   - **In code** — grep for explicit markers: `rg -n 'INVARIANT|@invariant|Invariant:' src/`, plus
     assertion messages (`assert …, "…"`) and contract decorators (`@require`/`@ensure`, icontract/deal).
   - **In docs** — grep the design/spec docs for **normative/modal language**:
     `rg -niE 'must not|must |shall|always|never|only .* (may|can)|is guaranteed to|must be sorted'`.
     (Modal language is noisy — treat these as *candidates*, not facts.)
   For each candidate, **classify** it into the DSL: a layering/dependency rule → BOUNDARY `forbid`; a code
   shape → STRUCTURAL `forbid-pattern`; a behavioral/data rule ("the query set is always sorted", "state
   resets each session") → a PBT `property`; otherwise a prose row. Then **curate by risk**:
   - **Every stated invariant becomes at least a cited prose row** (Tier `prose`, source path:line in `Why`)
     — capture it; nothing written down should be lost.
   - **Promote to an active, enforced rule only after** (a) `check` **passes** and (b) the rule is
     **not vacuous** — a `forbid-pattern` that matches *zero* sites enforces nothing (confirm the match count
     with `rg`/`ast-grep`), and (c) you've confirmed the drafted rule **actually means what the source said**
     (`check` proves the code complies, not that the rule is faithful). Present the promotable rules as a
     batch for a yes/no, rather than silently inserting them.
   - **A stated invariant the code *violates* is drift** — the design says X, the code doesn't do X. Surface
     it (as a `proposed` prose row + a drift note), don't bury it. This is often the most valuable finding.
   Record provenance: mark each invariant design-sourced vs code-inferred so later runs can re-verify it
   against the original intent.
6. **Validate.** Run `archagent gen`, then `archagent check`. Confirm each new invariant parses and flags
   what it should (try a quick local violation if unsure). Fix or refine.
7. **Evaluate health.** Run `archagent evaluate` (the `evaluate` skill judges the candidates). For each
   confirmed *system-level* smell, decide with the team: change the design, or accept it and record why.
   Turn accepted fixes into an ADR under `decisions/` and — where enforceable — a `check` invariant so it
   can't regress. This is how `evaluate` feeds back into the artifact and the enforcement tier.
   *Expect some candidates to be dismissible:* a shared kernel/`foundation` that every layer depends on will
   always show `layer-skip`, and flat peer capabilities under one orchestrator show skips whenever the
   orchestrator calls a capability directly — both are correct. Consider modelling flat peer subsystems as a
   single `domain` tier rather than forcing a strict `ui → app → domain → infra` ladder.
8. **Index + log.** Update `architecture/index.md` and append a line to `architecture/log.md`.

First pass: the top-level map, 1–3 subsystems, and the highest-value invariants. Then iterate.

## Metadata field rules (keep drift quiet)

The `**Field:**` lines are parsed and tokenised, so a few rules avoid phantom drift:
- **Omit a field entirely when it has no value.** Never write `none`, `n/a`, or a sentence as the value —
  it gets split into fake declarations. A leaf subsystem with no outgoing edges simply has no `**Connects:**`
  line. Same for `**Service:**`, `**Services:**`, `**Config:**`.
- **`**Covers:**` matches source-code files only** (`.py`, `.ts`, …). Data files (prompt `.md`, fixtures,
  SQL, config) can't be Covered — describe them in prose. (A glob that matches only data files is accepted
  and not flagged, but contributes no code coverage.)
- **No service topology → no `**Services:**`.** For a single-process app (a CLI, a library, one process)
  with no `docker-compose`/`Procfile`/k8s, omit `**Services:**` and describe the process in prose. A
  declared service with no IaC is reported as *dangling* forever.
- **Incremental first pass vs undocumented-module drift.** As soon as any subsystem declares `**Covers:**`,
  `drift` reports every *un*-covered source module as "undocumented". That's expected while iterating —
  treat it as a to-do list, or give every module a (possibly stub) `**Covers:**` so drift stays quiet.
- **Declarations must use the bold `**Field:**` form** and live outside fenced code blocks; a plain word at
  a line start, or a Mermaid node, is not parsed as a declaration.

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
  - **undeclared dependency** — a subsystem imports another it doesn't declare: add it to `Connects`
    (if the coupling is intended) or remove the import (if it isn't).
  - **stale dependency / undocumented entry point / undocumented route** — a `Connects` `import`-kind edge
    with no matching import, a `[project.scripts]`/`package.json bin` command absent from the docs, or a web
    route not in the OpenAPI spec/docs: fix the declaration, or document the entry point / route.
  - **undocumented / dangling config** — an env key read in code but not in the manifest (add it to
    `architecture/deployment.md`'s `**Config:**` or `.env.example`), or a declared key never read (remove it).
  - **undocumented / dangling service** — a service in IaC (docker-compose/Procfile/k8s) not in the
    deployment view's `**Services:**` (add it), or a declared service no longer deployed (remove it).
  - **missing / extra deployment edge** — the code depends across services (via subsystem `**Service:**`
    mappings) that `docker-compose depends_on` doesn't wire (add the `depends_on` — likely a runtime bug),
    or a `depends_on` with no matching code dependency (remove it or record why).
  - **connector-kind mismatch** — a `**Connects:** X via async-event` the code contradicts (it makes a
    blocking HTTP call to X). The doc claims a decoupling the code doesn't have: fix the connector kind, or
    change the code to actually be asynchronous.
- **Verify, don't rewrite.** Re-check each existing claim and invariant against the *current* code. Leave
  what still holds; only change what moved.
- **Re-mine intent, flag divergence.** Re-read the design/spec docs (new ones may have appeared) and re-mine
  stated invariants (step 5b) into the table. Where the *documented intended architecture* has significantly
  diverged from the code, surface it prominently — decide whether the code or the doc is wrong.
- **Declare coverage, connectors, tier & service.** Give each `subsystems/<name>.md` a `**Covers:** <glob>`
  and a `**Connects:** <subsystem> via <kind>, …` line (kinds: `import` / `sync-call` / `async-event` /
  `shared-data` / `pipe`; so `drift` checks import staleness + topology and `evaluate` can judge coupling),
  plus `**Tier:**` and `**Service:**` where they apply (layering + per-service data ownership).
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
