# evaluate — system-level smell signals

**Covers:** `src/archagent/evaluate.py`, `src/archagent/cochange.py`, `src/archagent/hotspots.py`, `src/archagent/dupdecide.py`, `src/archagent/history.py`, `src/archagent/investigations.py`
**Tier:** domain
**Connects:** config via import, drift via import, extraction via import

## Purpose

Asks whether the architecture is *healthy*, as distinct from whether it matches the docs. Produces
**candidate signals** — a signal is a measurement that *might* indicate a problem, never a verdict — which
a person or an agent then judges. `--group` filters them.

## The six groups

The letters appear throughout this document, the CLI and the report, so they are worth having up front.
Each is a family of signals sharing an evidence source.

| Group | Evidence it reads | Signals |
|---|---|---|
| A | declared data ownership | `duplicated-source-of-truth`, `shared-persistency`, `service-intimacy`, `shared-library` |
| B | the import/connector graph and git co-change | `layer-inversion`, `layer-skip`, `unstable-dependency`, `unstable-interface`, `implicit-coupling`, `extraneous-adjacent-connector` |
| C | subsystem shape | `god-component`, `cycle-*`, `distributed-monolith` |
| D | deployment and observability scans | `hardcoded-endpoint`, `no-request-tracing`, `trace-chain-gap` |
| E | git history per file | `change-prone-file` |
| F | duplicated decisions in source | `scattered-source-of-truth`, `enum-value-escape` |

A, C and D are computed from the artifact and the code alone. E needs git history. **B and F are each
half-and-half**, which is worth stating precisely because getting it wrong produced a bug: B's layering
signals are static while `implicit-coupling` and `unstable-interface` come from co-change, and F's
`scattered-source-of-truth` needs history to rank duplications while `enum-value-escape` is a pure code
scan that runs with no git at all (`evaluate.py:305-307`).

That last one is easy to get wrong. The coverage report used to name `B/E/F — git history` as inactive
under `--no-history`, so a run could report an enum escape and, in the same output, say the family it
came from had been skipped. Corrected: the label now names B, E and *F's history-ranked half* only.

**And the claim is now machine-checkable.** Each `Inactive` entry carries the `signs` it stands for, not
just a prose label, and a test asserts no reported sign appears in an inactive entry. The previous tests
matched the substring `"git history"`, which the buggy and the fixed label both contain — they passed
either way and could not have caught it. `signs` is empty where a family is *degraded* rather than
absent: `E — bug-fix weighting` still emits `change-prone-file`, ranked on total churn.

**Churn** means one thing throughout: the number of commits touching a file in the analysed window.
*Fix-churn* is the subset of those commits the recogniser labelled as bug fixes. Both are compared as
percentiles within the repository, never as absolute counts — a hundred commits is a lot in one project
and a quiet month in another.

## Topology and components

`evaluate.py` is the composition root: it builds a subsystem model from the artifact, runs each signal
family, and assembles an `EvaluationResult`. The history-based checks live in their own modules:

| Module | Signal |
|---|---|
| `cochange.py` | subsystem co-change, plus per-file churn (total and bug-fix-labelled) |
| `history.py` | the learned per-repo bug-fix commit recogniser everything else weights by |
| `hotspots.py` | group E — churn x indentation-complexity, both as within-repo percentiles |
| `dupdecide.py` | group F — one decision branched on across files; enums bypassed by raw strings |
| `investigations.py` | recorded verdicts, so an answered finding stops asking |

## Key abstractions

**Learn the project's vocabulary, do not hardcode it.** A fixed `fix(...)` matcher finds **zero** of
Django's ~16,000 fix commits. `history.py` learns each repository's wording from its own commits and
guidelines.

**Findings are candidates with a stable identity.** Each carries an id (`sign:owner:hash`) that survives
re-runs, so a label or an investigation attaches to the finding rather than to a run.

**Severity is mechanical; a rating is not.** `severity` counts files and commits. Whether something is
minor, moderate or critical depends on what it *causes*, which only reading the code establishes — so
findings that might have consequences are marked for investigation rather than rated.

## State and tiering

Git history (read), the artifact (read), `<arch-dir>/investigations/` (read; written by `investigate`),
`.archagent/history-profile.json` (read).

## Lifecycles

```mermaid
stateDiagram-v2
    [*] --> candidate: a signal fires
    candidate --> flagged: triage says a consequence is plausible
    candidate --> [*]: minor by default, never investigated
    flagged --> investigated: someone reads the code and records a rating
    investigated --> stale: the finding's evidence moves
    stale --> investigated: re-recorded against the new evidence
```
_A finding's life. The transition worth noticing is `investigated -> stale`: a recorded verdict was about
the finding as it stood, so when the set of involved files changes the verdict is shown but the question
reopens rather than a stale answer being presented as current._

## Key flows

```mermaid
sequenceDiagram
    participant H as history.py
    participant C as cochange.py
    participant D as dupdecide.py
    participant E as evaluate.py
    E->>H: learn this repo's bug-fix wording (bounded by --until)
    H-->>E: recogniser + cautions
    E->>C: mine history with that recogniser
    C-->>E: per-file churn, fix-churn, co-change (or mining_failed)
    E->>D: scan code for duplicated decisions
    D-->>E: clusters, owners, enum escapes
    E-->>E: rank by churn, triage, attach recorded investigations
```
_Why the order matters: the recogniser is learned first because every later weighting depends on it, and
it must be learned from the same window the mining uses or the run leaks future information into a
past-bounded measurement._

## Invariants

- BND-001 — does not import the CLI.
- STR-002, STR-003 — and does not reach the terminal by importing `typer` or `rich` directly, which BND-001
  alone does not prevent.
- BND-004 — `hotspots` must not import `dupdecide`; the dependency runs the other way. Planting that
  import to test the rule produced an immediate circular-import crash at startup, which is what the rule
  is protecting against.
- STR-006 — `hotspots` imports nothing internal at all, which is the property BND-004 approximates with
  one edge.
