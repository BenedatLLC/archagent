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

## Evaluation

How archagent is evaluated, and the rules by which a proposed change is accepted, are in
[`docs/designs/evaluating-archagent.md`](designs/evaluating-archagent.md). Four parts: orientation, the
instruments that produce evidence, the process that turns evidence into a decision, and the limits. Start
with "If you are reading this for the first time".

Open items from that design, in the order they unblock things:

- [ ] **Measure the noise floor** (§15). How far a score moves between identical runs. Three acceptance
  rules say "significant" and none can be evaluated without it. This blocks everything downstream.
- [ ] **Build the recurrence suite** (§13) from the nine confirmed obstudio defects, phrased as facts
  about the pinned target rather than about any one artifact.
- [ ] **Build the per-repository checklist format** (§14) — ground truth stated, judged
  correct/wrong/absent. Covers the misreading class the recurrence suite provably cannot.
- [ ] **The evaluation ledger** (§17). One row per run, carrying the variance sources, not just scores.
- [ ] **Wire the update path** (§16). `check_update_captured` and `update_quality` are built and have
  never run; they need the changed-file set from a `git diff` between the two revisions.
- [x] **Leave-one-out threshold sensitivity** (§18) — `scripts/thresholds.py`. Reports whether a
  threshold's value is held in place by a single repository, and distinguishes that from *unconstrained*
  (nothing responds) and *thin* (too few findings to say). First run:
  `docs/evaluations/thresholds/RESULTS.md` — three thresholds pinned, all thin, `TIGHTNESS` unconstrained.
- [x] **Sweep `PCTILE_BAR` and `MIN_LOC`.** History is mined once per repository and reused across every
  value and threshold. The first non-thin verdicts: `MIN_LOC = 30` clean, `PCTILE_BAR = 0.75` **unranked**
  — no repository pins it and nothing prefers it to its neighbours either. Ranking it needs precision
  labels across the sweep, which the corpus does not have.
