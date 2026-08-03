# 0003 — `drift.py` holds the shared git and source-file plumbing

## Status
Accepted, with a known cost

## Context
Seven modules import `drift`. Most of them do not want the drift check: they want `_git`,
`_source_files`, `_import_graph`, or `_glob_files`. `drift.py` is the largest non-`evaluate` module at 605
lines and is doing two jobs — the doc-vs-code diff, and the plumbing everything else stands on.

## Decision
Keep the plumbing there for now, and record that it is a hub rather than pretending otherwise. Extracting
a `gitutil` module is the obvious refactor and is deliberately deferred: the boundary is not yet obvious
(`_source_files` is about configuration, `_git` about history, `_import_graph` about language analysis),
and splitting on the wrong seam is worse than a known hub. The cycle above raises the priority: this is
now a recorded structural defect rather than an aesthetic complaint.

## Consequences

Writing this artifact and running `evaluate` against it made the cost concrete, in a way that reading the
code had not:

- **A real dependency cycle.** `drift` (domain) imports `extraction` (infra) for the scanners
  (`configscan`, `connscan`, `deployscan`), and `extraction` imports back into `drift` — `invscan.py:24`
  takes `_source_files`. That one edge closes the loop; `connscan.py` imports only `configscan` and
  reaches `drift` in neither direction. `evaluate` reports it as `cycle-subsystem: drift ↔ extraction` at high
  confidence, and separately as `layer-inversion: extraction (infra) depends up on drift (domain)`. Two
  findings, one cause.
- `drift.py` is flagged as a change-prone complex file, alongside `evaluate.py` and `cli.py`.

**These findings are correct and are not to be suppressed.** They are the reason to do the extraction
rather than an argument against having declared the layers.

The fix is to move `_git`, `_source_files`, `_glob_files` and `_import_graph` into a leaf module that both
`drift` and `extraction` may import. That breaks the cycle and removes the inversion in one change. It is
deferred rather than rejected — see below — and BND-003 keeps the damage bounded meanwhile: `config` must
never import `drift`.

**The bounding rules were later strengthened from edges to classes.** BND-003 forbids `config` three named
targets and BND-004 forbids `hotspots` one, so neither covers a module added afterwards — the property
each is really protecting is "imports nothing internal". STR-005 and STR-006 state that directly. STR-004
also retires the claim below that "only `drift.py` may invoke `git`" is unenforceable: the pattern is the
string literal `"git"`, matching `drift.py:288` and nowhere else. Since this decision is what makes the
plumbing worth centralising, having it checked rather than reviewed matters more here than elsewhere.

## Rejected alternatives
Duplicating `_git` into each caller. Rejected — that is the exact smell `evaluate`'s
scattered-source-of-truth check exists to find, and a tool that commits it has no standing.
