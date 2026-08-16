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

**Coverage and depth are different questions, and only the first was measured.** `status` reports the
share of files some subsystem claims. An artifact can score 100% on that while a reader finds its
documents too thin to trace a change through — which is exactly what happened on a reviewed artifact, and
is why `status` now also reports **prose words per file claimed**, diagram count, and how many type or
table declarations each document covers.

The thinness bar is *relative* — under half the median density of the artifact's own documents. An
absolute words-per-file threshold would punish a terse house style everywhere; one document far below its
siblings is a claim about this artifact rather than about prose in general.

**This subsystem is itself flagged `no diagram`, and that is the right behaviour.** It covers six type
declarations and draws nothing, so the check asks the question. The answer here is no: `status`, `graph`
and `lint-docs` are three independent commands rather than a set of relationships, and a diagram would
restate the table above it. The flag is a prompt, not a verdict — the same rule every other signal in
this tool follows, and leaving it standing is cheaper than adding a decorative diagram to silence it.

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
