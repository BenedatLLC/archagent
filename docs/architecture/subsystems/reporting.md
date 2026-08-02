# reporting — describe-time helpers

**Covers:** `src/archagent/status.py`, `src/archagent/graph.py`, `src/archagent/docscan.py`
**Tier:** domain
**Connects:** config via import, drift via import, extraction via import

## Purpose

Three small commands that support the *describe* step rather than enforcement: how much of the code is
documented, what the system map looks like, and whether the diagrams parse.

| Module | Command | Answers |
|---|---|---|
| `status.py` | `archagent status` | per-package coverage — how much code a subsystem doc claims |
| `graph.py` | `archagent graph` | a Mermaid system map generated from `**Covers:**` and `**Connects:**` |
| `docscan.py` | `archagent lint-docs` | do the Mermaid blocks parse, without needing Node |

## Key abstractions

**Coverage is a prompt, not a score.** `status` exists to show an author where the artifact is thin. The
evaluation rubric later learned the same lesson the hard way: coverage alone is maximised by one glob
claiming everything, so it has to be read alongside how the claims are spread.

**The graph is generated, never authored.** It is derived from the metadata lines, so a diagram cannot
drift from the declarations — it *is* the declarations.

## State and tiering

Read-only, except `graph --write`, which inserts a generated block into `index.md`.

## Lifecycles / key flows

None.

## Invariants

None specific.
