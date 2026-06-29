# archagent: invariant — add or change an architectural invariant

Add (or modify) a row in `architecture/invariants.md` and confirm it works.

## Steps
1. Decide the **Type** (BOUNDARY, INTERFACE, DATAFLOW, STRUCTURAL, PURPOSE) and the cheapest **Tier**
   that can catch it (structural → contract → pbt → model-check).
2. Write the **Rule** in the compact DSL:
   - `forbid <a> -> <b>` (BOUNDARY)
   - `forbid-pattern <ast-grep pattern> [in|outside <scope>]` (STRUCTURAL) — `in <scope>` flags only
     there; `outside <scope>` flags everywhere except there ("only `<scope>` may do this"). `<scope>`
     is a path/glob or a dotted module.
3. Add the row: ID, Type, Tier, Applies-to (language), Rule, Severity, Why (link an ADR), Status.
4. Write or extend the ADR in `decisions/` explaining what the invariant prevents and why it matters.
5. Run `archagent check`. Confirm it PASSES on current clean code, and (sanity-check) that it would FAIL
   on a deliberate violation. Refine the rule until it catches the right thing.
