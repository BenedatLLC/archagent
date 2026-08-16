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

**The caption is authored, never generated, and lives outside the replaced region.** `graph --write` seeds
an obviously-unfinished placeholder between `archagent:graph-caption` markers and never touches it again,
so a re-run refreshes the picture without eating the sentence someone wrote about it. The caption is not
generated on purpose: archagent can see that a node has high fan-in, but what that *means for this system*
is the judgement it defers to the agent everywhere else, and a generated caption would restate the picture
— the decorative-caption failure the `describe` prompt forbids. `check_orientation` treats an unfilled
placeholder as missing, because a slot that still holds it looks answered.

## State and tiering

Read-only, except `graph --write`, which inserts a generated block into `index.md`.

## Lifecycles / key flows

None.

## Invariants

None specific.
