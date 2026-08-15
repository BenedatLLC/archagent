# Working in this repo with archagent

This repo's architecture is described under `architecture/` and enforced by **archagent**.
Treat the architecture as the shared source of truth: read it before changing a subsystem,
and keep it current as you work.

## Before changing code
- Read `architecture/constitution.md` (always) and the relevant `architecture/subsystems/<name>.md`.
- Architectural rules live in `architecture/invariants.md` and are enforced by `archagent check`.

## Workflow
- **describe** — build or update the architecture artifact (skill: `archagent-describe`).
- **check** — verify code against the architecture; fix violations or change the invariant (skill: `archagent-check`).
- **invariant** — add or change a checkable architectural rule (skill: `archagent-invariant`).

## Commands
- `archagent check` — verify code against the invariants (exit 1 on an error-severity violation).
- `archagent gen` — regenerate checker configs from `architecture/invariants.md` (`check` does this for you).
- If archagent isn't installed: `uvx archagent check`, or `uv tool install archagent`.

## Rules
- Don't work around a failing invariant — fix the code, or change the invariant and record why in an ADR.
- Existing docs are hypotheses: verify them against the code before trusting them.
- Write architecture docs for a junior engineer **and** an agent: purpose before mechanism, define jargon,
  self-contained sections, ground every claim in a real file path, and cut what the code already says.
