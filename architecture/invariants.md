# Invariants

Rules `archagent check` enforces on this repository. Each was verified against the code before being
written down — a rule that does not currently hold is a finding, not an invariant.

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| BND-001 | BOUNDARY | structural | python | `forbid archagent.evaluate -> archagent.cli` | error | [0001](decisions/0001-cli-is-the-only-output-layer.md) | active |
| BND-002 | BOUNDARY | structural | python | `forbid archagent.drift -> archagent.cli` | error | [0001](decisions/0001-cli-is-the-only-output-layer.md) | active |
| BND-003 | BOUNDARY | structural | python | `forbid archagent.config -> archagent.drift, archagent.evaluate, archagent.cli` | error | [0003](decisions/0003-drift-holds-shared-git-plumbing.md) | active |
| BND-004 | BOUNDARY | structural | python | `forbid archagent.hotspots -> archagent.dupdecide` | error | [0003](decisions/0003-drift-holds-shared-git-plumbing.md) | active |
| STR-001 | STRUCTURAL | structural | python | `forbid-pattern print($$$) outside src/archagent/cli.py` | error | [0001](decisions/0001-cli-is-the-only-output-layer.md) | active |

## Rules deliberately not written as invariants

**"Only `drift.py` may invoke `git`."** True today and load-carrying — it is why `--until` could be added
in one place — but the DSL cannot scope a string literal to a module, so expressing it would need a
pattern that also matches the word "git" in comments. Enforced by review and by ADR 0003 instead.

**"A scan must distinguish failure from emptiness."** The most valuable rule in the repo (ADR 0002) and
not mechanically checkable: it is a claim about what a return value *means*.
