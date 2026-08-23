# reporting — describe-time helpers

**Covers:** `src/archagent/status.py`, `src/archagent/described.py`, `src/archagent/graph.py`, `src/archagent/docscan.py`
**Tier:** domain
**Connects:** config via import, drift via import, extraction via import

## Purpose

A few small commands that support the *describe* step rather than enforcement: how much of the code is
documented, how much of it the documents actually discuss, what the system map looks like, and whether
the docs are internally consistent.

| Module | Command | Answers |
|---|---|---|
| `status.py` | `archagent status` | per-package coverage — how much code a subsystem doc claims |
| `described.py` | `archagent status` (the Described section) | of the code claimed, how much is actually named somewhere |
| `graph.py` | `archagent graph` | a Mermaid system map generated from `**Covers:**` and `**Connects:**` |
| `docscan.py` | `archagent lint-docs` | do the Mermaid blocks parse, and does every cited invariant ID exist |

## Key abstractions

**Coverage and depth are different questions, and only the first was measured.** `status` reports the
share of files some subsystem claims. An artifact can score 100% on that while a reader finds its
documents too thin to trace a change through — which is exactly what happened on a reviewed artifact, and
is why `status` now also reports **prose words per file claimed**, diagram count, and how many type or
table declarations each document covers.

The thinness bar is *relative* — under half the median density of the artifact's own documents. An
absolute words-per-file threshold would punish a terse house style everywhere; one document far below its
siblings is a claim about this artifact rather than about prose in general.

**Assignment is not description, and `described.py` is the third question.** A `**Covers:**` glob proves a
file is *claimed*; it says nothing about whether the claiming document mentions it. A reviewed artifact
scored 727 of 727 files assigned and 1.00 on the deterministic rubric while a 17-line module wiring an
optional whole-ORM read cache — which changes staleness reasoning in the permission and search paths the
artifact documents in detail — appeared nowhere in any document. The reviewer found it by running
`grep -r cachalot architecture/` and getting nothing back. That grep is this module.

Mention is a weak proxy taken alone: a module named once in a table row is not described. Two things keep
it honest. Modules under `MIN_LINES` are excluded, so a bare `__init__` is not a finding — but the floor
is *low* (10 lines), because size turned out to be a bad proxy for significance: the 17-line cache module
above was excluded by the first version's 40-line floor, while the largest unmentioned files by line count
were UI components the artifact describes deliberately as a group. And the result is reported as a
**grouped list of units, not a score**, so a reader judges the list rather than a number judging them.

**`lint-docs` checks invariant-ID integrity as well as Mermaid.** The two look unrelated and share a job:
catching what `check` structurally cannot. `check` reads `invariants.md` and nothing else, so a subsystem
doc is free to cite an ID no row defines, and every existing check still passes while a reader chasing the
citation lands nowhere. Only the *unknown ID* half is checked. A citation that describes a rule
differently from its row was implemented and then removed — a DSL row names modules where prose names
concepts, so a faithful restatement shares no vocabulary with the row it restates, and three of four
findings were false positives.

**This subsystem is itself flagged `no diagram`, and that is the right behaviour.** It covers eight type
declarations and draws nothing, so the check asks the question. The answer here is no: `status`,
`described`, `graph` and `lint-docs` are independent commands rather than a set of relationships, and a
diagram would restate the table above it. The flag is a prompt, not a verdict — the same rule every other signal in
this tool follows, and leaving it standing is cheaper than adding a decorative diagram to silence it.

**Coverage is a prompt, not a score.** `status` exists to show an author where the artifact is thin. The
evaluation rubric later learned the same lesson the hard way: coverage alone is maximised by one glob
claiming everything, so it has to be read alongside how the claims are spread.

**`graph` reads the tier vocabulary rather than its own copy of it.** `tier_of` used to exist here as well
as in `evaluate`, which is how a shared parsing rule ends up in three places; it now comes from
`tiers.py`, a leaf both can import without closing a dependency cycle.

**The graph is generated, never authored.** It is derived from the metadata lines, so a diagram cannot
drift from the declarations — it *is* the declarations.

**The index is `README.md`, and the name is for the forges rather than for archagent** (issue #28). GitHub
renders a directory's `README.md` when a reader opens it and renders nothing otherwise, so the artifact's
entry document was the one file a browsing reader never saw. Switched outright rather than aliased —
pre-1.0 is when a rename is free, and two names for one document would need explaining forever.

`graph --write` refreshes a **provenance stamp** beside the map: the archagent version and the repository
revision that last generated the artifact, answering the question a reader has on arrival. It is generated
because a hand-written one is issue #18's defect in its quietest form — right the day it is typed and
wrong every day after, with nothing ever prompting an update. Unlike the map section, the stamp is never
*inserted*: an artifact whose author removed the markers does not get a block pushed back into prose it
did not ask for.

**The caption is authored, never generated, and lives outside the replaced region.** `graph --write` seeds
an obviously-unfinished placeholder between `archagent:graph-caption` markers and never touches it again,
so a re-run refreshes the picture without eating the sentence someone wrote about it. The caption is not
generated on purpose: archagent can see that a node has high fan-in, but what that *means for this system*
is the judgement it defers to the agent everywhere else, and a generated caption would restate the picture
— the decorative-caption failure the `describe` prompt forbids. `check_orientation` treats an unfilled
placeholder as missing, because a slot that still holds it looks answered.

## State and tiering

Read-only, except `graph --write`, which refreshes two generated blocks in the artifact's `README.md`:
the system map and the provenance stamp.

## Lifecycles / key flows

None.

## Invariants

None specific.
