# Command reference

Every command takes `--project PATH` (default `.`) to run against a repo other than the current
directory. `archagent --version` (`-V`) prints the installed version — worth recording in any bug report
or evaluation, since what a command reports depends on which build produced it.

The README has the short version of this page; here is each command in full.

**Contents** — [Setting up](#setting-up) · [Checking](#checking) · [Reflexion](#reflexion) ·
[Reading the artifact](#reading-the-artifact) · [Diagnostics](#diagnostics) · [Agent skills](#agent-skills)

---

## Setting up

### `archagent init [PATH]`

Scaffold `archagent.toml`, the `architecture/` templates, and the per-agent skills into a repo.

It **auto-detects which coding agents you use** by looking for `.claude/`, `.cursor/` and `.openhands/`,
and installs skills for those. **Codex is opt-in** (`--agents codex`) because it keeps no per-repo
directory to detect. Override detection with `--agents claude,cursor`, `all` or `none`.

It also detects languages and guesses `root_package` / `source_paths` — check those in the generated
`archagent.toml`, since a wrong `root_package` quietly scopes the boundary checks to nothing.

It asks **where the architecture docs should live** — the default is `architecture/`, but if it finds a
plausible existing home like `docs/architecture` it offers that. Set it directly with
`--arch-dir docs/architecture`, or pass `--yes` to take the default without prompting.

It **never creates or overwrites your top-level `CLAUDE.md` / `AGENTS.md`**. The full agent instructions
go in `<arch-dir>/AGENTS.md` instead. Add `--wire` to append a short additive pointer to your top-level
file(s).

| Option | Effect |
|--------|--------|
| `--agents auto\|all\|none\|<list>` | which agents get skills installed (default `auto`) |
| `--arch-dir PATH` | where the architecture docs live; skips the prompt |
| `-y` / `--yes` | non-interactive throughout |
| `--wire` | append a pointer to top-level `CLAUDE.md` / `AGENTS.md` |
| `--force` | re-scaffold everything — **clobbers your edits to user-owned files** |

> Don't use `--force` to upgrade. It overwrites `invariants.md` and everything else you authored. Use
> `archagent upgrade`.

### `archagent upgrade`

Refresh the archagent-owned prompts — the agent skills and `<arch-dir>/AGENTS.md` — to match the
installed tool. Your `archagent.toml` and all architecture content are left untouched. `--agents` scopes
which agents are refreshed.

The prompts ship inside the archagent package, so this only helps once the tool itself is current. See
[Upgrading](../README.md#upgrading) for the two-step sequence.

### `archagent install-hook`

Install a git pre-commit hook that runs `archagent check` on every commit. It writes a native
`.git/hooks/pre-commit`, is idempotent, and composes with a hook you already have. `--skip-pbt` installs
the static-only variant, leaving the property tests to your test suite.

---

## Checking

### `archagent check`

Regenerate the checker configs, run the checkers, and report adherence per invariant. Exits 1 on an
error-severity failure, so it works as a commit hook and in CI unchanged.

`--skip-pbt` runs only the fast static tiers (BOUNDARY + STRUCTURAL) and skips the property-based tests.

An invariant whose checker could not run is reported as **skipped**, never as passing. This matters more
than it sounds: a report that prints "all invariants hold" having checked none of them is worse than no
report at all.

### `archagent gen`

Regenerate only the checker configs from `architecture/invariants.md`. `check` does this for you; `gen`
exists for when you want to inspect the generated config. Output lands in `.archagent/generated/` and is
gitignored — it is derived from the table and rebuilt on every `check`.

---

## Reflexion

These two are informational. Neither gates a commit; both produce a work-list.

**Neither writes anything.** They print a report, or JSON with `--json`, and that is all. A signal is a
candidate, and a candidate written into the artifact before anyone judged it is a claim nobody made. Two
commands do record: `archagent investigate --record` stores a verdict under `<arch-dir>/investigations/`,
and `/archagent-evaluate` turns accepted findings into ADRs and invariant rows by way of `describe`.

### `archagent drift`

Diff the architecture docs against the code and report where they disagree:

| Check | What it compares |
|-------|------------------|
| dangling references | files and symbols the docs name that no longer exist |
| stale docs | git: a doc untouched while the code it covers changed |
| undocumented modules | source files no subsystem's `**Covers:**` claims |
| subsystem dependencies | declared `**Connects:** … via import` edges vs the real import graph (Python `ast`, JS/TS regex) |
| entry points | `[project.scripts]` + `package.json` `bin` vs what the docs describe |
| web-route surface | Flask / FastAPI / Django / Express / Fastify / NestJS routes vs a committed OpenAPI spec, else the docs |
| configuration | env keys actually read in code vs a `.env.example` or the `**Config:**` manifest |
| deployment topology | services in docker-compose / Procfile / k8s vs the `**Services:**` list, and code cross-service calls vs compose `depends_on` |
| connector kinds | a declared `via async-event` that the code contradicts with a blocking HTTP call |

`--json` for tooling and agents. `--exit-code` fails CI on any drift. `--until` / `--as-of <tag>` bound
the git staleness comparison to a past revision (same semantics as `evaluate`).

### `archagent evaluate`

Judge the *architecture model itself* for **system-level** smells, and emit them as candidate signals for
`/archagent-evaluate` to judge in context. Advisory — not a commit gate. Run it at design review and
periodically.

Grouped by what they draw on:

**Data and source of truth** (needs `**Service:**` maps; silent on a single-service repo, where none of
these can apply) — shared persistency, duplicated ownership, cross-service data intimacy, shared
libraries.

**Structure** — God Components; circular subsystem/service dependencies (reported with shape and
severity); unstable dependencies (Martin's `I = Ce/(Ca+Ce)`, flagged at `DoUD ≥ 0.30`); leaky
abstractions (layer inversion and layer skipping, via `**Tier:**`).

**Connectors** — distributed monolith (a synchronous service cycle, from typed `**Connects:**` edges *and*
from sync-call edges inferred from the code, so it works with no annotation at all); extraneous adjacent
connectors; hard-coded service endpoints.

**Operability and exposure** — cross-boundary observability (no request tracing at all, and gaps in an
otherwise-traced chain); a permissive cross-origin policy (`Access-Control-Allow-Origin: *`, an
unconditional WebSocket `CheckOrigin`, wildcard CORS middleware), rated high only when the same service
also registers a state-changing route — "it binds to localhost" is not a restriction, because a browser
on any site can reach `127.0.0.1`; and a server-side fetch of a caller-supplied URL (the SSRF shape:
request input reaching an outbound HTTP call), reported together with whatever guard it found, since a
scheme check constrains what the string looks like and never where the request goes. These scan every
language, not only the configured ones.

**Git history** — shotgun surgery and implicit coupling; unstable interfaces (both from subsystem
co-change); change-prone complex files (per-file churn × indentation complexity, both as within-repo
percentiles); and a scattered single source of truth, either *inferred* (one decision's value set branched
on across several files, likely owner inferred, ranked by the churn of the files involved) or *declared*
(an enum bypassed by comparisons against its raw member strings — the one signal here that needs no git,
so it still runs under `--no-history`).

Options: `--json`, `--group A|B|C|D|E|F`, `--min-severity`, `--no-history`, `--since`, `--until`,
`--as-of`, `--exit-code`.

`--until` / `--as-of <tag>` bound the history so a run can be reproduced *as of* a past revision. They do
not check anything out, and the run warns if your working tree is newer than the window.

### `archagent investigate <finding-id>`

Print an investigation brief for one `evaluate` finding: what the concept is, how many times it is
declared, whether the copies have drifted, whether any code path actually misbehaves, and whether it fails
loudly or silently.

This exists because `evaluate`'s severity counts files and commits, and a **minor / moderate / critical**
rating requires someone to read the code. `--record <file.md> --rating <level> [--by NAME]` stores the
verdict in the artifact under `<arch-dir>/investigations/`, so the next run reports the answer instead of
asking the question again.

Pass the same `--until` the run used, so the brief describes the finding as it stood when it was reported.

---

## Reading the artifact

### `archagent status`

A repo-scale and coverage snapshot, in three parts.

**Coverage** — per top-level package, how many source files a subsystem's `**Covers:**` claims.

**Depth** — how much each subsystem document actually *says* about the code it claims: prose words per
file, diagrams, and type/table declarations covered. Coverage answers "is this described by something";
depth answers "is the description usable", and the two come apart — an artifact can sit at 100% coverage
while a reader still cannot trace a change through it. It flags a document under half the median density
of its siblings (relative, so a terse house style is not punished) and one that covers five or more type
declarations while drawing nothing.

**Described** — of the modules assigned to a subsystem, how many are actually *named* somewhere in a
document. Assignment is not description: a `**Covers:** src/**/*.py` glob claims every file in a tree and
says nothing about whether any of them is mentioned.

Use it to size a `describe` pass — a fixed "document three subsystems and stop" is wrong for a large repo
— and to state coverage in the artifact's `README.md` as an "N of M" count.

### `archagent graph`

Generate a Mermaid system map — one node per subsystem, one edge per typed `**Connects:**` — from the
metadata the docs already declare. `--write` splices it into the artifact's `README.md` between the
`<!-- archagent:graph -->` markers, idempotently, so the diagram stays in sync instead of being
hand-redrawn.

### `archagent lint-docs`

Lint the architecture docs, deterministically and with no Node required:

- **Mermaid syntax** — a stray second `:` in a `stateDiagram-v2` label, an unclosed or empty block, an
  unknown diagram type.
- **Invariant IDs** — an ID cited in prose (`INV-004`, `BND-001`) that no row in `invariants.md` defines.
  A citation to an invariant that does not exist reads exactly like a citation to one that does.

`--json`, `--exit-code`.

### `archagent scan-invariants`

Scan docs and code for **stated invariants** — explicit `INVARIANT` / `@invariant` / assert / contract
markers, plus modal language like MUST / NEVER / "only X may" — and emit them as candidates for
`/archagent-describe` to classify, verify, and lift into `invariants.md`.

`--json`, `--markers-only` (skip the modal-prose pass, which is the noisier of the two).

---

## Diagnostics

### `archagent history-profile`

Learn how *this* repo words its bug-fix commits — `Fixed #123` vs `fix(scope):` vs free-form — which the
history signals in `evaluate` rely on. It prints what it inferred.

`--write` caches the result to `.archagent/history-profile.json`. **Commit that file.** Unlike the
generated configs it is small, it makes the history-based `evaluate` signals reproducible across machines
and CI, and it is the file to hand-edit (or let an agent rewrite from `--evidence`) when the inferred
recognizer misreads your convention. A cached profile always wins over inference. `evaluate` reads it if
present and otherwise infers one in memory; it never writes it.

`--evidence` dumps the raw facts — commit guidelines, leading-word frequencies, per-pattern match rates —
for an agent to judge.

### `archagent modules`

How each Python source file resolves to an import module, flagging top-level **name collisions**: two
packages that install under the same name, which quietly breaks import-linter scoping and therefore
silently weakens every BOUNDARY invariant.

### `archagent help`

A concise overview of the lifecycle and the command or skill for each step.

---

## Agent skills

Invoked inside your coding agent. The Claude Code slash form is shown; in other agents, describe the task
and the agent activates the skill.

| Skill | What it does |
|-------|--------------|
| `/archagent-describe` | build **or update** the architecture artifact |
| `/archagent-check` | run `archagent check` and resolve the violations |
| `/archagent-invariant` | add or change a checkable invariant |
| `/archagent-evaluate` | judge the architecture for system-level smells and recommend fixes |
| `/archagent-help` | overview of the lifecycle and which command or skill to use at each step |

The skills come from one neutral source and are installed per agent:

| Agent | Where skills are installed |
|-------|----------------------------|
| Claude Code | `.claude/skills/` |
| Cursor | `.cursor/skills/` |
| Codex | `.agents/skills/` |
| OpenHands | `.openhands/microagents/` |

Plus `<arch-dir>/AGENTS.md`, the full instructions, which archagent owns and `upgrade` refreshes. Codex
also reads a root `AGENTS.md` from the repo root down, so `--wire` alone gives it a working integration
even with no skills installed.
