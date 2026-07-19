# Architecture Constitution

Always-loaded rules for working in this repo. Keep this file **terse** — detail belongs
in `subsystems/` and `decisions/`, which are read on demand.

## How to work here
- Before changing a subsystem, read its doc in `architecture/subsystems/`.
- Every architectural rule lives in `architecture/invariants.md` and is enforced by `archagent check`.
- Don't work around a failing invariant — fix the code, or change the invariant and record why in an ADR.
- Record non-obvious decisions as ADRs in `architecture/decisions/`.

## Conventions
- _TODO: build/test commands, naming conventions, directory layout._

## Documentation conventions
- _TODO: where design/spec docs live (e.g. `designs/`, `rfcs/`), how they're named and organized, and
  where intended-behavior invariants are stated — so `describe`/`drift` and other agents know where to
  look for intent, and where new decisions get written down._

## Architectural patterns
- _TODO: the handful of patterns this system relies on (and the invariants that protect them)._
