# archagent

Keep your codebase adherent to a described architecture — and teach your coding agent
to reason about it.

You describe the architecture as markdown in your repo (including a table of machine-checkable
**invariants**). archagent generates configs for existing tools (import-linter, dependency-cruiser,
ast-grep) from that single source and runs them, reporting adherence per invariant. The checkers
are deterministic; the LLM only ever *proposes*.

> Status: early. v1 covers BOUNDARY invariants (Python via import-linter, JS/TS via dependency-cruiser),
> STRUCTURAL invariants (any language via ast-grep, path-scopable), and a PBT tier for behavioral/data
> invariants (Python via Hypothesis) — all driven by `architecture/invariants.md`, plus per-agent
> delivery for Claude Code, Cursor, and OpenHands.

## Install

archagent installs once (from outside your repos) and scaffolds into each project (like Spec-Kit).
It isn't on PyPI yet, so install from the repo:

```bash
uv tool install git+https://github.com/BenedatLLC/archagent   # gives you an `archagent` command
```

Then run it inside a project (see **Workflow** below). Once published, `uvx archagent init .` will work too.

## Upgrading

The prompts (agent skills + `architecture/AGENTS.md`) ship inside the archagent package, so upgrading is
**two steps**: update the tool, then refresh the repo.

1. **Update the archagent tool:**
   ```bash
   uv tool upgrade archagent                                   # installed from GitHub
   # or, from a local checkout:
   git -C /path/to/archagent pull && uv tool install --force /path/to/archagent
   ```
2. **Refresh the repo's prompts:**
   ```bash
   cd your-repo
   archagent upgrade      # refreshes the skills + architecture/AGENTS.md only; leaves your
                          # archagent.toml and architecture content untouched (--agents to pick which)
   ```
3. **Restart your coding-agent session** so it reloads the updated skills (`/skills` in Claude Code to confirm).

> `archagent upgrade` alone won't help if the installed tool is stale — the prompts come from the package,
> so do step 1 first. Don't use `archagent init --force` to upgrade: it re-scaffolds everything and would
> overwrite your `invariants.md` and other authored content.

## The architecture artifact

`init` scaffolds an `architecture/` directory in your repo — plain markdown, versioned in git, the
shared source of truth that both humans and agents read and write:

| File | Tier | What it holds |
|------|------|---------------|
| `constitution.md` | hot (always loaded) | terse conventions + the handful of patterns the system relies on, and how to work here |
| `invariants.md` | hot | the **single source of truth** for checkable rules (the table archagent parses) |
| `subsystems/<name>.md` | cold (on demand) | one doc per subsystem, the narrative architecture across the six dimensions |
| `decisions/NNNN-*.md` | cold | ADRs — the *why* behind decisions, and the rejected alternatives |
| `index.md` | hot | catalog of the docs |
| `log.md` | — | append-only, chronological change log (grep/tail friendly) |
| `AGENTS.md` | — | how to work with archagent in this repo (archagent-owned; refreshed by `upgrade`) |

Two tiers, on purpose: the **hot** files are loaded into the agent every session, so they stay terse.
The **cold** files (subsystem docs, ADRs) are retrieved only when relevant, so they can be full
narrative — written so a new engineer can learn a subsystem by reading one doc, without chasing links.

## How architecture is modeled

Each subsystem is described across **six dimensions** (in `subsystems/<name>.md`):

1. **Process topology & components** — what the pieces are, how they connect, the entry points.
2. **Key abstractions & patterns** — the few patterns the system leans on, each with a concrete example.
3. **State & tiering** — what state exists and *where* it lives: in-memory, durable files, a database,
   a cache, a vector store. The storage tiers are made explicit.
4. **Lifecycles** — how components and state move through their states over time, as a **Mermaid
   `stateDiagram`** with a plain-language caption. State machines live here.
5. **Key flows** — the important end-to-end paths, as a **Mermaid `sequenceDiagram`** with a caption.
6. **System-wide invariants** — what must always hold; the checkable ones are linked to `invariants.md`.

Diagrams are text (Mermaid), so they diff cleanly and an agent can read and edit them. The *why*
behind any non-obvious choice goes in an ADR under `decisions/`, which invariants link to.

```mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Active
    Active --> Retired
    Retired --> [*]
```
_A lifecycle is a state machine + a one-line caption: what it shows and the key takeaway._

## Invariants are a markdown table

`architecture/invariants.md` — the first table is parsed; the prose around it is for humans:

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| BND-001 | BOUNDARY | structural | python | `forbid app.domain -> app.web` | error | [0007](decisions/0007-hexagonal.md) | active |
| BND-010 | BOUNDARY | structural | ts | `forbid src/domain -> src/ui` | error | [0008](decisions/0008-layers.md) | active |
| STR-002 | STRUCTURAL | structural | python | `forbid-pattern print($$$)` | warn | [0009](decisions/0009-no-io.md) | active |

- **Type** (the dimension it protects): BOUNDARY · INTERFACE · DATAFLOW · STRUCTURAL · PURPOSE.
- **Tier** (how it's enforced, cheapest first): structural · contract · pbt · model-check.
- **Rule** (compact DSL):
  - `forbid <a> -> <b>[, <c>...]` — BOUNDARY (must not import *directly*).
  - `forbid-pattern <ast-grep pattern> [in|outside <scope>]` — STRUCTURAL (a code shape that must not
    appear). `in <scope>` flags matches only there; `outside <scope>` flags everywhere *except* there
    (the "only `<scope>` may do this" case). `<scope>` is a path/glob (`src/app/domain`) or a dotted
    module (`app.domain.workflow`); omit it to scan all sources.
  - `property <path::test>` — a **behavioral / data invariant** ("all state is per-user", round-trip
    properties) checked by a **property-based test**. `gen` scaffolds a Hypothesis `@given` stub (you
    fill in the property); `check` runs it in the *project's* env (`[python] test_command`) and reports
    the minimal counterexample on failure.
  - `property stateful <path::TestCase>` — for **stateful** systems (state machines, stores, lifecycles):
    `gen` scaffolds a Hypothesis `RuleBasedStateMachine` (random sequences of `@rule` operations checked
    against `@invariant` methods) — the right tool for state/data-layer bugs a single `@given` can't catch.
- **Severity**: `error` fails `check`; `warn` is reported but doesn't fail.
- **Why**: a link to the ADR with the rationale.

## How it works

```
architecture/invariants.md  ──gen──▶  checker configs  ──check──▶  per-invariant report
      (single source)            (existing tools = the diff)        (PASS / WARN / FAIL)
```

archagent doesn't reimplement architecture checking — it compiles your invariant table into configs for
tools that already do it, and maps their results back to invariant IDs. The capability matrix picks the
tool per `(invariant tier × language)`:

| Tier / invariant | Python | JS / TS |
|------------------|--------|---------|
| BOUNDARY / layering | import-linter | dependency-cruiser |
| STRUCTURAL (code shape) | ast-grep | ast-grep |
| PBT (behavioral / data) | Hypothesis | fast-check *(planned)* |

Adding a language is adding a column, not rewriting anything. Generated configs live under
`.archagent/generated/` and are gitignored — they're derived from the table and regenerated on every
`check`.

## Workflow

**Set up the architecture (once per repo):**

1. **`archagent init .`** — scaffold `archagent.toml`, the `architecture/` templates, and the phase
   skills. It **auto-detects which agents you use** (`.claude/`, `.cursor/`, `.openhands/`) and installs
   skills for those; override with `--agents claude,cursor` / `all` / `none`. It also detects languages
   and guesses `root_package` / `source_paths` — check those in `archagent.toml`. It **never creates or
   overwrites your top-level `CLAUDE.md` / `AGENTS.md`**; the full instructions go in
   `architecture/AGENTS.md`. Add `--wire` to append a small additive pointer to your top-level file(s).
2. **`/archagent-describe`** (in your coding agent) — document the *current* architecture: it surveys any
   existing docs, **verifies them against the code**, and writes the constitution, the per-subsystem docs
   (the six dimensions), and an initial set of invariants.
3. **`archagent check`** (or `/archagent-check`) — verify the code against those invariants.

**Keep it honest as you work:**

- **Every commit / PR** — `archagent check` (wire into pre-commit + CI) gates changes against the invariants.
- **Add an invariant** — **`/archagent-invariant`**, or edit `architecture/invariants.md` by hand, to
  encode a new rule (from a design decision, or lifted from a subsystem doc); `check` confirms it catches
  the right thing.
- **See what drifted** — `archagent drift` reflexion-diffs the `architecture/` docs against the code:
  **dangling references** (a doc names code that no longer exists), **stale docs** (a subsystem doc's
  covered code changed after the doc, via git), and **undocumented modules** (code owned by no subsystem's
  `**Covers:**`). Informational — its output (`--json` for tooling) is the update work-list.
- **Update the architecture** (a new design, or the code changed) — re-run **`/archagent-describe`**:
  it's *build-**or-update***. Start from `archagent drift`, then refresh the subsystem(s) that changed and
  reconcile the invariants. Do this at **design-review time** (does the proposed design fit the
  architecture?) and **periodically** as the code evolves; record decisions as ADRs in
  `architecture/decisions/`.
- **Upgrade the prompts** — update the tool, then `archagent upgrade` (refreshes the skills +
  `architecture/AGENTS.md` only, leaving your config and architecture content untouched). See
  [Upgrading](#upgrading).

> Cadence: `describe` at design-review + periodically; `check` on every commit. archagent enforces *your
> system's* design rules — not generic metrics (cycle counts, coupling scores).

The three skills (`describe`, `check`, `invariant`) come from one neutral source and are installed per
agent — Claude Code `.claude/skills/`, Cursor `.cursor/skills/`, OpenHands `.openhands/microagents/` — plus
`architecture/AGENTS.md` (the full instructions, archagent-owned). In Claude Code, invoke a skill directly
as `/archagent-describe` (etc.) or just describe the task and Claude activates it.

## Commands

CLI:
- `archagent init [PATH]` — scaffold `archagent.toml` + `architecture/` templates + agent skills.
  Auto-detects agents (`--agents auto`); override with `--agents claude,cursor` / `all` / `none`.
  `--wire` adds an additive pointer to top-level `CLAUDE.md`/`AGENTS.md`; `--force` re-scaffolds everything.
- `archagent check` — regenerate configs, run the checkers, report per invariant (exit 1 on an
  error-severity failure).
- `archagent drift` — reflexion-diff the `architecture/` docs against the code: dangling references,
  stale docs (git), and undocumented modules (when subsystem docs declare `**Covers:**`). Informational;
  `--json` for tooling/agents, `--exit-code` to fail CI on any drift.
- `archagent gen` — regenerate only the checker configs from `architecture/invariants.md` (`check` does
  this for you).
- `archagent upgrade` — refresh the archagent-owned prompts (skills + `architecture/AGENTS.md`) to the
  latest; leaves your config and architecture content untouched.

Agent skills (invoke in your coding agent; Claude Code slash form shown):
- `/archagent-describe` — build or update the architecture artifact.
- `/archagent-check` — run `archagent check` and resolve violations.
- `/archagent-invariant` — add or change a checkable invariant.

## Configuration

A small `archagent.toml` at the repo root tells archagent where the code is:

```toml
[project]
languages = ["python", "ts"]

[python]
root_package = "app"
source_paths = ["src"]

[ts]
source_paths = ["src"]
```

## Try it

```bash
uv run archagent check --project examples/sample_py    # Python (import-linter + ast-grep)
uv run archagent check --project examples/sample_ts    # TS (dependency-cruiser + ast-grep)
```

## What it composes

import-linter (Python boundaries) · dependency-cruiser (JS/TS boundaries) · ast-grep (structural,
any language) · grep/git for retrieval and history. archagent is the thin layer that turns one
markdown table into those tools' configs and reports results per invariant.

## Development

```bash
uv sync --group dev
uv run pytest            # unit tests (DSL + table parsing, config generation, init/upgrade logic)
                         # + an end-to-end check on examples/sample_py (real import-linter + ast-grep)
```

Tests run in CI on every push/PR (`.github/workflows/ci.yml`). The TS/PBT paths need Node / a target
test env, so they're validated via the examples rather than in the unit suite.
