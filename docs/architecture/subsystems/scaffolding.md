# scaffolding — getting archagent into a repository

**Covers:** `src/archagent/init.py`, `src/archagent/hooks.py`, `src/archagent/templates/**`

**Tier:** infra

## Purpose

`init` scaffolds the artifact and the per-agent skill prompts into a target repo; `upgrade` refreshes only
the tool-owned files; `install-hook` adds a pre-commit hook running `archagent check`.

## Topology and components

`init.py` copies `templates/` into the target, choosing the architecture directory (prompting unless
`--arch-dir` or `--yes`), and detects which coding agents are present to decide which skills to install.
`hooks.py` writes the git hook. The templates themselves ship as package data.

## Key abstractions

**Tool-owned versus user-owned files.** `upgrade` refreshes the prompts and `architecture/AGENTS.md` and
touches nothing else. This is why upgrading never overwrites an authored `invariants.md` — and why
`init --force` is documented as the wrong way to upgrade.

**The prompts are data, not code.** `templates/agent/phases/*.md` hold the judgement archagent does not
encode: how to describe a system, how to judge findings, how to write a report. They ship in the wheel and
are the only place a model's instructions live.

**One neutral prompt, four destinations.** The same skill bodies are written to `.claude/skills/`,
`.cursor/skills/`, `.agents/skills/` (Codex) or `.openhands/microagents/` depending on which agents are
selected. Adding an agent is adding an entry to `KNOWN_AGENTS` and a directory to the map, not writing
another set of prompts — the thing that would drift.

**Detection and support are separate questions, and Codex is where they come apart.** Auto-detection works
by finding a per-repo directory, and Codex keeps none: its config lives under `~/.codex/`, which says
nothing about *this* repository. So Codex is fully supported and opt-in — `--agents codex` — rather than
detected. Guessing from a user-level signal would install skills into repositories that never asked for
them, and the alternative of leaving Codex out entirely would be worse: it also reads a root `AGENTS.md`
from the repo root down, so `--wire` alone gives it a working integration with no skills installed.

## State and tiering

Writes into the target repository once, then gets out of the way.

## Lifecycles / key flows

Not applicable — a one-shot copy.

## Invariants

None. `init.py` imports nothing internal.
