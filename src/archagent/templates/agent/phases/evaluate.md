# archagent: evaluate — judge the architecture for system-level problems

Assess the *health of the architecture itself* and recommend fixes. This is **system-level** work —
subsystems, services, tiers, data ownership — not a class/inheritance linter. A fix may be a new
abstraction or a rearrangement of classes, but every finding is framed at the subsystem/service level.

Run this at design-review time and periodically. It complements the others: `drift` checks the model
still matches the code; `check` enforces declared invariants; **`evaluate` asks whether the described
architecture is well-formed.**

## Principles
- **Candidates, not verdicts.** `archagent evaluate` computes deterministic *candidate signals* from the
  model + structure graph. Your job is to judge each one in this system's context — confirm, dismiss with
  a reason, or reframe — then prioritize. Do not just echo the tool's list.
- **Cluster to roots.** A few structural roots usually explain most findings. Group related candidates and
  report the underlying cause once, not every symptom.
- **Rank by value.** Order by severity × confidence × how much the fix would help. Lead with the few that matter.

## Steps
1. Run `archagent evaluate --json` and read the findings. Also read the relevant `architecture/subsystems/*.md`,
   `deployment.md`, and `constitution.md` for the intended design.
2. **Check the run's coverage first — before reading a single finding as good news.** The JSON's `inactive`
   list names every signal family that produced *nothing because the metadata it needs is absent* (no
   `**Service:**`, `**Tier:**`, or `**Connects:**`). A group with zero findings there is **not** "clean" —
   it wasn't measured. If a family you care about is inactive, the highest-value move is often to add that
   metadata (in the `describe` step) and re-run, not to write a report. Likewise read `history`: if
   `cautions` flags a thin or bulk-heavy or non-conventional history, weight the co-change findings lightly
   and say so.
3. For each candidate, decide:
   - **Confirm** — real problem. Explain the impact in this system's terms (what change becomes risky/slow).
   - **Dismiss** — expected here (say why: e.g. an intentional shared kernel, a framework-imposed hub).
   - **Reframe** — the signal points at a deeper cause; describe that instead.
4. **Cluster** confirmed findings into a handful of architectural roots.
5. **Write the report for a developer of *this* codebase who has never run `evaluate` and never will.**
   Not a colleague who knows what a "Group B unstable-interface finding at low confidence" is — translate
   every tool signal into what you'd say to a teammate over coffee. See **Report shape** below.
6. Where a fix should be protected against regression, propose a **`check` invariant** for it (e.g. a
   forbidden dependency or a layer rule) — this is how an evaluation finding graduates into enforcement.
7. Record it: append to `architecture/log.md`, and open an ADR under `architecture/decisions/` for any root
   the team decides to act on.

## Report shape
The output should read like a **findings report**, not a tool-execution transcript. For each confirmed root,
three fixed parts:
- **Problem** — plain English, as if the reader has never heard of this tool or its vocabulary.
- **Evidence** — real code (file · function · a short quote or paraphrase) and real git evidence (commit
  hashes, subjects, PR numbers). **Not** the tool's own summary metric — "these two files both branch on the
  same status," not "instability I = 0.8, DoUD ≥ 0.30."
- **Recommendation** — the concrete new boundary/abstraction/move, with rough effort/risk.

Keep it disciplined:
- **Dismissed and reframed candidates get one line each**, folded into a short "Also considered" list at the
  end — not a full subsection apiece. The report's weight should match the problems' actual importance.
- **Keep tool-execution narration out of the report.** Raw finding counts, which pass found what, detector
  mechanics, why a confidence was capped — that belongs in a working log or a bug note, not the document a
  teammate reads. If it must be recorded, link it as a separate scratch note.
- **Tool-identity terms are a footnote, not the prose.** A signal's group letter, internal sign name, and
  confidence tier can appear as a one-line parenthetical for someone auditing the process, but must not be
  load-bearing in the Problem or Evidence text.

