# Architecture log

## 2026-08-01 — artifact created

First description of archagent by archagent. Eight subsystems identified from the real import graph
(an `ast` walk over every module in the package), not from memory.

Two observations recorded at creation, both confirmed against the code rather than assumed:

- `drift.py` is a hub: seven modules import it, but most of them want `_git`, `_source_files` or
  `_import_graph` — shared plumbing — rather than the drift check itself. Recorded as ADR 0003.
- `evaluate.py` at 1095 lines is the largest module and imports twelve siblings. It is the composition
  root for the signal families rather than a god object, but it is the first place to watch.

## 2026-08-22 — update pass before the 1.0 release

Reconciled the artifact against everything added since it was written. `drift` named seven possibly-stale
documents and one undocumented module; both lists are now empty.

- **`described.py` was the undocumented module**, and it is the answer to a defect the artifact itself
  demonstrated. `status` reported which files a subsystem *claims*; it could not report whether the
  claiming document says anything about them. Assigned to `reporting`.
- **Four subsystems gained capabilities the documents did not mention**: `configscan` now resolves helper
  wrappers and pydantic-settings fields as well as literal `os.getenv` (98 keys to 228 on one reviewed
  repository); `lint-docs` checks invariant-ID citations as well as Mermaid syntax; `init` supports Codex
  as an opt-in agent; and `evaluate` gained the two group-D exposure signals.
- **`check` no longer reports an unrunnable checker as passing.** When ast-grep's JSON failed to parse,
  the handling branch returned a pass for every invariant it touched. It also strips colour from the
  tools it launches, because an inherited `FORCE_COLOR` made a parser stop matching — the same failure
  arriving by a different route. Recorded in `deployment.md`, since it is why archagent sets any
  environment variable at all.
- **Three line citations in `cli.md` had drifted** to point at unrelated code. Nothing checks a line
  number, and nothing here does now either; they were corrected by hand. A citation that resolves to the
  wrong lines reads exactly like one that resolves to the right ones, which is the shape of most of the
  defects in this log.

Coverage is 30 of 30 source files across 8 subsystem documents, and all 30 are named somewhere.
`reporting` stays flagged `no diagram` on purpose — the reasoning is in that document.

## 2026-08-23 — declared dependencies join the structural graph (issue #25)

`evaluate` built its subsystem graph only from parsed imports, so on a repository in a language archagent
cannot analyse every structural signal produced nothing and the run said so nowhere. obstudio is the
worked example: ten subsystems, seventeen declared connectors, zero code-derived edges, six silent
signals — and a **1.00** on the rubric's *evaluate signal families active*, which reads the tool's own
coverage report and therefore certified a gap it could not see.

Declared `**Connects:** … via import` edges now join the graph, per DD-4. Bounded three ways: only
`import` kinds, a confidence downgrade plus a note on any finding resting on an uncorroborated edge, and
a coverage entry when the whole graph is declared.

The change was measured before it shipped rather than after. On archagent, wardrowbe and fastapi-template
it adds zero edges — declared and parsed already agree, because `drift` reports any disagreement — so the
blast radius is exactly the repositories that were blind. obstudio goes from 21 findings to 29, and its
`implicit-coupling` count drops from 8 to 6 as two co-changing pairs turn out to have a declared
dependency after all.
