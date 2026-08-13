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
2. **Check the run's coverage first — before reading a single finding as good news.** Three fields, all
   of which change what the findings mean:
   - `inactive` names every signal family that produced *nothing because the metadata it needs is absent*
     (no `**Service:**`, `**Tier:**`, or `**Connects:**`). A group with zero findings there is **not**
     "clean" — it wasn't measured. If a family you care about is inactive, the highest-value move is often
     to add that metadata (in the `describe` step) and re-run, not to write a report. Note that groups E
     and F need none of that metadata: they run on any repo with git, and F's enum signal runs without git
     at all, so their silence *is* meaningful.
   - `truncated` names any family whose list was capped at its highest-ranked few. "10 findings" there
     means "10 of N" — say so in the report rather than implying the list is the whole inventory.
   - `history.cautions` and `history.profile` say how far to trust the history. Read the caution's scope:
     "only N commits mapped to subsystems" limits the *subsystem* co-change signals only — per-file churn,
     which drives group E and F's ranking, still used the whole window. If the profile reports no usable
     bug-fix convention, or warns it is over-matching, read the fix-labeled counts as noise and lean on
     total churn.
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
- **Permissive cross-origin policy** (group D) — the service sets `Access-Control-Allow-Origin: *`,
  accepts every WebSocket `Origin`, or configures CORS with a wildcard. Reported `high` when the same
  component also registers a `POST`/`PUT`/`PATCH`/`DELETE` route, `med` otherwise.
  **This is a candidate, not a vulnerability report.** Whether it is a defect depends on a threat model
  archagent does not have. Judge it by asking what is reachable and whether the artifact *says so*:
  - **Dismiss** when the surface is genuinely public and read-only, or the policy is deliberate and
    already described in `deployment.md`. Say which.
  - **Confirm** when the documents describe the system as private, internal, or "local only" while the
    policy is open. A local developer tool is the sharp case, and the one people get wrong: binding to
    `127.0.0.1` stops other machines, not other *websites* — any page the developer visits can call a
    localhost API from their browser. If a state-changing route sits behind it, that includes calling it.
  - Either way the fix is usually documentation before code: a trust boundary belongs in `deployment.md`
    next to the ports, saying who may reach each one. An undescribed boundary is the finding even when the
    policy turns out to be intended.
  When the route evidence says "matched textually rather than parsed", open the file before you rate it —
  that path exists because the service is in a language archagent cannot parse.
- **Change-prone complex file** (group E) — a single *file* that changes constantly **and** is deeply
  nested: the classic sign of an abstraction absorbing special cases it should be delegating. Both axes are
  percentiles within this repo, so it reads "unusually churny and unusually complex *here*". Distinct from
  the God Component signal, which is about a whole subsystem's structure — a change-prone file often sits
  inside one, but need not. When judging: open the file and ask what the special cases have in common; the
  useful recommendation names the seam (a strategy per provider, a state machine, a parser split), not
  "this file is too long".
- **Scattered single source of truth** (group F) — one decision (a set of domain values like
  `{pending, paid, shipped, refunded}`) branched on in several files instead of resolved in one. Found in
  the *code* — the tool reports the likely owner (the file branching on most of the set) and the files
  holding pieces — and ranked by how much those files churn. **Expect a specific false alarm here:**
  adapters, database backends, and plugin families legitimately branch on the same values in parallel
  behind one interface. That is not a defect; dismiss it with that reason in one line. Confirm it only when
  the pieces are genuinely partial copies of one rule that can drift — then the recommendation is "these
  N files should call the owner", naming the owner.

- **Enum bypassed by its raw values** (group F) — the project *declares* a single source of truth (an
  enum) and some other file re-decides it by comparing against the member strings, e.g.
  `state.value == "summarized"` instead of `state is WorkflowState.SUMMARIZED`. Higher precision than the
  clustering signal above, because the owner is declared rather than inferred — and it catches a case the
  clustering cannot see, where the values are *assigned* in the definer and only *compared* in one other
  file, so they never reach the "duplicated across three files" bar. This is the only group-F signal that
  runs without git. The dismissal to expect: a value that genuinely arrived serialized (a JSON field, a DB
  column, a request parameter) is legitimately compared as a string.
  **Read which of the two variants you got**, because the fix is different. When the escaping files share
  the enum's language, they can just import it. When they don't — a Python enum compared as bare strings by
  the TypeScript frontend, which was 5 of 9 such findings on one real repo — no import exists to fix it: a
  second copy of the vocabulary is unavoidable, and *nothing on either side fails* when the two drift. The
  recommendation there is to generate one side from the other (or both from a shared schema); the title
  says "across a language boundary" and the detail names both languages. Cross-language cases are the more
  reliable half of the signal — nothing links the two sides, so the match can't be explained away.
  **A purely-TypeScript escape is the weakest variant and says so**: `tsc` already rejects a stale literal
  compared against a typed value (TS2367), for string enums, union types and `as const` unions alike, so
  the only real risk there is a value that arrives untyped. Check that before writing it up.

### Severity is mechanical; the rating a reader needs is not

`evaluate`'s `severity` counts files and commits. It says nothing about consequence, and the two come
apart badly: in the first independent labelling round most enum escapes were minor-to-moderate, and one
was **critical** — a scattered call-type vocabulary had left a prompt-injection hook comparing against two
strings that exist in none of the four declarations, so it silently scanned nothing for embedding and
transcription requests and reported success.

Findings the tool marks `investigate: true` (with a `triage_reason`) are the ones where a consequence is
plausible enough to be worth the cost of finding out. **Your report must make the next step explicit**,
naming the command, because a reader who cannot act on a finding will drop it:

> `CallTypes` is declared four times and the copies have drifted. Whether that is currently breaking
> anything is not established — to find out, run `archagent investigate
> enum-value-escape:litellm/types/utils.py:e67c8c15`.

Rate a finding **minor / moderate / critical** only once someone has traced the code:

- **minor** — untidy; nothing depends on the duplication, or a typo fails loudly.
- **moderate** — a real maintenance hazard; the copies can drift and nothing would catch it.
- **critical** — it already misbehaves, or a plausible edit makes it misbehave *silently*.

Do not assign one of these from the counts. A finding whose investigation cannot point at a consequence is
minor by definition, and saying so plainly is more useful than hedging.

**Both new signals are low-to-medium confidence by construction and never fail a build.** They are also
worth cross-reading: a file that appears in *both* — churny and complex, and holding a duplicated decision —
is usually the strongest root in the whole report, because two independent signals agree on it.

### The learned commit-wording profile
Recognizing a bug-fix commit is per-project, not universal (`Fixed #123` vs `fix(scope):` vs free-form), so
archagent learns each repo's wording rather than hard-coding one. The JSON's `history.profile` reports what
it learned: the `style`, the patterns, and how many sampled subjects they labelled. Check it before leaning
on a fix-count: if `cautions` says the recognizer is over-matching or that no convention was found, read the
fix counts as noise and use total churn instead. `archagent history-profile --evidence` dumps the raw
facts — commit guidelines, leading-word frequencies, per-pattern match rates — if you want to judge them
yourself and write a sharper recognizer to `.archagent/history-profile.json`; a cached profile always wins
over the inferred one.

To enable the layering checks, give each subsystem doc a `**Tier:**` line (e.g. `ui` / `domain` / `infra`);
for the data + connector signals, give the subsystems a `**Service:**` line and a `**Connects:** … via
<kind>` line (typed edges). Co-change quality depends on clean history — if a repo has few commits or huge
bulk commits, weight the history signals lightly.
