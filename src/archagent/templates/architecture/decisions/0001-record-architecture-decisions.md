# 0001 — Record architecture decisions

## Status
Accepted

## Context
We want the *why* behind architectural choices to survive. Without it, future engineers
and coding agents re-litigate settled decisions or violate intent without knowing it.

## Decision
Record significant architectural decisions as ADRs in `architecture/decisions/`, one file
per decision (`NNNN-title.md`). Invariants in `architecture/invariants.md` link here via
their `Why` column. Each ADR states the context, the decision, and — importantly — the
**rejected alternatives and why**, so they aren't revisited blindly.

## Consequences
- A durable, reviewable record of intent that humans and agents can both read.
- Rejected options are captured, preventing re-litigation.
