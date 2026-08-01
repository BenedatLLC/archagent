# Architecture index

| Document | What it holds |
|---|---|
| `constitution.md` | how this repo works; the layering and the deterministic-code rule |
| `invariants.md` | the checkable rules `archagent check` enforces on this repo |
| `deployment.md` | how it runs (a CLI, no services) and what it configures |
| `subsystems/cli.md` | command surface and output |
| `subsystems/config.md` | `archagent.toml` loading |
| `subsystems/invariant-pipeline.md` | invariants table -> checker configs -> results |
| `subsystems/drift.md` | doc-vs-code reflexion diff, and the shared git plumbing |
| `subsystems/evaluate.md` | system-level smell signals, including the history checks |
| `subsystems/extraction.md` | the static scanners the other subsystems read facts from |
| `subsystems/scaffolding.md` | `init` / `upgrade` and the shipped prompts |
| `subsystems/reporting.md` | coverage, module map, Mermaid lint |
| `decisions/` | ADRs — why the structure is the way it is |
| `investigations/` | what an `evaluate` finding turned out to mean (ADL-SPEC §6a) |
