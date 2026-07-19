# archagent — Roadmap

Planned future work, grouped by theme so it's easy to skim and pick up the highest-value item at any
given time. This is a **roadmap, not a schedule** — items are independent, expect to skip around. Check
a box (`- [x]`) when something ships; once a cluster is done we can summarize it into a release.

Rationale and design detail for most items live in `~/research/architecture-agent/` — start with
`PLAN.md` (the phased arc), then `evaluate-design.md`, `evaluate-research.md`, and the paper notes.

**Principles that scope everything below** (see `design-decisions.md`, DD-1..4):
- System-specific design rules + the intended-model loop — **not** generic metrics dashboards (that's a
  continuous sensor's lane, e.g. Archy).
- Lightweight: compose existing tools, static extraction, no execution, no MCP, additive metadata.
- Every signal gated and low-noise; *candidates* the agent judges, not verdicts.
- "Intended-model-if-present, else inferred" — declared metadata is ground truth; inference corroborates
  or contradicts it.

---

## Shipped so far (context)

- **Commands:** `init` (per-agent skill delivery, agent auto-detect, `--wire`, `upgrade`), `gen`, `check`
  (import-linter · dependency-cruiser · ast-grep · property-based-test tiers), `drift`, `evaluate`.
- **Skills:** `describe` (build-or-update), `check`, `invariant`, `evaluate` — wired into one loop.
- **`drift`** (reflexion-diff): dangling refs · git-stale docs · undocumented modules · subsystem
  dependency edges · entry points · web-route surface (OpenAPI-else-docs) · config keys · deployment
  topology · service-edge cross-check · connector-kind mismatch.
- **`evaluate`** (system-level smells): A data/source-of-truth · B boundaries (unstable dependency,
  layering, shotgun surgery, unstable interface, extraneous adjacent connector) · C structural (god
  component, cycles, distributed monolith) · D lifecycle (hard-coded endpoints, cross-boundary
  observability).
- **Connector-typed edges** (`**Connects:** … via <kind>`) + inference from code. Python + JS/TS.

---

## Connectors & topology (Tier B and beyond)

- [x] **Config/env-driven endpoint inference.** `connscan` resolves a call target from an
  `*_URL`/`*_ENDPOINT`-shaped env key (already extracted by `configscan`) whose base name matches a
  service, in a file that makes HTTP calls — so `requests.get(os.getenv("BILLING_URL"))` resolves to the
  billing service. Feeds both the drift mismatch and the inferred distributed-monolith. *(shipped 2026-07-18)*
- [ ] **Module-constant / base-URL client resolution.** Follow a call's host back to a module-level
  `X = "http://…"` constant, or to a `base_url=`/`baseURL:` on a client the later `.get("/path")` uses.
  Light data-flow, not a regex. Raises recall; watch for noise.
- [ ] **Async producer↔consumer pairing.** Match a publish topic/queue to its subscriber across services
  so `async-event` edges get a resolved *target*, not just "emits events." The hard half of inference.
- [ ] **Richer connector attributes.** Optional free-form properties on an edge (`{protocol=grpc}`,
  multiplicity, direction) in the ACME open-property style, for finer analysis later.

## Mine stated invariants (issue #3)

Enforce the invariants a team has already written down but never checked — from design/spec docs and
in-code markers. Design in `~/research/architecture-agent/invariant-extraction-design.md`. Risk-tiered
curation: auto-capture every stated invariant as a cited prose row; promote to an *active* rule only on a
passing, non-vacuous `check` + confirmation; a stated-but-violated invariant is drift.

- [x] **Stage 1 — `describe` prompt guidance.** Locate docs via index files (README/AGENTS/CLAUDE) + spec
  dirs; capture the repo's documentation conventions into the constitution; mine markers
  (`INVARIANT`/`@invariant`/asserts/contracts) + modal language (MUST/NEVER/ALWAYS/"only X may"); classify →
  DSL tier; verify (`check` + vacuity guard); risk-tiered curation; provenance; flag design-vs-code
  divergence. *(shipped 2026-07-18)*
- [x] **Stage 2 — deterministic candidate scanner.** `archagent scan-invariants` (`invscan.py`) scans docs +
  source for markers (`INVARIANT`/`@invariant`/asserts/contracts, high confidence) + modal language in docs
  (MUST/NEVER/"only X may", low confidence) and emits candidates with a coarse tier guess (`--json`,
  `--markers-only`) — enumeration is now *process, not luck*. Agent classifies / verifies / curates.
  Validated on mra2 (found all 6 `INVARIANT:` markers the issue flagged as missed). *(shipped 2026-07-18)*

## Enforcement & CI hardening (Phase 3)

- [ ] **`check` as a pre-commit hook + GitHub Action.** The per-commit gate (DD-4). Ship a ready-made
  hook and a workflow template so violations block a PR.
- [ ] **Robustness.** One malformed rule shouldn't blank a whole run — isolate parse/exec failures per
  invariant and surface them as SKIP with a reason.
- [ ] **More BOUNDARY forms.** `layers` (an ordered stack, each may depend only downward) and interface
  rules ("only X may import Y"), beyond today's pairwise `forbid a -> b`.

## New invariant tiers

- [ ] **Contract tier.** Pre/postcondition checks — icontract/deal (Python), zod/`tsc` (TS) — generated
  from the invariants table, executed in the target env like the PBT tier. Fills the gap between
  structural rules and full property tests.

## Evaluate — more smell signals

- [ ] **Scattered parasitic functionality** (Garcia). One concern smeared across many subsystems, several
  of which also own unrelated work — the dual of god-component. Needs agent judgment over a co-change +
  concern-mapping candidate, so likely a skill-side signal more than a pure metric.
- [ ] **Lock-step deployment.** Services that always co-change/co-deploy together (from git history) —
  a distributed-monolith signal complementary to the structural cycle check.
- [ ] **Deeper CLI-surface extraction.** Subcommands/args as an interface surface (like web routes),
  diffed against docs.
- [ ] **Deeper observability.** Beyond "is anything traced": correlation-id propagation *through* call
  chains, structured-logging coverage per service boundary.

## Behavioral depth (Phase 4)

- [ ] **Behavioral-drift candidates.** State/lifecycle/flow signals (from the Mermaid state/sequence
  diagrams vs the code) for the agent to reason about — the dimension static structural tools can't reach
  and the survey's identified white space.

## The update loop

- [ ] **Agent applies edits from the report.** Tighten `describe`-update so the agent consumes a
  `drift`/`evaluate` work-list and proposes the concrete localized edits (never a whole rewrite), closing
  extract → diff → *update* end to end.
- [ ] **Optional runtime OpenAPI generation.** For frameworks where static route extraction is lossy,
  offer an opt-in runtime spec dump to diff against.

## Distribution & adoption

- [ ] **Publish to PyPI.** `uvx archagent` with no clone. The single biggest adoption unlock.
- [ ] **More agents / plugin distribution.** Auto-detect additional coding agents; borrow Archy's plugin
  packaging.

## Measurement

- [ ] **Does archagent keep agents adherent?** The evaluation the survey called for — measure whether an
  agent working under archagent drifts less than one without it (cf. the Constraint Decay result that
  motivates the project). This is what turns the thesis into evidence.

---

## Not planned / out of scope

Recorded so we don't relitigate:
- **Per-artifact config lint** (e.g. "service missing a healthcheck") — deployment-config linting
  (kube-score/checkov territory), not system-level architecture. Tried and removed 2026-07-12.
- **Generic structural-metric dashboards** — cycle counts, health scores, coupling trends over time.
  A continuous sensor's job (Archy), not archagent's (DD-4).
- **Heavy formalism** — CSP/TLA+/Lean connector semantics, autoformalization, a custom graph DB. The
  value from the ADL work is the *vocabulary and the one edge attribute*, not the formal machinery.
