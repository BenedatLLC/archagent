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
| STR-002 | STRUCTURAL | structural | python | `forbid-pattern typer outside src/archagent/cli.py` | error | [0001](decisions/0001-cli-is-the-only-output-layer.md) — BND-001/002 and STR-001 are all evaded by importing the CLI framework directly | active |
| STR-003 | STRUCTURAL | structural | python | `forbid-pattern rich outside src/archagent/cli.py` | error | [0001](decisions/0001-cli-is-the-only-output-layer.md) — as STR-002, for the rendering library | active |
| STR-004 | STRUCTURAL | structural | python | `forbid-pattern "git" outside src/archagent/drift.py` | error | [0003](decisions/0003-drift-holds-shared-git-plumbing.md) — one module owns the git plumbing, so `--until` lands in one place | active |
| STR-005 | STRUCTURAL | structural | python | `forbid-pattern from .$M import $$$ in src/archagent/config.py` | error | [0003](decisions/0003-drift-holds-shared-git-plumbing.md) — `config` is importable by everything only while it imports nothing | active |
| STR-006 | STRUCTURAL | structural | python | `forbid-pattern from .$M import $$$ in src/archagent/hotspots.py` | error | [0003](decisions/0003-drift-holds-shared-git-plumbing.md) — keeps `hotspots` a leaf rather than forbidding one edge of it | active |

**On the shape of these rules.** STR-002 through STR-006 exist because the four BOUNDARY rules each forbid
one *edge* where the intent is a *class* of edge, which is a review finding
([#6](https://github.com/BenedatLLC/archagent/issues/6)) rather than a hypothetical. BND-001, BND-002 and
STR-001 all enforce ADR 0001, and all three are evaded by `import typer` in a domain module — nothing
forbade reaching the terminal by a different route. STR-005 and STR-006 are the useful discovery: the DSL's
`in <scope>` form expresses an allow-list ("this module may import nothing internal") that a deny-list of
named targets can only approximate, and unlike BND-003 and BND-004 it covers modules added later. Those
two BOUNDARY rules are kept alongside, because naming the critical direction with an ADR link is worth
more at a failure than a generic "no internal imports" message.

A bare identifier is a deliberate pattern choice. `typer` matches `import typer`, `from typer import X`
*and* `typer.Option(...)`, which four separate import-form rules would not; ast-grep matches AST nodes, so
it does not fire on the word in a comment or a string.

## Rules deliberately not written as invariants

**Previously here: "Only `drift.py` may invoke `git`."** It was listed as inexpressible on the grounds that
a pattern would also match the word "git" in comments. That was wrong — `ast-grep` matches AST nodes, so
the pattern `"git"` matches the string literal and nothing else. It is now STR-004, and it fires on
exactly one site inside `drift.py` and none outside. The lesson is worth keeping: *"the DSL cannot express
this" was an assumption nobody tested.*

**"A scan must distinguish failure from emptiness."** The most valuable rule in the repo (ADR 0002) and
not mechanically checkable: it is a claim about what a return value *means*.
