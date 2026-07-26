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
  (import-linter · dependency-cruiser · ast-grep · property-based-test tiers), `drift`, `evaluate`,
  `status` (per-package coverage), `graph` (Mermaid system map from metadata, `--write` into index.md),
  `lint-docs` (Mermaid syntax linter, no Node), `modules` (module-resolution diagnostic + collision check).
- **Skills:** `describe` (build-or-update), `check`, `invariant`, `evaluate` — wired into one loop.
- **`drift`** (reflexion-diff): dangling refs · git-stale docs · undocumented modules · subsystem
  dependency edges · entry points · web-route surface (OpenAPI-else-docs) · config keys · deployment
  topology · service-edge cross-check · connector-kind mismatch.
- **`evaluate`** (system-level smells): A data/source-of-truth · B boundaries (unstable dependency,
  layering, shotgun surgery, unstable interface, extraneous adjacent connector) · C structural (god
  component, cycles, distributed monolith) · D lifecycle (hard-coded endpoints, cross-boundary
  observability). Reports its own **coverage** (which families were inactive for missing metadata) and
  **history hygiene** (commits mined, conventional-commit %, bulk skips) so "zero findings" is never read as
  "clean."
- **Connector-typed edges** (`**Connects:** … via <kind>`) + inference from code. Python + JS/TS.

## Releases

- **0.2.0** (2026-07-21) — **Configurable architecture-docs location:** `init --arch-dir docs/architecture`
  (+ interactive discovery of `docs/`/`design/`/`spec/` dirs, `--yes` to skip prompts); recorded as
  `[project] architecture_dir` and honored by drift/evaluate/check/gen, wiring, and `upgrade`. **Phase 3
  (initial):** `archagent install-hook` — a native `.git/hooks/pre-commit` gate (idempotent, composes with an
  existing hook), and `check --skip-pbt` to run the fast static tiers only. Plus `docs/RELEASING.md` and
  README cleanup.
- **0.1.0** (2026-07-19) — First PyPI release. The full loop: `init`/`gen`/`check` with the four invariant
  tiers (BOUNDARY · STRUCTURAL · PBT); the `describe`/`check`/`invariant`/`evaluate` skills; `drift`
  (reflexion-diff) and `evaluate` (system-level smells) with their complete signal sets; connector-typed
  edges + inference; stated-invariant mining (`scan-invariants` + describe); per-agent delivery (Claude
  Code / Cursor / OpenHands); the ADL-SPEC. Python + JS/TS.

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

- [x] **`check` as a native pre-commit hook.** `archagent install-hook` writes a `.git/hooks/pre-commit`
  block that runs `archagent check` (idempotent; composes with an existing hook). `check --skip-pbt` runs
  the fast static tiers only (BOUNDARY + STRUCTURAL), so the hook can leave property tests to the test
  suite. *(shipped 2026-07-21)*
- [ ] **Team-shared pre-commit (framework) + GitHub Action.** Ship a `.pre-commit-hooks.yaml` in this repo
  so users reference `archagent-check` from their `.pre-commit-config.yaml` (committed → gates the whole
  team), and a workflow template `init` can scaffold. The native hook above is local-only.
- [ ] **`test_architecture.py` generator.** A subcommand that emits a test (pytest / vitest) which runs the
  static tiers via archagent's API and asserts no violations — so the whole gate runs inside an existing
  test suite (option 3). Behavioral tiers (PBT, future contract) already run there natively.
- [ ] **Robustness.** One malformed rule shouldn't blank a whole run — isolate parse/exec failures per
  invariant and surface them as SKIP with a reason.
- [ ] **More BOUNDARY forms.** `layers` (an ordered stack, each may depend only downward) and interface
  rules ("only X may import Y"), beyond today's pairwise `forbid a -> b`.

## Contract tier (design by contract)

A fourth enforcement tier alongside BOUNDARY / STRUCTURAL / PBT: pre/postconditions and class invariants,
executed in the target env like the PBT tier. Fills the gap between a structural rule ("A may not import B")
and a full property test ("for all inputs, this holds") — the middle ground of "this function guarantees X on
return," "this class always satisfies Y." Same principles as everything else here: *candidates the agent
judges, not verdicts*; **intended-model-if-present, else inferred**; compose existing tools, no bespoke
formalism.

**Proposed Python tool: `icontract`** — chosen because `icontract-hypothesis` folds straight into the
Hypothesis-based PBT tier we already run: it derives strategies from a function's preconditions and checks
its postconditions, so a mined `@require`/`@ensure` becomes a property test in the *existing* runner rather
than a new one. It also has first-class class invariants with Liskov-style inheritance checking (covering the
behavioral item below), a clean decorator model with no import hooks, and violation messages that report the
failing sub-expression's values. Runner-up `deal` stays in view for one thing — its flake8 linter can catch
some violations *statically*, attractive if we later want a contract check that runs without executing the
target. TS side is still `zod` / `tsc`.

Two open design decisions scope this whole section:

1. **Derived vs. authored.** Do contracts *fall out of* the invariants table (archagent generates the
   `@requires`/`@ensures` from a mined/classified invariant), or is there an *authoring surface* where a
   contract is declared metadata a person writes directly? Likely both, staged: derived first (reuses the
   stated-invariant pipeline, no new syntax), authoring later.
2. **Function-level vs. behavioral (class/interface).** Function pre/postconditions are the easy half.
   Class invariants and Liskov-style behavioral subtyping (a subclass may weaken preconditions / strengthen
   postconditions, never the reverse; invariants are inherited) are the harder, higher-value half and touch
   the STRUCTURAL tier.

