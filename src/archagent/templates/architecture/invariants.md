# System Invariants

The **first markdown table below** is the single source of truth for `archagent`
(parsed by `archagent gen` / `archagent check`). The prose around it is for humans.

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|

No invariants yet — add rows to the table above. Example rows:

- `| BND-001 | BOUNDARY   | structural | python | `forbid app.domain -> app.web` | error | [0002](decisions/0002-...) | active |`
- `| BND-010 | BOUNDARY   | structural | ts     | `forbid src/domain -> src/ui`  | error | [0003](decisions/0003-...) | active |`
- `| STR-002 | STRUCTURAL | structural | python | `forbid-pattern print($$$)`    | warn  | [0004](decisions/0004-...) | active |`

**Columns**
- `Type` (after the architecture dimensions): BOUNDARY · INTERFACE · DATAFLOW · STRUCTURAL · PURPOSE
- `Tier` (how it's enforced): structural · contract · pbt · model-check
- `Rule` (compact DSL): `forbid <a> -> <b>` (BOUNDARY) · `forbid-pattern <pattern> [in|outside <scope>]`
  (STRUCTURAL — `in`/`outside` scope it to a path or dotted module; omit to scan all sources)
- `Severity`: error (fails `check`) · warn
- `Why`: link to the ADR carrying the rationale
- `Status`: active · proposed · deprecated