- [ ] **Groups A–D have no evidence and the corpus cannot produce any** — they read declared metadata no
  corpus repo has. Split proposed: synthetic injection for recall, artifact-bearing repos for precision.
  See [#9](https://github.com/BenedatLLC/archagent/issues/9).

## Releases

- **0.3.0** (2026-08-03) — **Two new `evaluate` signal groups.** Group **E** `change-prone-file` (per-file
  churn × indentation complexity, both as within-repo percentiles) and group **F** `scattered-source-of-truth`
  (one decision branched on across files) + `enum-value-escape` (an enum bypassed by its raw member
  strings — a pure code scan that needs no git). Ranked by a **learned per-repo bug-fix commit
  recognizer** (`archagent history-profile`) rather than a hard-coded `fix(...)` pattern, which finds zero
  of Django's ~16,000 fix commits.
  **`archagent investigate <finding-id>`** turns a candidate into a verdict: it prints the questions that
  decide whether a finding matters, and `--record --rating minor|moderate|critical` stores the answer in
  the artifact under `<arch-dir>/investigations/` so the next run reports it instead of asking again
  (ADL-SPEC §6a).
  **`--until` / `--as-of <tag>`** on `evaluate` and `drift` bound history to a past revision, so a run can
  be reproduced as of a commit; the run warns if the checked-out tree is newer than the window.
  **Drift correctness:** a `**Covers:**` glob is no longer reported as a missing file, a reference to code
  in a language archagent does not analyse is no longer reported as deleted, and a wrapped `**Config:**`
  manifest is read whole instead of to its first line. **`evaluate --json`** now carries the signs each
  inactive family stands for, so a consumer can check the coverage report against the findings list.
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
  one repo's false alarms. Nobody knows which ones actually change the output and which are decoration.
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

## Structural debt found by describing archagent with archagent

- [ ] **Break the `drift` ↔ `extraction` cycle.** Declaring archagent's own architecture let `evaluate`
  run its structural signals for the first time, and they found a genuine 2-node cycle at high confidence
  plus the layer inversion behind it: `drift` (domain) imports the scanners, and `invscan`/`connscan`
  import back into `drift` for `_source_files` and `_glob_files`. Fix: move `_git`, `_source_files`,
  `_glob_files` and `_import_graph` into a leaf module both may import. ADR 0003 records the decision and
  its cost. Deferred once already; the cycle makes it a defect rather than an aesthetic complaint.

## Findings that explain themselves

- [x] **On-demand investigation** — `archagent investigate <finding-id>`. `evaluate`'s severity counts
  files and commits and says nothing about consequence; the first independent labelling round found most
  enum escapes minor-to-moderate and one **critical**, where a drifted call-type vocabulary had silently
  disabled a prompt-injection hook for two request categories. Findings now carry a stable id and a
  deterministic `investigate` flag with a `triage_reason` (wide spread, large vocabulary, heavy fix churn,
  a crossed language boundary, or a `.value ==` unwrap), and the CLI names the command to run. The command
  prints a brief — seven questions modelled on a worked example, the files to start from, and the
  minor/moderate/critical scale — rather than pretending to answer them.
- [x] **Investigation write-back** — `archagent investigate <id> --record <file.md> --rating
  minor|moderate|critical --by NAME`. Investigations land in the **architecture artifact** under
  `<arch-dir>/investigations/` (ADL-SPEC §6a), as markdown meant to be committed. They belong with the
  architecture documents rather than under `.archagent/`, which is configuration and generated output: an
  investigation is durable, human-facing prose about the system, of the same kind as an ADR — the
  difference being that an ADR records a decision and an investigation records the analysis that may
  justify one. A finding with a recorded
  investigation reports its verdict instead of re-inviting the work, and drops out of the investigation
  queue. The rating vocabulary is enforced, because a word nothing reads makes the record useless.
  Staleness uses a fingerprint wider than the finding id — the id keys on owner and value set, so a
  changed *set of involved files* is invisible to it. When the evidence has moved the old verdict is still
  shown but marked stale, and the question reopens: the verdict was about the finding as it stood.
- [~] **Qualitative rubric criteria** (design §9, judged half) — **criteria and machinery shipped;
  uncalibrated.** Seven criteria in `tests/rubric_judged.py`, each with anchored descriptors at 1/3/5
  rather than a bare scale, because an unanchored 1–5 measures the judge's mood and two runs cannot say
  why they differ: accuracy, completeness, prose clarity (against `writing-style.md`), diagram clarity,
  invariant **logical strength** and invariant **business criticality** kept separate (a rule can be
  airtight and protect nothing, or guard the crown jewels and be trivially evadable), and update quality
  for the second run. `selfeval brief` writes them for a reviewing session; `selfeval judged` ingests.
  **A score with no `file:line` citation is discarded, not averaged** — the failure mode here is fluent,
  confident, unfalsifiable prose, which is what a language model produces most readily, and a demo run
  correctly threw away a "5/5, the writing is clear and professional". `0` means unsure and is excluded
  rather than counted as failure. Every stored review carries its own uncalibrated caveat, so a number
  cannot be quoted apart from it.
  **First real review (2026-08-02) broke the instrument three ways** — `docs/evaluations/selfeval/archagent/CALIBRATION.md`.
  Fields were read to end-of-line, so a review whose evidence sat indented under `why:` lost five of six
  scores to the citation rule and reported the sixth as the artifact's score. The citation rule checked
  that a `file:line` was *present*, which a fabricated one satisfies equally — four of that review's
  citations pointed at nothing, including line 1593 of a 248-line file. And a mean over the fragment that
  survived was indistinguishable from a mean over the whole. All three fixed: fields run to the next key,
  `unresolved_citations` resolves every citation against the tree, and the record carries
  `scored`/`answered`. The finding that matters most: the four criteria answerable from the artifact text
  scored 3–4 cleanly, while the two requiring the code to be opened were the two that were fabricated.
- [x] **Orientation check** (design §9, deterministic half). `check_orientation` requires the index to
  carry a system map and prose before its catalog. Both were already mandated — `describe` step 8(b)
  and the shipped `index.md` markers — and archagent's own artifact had neither while every check passed.
  A requirement nobody verifies stops happening quietly. Also: the rubric now invokes the checkout being
  scored rather than whatever `archagent` is on `PATH`, after a stale global install failed the
  `tools.clean` gate and was read as an artifact defect.
- [x] **Artifact follow-ups from that review** — all three closed, and the outcomes differed sharply.
  [#5](https://github.com/BenedatLLC/archagent/issues/5) (abstractions named before grounding) held on all
  three counts and was fixed with worked examples: BND-001 traced through the whole invariant pipeline,
  groups A–F enumerated, and what a scanner actually returns rather than what it extracts.
  [#4](https://github.com/BenedatLLC/archagent/issues/4) (decorative captions) did not hold — all five
  captions already stated takeaways and the "missing" state diagram already existed; the real gap was
  `drift`, the central check, having no diagram at all.
  [#6](https://github.com/BenedatLLC/archagent/issues/6) held and produced the most: five new rules
  (STR-002…STR-006), each verified by planting a violation rather than by passing on a clean tree.
  `import typer` in a domain module left BND-001 passing, and two claims the artifact made about its own
  DSL were untested guesses — "only `drift.py` may invoke `git`" is expressible (`ast-grep` matches AST
  nodes, not comments), and the allow-list the issue assumed was missing is just `forbid-pattern
  from .$M import $$$ in <module>`.
- [ ] **Calibrate the judged criteria** (§11). The findings half of this was done and produced 68%
  agreement between an independent reviewer and the person who built the checks, with errors in both
  directions. The equivalent for these criteria needs artifacts of known quality to score, which needs a
  real `describe` run first. Until then the judged mean gates nothing.

## Measurement

Designed in **`docs/designs/evaluating-archagent.md`**, which separates three things that had been
conflated: the deterministic signals (L1), the skills that judge them into a report (L2), and the artifact
as context for a coding agent (L3, the research claim). Near-term goal is confidence in the tool; a paper
is a later consideration. Items below are in build order.

**Where this stands (2026-08-01).** L1 has evidence that does not depend on our judgement: across four
pre-registered runs, 3 of 4 adequately-powered repositories show that flagged files go on to accumulate
significantly more defect-fixing commits than churn-matched controls, in two languages and three
architectures (`docs/evaluations/defect-study/RESULTS.md`). Magnitudes are not comparable across repositories
and small repositories remain unmeasured. L2 has no evidence at all. Four pieces are built — the deterministic rubric (works today, no agent
needed), the spot-check worksheet and label store, the objective half of the blind comparison, and the
agreement statistics — and every one of them waits on the same thing: **the label store is empty**. Labels
from whoever built the checks would recreate the closed loop the design exists to break, so this is a
people problem, not a code problem, and it gates the judged rubric, the judged blind comparison and any
feedback loop. Two components deliberately refuse to run rather than produce numbers worth less than
nothing: `selfeval run` (comparing scorecards is meaningless before the agent-variance noise floor is
known) and `blindcomp` generation (one session writing its own guidance's output and grading it measures
self-preference).

- [x] **`--until` / `--as-of` plumbing** (design §5) — **shipped.** `mine_cochange` takes `--since` but not `--until`,
  All three paths that read the repository are bounded — the co-change miner, the commit-wording profile
  (`history._subjects`, the leakage that was easy to miss), and `drift`'s staleness comparison — plus
  `--as-of <rev>`, which reads a tag's own commit date. A bounded run also ignores a cached profile, since
  a cache carries no record of the window it was learned over. The fourth path, file *contents*, cannot be
  bounded by a flag: `evaluate` warns when `HEAD` is newer than `--until` rather than silently measuring
  present-day code against past history.
- [x] **Pinned-corpus regression** (§6) — **shipped.** `pytest -m corpus` clones selected repositories at a
  pinned tag into a temp worktree, runs `evaluate` as of that tag, and diffs a projection of the findings
  against a recorded expectation; `ARCHAGENT_UPDATE_CORPUS=1` re-records after review. Excluded from the
  default suite. The clone is blobless rather than shallow — `--depth` would truncate the history that
  churn is computed from and produce different numbers rather than an error. Diffs are summarised as
  LOST / NEW / CHANGED per finding, because a *lost* finding is the failure that matters and is invisible
  in a raw JSON dump. Recorded so far: datasette, django, litellm; opencode and openhands are declared but
  unrecorded, which skips before any network work. It earned its keep on first use by catching a silent
  failure in the miner (below).
- [x] **A failed history walk is no longer silent** — found by the corpus harness on its first real run.
  `git log --name-only` over 3000 litellm commits took longer than the miner's 30s timeout, `_git`
  returned None, and `mine_cochange` returned all-zero counts: every history signal went quiet and the run
  read as a clean repository. It was recorded as litellm's regression baseline before anyone noticed —
  the worst outcome available, since the baseline would then have enforced the broken behaviour. The walk
  now gets a 300s budget, a failure sets `CoChange.mining_failed`, and `evaluate` reports it as a loud
  caution plus an inactive family rather than silence.
- [~] **Held-out defect study** (§7) — **harness shipped, run 1 inconclusive.**
  `scripts/defect_study.py flag|outcome|report` computes the signals as of a cutoff, writes the flagged set
  to disk, and refuses to compute outcomes until that file exists, so the pre-registered ordering is
  mechanical. Renames are followed back to each file's name at the cutoff, deleted files are excluded and
  counted, the statistic is a Mantel-Haenszel rate ratio across churn deciles with a seeded bootstrap
  interval, and a zero-width interval is reported as degenerate rather than as confidence.
  Run 1 (poetry, scrapy) was null but **underpowered** — 10 and 13 flagged files after stratification,
  which a simulation of this design's own estimator later showed detects a genuine 1.5× effect about a
  quarter of the time. The power bar (≥60 flagged, ≥120 controls) now lives in the manifest, decided in
  advance rather than discovered afterwards.
  **Run 2** added four larger repositories, keeping run 1 on record rather than replacing it. Two cleared
  the bar and they split: **home-assistant RR 2.05 [1.55, 2.67] passes**, angular RR 1.47 [0.98, 2.18]
  just misses. The more informative comparison is the specificity check — home-assistant's flagged files
  take 2.05× the *defect fixes* but only 1.28× *all* commits, so churn is absorbed and something else
  remains; angular's take ~1.4× of both, the pattern of a set that is merely busier. Full record:
  `docs/evaluations/defect-study/RESULTS.md`.
  **Run 3** (nova) was pre-registered before running — the prediction and what each outcome would license
  are in commit `5d890cc` — and it killed the explanation run 2 left open. Nova is a deeply coupled Python
  service, nothing like home-assistant's plugin registry, and it passes with the same signature:
  RR 4.45 [1.63, 16.14] on defect fixes against 1.35 on all commits. Architecture does not explain the
  earlier pass. What remains is that both passes are Python and the one near-miss is TypeScript.
  **Standing:** two of three powered repositories pass, both with the specificity signature; pooled
  (exploratory) RR 1.77 [1.45, 2.16]. Enough to say the signal predicts defect activity beyond churn in
  the Python repositories tested; not enough to say it of TypeScript.
  **Run 4** (kibana, pre-registered in `8f6f726`) killed the language explanation too: it passes at
  RR 4.27 [2.05, 11.71] with the cleanest specificity in the study — an all-commits ratio of **0.99**,
  meaning stratification absorbed churn essentially exactly, against 4.27 on defect fixes. The power bar
  now counts **events, not files** (nova cleared the file bar within one file and still returned
  [1.63, 16.14] on 28 events); kibana clears it with 438.
  **Standing: three of four adequately-powered repositories pass, across two languages and three
  architectures**, and the fourth is not a counter-example — angular shows the same effect at reduced
  magnitude (~1.5× in the two deciles holding 52 of its 63 flagged files). Pooled (exploratory)
  RR 1.83 [1.51, 2.21]. Magnitudes are not comparable across repositories: the ratio tracks how
  concentrated defect fixes are, so pass/fail stands but the numbers are not effect sizes for the check in
  general. Full record, newest first, with corrections marked in place:
  `docs/evaluations/defect-study/RESULTS.md`.
- [x] **Prettier** — the clone validation repaired it and it ran: RR 0.93 [0.39, 3.21]. Clears the events
  bar (134) but not the file bar (22 flagged), so recorded, not counted.
- [x] **Angular explained, and an earlier claim corrected.** Its flagged set is *not* unusual — central
  framework code (http client, ngtsc handlers, router, language-service), nothing test-adjacent or
  generated. Churn predicts defects there about as strongly as elsewhere (d9/d5 = 4.3, against 4.5 for
  home-assistant). The per-decile view is what settles it: angular's flagged files carry ~1.5× the fixes
  of churn-matched peers in deciles 8 and 9 — the same order as home-assistant's decile 8 — and only
  decile 7 inverts (0.87 on 11 files). So run 4's description of angular as showing "no specificity" and
  being "merely busier" over-read a pooled interval whose lower bound was 0.978. It is **a weaker signal
  the sample cannot resolve**, not the absence of one. The maintenance-mode hypothesis has partial support
  (highest defect-fix share, 15.5%) but does not explain the null, since home-assistant's distribution is
  flatter still and it passes.
- [ ] **Report effect sizes with the concentration caveat.** Across repositories the rate ratio tracks how
  concentrated defect fixes are — 4–5% of files carrying fixes gives RR ~4.3–4.5 (kibana, nova), 28–37%
  gives 0.93–2.05. That is partly mechanical: a ratio has more room when fixes are rare. Pass/fail is a
  within-repository comparison and stands, but the magnitudes are not comparable across repositories and
  should not be quoted as the check's effect size in general. Compute signals as of T, then ask whether the flagged files
  accumulate more **defect-fixing commits** in (T, now] than churn-matched controls — an outcome that does
  not depend on our own labelling, which is the weakness in every quality number we currently have.
  Recognise defect fixes from commit wording (no external service), cross-checked on a couple of repos
  against issues a public tracker confirms were labelled bugs; archagent itself never gains an
  issue-tracker dependency. **The controls are the experiment** — churn predicts churn, so an unmatched
  comparison proves nothing. This is the only item that can retire a signal.
- [~] **The rubric, deterministic half** (§9) — **shipped.** `tests/rubric.py` +
  `python scripts/selfeval.py score <path>`: ADL conformance (a gate), Covers globs resolving, coverage,
  falsifiable-claim count, drift-after-describe, clean command exits (a gate), and how many `evaluate`
  families were active. Needs no agent and no model.
  **Every graded criterion is paired with its counter-criterion**, as §20.3 requires, and the tests build
  the degenerate artifacts to prove it. The specificity target scales with the codebase (√ of the
  source-file count, floored at 8, capped at 120): a flat constant asked the same of a 20-file project and
  a 10,000-file monorepo, so it was either trivial for one or negligible for the other. The *shape* is now
  defensible; the constants are still chosen rather than measured, and calibrating them needs real
  artifacts of known quality to score. Within specificity, no single *kind* of claim may satisfy more than
  half the target: raw marker counting let six annotated subsystems contribute 18 of 27 claims, so the
  score was largely measuring how many one-line annotations someone had typed. Claims are also counted at
  the granularity they are checked at — a `**Config:**` line naming three keys is three claims, not one. one glob claiming the whole codebase scores 1.00 on coverage share
  and under 0.50 on concentration; documents too vague to contradict score 1.00 on drift and under 0.20 on
  specificity. In both cases the real artifact outscores the gamed one overall. Demonstrated on
  `examples/sample_py`, which is an invariants-only fixture: 0.39 overall, gate failed, perfect drift
  against 0.17 specificity.
- [ ] **The rubric, judged half** (§9). 1–5 against anchored descriptors with a cited `file:line` behind
  every score. Gated on the calibration of §11, whose machinery now exists but holds no labels: an
  uncalibrated judged score is a number of unknown meaning, and the agreement rate is what changes that.
- [ ] **End-to-end self-evaluation** (§8). `scripts/selfeval.py run` is stubbed with an explicit refusal.
  Steps 2 and 5 need a coding agent invoked non-interactively, which would make archagent an agent
  *caller* rather than an agent *callee* — a different kind of dependency from anything it ships today.
  Three questions first: which agent, how it is pinned, and how much of a score is agent variance. Until a
  repeat run on identical inputs establishes that noise floor, comparing two scorecards is reading tea
  leaves. Scoring an artifact you produced by hand already works.
- [~] **Human spot-check and calibration** (§11) — **shipped, unused.** `scripts/spotcheck.py
  generate|ingest|report` plus `tests/spotcheck.py`. The three properties that decide whether labels are
  worth collecting are implemented and tested: the tool's severity/confidence/recommendation go to a side
  file the reviewer never opens (in the same file they would anchor the verdict, and the exercise would
  measure agreement with our own prior); the worksheet is an offline markdown file with a lenient parser,
  because thirty items is a week of spare moments; and labels persist under a revision-independent key so
  a re-run only asks about what is new. Changing a recorded verdict **requires a note** and the prior one
  is kept — otherwise labels drift toward whatever the tool currently claims and the calibration they feed
  becomes circular. `unsure` is excluded from the precision denominator rather than counted as a
  dismissal. Intervals are Wilson, which stays inside [0,1] at these sample sizes.
  **No labels have been collected yet** — the round trip was exercised with throwaway answers and the
  store cleared. Real calibration needs a reviewer who did not build the checks. A small stratified sample of findings and rubric scores,
  reviewed by a person with the tool's own severity/confidence **withheld** until after the verdict, so the
  exercise measures agreement with reality rather than with our prior. The point is not volume — nobody is
  labelling 78 hotspot findings — but the agreement rate between person and model judge, which is what
  turns a rubric score into an estimate with an error bar instead of an assertion. Verdicts persist in a
  label store keyed revision-independently, so labels survive re-runs and are never spent twice; changing
  one requires a note, or labels drift toward whatever the tool currently claims. Build it *with* the
  judged half of the rubric, not after. Note the convergence: this store is the "reviewed — intended,
  dismissed" record Appendix A of the hotspots design wanted a `capabilities.md` file for, which probably
  makes that file unnecessary.
- [ ] **Judge tooling: trial DeepEval against a hand-rolled baseline** (§12). A dev/test dependency only —
  nothing evaluation-related enters the shipped package. Its `DAG` metric (deterministic branching with
  model calls at the leaves) is close to the rubric's half-gates/half-judged shape, and it is pytest-shaped;
  against that, its metric catalogue assumes a query→answer→context triple that an architecture artifact
  judged against a codebase is not, and its annotation features are the hosted product while our label
  store stays a local file. Decide by building one rubric criterion both ways at item 4 above, not by
  adopting up front. Keep the judge behind a thin interface with our scorecard schema as the stable part.
- [~] **Blind comparison of the skill layer** (§10) — **objective half shipped; generation deliberately
  not automated.** `scripts/blindcomp.py prepare|score` writes three briefs over a byte-identical findings
  payload (digest recorded on each, so a differing input cannot pass unnoticed), then blinds and shuffles
  the returned reports, scores them without seeing which arm wrote which, and unblinds afterwards.
  Generation is left to separate sessions on purpose: one model writing arm A (its own guidance), arms B
  and C, then grading all three would measure self-preference, which is the failure §10 names.
  Scoring is objective only — the ground-truth verdicts from the corpus pass (`tests/blindcomp_truth.toml`,
  three findings labelled by reading code, including the archetypal intended family a good report must
  dismiss *with a reason*), plus machine-checkable hygiene: evidence citations, clustering, and "tells"
  that would identify an arm. §20.2 requires a gate to be objective, so this is the half that carries a
  decision even once a judge exists.
  Attribution took three attempts: a plain proximity window credits one dismissal against every finding
  near it; *nearest* mention breaks on "…by design, dismissed. NextFile.py — …"; the rule that works is
  the most recent finding named **before** the dismissal, which is how prose reads. Same findings, three arms — shipped guidance, a
  generic prompt, no guidance — shuffled and scored by a judge that is not told which is which. The
  intended-family dismissals from the corpus pass give it real ground truth rather than taste.
- [ ] **Closing the loop — automatic feedback into prompts and tools** (§20). **Deferred until the basic
  evaluation is proven**; recorded so the pieces before it are built in a shape that admits it. Inspired by
  *Self-Harnesses* (arXiv 2606.09498): mine failures from traces, propose minimal edits tied to them,
  accept only if regression tests still pass. We already have their safeguard — the golden fixtures and
  pinned corpus. The difference is their acceptance metric is an objective task pass rate while ours would
  be partly model-judged, so the gate must be the objective criteria only (deterministic rubric half plus
  ground-truthed dismissals), with judged scores informing proposals and never deciding them. Preconditions:
  noise floor measured, calibration established, three-way repo split, blocking regression nets, and traces
  persisted. Prompts and config are eligible; thresholds stay on the slow defect-study loop, and check code
  is proposed rather than applied. Evaluation assets stay read-only to any proposer — an agent that can
  edit both the prompt and the test will improve the score.
- [ ] **Does archagent keep agents adherent?** (L3) The evaluation the survey called for — measure whether
  an agent working under archagent drifts less than one without it (cf. the Constraint Decay result that
  motivates the project). This is what turns the thesis into evidence. Deliberately last: it is the
  hardest to design and the least useful while L1 and L2 are unmeasured.

---

## Not planned / out of scope

Recorded so we don't relitigate:
- **Per-artifact config lint** (e.g. "service missing a healthcheck") — deployment-config linting
  (kube-score/checkov territory), not system-level architecture. Tried and removed 2026-07-12.
- **Generic structural-metric dashboards** — cycle counts, health scores, coupling trends over time.
  A continuous sensor's job (Archy), not archagent's (DD-4).
- **Heavy formalism** — CSP/TLA+/Lean connector semantics, autoformalization, a custom graph DB. The
  value from the ADL work is the *vocabulary and the one edge attribute*, not the formal machinery.