- [ ] **Derived contract tier (function-level).** Take a pre/postcondition already in the invariants table
  (from stated-invariant mining or `describe`) and emit an executable check — an `icontract`
  `@require`/`@ensure` (Python) or a `zod` schema / `tsc` assertion (TS) — run in the target env, reported
  like PBT. On Python, `icontract-hypothesis` turns the emitted contract into a property test executed by the
  existing PBT runner (no second execution path). No new authoring syntax; the invariants table is the
  source. This is the original "contract tier" item, unchanged in intent.
- [ ] **Contract authoring surface.** Let a team *declare* a contract in the ADL (a `@requires`/`@ensures`
  row against a named function/module, or a `**Contract:**` marker in a component doc) and have archagent
  wire it into the tier — the DbC analogue of how BOUNDARY rules are authored today. Turns contracts from a
  derived by-product into first-class, human-owned metadata. Depends on the derived tier existing first.
- [ ] **Class / interface behavioral contracts.** Class invariants (a condition true after every public
  method) and behavioral-subtyping checks (Liskov): flag a subclass that strengthens a precondition or
  weakens a postcondition/invariant relative to its base. `icontract` models class invariants and enforces
  this inheritance discipline directly; the subtyping check is partly static (compare declared contracts up
  the hierarchy) and partly runtime. This is the OO-DbC (Eiffel) tradition and the part the current framing
  omits entirely.
- [ ] **Verification-only vs. shipped instrumentation.** Decide (and probably offer both) whether archagent
  *checks* contracts in a throwaway run (like the PBT tier — nothing lands in the user's code) or can
  *generate* the contract decorators into the target as durable runtime guards. Default to verification-only,
  matching the "additive metadata, no execution surprises" principle; instrumentation is opt-in.
- [ ] **Vacuity / triviality guard.** Reuse the stated-invariant vacuity check so a generated contract that
  can never fail (e.g. `ensure result is not None` on a function that structurally cannot return `None`) is
  surfaced as noise, not a passing rule — the same non-vacuous-`check` gate that curates mined invariants.

## Evaluate — more smell signals

- [ ] **Scattered single-source-of-truth** (single-owner decision drift). A decision/state that should have
  one owner but is re-implemented across several files. **Designed + validated on real repos** —
  `docs/designs/hotspots-and-single-source-of-truth.md`. The check is an autonomous code-first scan: find a set of
  domain values branched on across multiple files (tightness-filtered, vendored/generated excluded), rank by
  change history, report as findings the agent judges — **no new file format**. A durable *declared-owner
  list* (`capabilities.md`) that persists confirmations/dismissals is **deferred future work** — see
  Appendix A of the design.
- [ ] **Churn × complexity hotspots.** A *single-file* signal (distinct from pairwise co-change): a file with
  both heavy git churn (many commits, especially bug fixes) **and** high complexity is a classic
  bad-architecture / too-many-edge-cases smell (cf. Feathers / CodeScene hotspots). **Designed + validated**
  — `docs/designs/hotspots-and-single-source-of-truth.md` (Check A); ships first, no new file format. Complexity via a
  language-light indentation proxy; extend `cochange.py` (no PyDriller). Remaining calibration: percentile
  bar, raw- vs. fix-churn axis.
- [ ] **See through one hop of indirection in co-change.** Today shotgun-surgery only sees *direct* import
  edges, so two subsystems coupled through a shared factory/base look like a missing interface when the
  interface already exists (that third module). Credit transitive/indirect links (or flag the shared
  intermediary as the change-magnet) so the finding points at the real cause. Prompt-side mitigation shipped
  (the skill now tells the reader to check for indirection); this is the tool-side fix.
- [ ] **Scattered parasitic functionality** (Garcia). One concern smeared across many subsystems, several
  of which also own unrelated work — the dual of god-component. Needs agent judgment over a co-change +
  concern-mapping candidate, so likely a skill-side signal more than a pure metric. (Reconcile with
  capability fragmentation above — that's the *within*-subsystem cousin.)
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
- [ ] **Formal-spec drift (TLA+ as behavioral source of truth).** For teams that write a formal spec at
  design time, treat a `.tla` module the way we treat OpenAPI for routes: an authoritative *intended* model
  archagent reads (state constants, next-state actions, declared invariants) and diffs against the code —
  the formal upgrade of behavioral-drift above (Mermaid → TLA+). archagent does **not** model-check
  (interleavings/liveness stay TLA+'s job at design time — see the heavy-formalism exclusion below); its job
  is the maintenance-time tether the spec never had, catching where agent-written code has quietly diverged
  from the validated model. Two mechanisms: **(a) state-space diff** — the states the code actually branches
  on vs. the states the spec models (a state in code but not the spec, or a spec-forbidden transition);
  **(b) safety invariants → invariants table** — import a proven state-safety invariant as a stated
  invariant and generate a contract-/PBT-tier check where runtime-checkable (liveness/temporal doesn't map).
  **First probe:** reuse Check B's branch-literal extraction (the code's realized state space) and diff it
  against the spec's declared states — a mostly-deterministic check on machinery already being built for
  hotspots/single-source-of-truth. The ADL would name the `.tla` module as the behavioral source for the
  subsystem ("intended-model-if-present, else inferred").

## The update loop

- [ ] **Agent applies edits from the report.** Tighten `describe`-update so the agent consumes a
  `drift`/`evaluate` work-list and proposes the concrete localized edits (never a whole rewrite), closing
  extract → diff → *update* end to end.
- [ ] **Optional runtime OpenAPI generation.** For frameworks where static route extraction is lossy,
  offer an opt-in runtime spec dump to diff against.

## Distribution & adoption

- [x] **Publish to PyPI.** `uvx archagent` / `uv tool install archagent`, no clone. *(v0.1.0 shipped 2026-07-19 — https://pypi.org/project/archagent/)*
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