## What the signals mean (regime A, static)
- **Unclear single source of truth / Shared persistency / Service intimacy** (group A) — two services declare
  the same table (the schemas will drift), share a datastore, or one reads another's owned tables directly.
  Give each service its own store and share data through an API/events. Needs `**Service:**` on subsystem
  docs (so files map to services); only fires when ≥2 services exist.
- **Shared library across services** (A) — an internal module imported by ≥2 services couples their releases.
  Vendor a copy or extract a versioned package/service.
- **God Component / Blob** (group C) — a subsystem with outsized fan-in **and** fan-out, or an outsized share
  of the code. Split along its seams; extract the most-depended-on responsibility behind a narrow interface.
- **Tangled / circular dependency** (C) — a dependency cycle among subsystems or services. Break with an
  interface, inversion, or async messaging.
- **Distributed monolith / event-coupled cycle** (C) — a cycle of *services*. Edges come from the declared
  `**Connects:**` kinds **and** sync-call edges inferred from the code (hard-coded HTTP calls, or
  config-driven `*_URL` endpoint env keys, whose target resolves to a service), so this fires even with no
  declarations — inferred cycles are marked "(inferred
  from code)" at low confidence, so verify them. If any edge is synchronous (`sync-call` / `shared-data` /
  `import`) the services can't deploy independently → distributed monolith (high); an all-`async-event`
  cycle is only informational. Needs `**Service:**` on the subsystem docs (plus `**Connects:**` for the
  declared edges).
- **Extraneous adjacent connector** (B) — the same subsystem pair wired by two different connector kinds
  (e.g. a `sync-call` *and* an `async-event`). The parallel paths cancel each other's guarantees — pick one.
- **Unstable Dependency** (B) — a subsystem depends on more-volatile ones (instability `I = Ce/(Ca+Ce)`).
  Depend toward stability; put a stable interface in front of the volatile target.
- **Leaky abstraction — layer inversion / skip** (B) — a lower tier depends up on a higher one, or a tier
  reaches past its neighbor to a distant one. Needs `**Tier:**` on the subsystem docs. Route through the
  adjacent layer, or invert with an interface.
- **Hard-coded endpoint** (D) — a literal address in code; a barrier to local development and relocation.
  Move to config / service discovery.
- **No request tracing across services / trace-chain gap** (D) — services make cross-service calls but
  can't be followed as one request: either nothing anywhere traces/correlates, or one service makes outbound
  calls with no trace context while others have it. Adopt distributed tracing or a propagated correlation ID.
  Needs `**Service:**` on the subsystem docs; only fires with ≥2 services that actually call each other.

## History signals (regime B, from git co-change)
Mined from `git log`; require a git repo (skip with `--no-history`, window with `--since`).
- **Shotgun surgery / implicit cross-module coupling** (group B) — two subsystems co-change often but neither
  *directly* imports the other. A change to one keeps forcing a change to the other with no direct code link —
  often the boundary is wrong. Merge the shared concern, or add the missing explicit interface. The
  highest-value smell here — **but verify the link is truly absent before concluding "no dependency."** The
  signal only sees *direct* import edges; two subsystems can be genuinely coupled through **one hop of
  indirection** — both depend on a third module (a shared factory, a common helper, a base class) that the
  co-change check doesn't credit as a link between them. Read the code: if the coupling runs through a shared
  intermediary, the interface already exists (it's that third module) — the finding is then "this shared
  module is a change-magnet," not "these two need a new interface."
- **Unstable interface** (B) — a widely-depended-on subsystem that keeps changing with its dependents,
  spreading churn. Freeze its contract, or split the volatile part from the stable one.

To enable the layering checks, give each subsystem doc a `**Tier:**` line (e.g. `ui` / `domain` / `infra`);
for the data + connector signals, give the subsystems a `**Service:**` line and a `**Connects:** … via
<kind>` line (typed edges). Co-change quality depends on clean history — if a repo has few commits or huge
bulk commits, weight the history signals lightly.
