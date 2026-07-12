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
2. For each candidate, decide:
   - **Confirm** — real problem. Explain the impact in this system's terms (what change becomes risky/slow).
   - **Dismiss** — expected here (say why: e.g. an intentional shared kernel, a framework-imposed hub).
   - **Reframe** — the signal points at a deeper cause; describe that instead.
3. **Cluster** confirmed findings into a handful of architectural roots.
4. Write a prioritized report: for each root — the problem, the evidence (subsystems/services + metric), the
   **recommended fix** (the new boundary/abstraction/move), and the effort/risk. Highest value first.
5. Where a fix should be protected against regression, propose a **`check` invariant** for it (e.g. a
   forbidden dependency or a layer rule) — this is how an evaluation finding graduates into enforcement.
6. Record it: append to `architecture/log.md`, and open an ADR under `architecture/decisions/` for any root
   the team decides to act on.

## What the signals mean (regime A, static)
- **Unclear single source of truth / Shared persistency / Service intimacy** (group A) — two services declare
  the same table (the schemas will drift), share a datastore, or one reads another's owned tables directly.
  Give each service its own store and share data through an API/events. Needs `**Service:**` on subsystem
  docs (so files map to services); only fires when ≥2 services exist.
- **Shared library across services** (A) — an internal module imported by ≥2 services couples their releases.
  Vendor a copy or extract a versioned package/service.
- **God Component / Blob** (group C) — a subsystem with outsized fan-in **and** fan-out, or an outsized share
  of the code. Split along its seams; extract the most-depended-on responsibility behind a narrow interface.
- **Tangled / circular dependency** (C) — a dependency cycle among subsystems or services. Service cycles are
  worse (they block independent deployment — a distributed monolith). Break with an interface, inversion, or
  async messaging.
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
  depends on the other. A change to one keeps forcing a change to the other with no code link — the boundary
  is wrong. Merge the shared concern, or add the missing explicit interface. The highest-value smell here.
- **Unstable interface** (B) — a widely-depended-on subsystem that keeps changing with its dependents,
  spreading churn. Freeze its contract, or split the volatile part from the stable one.

To enable the layering checks, give each subsystem doc a `**Tier:**` line (e.g. `ui` / `domain` / `infra`);
for the data signals, give the services a `**Service:**` line. Co-change quality depends on clean history —
if a repo has few commits or huge bulk commits, weight the history signals lightly.
