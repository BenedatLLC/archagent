# 0001 — The CLI is the only output layer

## Status
Accepted

## Context
Every subsystem produces results a user might want to see. If each printed its own, output formatting
would be spread across twenty modules, `--json` would have to be threaded through every call, and the
library would be unusable from anything but a terminal.

## Decision
`cli.py` is the only module that writes to stdout. Everything below it returns data structures —
`EvaluationResult`, `DriftResult`, `Scorecard` — and the CLI decides how to render them.

Verified: `print(` appears in `cli.py` and nowhere else in `src/archagent/`. Enforced by STR-001.

## Consequences
`--json` was added to `evaluate` and `drift` by changing one function each. The evaluation harness in
`tests/` calls `evaluate()` directly and never shells out.

## Rejected alternatives
A logging façade every module writes to. Rejected: it makes structured output (the `--json` mode agents
consume) a second-class path reconstructed from strings.
