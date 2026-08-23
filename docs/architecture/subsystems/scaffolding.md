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

**`init` reports its own guesses rather than delegating the check to the README** (issue #27). It writes
`archagent.toml` from very little: languages are detected, `root_package` is guessed from the package
layout, and `source_paths` is not inferred at all — it is a fixed `src`. `describe_settings` annotates
every value with its provenance and verifies each source path by counting files of the right kind under
it, so a TypeScript project keeping its code in `web/src` is told so at the moment the config is written.

The failure it guards is silent and total. A `root_package` naming nothing scopes every BOUNDARY contract
to an empty module set; a `source_paths` pointing at the wrong directory scopes every structural rule to
no files. In both cases `check` reports that all invariants hold, having examined none of them — this
project's recurring defect wearing a configuration hat.

It names a likelier directory and never writes one. Choosing on the reader's behalf would replace a
visible bad guess with an invisible one, and `node_modules` holds more JavaScript than any project
directory, so the candidate search skips vendored and build trees.

**The likelier directory is the one that *contains* the package, not the one with the most files.** These
give different answers, and the file-count answer is wrong for every repository whose package sits at the
root. Rehearsing the 1.0.0rc1 onboarding on httpx, `init` guessed `root_package = httpx` correctly and
then suggested `tests/` — because a real test suite is larger than the package it tests. Following that
hint produces precisely the silent, total failure described two paragraphs above, offered as the remedy
for it.

`_containing_dir` uses the `root_package` already guessed a few lines earlier: `source_paths` names the
parent of the package, so the answer is `.` for httpx, dspy and requests, and `backend` for a
`backend/app/` layout. File counting remains the fallback for when no package was found at all.
`_guess_python_root` searches one level down for the nested case, but only accepts an unambiguous
answer — two candidates would make `root_package` a guess, and that is the other half of the same
silent failure.

**Tool-owned versus user-owned files.** `upgrade` refreshes the prompts and `architecture/AGENTS.md` and
touches nothing else. This is why upgrading never overwrites an authored `invariants.md` — and why
`init --force` is documented as the wrong way to upgrade.

**The prompts are data, not code.** `templates/agent/phases/*.md` hold the judgement archagent does not
encode: how to describe a system, how to judge findings, how to write a report. They ship in the wheel and
are the only place a model's instructions live.

**Nothing exercised the prompts until `tests/test_prompts.py`.** They ship as package data and no code
imports them, so a wrong instruction survived until a person read it — `describe` carried advice to model
flat peer subsystems as one tier "rather than forcing a strict ladder", which is advice to distort the
architecture to quiet a false positive that had since been fixed twice. The tests assert the few claims
worth pinning: that `describe`'s hand-off to `/archagent-evaluate` is an instruction rather than an
allusion, that signal-reading guidance lives in the `evaluate` prompt, and that no prompt tells a reader
to re-tier a subsystem to silence a finding.

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
