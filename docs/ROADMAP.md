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

- [x] **Scattered single-source-of-truth** (single-owner decision drift). A decision/state that should have
  one owner but is re-implemented across several files. **Shipped** as `dupdecide.py` → the group-F
  `scattered-source-of-truth` finding: an autonomous code-first scan (domain values branched on across
  multiple files, tightness-filtered, vendored/generated excluded), ranked by change history, reported as
  findings the agent judges — no new file format. Design:
  `docs/designs/hotspots-and-single-source-of-truth.md`. The Appendix-A **"never calls the owner"** detector
  also shipped, by a different route: where the project already *declares* an owner as an enum, no
  `capabilities.md` entry is needed to know the authority, so `find_enum_escapes` flags files that re-decide
  it by comparing against its raw member strings. A durable *declared-owner list* that persists
  confirmations/dismissals remains **deferred** — see the follow-ups below for what it would buy.
- [x] **Churn × complexity hotspots.** A *single-file* signal (distinct from pairwise co-change): a file with
  both heavy git churn (many commits, especially bug fixes) **and** high complexity is a classic
  bad-architecture / too-many-edge-cases smell (cf. Feathers / CodeScene hotspots). **Shipped** as
  `hotspots.py` → the group-E `change-prone-file` finding: per-file churn from `cochange.py` (no PyDriller)
  crossed with an indentation complexity proxy, both as within-repo percentiles, top quartile on both.
  Its prerequisite — a *learned* per-repo bug-fix commit recognizer (`history.py`, the `history-profile`
  command) — shipped with it. Remaining calibration: the percentile bar, and whether raw or fix churn is
  the better axis.

### Follow-ups from the evaluation pass

Measured over six repos with every group-F finding labelled by reading the cited code; full record in
`research/architecture-agent/feedback/probe-results.md`. Current state: Check B 71% confirmed (7% detector
error), enum escape 84%, Check A defensible with no labelling surprises. What is left, roughly in the order
the evidence argues for:

- [x] **TypeScript union-of-string-literal types as declared owners — investigated, and deliberately not
  built.** The premise was wrong. Running `tsc --strict` on the four shapes shows it already rejects a
  comparison between a typed value and a literal outside its type (TS2367) for string enums, union types,
  `as const` unions and `switch` arms alike. A stale string cannot survive a TypeScript build when the
  compared value is typed, so treating unions as owners would have flagged idiomatic, compiler-checked
  code. opencode's zero TS escapes is therefore *correct behaviour*, not a recall gap. The narrowing
  shipped instead: a purely-TypeScript escape now says so and defers to the compiler, since it only bites
  where the value arrives untyped (a `string`/`any` field off an API response, or — as with OpenHands'
  `ActionType` — an event typed with literal unions rather than the enum). Python keeps the stronger claim,
  having no such checker, and cross-language escapes are unaffected because neither compiler sees the other
  side.

  **Verified with a real `tsc` run** (OpenHands frontend, deps installed, baseline typecheck clean, stale
  literal injected at each finding site): `ActionType` errors at both sites — TS2367 in `guards.ts:44` and
  TS2678 in `get-action-content.ts:132` — so it is compiler-guarded and its finding is a false positive.
  `I18nKey` produces **no error**, because `type Suggestion = { label: I18nKey | string }` widens the field
  back to `string`, so TypeScript can never narrow it and the switch is unchecked; renaming a member would
  leave those arms silently stale. One guarded, one real — exactly the distinction the narrowed
  recommendation asks the reader to make, so the wording holds. A blanket suppression of TS-only escapes
  would have discarded a real finding.

- [x] **Branch on enum *members*, not just their values — shipped.** `state == WorkflowState.DONE`,
  `state is WorkflowState.DONE`, `case Kind.ALPHA:` and arm forms now count as branch values when the
  qualifier is an enum this repo declares (which is what keeps every `self.config.DEBUG` out). Added 3
  findings on OpenHands with no losses elsewhere: `ProviderType` dispatched across 5 `app_server` files
  and 3 `enterprise/server` files (`if provider == ProviderType.GITHUB / elif … GITLAB / elif …
  BITBUCKET`, the same ladder re-written in each), and `AgentState` across 8 frontend files.

  The implementation lesson is worth keeping: enriching the value set *broke* clustering at first.
  Member tokens appear in many files, so union-find used them as bridges between unrelated string
  clusters — on `litellm/proxy` everything merged into one 61-value blob at cohesion 0.09, which then
  failed the cohesion bar and took a real, confirmed cluster down with it. The two vocabularies are now
  clustered separately (members are tagged internally, since a dot cannot tell them apart — litellm
  branches on the string `"response.created"`). Regression test included.
- [ ] **The last grab-bag class: mixed-concept clusters that are dense enough to pass.** The cohesion bar
  (0.6) removed the chain-shaped grab-bags, but litellm's `integrations` cluster survives at 0.60 by mixing
  call types, kwarg names and metadata keys. Distinguishing it likely needs the values' *shape* (are they
  drawn from one naming family?) rather than more graph statistics.
- [ ] **Durable dismissals.** Three of fourteen surviving group-F findings are intended families — database
  backends, per-protocol adapters — that are correct to surface once and re-surface on every run forever.
  This is the concrete case for the deferred declared-owner overlay, and the clearest thing it would buy.
- [ ] **Threshold sensitivity sweep.** Eight knobs (`PCTILE_BAR`, `MIN_LOC`, `MIN_FILES_PER_VALUE`,
  `TIGHTNESS`, `COHESION`, `MIN_ESCAPED_VALUES`, `MIN_PAIR_COVERAGE`, `DECISION_MIN_CHURN`), each set from
  one repo's false alarms. Nobody knows which are load-bearing and which are decoration.
- [ ] **Golden-output fixture.** Unit tests cover mechanics; nothing catches an aggregate behaviour change.
  A small committed repo with asserted findings would make regressions show up as a diff — the four fixes
  in the evaluation pass were all found by hand, and would not have been caught by CI.
- [ ] **Validate the dismissal guidance with an unprimed reader.** Whether the skill text *leads* someone
  to dismiss an intended family correctly is still untested — the one run of it was by a session that had
  already labelled the findings.
- [ ] **Smaller known gaps.** Aliased imports (`import WorkflowState as WS`) are missed; `_IN_SET` reads a
  `for x in ("a", "b"):` loop header as a membership test; `enum_defs` skips Java/Kotlin enums (their
  bodies carry constructor arguments the parser doesn't read) and Go, which has no enum construct.
- [ ] **A repo where subsystems cut across directories.** Declaring `**Covers:**` for datasette proved the
  subsystem-grouped path of Check B *runs* (and activated 8 co-change findings the directory fallback could
  not produce), but its subsystems track its directories too closely to show whether the grouping choice
  changes what is found.
- [ ] **Separate config-threading check** (design §6.4) — "key X is read in files A, B and C; is one owner
  passing it through, or does each read it independently and risk a stale default?" Built on the config
  scanner `drift` already has, so the raw fact is already extracted deterministically. Untouched.
### More signals

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
