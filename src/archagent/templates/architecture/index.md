# Architecture Index

_Open with two or three sentences on what this system **is** and what it does — a reader who has never
seen the repo lands here first, and a catalog answers no question they are asking yet. Then say what to
read first and in what order. Keep configuration notes at the bottom of this file._

_Say once, here, how the two kinds of rule relate: an **ADR** in `decisions/` is prose recording *why* the
structure is as it is and binds nobody; a row in `invariants.md` is a **mechanical** rule with a checker
behind it, enforced by `archagent check`. Some ADR conclusions are backed by an invariant; most are not,
because most are not expressible as a rule._

## System map
<!-- archagent:graph -->
_No system diagram yet — run `archagent graph --write` to generate a Mermaid flowchart of the subsystems
and their `**Connects:**` edges here (it replaces everything between the `archagent:graph` markers)._
<!-- /archagent:graph -->

## Subsystems
- _none yet — add `subsystems/<name>.md` (copy `subsystems/_TEMPLATE.md`) and link it here._

## Decisions (ADRs)
- [0001 — Record architecture decisions](decisions/0001-record-architecture-decisions.md)

## Coverage
- _Run `archagent status` for the package count. State it here as "N of M packages documented" — never
  "not yet documented (first pass)"; the artifact says what's true now, and `log.md` holds the history._
