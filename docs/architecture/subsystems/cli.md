# cli — the command surface

**Covers:** `src/archagent/cli.py`, `src/archagent/__init__.py`
**Tier:** ui
**Connects:** invariant-pipeline via import, drift via import, evaluate via import, scaffolding via import, reporting via import, extraction via import, config via import

## Purpose

The only module a user or an agent talks to, and the only one that produces output. Everything below it
returns data; `cli.py` decides how it is rendered — a Rich table for a person, `--json` for an agent.

## Topology and components

One [Typer](https://typer.tiangolo.com) application with fifteen commands, each a thin adapter: parse
options, call one function, render its result. `__init__.py` exposes `main` as the `archagent` entry point
and is the only importer of this module.

The commands group by lifecycle stage: `init`/`upgrade` (scaffold), `gen`/`check` (enforce),
`drift`/`modules`/`status`/`graph`/`lint-docs` (diff and describe), `scan-invariants` (mine),
`evaluate`/`investigate`/`history-profile` (judge), `install-hook` (automate), `help` (orient).
Fifteen in seven groups, and the count is worth stating because it drifted: this document said fourteen
until `investigate` and `history-profile` were added, and nothing checks a number written in prose.

## Key abstractions

**Result objects, rendered late.** `run_evaluate()` returns an `EvaluationResult`; the CLI renders it
twice, as text and as JSON, from the same object (`cli.py:375`). Adding a field to a finding does not
touch the command.

**The JSON is a superset of the text, not a parallel format.** `--json` emits every field the rendered
report shows and some it does not — each inactive family carries the `signs` it stands for
(`cli.py:423`), so an agent can check the coverage report against the findings list rather than reading
prose. The text view collapses that to a label because a person reading a terminal does not need it.

**A clean report must mean something was checked.** `check` lists every rule `gen` skipped under *Not
checked — asserted in invariants.md, verified by nobody*, and an artifact whose rules are all `prose` tier
gets `No invariant was checked … this is not a passing run` instead of a pass. The passing line names the
count (`All 10 checked invariant(s) hold`). This came from a reviewed artifact with eight prose rules, two
of them false, where `check` printed an empty table and "All invariants hold." — ADR 0002's failure mode
arriving through the report rather than through a scan.

**Findings carry their own next step.** A finding marked `investigate` prints the exact command that acts
on it (`cli.py:441`). A reader who cannot act on a finding drops it.

## State and tiering

Stateless. Every command reads the filesystem and git, writes at most to `.archagent/` or the artifact,
and exits. Nothing is cached in process.

## Lifecycles

None — no command has states. A lifecycle diagram here would be decoration.

## Key flows

```mermaid
sequenceDiagram
    participant U as user / agent
    participant C as cli.py
    participant E as evaluate
    participant G as git
    U->>C: archagent evaluate --json
    C->>E: evaluate(config, until=...)
    E->>G: log --name-only (bounded)
    G-->>E: commits + files
    E-->>C: EvaluationResult (findings, cautions, coverage)
    C-->>U: JSON, or a rendered report
```
_The shape every command takes: the CLI holds no logic, and the same result object serves both output
modes. The git call is the only external process in this path._

## Invariants

- STR-001 — `print()` appears only here.
- STR-002, STR-003 — and so do `typer` and `rich`. These exist because BND-001, BND-002 and STR-001 all
  enforce ADR 0001 and all three are evaded by a domain module importing the CLI framework directly:
  planting `import typer` in `evaluate.py` leaves BND-001 passing.
- BND-001, BND-002 — nothing below imports this module.
