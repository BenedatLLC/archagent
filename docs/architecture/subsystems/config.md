# config — what the target repo declares

**Covers:** `src/archagent/config.py`
**Tier:** infra

## Purpose

Reads `archagent.toml` from the target repository: which languages to analyse, where the source lives,
where the architecture artifact lives, and how to run the project's tests.

## Topology and components

Three frozen-in-practice dataclasses — `Config`, `PythonConfig`, `TSConfig` — and one loader,
`load_config(project_root)`. It imports nothing internal, which is why nine other modules can depend on it
without creating a cycle (BND-003).

## Key abstractions

**A missing file is a valid configuration.** `load_config` on a repo with no `archagent.toml` returns
defaults rather than failing (`config.py:78`), so every command works on an unconfigured repository. That
is what lets `archagent evaluate` run against a clone with no setup.

**`architecture_dir` is configurable and must be respected.** It defaults to `architecture/` but a project
may set `docs/architecture`. Anything writing into the artifact resolves it through
`Config.architecture_dir` rather than hardcoding the name — investigations were moved to follow it.

## State and tiering

One TOML file in the target repo. No state of its own.

## Lifecycles / key flows

None. Loaded once per command.

## Invariants

- BND-003 — `config` imports no other archagent module, in either direction of the layering.
