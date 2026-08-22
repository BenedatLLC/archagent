# System Invariants

The **first markdown table below** is the single source of truth for `archagent`
(parsed by `archagent gen` / `archagent check`). The prose around it is for humans.

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status | Verification | Graduation path |
|----|------|------|-----------|------|----------|-----|--------|--------------|-----------------|

No invariants yet — add rows to the table above. Example rows:

- `| BND-001 | BOUNDARY   | structural | python | `forbid app.domain -> app.web` | error | [0002](decisions/0002-...) | active |`
- `| BND-010 | BOUNDARY   | structural | ts     | `forbid src/domain -> src/ui`  | error | [0003](decisions/0003-...) | active |`
- `| STR-002 | STRUCTURAL | structural | python | `forbid-pattern print($$$)`    | warn  | [0004](decisions/0004-...) | active |`
- `| CFG-001 | STRUCTURAL | prose      | python | `forbid-pattern os.environ outside app.config` | error | [0005](decisions/0005-...) | proposed | `rg -n "os.environ" --glob "!app/config.py"` | needs a scoped ast-grep pattern |`

The last two columns are optional and matter most for **`prose`** rows. `prose` means archagent cannot
generate a checker — not that nobody checks the rule, and without `Verification` those two look the same.
Name the test, the command or the audit that confirms it; `none` is a legitimate answer and better than a
blank. `Graduation path` says what would make it mechanical, or that nothing would.

**Record every invariant as a row** — including ones you can't enforce yet, and ones that are purely
descriptive (a rule you can only state in prose today). Give the non-enforceable ones **Tier `prose`**:
they live in the table but are never generated or run (`gen`/`check` skip them), so they stay documented,
greppable, and ready to graduate. Put the intended `forbid`/`forbid-pattern` in the Rule column if you have
one (it won't run while Tier is `prose`), otherwise a short plain-language description. Don't scatter
invariants as loose prose bullets outside the table.

**Columns**
- `Type` (after the architecture dimensions): BOUNDARY · INTERFACE · DATAFLOW · STRUCTURAL · PURPOSE
- `Tier` (how it's enforced): structural · contract · pbt · model-check · **prose** (documented only, never generated)
- `Rule` (compact DSL): `forbid <a> -> <b>` (BOUNDARY) · `forbid-pattern <pattern> [in|outside <scope>]`
  (STRUCTURAL — `in`/`outside` scope it to a path or dotted module; omit to scan all sources)
- `Severity`: error (fails `check`) · warn
- `Why`: link to the ADR carrying the rationale
- `Status`: active · proposed · deprecated
